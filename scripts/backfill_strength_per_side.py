#!/usr/bin/env python3
"""Write the ``per_side`` flag on stored ``strength_history`` rows (and, on request,
recompute the volumes a per-side unilateral row got wrong).

Why this exists
---------------
The extractor now writes ``per_side`` on every row it produces: true when THIS
exercise's load was written per side ("40/c") and doubled, false otherwise. The
insights page reads that flag and never guesses from the text. Rows stored before
the flag have none, and an unflagged row whose session text cannot rule out a
per-side load counts in no record and draws no chart point (see
``shared.strength_insights.row_notation``).

Rule (a flag is written only where it is certain)
-------------------------------------------------
* Rows that already carry a boolean flag are never touched.
* The stored text "rules out" a per-side load when it has no per-side wording AND
  is shorter than the storage cut (``STORED_DESCRIPTION_MAX_CHARS``): a cut text
  may have lost a "/c" past the cut.
* Text that rules it out: every unflagged row gets ``false``.
* Campus plan rows otherwise stay unflagged: their loads are kept as written
  ("35kg/cote" stays 35), so the text cannot tell a per-side figure from a total.
* Other rows: the stored text is re-extracted with the current extractor. A row
  takes the re-read flag only when exactly one re-read row has the same canonical
  exercise AND the same valid loads, and that row carries a boolean flag.

``--recompute-volume`` also recomputes the stored volume figures of entries that
hold a unilateral lift flagged per side: before the fix in
``shared/strength_volume.py`` their volume counted the other side twice. Only the
derived figures are rewritten (``total_sets``, ``total_reps``, ``volume_kg``,
``volume_kg_incomplete``, ``excluded_exercises``, ``per_exercise``).

Safety
------
* Two steps. A run without ``--apply`` writes a PLAN file and nothing else. The
  extractor is a model, so ``--apply --plan FILE`` writes exactly the reviewed
  plan, never a fresh re-read.
* ``--apply`` refuses a plan whose ``last_updated`` differs from the stored one
  (the pipeline wrote since the plan was made).
* Before any write it saves a LOSSLESS backup of the whole ``strength_history``
  (DynamoDB typed JSON, numbers kept as exact strings) to a new timestamped file,
  opened with ``x`` so an existing backup is never overwritten.
* Writes are per field (``entries[i].parsed_sets[j].per_side``), never the whole
  list, so no stored number is converted or rewritten. Each update is conditional
  on ``last_updated`` and on the ``activity_id`` at every index it touches.

The one-off re-read of 2026-10-17 (43 per side, 244 not, 23 unflagged) was not kept
as a script. This one applies the rule above; its counts can differ.

Usage
-----
    python3 scripts/backfill_strength_per_side.py --user-id 138362426 [--recompute-volume]
    python3 scripts/backfill_strength_per_side.py --user-id 138362426 --apply --plan PLAN.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "lambda_functions"))

from shared.strength_exercises import (  # noqa: E402
    canonicalize_exercise_name,
    stored_text_may_hide_per_side,
)
from shared.strength_insights import CAMPUS_PLAN, _positive_loads  # noqa: E402
from shared.strength_volume import _sides_for, compute_session_volume  # noqa: E402

DEFAULT_USER_CONFIG_TABLE = "strava-ai-boost-user-configuration"
DEFAULT_OUT_DIR = os.path.expanduser("~/strength-backfill")
VOLUME_FIELDS = (
    "total_sets", "total_reps", "volume_kg", "volume_kg_incomplete",
    "excluded_exercises", "per_exercise",
)
MAX_OPS_PER_UPDATE = 20


def _signature(row: Dict[str, Any]) -> Tuple[str, Tuple[float, ...]]:
    """Canonical exercise + sorted valid loads: what must match to copy a flag."""
    detail = row.get("sets_detail") if isinstance(row.get("sets_detail"), list) else []
    name = canonicalize_exercise_name(str(row.get("exercise") or ""))
    return name, tuple(sorted(_positive_loads(detail)))


def _jsonable(value: Any) -> Any:
    """Derived volume figures -> JSON (floats are fine: they are recomputed)."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def decide(
    entries: List[Dict[str, Any]],
    reread: Callable[[str], List[Dict[str, Any]]],
    recompute_volume: bool = False,
) -> Tuple[List[Dict[str, Any]], Counter]:
    """Return the list of write operations and the counts. Never mutates ``entries``.

    ``reread`` is the extractor, injected so the rule is testable without a model.
    """
    ops: List[Dict[str, Any]] = []
    stats: Counter = Counter()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        rows = entry.get("parsed_sets") if isinstance(entry.get("parsed_sets"), list) else []
        planned: Dict[int, bool] = {}
        todo = [j for j, r in enumerate(rows)
                if isinstance(r, dict) and not isinstance(r.get("per_side"), bool)]
        stats["already_flagged"] += sum(
            1 for r in rows if isinstance(r, dict) and isinstance(r.get("per_side"), bool))
        if todo:
            description = entry.get("description")
            if not stored_text_may_hide_per_side(description):
                for j in todo:
                    planned[j] = False
                stats["set_false_no_wording"] += len(todo)
            elif entry.get("sets_source") == CAMPUS_PLAN:
                stats["left_unflagged_campus"] += len(todo)
            else:
                by_sig: Dict[Tuple[str, Tuple[float, ...]], List[Optional[bool]]] = {}
                for r in reread(description or "") or []:
                    if isinstance(r, dict):
                        flag = r.get("per_side") if isinstance(r.get("per_side"), bool) else None
                        by_sig.setdefault(_signature(r), []).append(flag)
                for j in todo:
                    sig = _signature(rows[j])
                    matches = by_sig.get(sig, [])
                    if not sig[1]:
                        stats["left_unflagged_no_load"] += 1
                    elif len(matches) != 1:
                        stats["left_unflagged_no_unique_match"] += 1
                    elif matches[0] is None:
                        stats["left_unflagged_reread_has_no_flag"] += 1
                    else:
                        planned[j] = matches[0]
                        stats["set_true_reread" if matches[0] else "set_false_reread"] += 1
        for j, value in sorted(planned.items()):
            ops.append({"kind": "per_side", "entry": i, "row": j,
                        "activity_id": entry.get("activity_id"),
                        "exercise": rows[j].get("exercise"), "value": value})

        if recompute_volume:
            flagged = copy.deepcopy(rows)
            for j, value in planned.items():
                flagged[j]["per_side"] = value
            hit = any(
                isinstance(r, dict) and r.get("per_side") is True
                and _sides_for(r, canonicalize_exercise_name(str(r.get("exercise") or ""))) > 1
                for r in flagged
            )
            if hit:
                bw = entry.get("body_weight_kg_used")
                bw = float(bw) if isinstance(bw, (int, float, Decimal)) else None
                fresh = compute_session_volume(_jsonable(flagged), bw)
                fields = {k: _jsonable(fresh[k]) for k in VOLUME_FIELDS}
                stored = {k: _jsonable(entry.get(k)) for k in VOLUME_FIELDS}
                if fields != stored:
                    ops.append({"kind": "volume", "entry": i,
                                "activity_id": entry.get("activity_id"),
                                "old_volume_kg": stored["volume_kg"],
                                "fields": fields})
                    stats["volume_recomputed"] += 1
    return ops, stats


