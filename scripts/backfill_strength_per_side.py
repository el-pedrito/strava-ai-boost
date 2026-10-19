#!/usr/bin/env python3
"""Write the ``per_side`` flag on stored ``strength_history`` rows.

Why this exists
---------------
The extractor now writes ``per_side`` on every row it produces: true when THIS
exercise's load was written per side ("40/c") and doubled, false otherwise. The
insights page reads that flag and no longer guesses from the text. Rows stored
before the flag have none, and an unflagged row whose session text holds any
per-side wording counts in no record and draws no chart point (see
``shared.strength_insights.row_notation``).

This script re-reads the history once so old rows get the flag where it can be
decided for sure:

* ``campus_plan`` rows: ``false``. Plan loads are stored as written, never doubled.
* Rows from a text with no per-side wording at all: ``false``. Nothing to double.
* Other rows: the session text is re-extracted with the current extractor
  (``_extract_strength_sets``). A stored row takes the re-read flag only when
  exactly one re-read row has the same canonical exercise AND the same valid
  loads. Anything else stays unflagged, so it stays out of every load record.

Rows that already carry a boolean flag are never touched. Only ``per_side`` is
written: loads, reps and volumes are left as stored.

Note: the one-off re-read of 2026-10-17 (43 per side, 244 not, 23 unflagged) was
not kept as a script. This one applies the rule above; its counts can differ
slightly because the extractor is a model.

Behaviour
---------
* ``--dry-run`` is the DEFAULT. Pass ``--apply`` to write.
* ``--apply`` first writes a JSON backup of the whole ``strength_history`` to
  ``--backup`` (default ``/tmp/strength_history_backup_per_side.json``), then
  writes the entries list back under a condition on ``last_updated`` so a
  concurrent pipeline write makes it fail instead of being lost.

Usage
-----
    python3 scripts/backfill_strength_per_side.py --user-id 138362426
    python3 scripts/backfill_strength_per_side.py --user-id 138362426 --apply
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from collections import Counter
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "lambda_functions"))

from shared.strength_exercises import canonicalize_exercise_name  # noqa: E402
from shared.strength_insights import (  # noqa: E402
    CAMPUS_PLAN,
    _has_per_side_token,
    _positive_loads,
)

DEFAULT_USER_CONFIG_TABLE = "strava-ai-boost-user-configuration"
DEFAULT_BACKUP = "/tmp/strength_history_backup_per_side.json"


def _plain(obj: Any) -> Any:
    """Decimal -> float/int, recursively, for JSON backups and comparisons."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


def _to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj


def _signature(row: Dict[str, Any]) -> Tuple[str, Tuple[float, ...]]:
    """Canonical exercise + sorted valid loads: what must match to copy a flag."""
    detail = row.get("sets_detail") if isinstance(row.get("sets_detail"), list) else []
    name = canonicalize_exercise_name(str(row.get("exercise") or ""))
    return name, tuple(sorted(_positive_loads(detail)))


def decide_flags(
    entries: List[Dict[str, Any]],
    reread: Callable[[str], List[Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], Counter]:
    """Return a copy of ``entries`` with ``per_side`` added where it is certain.

    ``reread`` is the extractor (injected so the rule can be tested without a
    model). Pure apart from calling it.
    """
    out = copy.deepcopy(entries)
    stats: Counter = Counter()
    for entry in out:
        rows = [r for r in (entry.get("parsed_sets") or []) if isinstance(r, dict)]
        todo = [r for r in rows if not isinstance(r.get("per_side"), bool)]
        stats["already_flagged"] += len(rows) - len(todo)
        if not todo:
            continue
        if entry.get("sets_source") == CAMPUS_PLAN or not _has_per_side_token(entry):
            for row in todo:
                row["per_side"] = False
            stats["set_false_no_wording"] += len(todo)
            continue
        description = entry.get("description") or ""
        reread_rows = [r for r in (reread(description) or []) if isinstance(r, dict)]
        by_sig: Dict[Tuple[str, Tuple[float, ...]], List[Optional[bool]]] = {}
        for r in reread_rows:
            flag = r.get("per_side") if isinstance(r.get("per_side"), bool) else None
            by_sig.setdefault(_signature(r), []).append(flag)
        for row in todo:
            sig = _signature(row)
            matches = by_sig.get(sig, [])
            if not sig[1] or len(matches) != 1 or matches[0] is None:
                stats["left_unflagged"] += 1
                continue
            row["per_side"] = matches[0]
            stats["set_true_reread" if matches[0] else "set_false_reread"] += 1
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user-id", required=True, help="Strava athlete id")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument("--backup", default=DEFAULT_BACKUP)
    parser.add_argument("--apply", action="store_true",
                        help="Write the flags. Without it the script only reports.")
    args = parser.parse_args()

    import boto3
    from processing.content_generator import _extract_strength_sets

    def reread(description: str) -> List[Dict[str, Any]]:
        time.sleep(0.4)  # pace the model calls; back-to-back runs get throttled
        return _extract_strength_sets(description)

    table = boto3.resource("dynamodb", region_name=args.region).Table(
        os.environ.get("USER_CONFIG_TABLE", DEFAULT_USER_CONFIG_TABLE))
    item = table.get_item(Key={"user_id": args.user_id}).get("Item") or {}
    history = (item.get("user_preferences") or {}).get("strength_history") or {}
    entries = _plain(list(history.get("entries") or []))
    print(f"Per-side re-read for {args.user_id}: {len(entries)} entries")

    updated, stats = decide_flags(entries, reread)
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    if not args.apply:
        print("  (dry-run: nothing written; re-run with --apply)")
        return 0

    with open(args.backup, "w", encoding="utf-8") as fh:
        json.dump(_plain(history), fh, ensure_ascii=False)
    print(f"  backup written: {args.backup}")
    table.update_item(
        Key={"user_id": args.user_id},
        UpdateExpression="SET user_preferences.strength_history.entries = :e",
        ConditionExpression="user_preferences.strength_history.last_updated = :lu",
        ExpressionAttributeValues={
            ":e": _to_decimal(updated),
            ":lu": history.get("last_updated", ""),
        },
    )
    print("  flags written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
