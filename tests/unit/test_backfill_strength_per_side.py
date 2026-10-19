"""Unit tests for scripts/backfill_strength_per_side.py: a flag is written only
where it is certain, the run is two-step (plan, then apply the reviewed plan),
the backup is lossless and never overwritten, and writes touch single fields."""

import importlib
import json
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "lambda_functions"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

backfill = importlib.import_module("backfill_strength_per_side")


def _row(ex, kg, n=3, **extra):
    return {"exercise": ex, "sets_detail": [{"reps": 10, "weight_kg": kg}] * n, **extra}


def _never(_description):
    raise AssertionError("no re-read expected")


def _ops(ops):
    return {(o["entry"], o["row"]): o["value"] for o in ops if o["kind"] == "per_side"}


# --- the rule -------------------------------------------------------------

def test_text_without_wording_gives_false_without_a_reread():
    entries = [
        {"sets_source": "campus_plan", "description": "Fentes 35kg", "parsed_sets": [_row("Fentes", 35)]},
        {"sets_source": "athlete_text", "description": "dc 3x10 80",
         "parsed_sets": [_row("Développé couché", 80)]},
    ]
    ops, stats = backfill.decide(entries, _never)
    assert _ops(ops) == {(0, 0): False, (1, 0): False}
    assert stats["set_false_no_wording"] == 2
    assert "per_side" not in entries[0]["parsed_sets"][0]  # input untouched


def test_campus_row_with_per_side_wording_stays_unflagged():
    """'35kg/cote' is kept at 35: a per-side figure, not a total, so no 'false'."""
    entries = [{"sets_source": "campus_plan", "description": "Fentes 35kg/cote",
                "parsed_sets": [_row("Fentes", 35)]}]
    ops, stats = backfill.decide(entries, _never)
    assert ops == []
    assert stats["left_unflagged_campus"] == 1


def test_text_cut_at_storage_never_yields_false():
    """A 1000-character stored text may have lost a '/c' past the cut: it is
    re-read, but the re-read can only prove 'per side', never 'not per side'."""
    from shared.strength_exercises import STORED_DESCRIPTION_MAX_CHARS
    # Exactly what the pipeline stores: the text cut at the limit.
    desc = ("dc 3x10 80 " + "x" * 2000)[:STORED_DESCRIPTION_MAX_CHARS]
    assert len(desc) == 1000
    entries = [{"sets_source": "athlete_text", "description": desc,
                "parsed_sets": [_row("Développé couché", 80), _row("Développé incliné", 60)]}]
    calls = []

    def reread(text):
        calls.append(text)
        return [_row("Développé couché", 80, per_side=False),
                _row("Développé incliné", 60, per_side=True)]

    ops, stats = backfill.decide(entries, reread)
    assert calls == [desc]
    assert stats["set_false_no_wording"] == 0
    assert stats["left_unflagged_cut_text"] == 1
    assert _ops(ops) == {(0, 1): True}


def test_reread_flag_is_copied_only_on_a_unique_exact_match():
    entries = [{
        "sets_source": "athlete_text",
        "description": "dc 80x10 + press inc 3x10 40/c\ncurl 3x10 30\nface pull",
        "parsed_sets": [
            _row("Développé couché", 80, n=1),
            _row("Développé incliné haltères", 80),
            _row("Curl biceps", 30),                      # re-read gives another load
            {"exercise": "Face pull", "sets_detail": [{"reps": 10, "weight_kg": None}]},
            _row("Triceps à la corde", 40),               # re-read row has no flag
        ],
    }]

    def reread(_text):
        return [
            _row("Développé couché", 80, n=1, per_side=False),
            _row("Développé incliné haltères", 80, per_side=True),
            _row("Curl biceps", 32, per_side=False),
            _row("Triceps à la corde", 40),
        ]

    ops, stats = backfill.decide(entries, reread)
    assert _ops(ops) == {(0, 0): False, (0, 1): True}
    assert stats["left_unflagged_no_unique_match"] == 1
    assert stats["left_unflagged_no_load"] == 1
    assert stats["left_unflagged_reread_has_no_flag"] == 1