def _updates(ops: List[Dict[str, Any]], last_updated: Any) -> List[Dict[str, Any]]:
    """Chunk the ops into conditional per-field ``update_item`` kwargs."""
    out = []
    for start in range(0, len(ops), MAX_OPS_PER_UPDATE):
        chunk = ops[start:start + MAX_OPS_PER_UPDATE]
        names = {"#up": "user_preferences", "#sh": "strength_history", "#e": "entries",
                 "#ps": "parsed_sets", "#f": "per_side", "#aid": "activity_id",
                 "#lu": "last_updated"}
        values: Dict[str, Any] = {":lu": last_updated}
        sets, conds, seen = [], ["#up.#sh.#lu = :lu"], set()
        for n, op in enumerate(chunk):
            base = f"#up.#sh.#e[{int(op['entry'])}]"
            if op["entry"] not in seen:
                seen.add(op["entry"])
                values[f":a{op['entry']}"] = op["activity_id"]
                conds.append(f"{base}.#aid = :a{op['entry']}")
            if op["kind"] == "per_side":
                sets.append(f"{base}.#ps[{int(op['row'])}].#f = :v{n}")
                values[f":v{n}"] = bool(op["value"])
            else:
                for k, field in enumerate(VOLUME_FIELDS):
                    names[f"#v{k}"] = field
                    sets.append(f"{base}.#v{k} = :v{n}_{k}")
                    values[f":v{n}_{k}"] = _to_dynamo(op["fields"][field])
        out.append({
            "UpdateExpression": "SET " + ", ".join(sets),
            "ConditionExpression": " AND ".join(conds),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        })
    return out


