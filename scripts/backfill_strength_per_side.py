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
  exercise AND the same valid loads, and that row carries a boolean flag. On a text
  cut at storage, only ``true`` is taken: a "/c" lost past the cut could make a
  ``false`` wrong.

``--recompute-volume`` also recomputes the stored volume figures of entries that
hold a unilateral lift flagged per side: before the fix in
``shared/strength_volume.py`` their volume counted the other side twice. Only the
derived figures are rewritten (``total_sets``, ``total_reps``, ``volume_kg``,
``volume_kg_incomplete``, ``incomplete_reason``, ``excluded_exercises``,
``per_exercise``).

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
  list, so no stored number is converted or rewritten. The plan is ONE atomic
  update when it fits DynamoDB's 4 KB expression limit, otherwise a few
  whole-entry updates (the live plan of 2026-10-19 needs 2). A failure says
  which updates landed; every op is idempotent, so a fresh plan resumes.
  Each update is conditional on ``last_updated``, on the ``activity_id`` of every
  entry, on the ``exercise`` of every row it writes and on that row being still
  unflagged; ``--apply`` also checks them before the backup.

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
    stored_text_was_cut,
)
from shared.strength_insights import CAMPUS_PLAN, _positive_loads  # noqa: E402
from shared.strength_volume import _sides_for, compute_session_volume  # noqa: E402

DEFAULT_USER_CONFIG_TABLE = "strava-ai-boost-user-configuration"
DEFAULT_OUT_DIR = os.path.expanduser("~/strength-backfill")
VOLUME_FIELDS = (
    "total_sets", "total_reps", "volume_kg", "volume_kg_incomplete",
    "incomplete_reason", "excluded_exercises", "per_exercise",
)
# DynamoDB caps each expression string at 4 KB. Stay under it with a margin; the
# whole plan goes in ONE atomic update whenever it fits.
MAX_EXPRESSION_CHARS = 3800


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
                # A text cut at storage may have lost a "/c" past the cut: the
                # re-read can then prove "per side" but never "not per side".
                cut = stored_text_was_cut(description)
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
                    elif cut and matches[0] is False:
                        stats["left_unflagged_cut_text"] += 1
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


def _entry_groups(ops: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Ops grouped by entry, in plan order: an entry's ops always travel together."""
    groups: Dict[int, List[Dict[str, Any]]] = {}
    for op in ops:
        groups.setdefault(int(op["entry"]), []).append(op)
    return list(groups.values())


def _build_update(ops: List[Dict[str, Any]], last_updated: Any) -> Dict[str, Any]:
    """One conditional, per-field ``update_item`` for ``ops``.

    The condition pins ``last_updated``, the ``activity_id`` of every entry, the
    ``exercise`` of every row it writes and that the row is still unflagged, so a
    shifted list or a flag set meanwhile fails instead of being overwritten. Attribute names are declared only when used:
    DynamoDB rejects an unused one.
    """
    names = {"#up": "user_preferences", "#sh": "strength_history", "#e": "entries",
             "#lu": "last_updated"}
    values: Dict[str, Any] = {":lu": last_updated}
    sets: List[str] = []
    conds = ["#up.#sh.#lu = :lu"]
    seen = set()
    for n, op in enumerate(ops):
        i = int(op["entry"])
        base = f"#up.#sh.#e[{i}]"
        if i not in seen:
            seen.add(i)
            names["#aid"] = "activity_id"
            values[f":a{i}"] = op["activity_id"]
            conds.append(f"{base}.#aid = :a{i}")
        if op["kind"] == "per_side":
            names.update({"#ps": "parsed_sets", "#f": "per_side", "#ex": "exercise"})
            row = f"{base}.#ps[{int(op['row'])}]"
            sets.append(f"{row}.#f = :v{n}")
            values[f":v{n}"] = bool(op["value"])
            # Still the same lift, and still unflagged at the moment of the write.
            conds.append(f"{row}.#ex = :x{n}")
            conds.append(f"attribute_not_exists({row}.#f)")
            values[f":x{n}"] = op["exercise"]
        else:
            for k, field in enumerate(VOLUME_FIELDS):
                names[f"#v{k}"] = field
                sets.append(f"{base}.#v{k} = :v{n}_{k}")
                values[f":v{n}_{k}"] = _to_dynamo(op["fields"][field])
    return {
        "UpdateExpression": "SET " + ", ".join(sets),
        "ConditionExpression": " AND ".join(conds),
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
    }


def _fits(update: Dict[str, Any]) -> bool:
    return (len(update["UpdateExpression"]) <= MAX_EXPRESSION_CHARS
            and len(update["ConditionExpression"]) <= MAX_EXPRESSION_CHARS)


def _updates(ops: List[Dict[str, Any]], last_updated: Any) -> List[Dict[str, Any]]:
    """The plan as conditional updates: ONE atomic update when it fits the
    expression limits, otherwise whole-entry chunks (never split an entry)."""
    if not ops:
        return []
    # Greedy over whole entries: when everything fits, this is ONE update.
    out: List[Dict[str, Any]] = []
    chunk: List[Dict[str, Any]] = []
    for group in _entry_groups(ops):
        if chunk and not _fits(_build_update(chunk + group, last_updated)):
            out.append(_build_update(chunk, last_updated))
            chunk = []
        chunk += group
        if not _fits(_build_update(chunk, last_updated)):
            raise ValueError(f"entry {group[0]['entry']} alone exceeds the expression limit")
    out.append(_build_update(chunk, last_updated))
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
                       "recompute_volume": bool(args.recompute_volume),
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
        if op["kind"] == "per_side":
            rows = entries[i].get("parsed_sets") or []
            j = op["row"]
            row = rows[j] if j < len(rows) and isinstance(rows[j], dict) else None
            if row is None or row.get("exercise") != op["exercise"] \
                    or isinstance(row.get("per_side"), bool):
                print(f"  REFUSED: entry {i} row {j} is no longer an unflagged {op['exercise']}")
                return 2
        elif set(op.get("fields") or ()) != set(VOLUME_FIELDS):
            print(f"  REFUSED: volume op for entry {i} does not carry the current fields; re-plan")
            return 2
    backup_path = os.path.join(args.out_dir, f"backup_{args.user_id}_{_stamp()}.json")
    with open(backup_path, "x", encoding="utf-8") as fh:
        json.dump(_typed_backup(history), fh, ensure_ascii=False)
    print(f"  backup written: {backup_path}")
    updates = _updates(plan["ops"], history.get("last_updated"))
    for k, kwargs in enumerate(updates):
        try:
            table.update_item(Key={"user_id": args.user_id}, **kwargs)
        except Exception as exc:  # noqa: BLE001 - report progress, then stop
            print(f"  FAILED on update {k + 1}/{len(updates)} ({exc}).")
            if k == 0:
                print("  No earlier update was applied.")
            else:
                print(f"  Updates 1..{k} were applied (whole entries only).")
            print(f"  On a timeout, update {k + 1} itself may have landed.")
            again = " --recompute-volume" if plan.get("recompute_volume") else ""
            print(f"  Backup: {backup_path}. Make a fresh plan with the SAME options:")
            print(f"    python3 scripts/backfill_strength_per_side.py --user-id {args.user_id}{again}")
            print("  rows already flagged are skipped, so it resumes where it stopped.")
            return 3
    print(f"  {len(plan['ops'])} ops written in {len(updates)} update(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