def test_two_identical_reread_rows_are_not_a_unique_match():
    entries = [{"sets_source": "athlete_text", "description": "dc 3x10 40/c",
                "parsed_sets": [_row("Développé couché", 80)]}]
    ops, stats = backfill.decide(entries, lambda _t: [
        _row("Développé couché", 80, per_side=True), _row("Développé couché", 80, per_side=False)])
    assert ops == [] and stats["left_unflagged_no_unique_match"] == 1


def test_already_flagged_rows_are_never_reread_or_changed():
    entries = [{"sets_source": "athlete_text", "description": "dc 3x10 40/c",
                "parsed_sets": [_row("Développé couché", 80, per_side=True)]}]
    ops, stats = backfill.decide(entries, _never)
    assert ops == [] and stats["already_flagged"] == 1


def test_recompute_volume_fixes_a_per_side_unilateral_row():
    """Stored before the fix: 8 x 10 x 80 = 6400. Correct: 8 x 10 x 40 = 3200."""
    entries = [{
        "sets_source": "athlete_text", "description": "low row uni 4x10 40/c",
        "body_weight_kg_used": Decimal("92"),
        "parsed_sets": [_row("Tirage horizontal unilatéral machine", 80, n=4, per_side=True)],
        "total_sets": 8, "total_reps": 80, "volume_kg": Decimal("6400"),
        "volume_kg_incomplete": False, "excluded_exercises": [],
        "per_exercise": [{"exercise": "Tirage horizontal unilatéral machine", "sets": 8,
                          "reps": 80, "volume_kg": Decimal("6400"), "unilateral": True,
                          "volume_incomplete": False}],
    }]
    ops, stats = backfill.decide(entries, _never, recompute_volume=True)
    (op,) = ops
    assert op["kind"] == "volume" and op["old_volume_kg"] == 6400.0
    assert op["fields"]["volume_kg"] == 3200
    assert op["fields"]["total_sets"] == 8
    assert stats["volume_recomputed"] == 1
    assert backfill.decide(entries, _never)[0] == []  # off unless asked


# --- main(): two steps, lossless backup, per-field conditional writes -------

def _table(entries, last_updated="2026-10-19T06:43:36Z"):
    table = MagicMock()
    table.get_item.return_value = {"Item": {"user_preferences": {"strength_history": {
        "entries": entries, "last_updated": last_updated}}}}
    return table


def _entries():
    return [
        {"activity_id": "a1", "sets_source": "athlete_text", "description": "dc 3x10 37.5",
         "parsed_sets": [{"exercise": "Développé couché",
                          "sets_detail": [{"reps": 10, "weight_kg": Decimal("37.5")}]}],
         "volume_kg": Decimal("1123.456789")},
    ]


def test_dry_run_writes_a_plan_and_nothing_else(tmp_path):
    table = _table(_entries())
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path)],
                         table=table, reread=_never) == 0
    table.update_item.assert_not_called()
    (plan,) = list(tmp_path.glob("plan_u_*.json"))
    data = json.loads(plan.read_text())
    assert data["last_updated"] == "2026-10-19T06:43:36Z"
    assert data["ops"] == [{"kind": "per_side", "entry": 0, "row": 0, "activity_id": "a1",
                            "exercise": "Développé couché", "value": False}]


def _plan(tmp_path, table):
    backfill.main(["--user-id", "u", "--out-dir", str(tmp_path)], table=table, reread=_never)
    return str(next(tmp_path.glob("plan_u_*.json")))


def test_apply_backs_up_losslessly_first_then_writes_single_fields(tmp_path):
    table = _table(_entries())
    plan = _plan(tmp_path, table)
    order = []
    table.update_item.side_effect = lambda **kw: order.append(
        ("update", bool(list(tmp_path.glob("backup_u_*.json")))))
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table) == 0
    assert order == [("update", True)]  # the backup existed before the first write
    (backup,) = list(tmp_path.glob("backup_u_*.json"))
    raw = backup.read_text()
    assert '"N": "1123.456789"' in raw and '"N": "37.5"' in raw  # exact, typed
    kwargs = table.update_item.call_args.kwargs
    assert kwargs["UpdateExpression"] == "SET #up.#sh.#e[0].#ps[0].#f = :v0"
    assert kwargs["ConditionExpression"] == (
        "#up.#sh.#lu = :lu AND #up.#sh.#e[0].#aid = :a0 AND #up.#sh.#e[0].#ps[0].#ex = :x0"
        " AND attribute_not_exists(#up.#sh.#e[0].#ps[0].#f)")
    assert kwargs["ExpressionAttributeValues"] == {
        ":lu": "2026-10-19T06:43:36Z", ":a0": "a1", ":v0": False, ":x0": "Développé couché"}
    _assert_all_placeholders_used(kwargs)


