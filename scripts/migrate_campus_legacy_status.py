#!/usr/bin/env python3
"""Migrate the legacy Campus Coach ``status`` field out of DynamoDB.

Context
-------
The ``status`` attribute on ``strava-ai-boost-campus-coaching-sessions`` is a
legacy field the provider sync never rewrote, so it accumulated mixed, stale
values across several eras ('todo', 'done', 'skip', 'Fait'). It was the root
cause of the coach recommending already-done sessions. ``effective_status()``
has been changed to stop consulting it, but some rows still hold their ONLY
completion signal in ``status='Fait'`` (or 'skip'), with no ``local_status``,
``matched_activity_id`` or ``completed_at``. If the new code goes live before
those rows are migrated, they revert to 'todo' and the original bug returns.

This script preserves that completion information into ``local_status`` (the
top-precedence field ``effective_status`` reads) and then removes ``status`` so
the trap is eliminated rather than merely worked around.

Policy (per row, ``athlete-context`` rows skipped)
--------------------------------------------------
* ``status`` normalizes to done/skip AND no ``local_status`` yet
    -> SET ``local_status`` = normalized value, then REMOVE ``status``  (backfill)
* ``status`` normalizes to done/skip AND a ``local_status`` already exists
    -> REMOVE ``status`` only (``local_status`` already decides; info redundant)
* ``status`` normalizes to todo / unknown
    -> REMOVE ``status`` only (carries no completion signal; removing is safe)
* row has no ``status`` attribute
    -> nothing to do (this is what makes re-runs idempotent)

Safety
------
* Idempotent: once ``status`` is removed a re-run skips the row; an existing
  ``local_status`` is never overwritten.
* Safe under BOTH the old and new ``effective_status``: backfilling
  ``local_status=done`` yields 'done' either way, and removing a legacy value
  never changes the resolved status. It can therefore be run before OR after the
  code deploy, but MUST be run before the new code serves traffic (see the
  module docstring rationale).
* ``--dry-run`` is the DEFAULT. Pass ``--apply`` to write.
* Uses ambient credentials (no ``--profile``); region defaults to us-east-1.

Usage
-----
    python3 scripts/migrate_campus_legacy_status.py            # dry-run
    python3 scripts/migrate_campus_legacy_status.py --apply    # write changes
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import boto3

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "lambda_functions")
)

from shared.campus_status import (  # noqa: E402
    STATUS_DONE,
    STATUS_SKIP,
    normalize_status,
)

DEFAULT_TABLE = "strava-ai-boost-campus-coaching-sessions"
DEFAULT_REGION = "us-east-1"
ATHLETE_CONTEXT_PK = "athlete-context"

# Action categories reported to the operator.
ACTION_BACKFILL = "backfill_local_status_and_drop"
ACTION_DROP_REDUNDANT = "drop_status_local_already_set"
ACTION_DROP_NO_SIGNAL = "drop_status_no_completion_signal"
ACTION_SKIP = "skip_no_status"


def _classify(row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Return the action for a row and the ``local_status`` to backfill (if any).

    The second element is the canonical value to write to ``local_status``, or
    ``None`` when no backfill is required.
    """
    if "status" not in row:
        return ACTION_SKIP, None

    normalized = normalize_status(row.get("status"))
    local_present = normalize_status(row.get("local_status")) is not None

    if normalized in (STATUS_DONE, STATUS_SKIP):
        if not local_present:
            return ACTION_BACKFILL, normalized
        return ACTION_DROP_REDUNDANT, None
    return ACTION_DROP_NO_SIGNAL, None


def _scan_sessions(table: Any) -> List[Dict[str, Any]]:
    """Scan every session row, projecting only the fields the migration needs."""
    items: List[Dict[str, Any]] = []
    scan_kwargs: Dict[str, Any] = {
        "ProjectionExpression": "session_date, session_id, #st, local_status",
        "ExpressionAttributeNames": {"#st": "status"},
    }
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            if item.get("session_date") != ATHLETE_CONTEXT_PK:
                items.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return items


def _apply_row(table: Any, row: Dict[str, Any], backfill: Optional[str]) -> None:
    """Write the migration for a single row (backfill local_status, drop status)."""
    key = {"session_date": row["session_date"], "session_id": row["session_id"]}
    names = {"#st": "status"}
    if backfill is not None:
        table.update_item(
            Key=key,
            UpdateExpression="SET #ls = :ls REMOVE #st",
            ExpressionAttributeNames={"#st": "status", "#ls": "local_status"},
            ExpressionAttributeValues={":ls": backfill},
        )
    else:
        table.update_item(
            Key=key,
            UpdateExpression="REMOVE #st",
            ExpressionAttributeNames=names,
        )


def migrate(table_name: str, region: str, apply: bool) -> Dict[str, int]:
    """Run the migration (or dry-run) and return per-action counts."""
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    rows = _scan_sessions(table)
    counts: Dict[str, int] = {
        ACTION_BACKFILL: 0,
        ACTION_DROP_REDUNDANT: 0,
        ACTION_DROP_NO_SIGNAL: 0,
        ACTION_SKIP: 0,
    }

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] table={table_name} region={region} rows_scanned={len(rows)}")

    for row in rows:
        action, backfill = _classify(row)
        counts[action] += 1
        if action == ACTION_SKIP:
            continue

        key_repr = f"{row.get('session_date')}#{row.get('session_id')}"
        raw = row.get("status")
        detail = f"local_status={backfill}" if backfill is not None else "drop only"
        print(f"  [{action}] {key_repr} status={raw!r} -> {detail}")

        if apply:
            _apply_row(table, row, backfill)

    print("--- summary ---")
    for action, count in counts.items():
        print(f"  {action}: {count}")
    changed = (
        counts[ACTION_BACKFILL]
        + counts[ACTION_DROP_REDUNDANT]
        + counts[ACTION_DROP_NO_SIGNAL]
    )
    verb = "written" if apply else "would change"
    print(f"  rows {verb}: {changed}")
    if not apply and changed:
        print("  (dry-run: no writes performed; re-run with --apply to migrate)")
    return counts


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate the legacy Campus Coach 'status' field out of DynamoDB."
    )
    parser.add_argument(
        "--table",
        default=os.environ.get("COACHING_SESSIONS_TABLE", DEFAULT_TABLE),
        help=f"DynamoDB table name (default: {DEFAULT_TABLE}).",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", DEFAULT_REGION),
        help=f"AWS region (default: {DEFAULT_REGION}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes. Omit for a read-only dry-run (the default).",
    )
    args = parser.parse_args()

    migrate(table_name=args.table, region=args.region, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