def _typed_backup(history: Dict[str, Any]) -> Dict[str, Any]:
    """Lossless DynamoDB typed JSON: numbers stay exact strings ({"N": "37.5"})."""
    from boto3.dynamodb.types import TypeSerializer
    return TypeSerializer().serialize(history)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: Optional[List[str]] = None, table: Any = None, reread: Any = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", required=True, help="Strava athlete id")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                        help="Where plans and backups go (not /tmp: it does not survive a reboot)")
    parser.add_argument("--recompute-volume", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write the reviewed --plan")
    parser.add_argument("--plan", help="Plan file from a previous run (required with --apply)")
    args = parser.parse_args(argv)

    if table is None:
        import boto3
        table = boto3.resource("dynamodb", region_name=args.region).Table(
            os.environ.get("USER_CONFIG_TABLE", DEFAULT_USER_CONFIG_TABLE))
    item = table.get_item(Key={"user_id": args.user_id}).get("Item") or {}
    history = (item.get("user_preferences") or {}).get("strength_history") or {}
    entries = list(history.get("entries") or [])
    os.makedirs(args.out_dir, exist_ok=True)

    if not args.apply:
        if reread is None:
            from processing.content_generator import _extract_strength_sets

            def reread(description: str) -> List[Dict[str, Any]]:
                time.sleep(0.4)  # pace the model calls
                return _extract_strength_sets(description)
        ops, stats = decide(entries, reread, args.recompute_volume)
        for key in sorted(stats):
            print(f"  {key}: {stats[key]}")
        plan_path = os.path.join(args.out_dir, f"plan_{args.user_id}_{_stamp()}.json")
        with open(plan_path, "x", encoding="utf-8") as fh:
            json.dump({"user_id": args.user_id, "last_updated": history.get("last_updated"),
                       "entries": len(entries), "ops": ops}, fh, ensure_ascii=False, indent=1)
        print(f"  plan: {plan_path} ({len(ops)} ops). Nothing written.")
        print(f"  review it, then: --apply --plan {plan_path}")
        return 0

    if not args.plan:
        parser.error("--apply needs --plan (the reviewed output of a run without --apply)")
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    if plan.get("user_id") != args.user_id:
        print("  REFUSED: plan is for another user")
        return 2
    if plan.get("last_updated") != history.get("last_updated"):
        print("  REFUSED: history changed since the plan was made; re-run without --apply")
        return 2
    for op in plan["ops"]:
        i = op["entry"]
        if i >= len(entries) or entries[i].get("activity_id") != op["activity_id"]:
            print(f"  REFUSED: entry {i} is no longer activity {op['activity_id']}")
            return 2
    backup_path = os.path.join(args.out_dir, f"backup_{args.user_id}_{_stamp()}.json")
    with open(backup_path, "x", encoding="utf-8") as fh:
        json.dump(_typed_backup(history), fh, ensure_ascii=False)
    print(f"  backup written: {backup_path}")
    for kwargs in _updates(plan["ops"], history.get("last_updated")):
        table.update_item(Key={"user_id": args.user_id}, **kwargs)
    print(f"  {len(plan['ops'])} ops written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