def test_apply_refuses_a_stale_plan(tmp_path):
    plan = _plan(tmp_path, _table(_entries()))
    newer = _table(_entries(), last_updated="2026-10-20T08:00:00Z")
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=newer) == 2
    newer.update_item.assert_not_called()


def test_apply_refuses_a_shifted_entry(tmp_path):
    plan = _plan(tmp_path, _table(_entries()))
    shifted = _entries()
    shifted[0]["activity_id"] = "other"
    table = _table(shifted)
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table) == 2
    table.update_item.assert_not_called()


def test_apply_needs_a_plan(tmp_path):
    with pytest.raises(SystemExit):
        backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply"],
                      table=_table(_entries()))


def test_an_existing_backup_is_never_overwritten(tmp_path, monkeypatch):
    table = _table(_entries())
    plan = _plan(tmp_path, table)
    monkeypatch.setattr(backfill, "_stamp", lambda: "FIXED")
    (tmp_path / "backup_u_FIXED.json").write_text("original")
    with pytest.raises(FileExistsError):
        backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                       "--plan", plan], table=table)
    assert (tmp_path / "backup_u_FIXED.json").read_text() == "original"
    table.update_item.assert_not_called()


# --- update building: atomic when it fits, whole entries otherwise ----------

def _assert_all_placeholders_used(kwargs):
    """DynamoDB rejects a declared name or value that no expression uses."""
    text = kwargs["UpdateExpression"] + " " + kwargs["ConditionExpression"]
    import re
    used = set(re.findall(r"[#:][A-Za-z0-9_]+", text))
    declared = set(kwargs["ExpressionAttributeNames"]) | set(kwargs["ExpressionAttributeValues"])
    assert declared == used  # nothing unused, nothing undeclared


def _no_float(value):
    if isinstance(value, float):
        return False
    if isinstance(value, dict):
        return all(_no_float(v) for v in value.values())
    if isinstance(value, list):
        return all(_no_float(v) for v in value)
    return True


def _volume_op(i, aid):
    return {"kind": "volume", "entry": i, "activity_id": aid, "old_volume_kg": 6400.0,
            "fields": {"total_sets": 8, "total_reps": 80, "volume_kg": 3200.5,
                       "volume_kg_incomplete": False, "incomplete_reason": None,
                       "excluded_exercises": [],
                       "per_exercise": [{"exercise": "Tirage horizontal unilatéral machine",
                                         "volume_kg": 3200.5, "unilateral": True}]}}


def _flag_ops(n):
    return [{"kind": "per_side", "entry": k // 3, "row": k % 3, "activity_id": f"a{k // 3}",
             "exercise": f"Ex{k}", "value": bool(k % 2)} for k in range(n)]


def test_a_volume_only_plan_declares_only_names_it_uses():
    (update,) = backfill._updates([_volume_op(4, "a4")], "lu")
    assert "#ps" not in update["ExpressionAttributeNames"]
    _assert_all_placeholders_used(update)
    assert _no_float(update["ExpressionAttributeValues"])


def test_a_small_plan_is_one_atomic_update():
    ops = _flag_ops(9) + [_volume_op(1, "a1")]
    (update,) = backfill._updates(ops, "lu")
    assert update["UpdateExpression"].count(".#f = ") == 9
    assert update["ConditionExpression"].count("attribute_not_exists(") == 9
    _assert_all_placeholders_used(update)


