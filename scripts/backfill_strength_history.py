#!/usr/bin/env python3
"""Rebuild ``strength_history`` from past WeightTraining activities.

Why this exists
---------------
``_track_strength_history`` wrote with
``SET user_preferences.strength_history.entries = list_append(...)``. DynamoDB
rejects ``SET a.b.c`` when ``a.b`` does not exist and never creates intermediate
levels, so every write raised ValidationException for any athlete without an
existing ``strength_history`` map -- that is, all of them. The exception was
swallowed as a warning, so the history was permanently empty and silently so.

The write path is fixed (the parent map is now initialised first). This script
recovers the history that was lost in the meantime, so the coach's strength
progression tracking and the dashboard strength chart have their source back.

Behaviour
---------
* Reads WeightTraining activities from the activities table via the
  ``UserActivitiesIndex`` GSI.
* Re-runs the same extraction the pipeline uses (``_extract_strength_sets``),
  so backfilled entries are byte-compatible with newly written ones.
* Idempotent: activities already present in ``strength_history`` are skipped.
* ``--dry-run`` is the DEFAULT. Pass ``--apply`` to write.

Usage
-----
    python3 scripts/backfill_strength_history.py --user-id 138362426
    python3 scripts/backfill_strength_history.py --user-id 138362426 --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
import time
from decimal import Decimal
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "lambda_functions"))

DEFAULT_ACTIVITIES_TABLE = "strava-ai-boost-activities"
DEFAULT_USER_CONFIG_TABLE = "strava-ai-boost-user-configuration"
STRENGTH_TYPES = {"weighttraining", "workout", "crossfit"}
MIN_DESCRIPTION_LEN = 10


def _to_decimal(obj: Any) -> Any:
    """Recursively convert floats to Decimal (boto3 rejects float attributes)."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj



# A description that mentions no set/rep/load pattern has genuinely nothing to
# extract ("Seance upper, les sensations reviennent"). Distinguishing that from a
# failed call matters: treating it as a failure aborts a legitimate replay, while
# treating a failure as empty writes "this session had no exercises" -- which is
# what stored 52 empty rows.
_SET_PATTERN = re.compile(
    r"\d+\s*[x*]\s*\d+"      # 4x8, 3 x 10
    r"|\d+\s*-\s*\d+\s*-\s*\d+"  # 10-10-10
    r"|\d+\s*kg"               # 80kg
    r"|\d+\s*/\s*c",           # 55/c
    re.IGNORECASE,
)


def _looks_quantified(description: str) -> bool:
    """True when the text actually carries sets, reps or loads."""
    return bool(_SET_PATTERN.search(description or ""))


def _existing_entries(config_table: Any, user_id: str) -> List[Dict[str, Any]]:
    resp = config_table.get_item(Key={"user_id": user_id})
    prefs = (resp.get("Item") or {}).get("user_preferences") or {}
    history = prefs.get("strength_history") or {}
    return list(history.get("entries") or [])


def _strength_activities(activities_table: Any, user_id: str) -> List[Dict[str, Any]]:
    """All WeightTraining-like activities for the athlete, oldest first."""
    items: List[Dict[str, Any]] = []
    kwargs: Dict[str, Any] = {
        "IndexName": "UserActivitiesIndex",
        "KeyConditionExpression": Key("user_id").eq(user_id),
    }
    while True:
        resp = activities_table.query(**kwargs)
        items.extend(resp.get("Items") or [])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    strength: List[Dict[str, Any]] = []
    for item in items:
        raw = item.get("activity_data_json")
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        atype = str(data.get("type") or item.get("activity_type") or "").lower()
        if atype not in STRENGTH_TYPES:
            continue
        description = (
            item.get("original_description")
            or data.get("description")
            or ""
        )
        if not description or len(description) < MIN_DESCRIPTION_LEN:
            continue
        strength.append(
            {
                "activity_id": item.get("activity_id"),
                "description": description,
                "start_date": data.get("start_date_local")
                or data.get("start_date")
                or item.get("created_at", ""),
                "moving_time": data.get("moving_time") or 0,
            }
        )
    strength.sort(key=lambda a: a["start_date"])
    return strength