def test_a_live_size_plan_stays_under_the_limits_in_few_whole_entry_updates():
    """63 flags + 3 volumes (the live plan) does not fit one 4 KB condition once
    every row is pinned twice; it goes in a few whole-entry updates."""
    ops = _flag_ops(63) + [_volume_op(19, "a19"), _volume_op(20, "a20"), _volume_op(5, "a5")]
    updates = backfill._updates(ops, "lu")
    assert 1 < len(updates) <= 3
    for update in updates:
        assert len(update["UpdateExpression"]) <= 4096
        assert len(update["ConditionExpression"]) <= 4096
        assert _no_float(update["ExpressionAttributeValues"])
        _assert_all_placeholders_used(update)
    flags = sum(u["UpdateExpression"].count(".#f = ") for u in updates)
    guards = sum(u["ConditionExpression"].count("attribute_not_exists(") for u in updates)
    vols = sum(u["UpdateExpression"].count(".#v2 = ") for u in updates)
    assert (flags, guards, vols) == (63, 63, 3)


def test_a_plan_too_big_for_one_update_is_cut_between_entries(monkeypatch):
    monkeypatch.setattr(backfill, "MAX_EXPRESSION_CHARS", 400)
    ops = _flag_ops(30) + [_volume_op(2, "a2")]
    updates = backfill._updates(ops, "lu")
    assert len(updates) > 1
    owners = {}
    for k, update in enumerate(updates):
        assert update["ConditionExpression"].startswith("#up.#sh.#lu = :lu")
        _assert_all_placeholders_used(update)
        for i in {int(m) for m in __import__("re").findall(r"#e\[(\d+)\]",
                                                          update["UpdateExpression"])}:
            assert owners.setdefault(i, k) == k     # an entry never spans two updates
    flags = sum(u["UpdateExpression"].count(".#f = ") for u in updates)
    vols = sum(u["UpdateExpression"].count(".#v2 = ") for u in updates)
    assert (flags, vols) == (30, 1)                  # every op exactly once


def _two_entry_history():
    return [
        {"activity_id": f"a{k}", "sets_source": "athlete_text", "description": "dc 3x10 80",
         "parsed_sets": [{"exercise": "Développé couché",
                          "sets_detail": [{"reps": 10, "weight_kg": Decimal("80")}]}]}
        for k in range(2)
    ]


def test_a_failed_update_reports_what_landed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(backfill, "MAX_EXPRESSION_CHARS", 200)  # 1 entry fits, 2 do not
    table = _table(_two_entry_history())
    plan = _plan(tmp_path, table)
    table.update_item.side_effect = [None, RuntimeError("ConditionalCheckFailed")]
    code = backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table)
    out = capsys.readouterr().out
    assert code == 3
    assert table.update_item.call_count == 2
    assert "FAILED on update 2/2" in out and "Updates 1..1 were applied" in out
    assert "update 2 itself may have landed" in out


def test_apply_refuses_a_row_that_changed_exercise(tmp_path):
    plan = _plan(tmp_path, _table(_entries()))
    changed = _entries()
    changed[0]["parsed_sets"][0]["exercise"] = "Squat"
    table = _table(changed)
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table) == 2
    table.update_item.assert_not_called()


def test_apply_refuses_a_row_flagged_since_the_plan(tmp_path):
    plan = _plan(tmp_path, _table(_entries()))
    flagged = _entries()
    flagged[0]["parsed_sets"][0]["per_side"] = True
    table = _table(flagged)
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table) == 2
    table.update_item.assert_not_called()


def test_a_failed_single_update_says_nothing_was_applied(tmp_path, capsys):
    table = _table(_entries())
    plan = _plan(tmp_path, table)
    table.update_item.side_effect = RuntimeError("timeout")
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", plan], table=table) == 3
    out = capsys.readouterr().out
    assert "No earlier update was applied" in out and "Updates 1..0" not in out


def test_apply_refuses_an_old_plan_missing_a_volume_field(tmp_path):
    table = _table(_entries())
    old = _volume_op(0, "a1")
    del old["fields"]["incomplete_reason"]
    plan = tmp_path / "old_plan.json"
    plan.write_text(json.dumps({"user_id": "u", "last_updated": "2026-10-19T06:43:36Z",
                                "entries": 1, "ops": [old]}))
    assert backfill.main(["--user-id", "u", "--out-dir", str(tmp_path), "--apply",
                          "--plan", str(plan)], table=table) == 2
    table.update_item.assert_not_called()
    assert not list(tmp_path.glob("backup_u_*.json"))  # refused before the backup