def backfill(user_id: str, region: str, apply: bool, replace: bool = False) -> Dict[str, int]:
    from processing.content_generator import _extract_strength_sets  # noqa: E402
    from shared.strength_volume import compute_session_volume  # noqa: E402

    dynamodb = boto3.resource("dynamodb", region_name=region)
    activities_table = dynamodb.Table(
        os.environ.get("ACTIVITIES_TABLE", DEFAULT_ACTIVITIES_TABLE)
    )
    config_table = dynamodb.Table(
        os.environ.get("USER_CONFIG_TABLE", DEFAULT_USER_CONFIG_TABLE)
    )

    resp = config_table.get_item(Key={"user_id": user_id})
    prefs = (resp.get("Item") or {}).get("user_preferences") or {}
    raw_bw = prefs.get("body_weight_kg")
    body_weight_kg = float(raw_bw) if raw_bw is not None else None
    print(f"  body weight: {body_weight_kg if body_weight_kg else 'ABSENT (bodyweight tonnage will be incomplete)'}")

    existing = _existing_entries(config_table, user_id)
    known = set() if replace else {e.get("activity_id") for e in existing}
    print(f"  existing entries: {len(existing)}")

    candidates = _strength_activities(activities_table, user_id)
    print(f"  strength activities with a usable description: {len(candidates)}")

    new_entries: List[Dict[str, Any]] = []
    failures: List[str] = []
    skipped = 0
    for act in candidates:
        if act["activity_id"] in known:
            skipped += 1
            continue
        try:
            duration_min = int(float(act["moving_time"] or 0) / 60)
        except (TypeError, ValueError):
            duration_min = 0
        # Retry on empty output.
        #
        # `_extract_strength_sets` is best-effort by design: it swallows Bedrock
        # errors and returns [] so the pipeline never breaks. That is right for a
        # single activity but wrong for a bulk replay -- a throttled call would be
        # written as "this session had no exercises". A first --replace run stored
        # 52 empty entries out of 64 for exactly this reason. An empty result on a
        # non-empty description is treated as a failure, not as data.
        parsed: List[Dict[str, Any]] = []
        for attempt in range(4):
            parsed = _extract_strength_sets(act["description"])
            if parsed:
                break
            if not _looks_quantified(act["description"]):
                break
            if attempt < 3:
                wait = 2 ** attempt
                print(f"    ! empty extraction for {act['activity_id']}, retrying in {wait}s")
                time.sleep(wait)
        if not parsed:
            if _looks_quantified(act["description"]):
                failures.append(act["activity_id"])
                print(f"    FAILED {act['activity_id']}: description has sets but extraction returned nothing")
                continue
            # Nothing to extract, and that is the correct answer. Keep the entry so
            # the description stays available to the coach as narrative context.
            print(f"    - {act['activity_id']}: no quantified sets in the description")
        time.sleep(0.4)  # pace the calls; 64 back-to-back invocations get throttled
        # Same figures the pipeline now stores at write time, from the single
        # definition in shared/strength_volume.py. Without them every backfilled
        # row would fall back to a partial, explicit-weight-only tonnage.
        volume = compute_session_volume(parsed, body_weight_kg)
        entry = {
            "date": (act["start_date"] or "")[:10],
            "activity_id": act["activity_id"],
            "duration_min": duration_min,
            "description": act["description"][:1000],
            "parsed_sets": parsed,
            "total_sets": volume["total_sets"],
            "total_reps": volume["total_reps"],
            "volume_kg": volume["volume_kg"],
            "body_weight_kg_used": volume["body_weight_kg_used"],
            "volume_kg_incomplete": volume["volume_kg_incomplete"],
            "excluded_exercises": volume["excluded_exercises"],
            "per_exercise": volume["per_exercise"],
        }
        new_entries.append(entry)
        total_reps = sum(
            (s.get("sets") or 0) * (s.get("reps") or 0) for s in parsed
        )
        print(
            f"    + {entry['date']} {entry['activity_id']}: "
            f"{len(parsed)} exercises, {total_reps} reps"
        )

    print("\n--- summary ---")
    print(f"  already tracked (skipped): {skipped}")
    print(f"  to add: {len(new_entries)}")
    if failures:
        print(f"  EXTRACTION FAILED on {len(failures)}: {', '.join(failures[:10])}")
        if replace:
            print("  ABORTING: --replace would overwrite good rows with missing ones.")
            return {"added": 0, "skipped": skipped, "candidates": 0, "failures": len(failures)}

    if not apply:
        print("  (dry-run: no writes performed; re-run with --apply to backfill)")
        return {"added": 0, "skipped": skipped, "candidates": len(new_entries)}

    if new_entries:
        # Same two-step shape as the fixed write path: the parent map cannot be
        # created by a nested SET.
        config_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=(
                "SET user_preferences.strength_history = "
                "if_not_exists(user_preferences.strength_history, :init)"
            ),
            ExpressionAttributeValues={":init": {"entries": [], "last_updated": ""}},
        )
        if replace:
            config_table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET user_preferences.strength_history.entries = :entries",
                ExpressionAttributeValues={":entries": _to_decimal(new_entries)},
            )
        else:
            config_table.update_item(
                Key={"user_id": user_id},
                UpdateExpression=(
                    "SET user_preferences.strength_history.entries = "
                    "list_append(if_not_exists(user_preferences.strength_history.entries, "
                    ":empty), :entries)"
                ),
                ExpressionAttributeValues={
                    ":entries": _to_decimal(new_entries),
                    ":empty": [],
                },
            )
        print(f"  rows written: {len(new_entries)}")
    else:
        print("  nothing to write")

    return {
        "added": len(new_entries),
        "skipped": skipped,
        "candidates": len(new_entries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Strava athlete id")
    parser.add_argument(
        "--region", default=os.environ.get("AWS_REGION", "us-east-1")
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the entries. Without it the script only reports.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Re-extract every session, replacing existing entries (needed after an extraction schema change).",
    )
    args = parser.parse_args()

    print(f"Backfilling strength history for {args.user_id} ({args.region})")
    backfill(args.user_id, args.region, args.apply, args.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
