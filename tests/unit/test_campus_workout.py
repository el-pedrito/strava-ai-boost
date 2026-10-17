"""Tests for shared/campus_workout.py: one Campus session -> one Apple ``.workout`` file.

GATE 0 WARNING: the goldens in tests/fixtures/workout/gate0/ are the exact files checked
on the athlete's iPhone and Watch during Gate 0. Changing a golden (or the mapper so that
a golden changes) after Gate 0 requires redoing at least Gate 0 step 2b, see
docs/design/apple-watch-workouts.md.

Every assertion on content goes through ``_decode``, a test-only decoder that FAILS on any
field, wire type or enum value it does not know. Production has no decoder on purpose.
"""

import json
import os
import re
import struct
from decimal import Decimal
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared import campus_workout as cw  # noqa: E402
from shared import workout_file as wf  # noqa: E402

GATE0_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "workout", "gate0")
GUID = "0A7E0000-0000-4000-8000-0000000000FF"


# ------------------------------------------------------------ strict test decoder

class UnknownField(AssertionError):
    pass


def _varint(buf, pos):
    shift = result = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(buf):
    """Raw (field, wire, value) triples. Only varint, fixed64 and length-delimited."""
    pos, out = 0, []
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value = struct.unpack("<d", buf[pos:pos + 8])[0]
            pos += 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            value = bytes(buf[pos:pos + length])
            assert len(value) == length, "truncated field"
            pos += length
        else:
            raise UnknownField(f"wire type {wire} on field {field}")
        out.append((field, wire, value))
    assert pos == len(buf), "trailing bytes"
    return out


def _message(buf, schema, repeated=()):
    """Decode ``buf`` against ``schema`` {field: (key, wire, decoder)}; fail on anything else."""
    out = {}
    for field, wire, value in _fields(buf):
        if field not in schema:
            raise UnknownField(f"field {field}")
        key, expected_wire, decode = schema[field]
        if wire != expected_wire:
            raise UnknownField(f"field {field}: wire {wire}, expected {expected_wire}")
        decoded = decode(value)
        if field in repeated:
            out.setdefault(key, []).append(decoded)
        else:
            assert key not in out, f"field {field} repeated"
            out[key] = decoded
    return out


def _enum(allowed):
    def check(value):
        if value not in allowed:
            raise UnknownField(f"enum value {value} not in {sorted(allowed)}")
        return allowed[value]
    return check


def _utf8(raw):
    return raw.decode("utf-8")  # strict: invalid UTF-8 raises


def _same(value):
    return value


def _quantity(raw):
    return _message(raw, {1: ("unit", 0, _same), 2: ("value", 1, _same)})


def _bound(raw):
    msg = _message(raw, {1: ("speed", 2, _quantity), 2: ("per", 2, _quantity)})
    assert msg["speed"]["unit"] == wf.SPEED_UNIT_METERS
    assert msg["per"] == {"unit": wf.TIME_UNIT_SECONDS, "value": 1.0}
    return msg["speed"]["value"]


def _range(raw):
    msg = _message(raw, {1: ("lower", 2, _bound), 2: ("upper", 2, _bound)})
    # Every decoded alert: the lower bound is the slower speed (plan E, ordered bounds).
    assert msg["lower"] < msg["upper"], msg
    return msg


def _alert(raw):
    msg = _message(raw, {
        1: ("metric", 0, _enum({1: "AVERAGE", 2: "CURRENT"})),
        2: ("style", 0, _enum({1: "VALUE", 2: "RANGE"})),
        4: ("speed", 2, lambda r: _message(r, {1: ("target", 2, _bound), 2: ("range", 2, _range)})),
    })
    speed = msg.pop("speed")
    # Exactly one shape, and it must match the declared style.
    assert len(speed) == 1, speed
    if msg["style"] == "VALUE":
        assert "target" in speed, msg
        msg["target"] = speed["target"]
    else:
        assert "range" in speed, msg
        msg.update(speed["range"])
    return msg


def _time_goal(raw):
    return _message(raw, {
        1: ("unit", 0, _enum({1: "SECONDS", 2: "MINUTES", 3: "HOURS"})),
        2: ("value", 1, _same),
    })


def _goal(raw):
    msg = _message(raw, {1: ("kind", 0, _enum({1: "TIME", 4: "OPEN"})), 2: ("time", 2, _time_goal)})
    assert ("time" in msg) == (msg["kind"] == "TIME"), msg
    return msg


def _step(raw):
    return _message(raw, {1: ("goal", 2, _goal), 2: ("alert", 2, _alert), 3: ("name", 2, _utf8)})


def _interval_step(raw):
    msg = _message(raw, {1: ("purpose", 0, _enum({1: "WORK", 2: "RECOVERY"})), 2: ("step", 2, _step)})
    out = dict(msg["step"])
    out["purpose"] = msg["purpose"]
    return out


def _block(raw):
    return _message(raw, {1: ("steps", 2, _interval_step), 2: ("iterations", 0, _same)}, repeated=(1,))


def _custom(raw):
    return _message(raw, {
        1: ("activity", 0, _enum({37: "RUNNING", 50: "STRENGTH"})),
        2: ("location", 0, _enum({2: "INDOOR", 3: "OUTDOOR"})),
        3: ("name", 2, _utf8),
        4: ("warmup", 2, _step),
        5: ("blocks", 2, _block),
        6: ("cooldown", 2, _step),
    }, repeated=(5,))


def _decode(data):
    top = _message(data, {
        9: ("guid", 2, _utf8),
        11: ("workout", 2, _custom),
        1000: ("version", 0, _enum({1: 1})),
        1002: ("format", 0, _enum({5: 5})),
    })
    assert set(top) == {"guid", "workout", "version", "format"}, top
    return top


# ----------------------------------------------------------------- helpers

def _session(intervals, sport="road", **extra):
    base = {
        "session_id": "s1", "title": "Séance test", "week_date_iso": "2026-W50",
        "training_index": 1, "sport": sport, "training_type": "Intensity",
        "intervals": intervals,
    }
    base.update(extra)
    return base


def _work(duration, pace="", **extra):
    entry = {"type": "work", "duration": duration, "pace": pace}
    entry.update(extra)
    return entry


def _map(session):
    result = cw.map_session(session, guid=GUID)
    assert result.encodable, result.reason_code
    return result, _decode(result.bytes)["workout"]


def _only_step(workout):
    assert len(workout["blocks"]) == 1 and len(workout["blocks"][0]["steps"]) == 1
    return workout["blocks"][0]["steps"][0]


def _all_names(workout):
    names = [workout.get("name", "")]
    for edge in ("warmup", "cooldown"):
        if edge in workout:
            names.append(workout[edge].get("name", ""))
    for block in workout.get("blocks", []):
        names.extend(s.get("name", "") for s in block["steps"])
    return names


def _gate0(case):
    with open(os.path.join(GATE0_DIR, case + ".json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    with open(os.path.join(GATE0_DIR, case + ".workout"), "rb") as fh:
        golden = fh.read()
    return spec, golden


# ------------------------------------------------------------------- goldens

class TestGate0Goldens:
    def test_ef_45_golden(self):
        spec, golden = _gate0("ef_45")
        result = cw.map_session(spec["session"], guid=spec["guid"])
        assert result.bytes == golden
        top = _decode(golden)
        assert top["guid"] == spec["guid"]
        workout = top["workout"]
        assert (workout["activity"], workout["location"]) == ("RUNNING", "OUTDOOR")
        assert workout["name"] == "Footing endurance douce W50"
        assert "warmup" not in workout and "cooldown" not in workout
        step = _only_step(workout)
        assert step["purpose"] == "WORK"
        assert step["goal"] == {"kind": "TIME", "time": {"unit": "MINUTES", "value": 45.0}}
        assert "alert" not in step
        assert result.summary == "45' EF 5:57"

    def test_intensity_semi_golden(self):
        spec, golden = _gate0("intensity_semi")
        result = cw.map_session(spec["session"], guid=spec["guid"])
        assert result.bytes == golden
        workout = _decode(golden)["workout"]
        assert workout["warmup"]["goal"]["time"] == {"unit": "MINUTES", "value": 15.0}
        assert "alert" not in workout["warmup"]
        assert workout["cooldown"]["goal"]["time"] == {"unit": "MINUTES", "value": 5.0}
        (block,) = workout["blocks"]
        assert block["iterations"] == 4
        work, rec = block["steps"]
        assert (work["purpose"], rec["purpose"]) == ("WORK", "RECOVERY")
        assert work["name"] == "Semi Marathon 4:28"
        assert work["alert"]["metric"] == "CURRENT" and work["alert"]["style"] == "VALUE"
        assert work["alert"]["target"] == pytest.approx(1000 / 268)
        assert "alert" not in rec and rec["name"] == "Lent 11:14"
        assert result.summary == "WU 15' · 4x(9' Semi 4:28 + 2') · CD 5'"

    def test_sl_tempo_golden(self):
        spec, golden = _gate0("sl_tempo")
        assert cw.map_session(spec["session"], guid=spec["guid"]).bytes == golden
        workout = _decode(golden)["workout"]
        (block,) = workout["blocks"]
        assert block["iterations"] == 1
        aero, rec, tempo = block["steps"]
        assert [s["purpose"] for s in block["steps"]] == ["WORK", "RECOVERY", "WORK"]
        assert "alert" not in aero
        assert rec["goal"]["time"] == {"unit": "SECONDS", "value": 90.0}
        assert tempo["alert"]["metric"] == "CURRENT"
        assert tempo["name"] == "Tempo 5:13"

    def test_ppg_renfo_golden(self):
        spec, golden = _gate0("ppg_renfo")
        result = cw.map_session(spec["session"], guid=spec["guid"])
        assert result.bytes == golden
        workout = _decode(golden)["workout"]
        assert (workout["activity"], workout["location"]) == ("STRENGTH", "INDOOR")
        assert workout["name"] == "Renforcement W50"
        flat, repeated = workout["blocks"]
        assert (len(flat["steps"]), flat["iterations"]) == (13, 1)
        assert (len(repeated["steps"]), repeated["iterations"]) == (3, 3)
        first = flat["steps"][0]
        assert first["name"] == "Fente bulgare lestée x6 rép."
        assert first["goal"] == {"kind": "OPEN"}
        hold = flat["steps"][4]
        assert hold["name"] == "Gainage ventral"
        assert hold["goal"]["time"] == {"unit": "SECONDS", "value": 30.0}
        assert all("alert" not in s for b in workout["blocks"] for s in b["steps"])
        assert result.metrics == {}
        assert result.summary == "13 étapes · 3x(3 étapes)"

    def test_race_semi_golden(self):
        spec, golden = _gate0("race_semi")
        assert cw.map_session(spec["session"], guid=spec["guid"]).bytes == golden
        step = _only_step(_decode(golden)["workout"])
        assert step["goal"]["time"] == {"unit": "SECONDS", "value": 96 * 60 + 42.0}
        assert step["alert"]["metric"] == "AVERAGE"
        assert step["name"] == "course 4:28"


# Local dump of real Campus sessions, never committed. Override with CAMPUS_DUMP_PATH.
REAL_DUMP_PATH = os.environ.get("CAMPUS_DUMP_PATH", "/tmp/wk/campus_sessions.json")
_PACE_IN_TEXT_RE = re.compile(r"(\d{1,2}):(\d{2})\s*/\s*km")


def _string_values(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _string_values(value)
    elif isinstance(node, str):
        yield node


def _golden_texts(node):
    """Titles, step names and paces of a golden session (the athlete-specific fields)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("title", "name", "pace") and isinstance(value, str) and value:
                yield value
            else:
                yield from _golden_texts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _golden_texts(value)


class TestGate0NoRealContent:
    """The goldens are public: none of their titles, names or paces may come from the real plan."""

    def test_goldens_share_no_title_name_or_pace_with_the_real_dump(self):
        if not os.path.exists(REAL_DUMP_PATH):
            pytest.skip("no local Campus dump")
        with open(REAL_DUMP_PATH, encoding="utf-8") as fh:
            raw = fh.read()
        real_strings = set(_string_values(json.loads(raw)))
        real_paces = {m.groups() for m in _PACE_IN_TEXT_RE.finditer(raw)}
        leaks = []
        for case in sorted(f for f in os.listdir(GATE0_DIR) if f.endswith(".json")):
            with open(os.path.join(GATE0_DIR, case), encoding="utf-8") as fh:
                session = json.load(fh)["session"]
            for text in _golden_texts(session):
                if text in real_strings:
                    leaks.append((case, "value"))
                if any(m.groups() in real_paces for m in _PACE_IN_TEXT_RE.finditer(text)):
                    leaks.append((case, "pace"))
        # Report only the case and the kind: the failure message must not echo real data.
        assert not leaks, leaks


# ------------------------------------------------------------- section B rules

class TestSport:
    def test_road_is_outdoor_running(self):
        _, workout = _map(_session([_work("10 min")]))
        assert (workout["activity"], workout["location"]) == ("RUNNING", "OUTDOOR")

    def test_ppg_is_indoor_strength(self):
        _, workout = _map(_session([_work("10 min")], sport="ppg"))
        assert (workout["activity"], workout["location"]) == ("STRENGTH", "INDOOR")

    def test_other_sport_is_unsupported(self):
        for sport in ("trail", "bike", None, ""):
            result = cw.map_session(_session([_work("10 min")], sport=sport), guid=GUID)
            assert (result.encodable, result.reason_code, result.bytes) == (False, "unsupported_sport", None)

    def test_no_intervals(self):
        for intervals in ([], None, "x"):
            result = cw.map_session(_session(intervals), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "no_intervals")


class TestLegacyShape:
    def test_flat_entry_with_repeat_above_one_is_refused(self):
        result = cw.map_session(_session([_work("1 min", repeat=9), _work("1 min", type="recovery")]), guid=GUID)
        assert (result.encodable, result.reason_code) == (False, "legacy_shape")

    def test_flat_entry_with_repeat_as_string_or_decimal(self):
        from decimal import Decimal
        for raw in ("3", Decimal("3")):
            result = cw.map_session(_session([_work("1 min", repeat=raw)]), guid=GUID)
            assert result.reason_code == "legacy_shape"

    def test_flat_entry_with_repeat_one_is_accepted(self):
        result = cw.map_session(_session([_work("1 min", repeat="1")]), guid=GUID)
        assert result.encodable

    def test_non_dict_entry_is_bad_shape(self):
        result = cw.map_session(_session(["10 min"]), guid=GUID)
        assert result.reason_code == "bad_shape"

    def test_only_warmup_is_no_intervals(self):
        result = cw.map_session(_session([_work("10 min", type="warm-up")]), guid=GUID)
        assert (result.encodable, result.reason_code, result.bytes) == (False, "no_intervals", None)

    def test_only_warmup_and_cooldown_is_no_intervals(self):
        result = cw.map_session(_session([
            _work("10 min", type="warm-up"), _work("5 min", type="cool-down"),
        ]), guid=GUID)
        assert (result.encodable, result.reason_code) == (False, "no_intervals")

    def test_only_cooldown_is_no_intervals(self):
        result = cw.map_session(_session([_work("5 min", type="cool-down")]), guid=GUID)
        assert (result.encodable, result.reason_code) == (False, "no_intervals")

    def test_block_without_exercises_is_bad_shape(self):
        result = cw.map_session(_session([{"type": "block", "repeat": 2, "exercises": []}]), guid=GUID)
        assert result.reason_code == "bad_shape"


class TestEdges:
    def test_warmup_only_at_index_zero(self):
        _, workout = _map(_session([_work("5 min"), _work("10 min", type="warm-up")]))
        assert "warmup" not in workout
        assert [s["purpose"] for s in workout["blocks"][0]["steps"]] == ["WORK", "WORK"]

    def test_cooldown_only_at_last_index(self):
        _, workout = _map(_session([_work("5 min", type="cool-down"), _work("10 min")]))
        assert "cooldown" not in workout
        assert len(workout["blocks"][0]["steps"]) == 2

    def test_warmup_and_cooldown_at_their_index(self):
        _, workout = _map(_session([
            _work("10 min", type="warm-up"), _work("20 min"), _work("5 min", type="cool-down"),
        ]))
        assert workout["warmup"]["goal"]["time"]["value"] == 10.0
        assert workout["cooldown"]["goal"]["time"]["value"] == 5.0
        assert len(workout["blocks"][0]["steps"]) == 1


class TestBlocks:
    def test_consecutive_flat_steps_make_one_block_of_one(self):
        _, workout = _map(_session([_work("1 min"), _work("1 min", type="recovery"), _work("2 min")]))
        (block,) = workout["blocks"]
        assert (len(block["steps"]), block["iterations"]) == (3, 1)

    def test_flat_steps_around_a_block_keep_order(self):
        block = {"type": "block", "repeat": 5, "exercises": [_work("30 sec"), _work("30 sec", type="recovery")]}
        _, workout = _map(_session([_work("3 min"), block, _work("4 min")]))
        assert [(len(b["steps"]), b["iterations"]) for b in workout["blocks"]] == [(1, 1), (2, 5), (1, 1)]
        assert workout["blocks"][0]["steps"][0]["goal"]["time"]["value"] == 3.0
        assert workout["blocks"][2]["steps"][0]["goal"]["time"]["value"] == 4.0

    def test_repeat_98_is_the_verified_maximum(self):
        block = {"type": "block", "repeat": 98, "exercises": [_work("30 sec")]}
        _, workout = _map(_session([block]))
        assert workout["blocks"][0]["iterations"] == cw.MAX_REPEAT == 98

    def test_repeat_1_is_accepted(self):
        block = {"type": "block", "repeat": "1", "exercises": [_work("30 sec")]}
        _, workout = _map(_session([block]))
        assert workout["blocks"][0]["iterations"] == 1

    def test_repeat_above_98_is_refused_not_clamped(self):
        for raw in (99, 250):
            block = {"type": "block", "repeat": raw, "exercises": [_work("30 sec")]}
            result = cw.map_session(_session([block]), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "bad_repeat"), raw

    def test_repeat_below_1_is_refused_not_clamped(self):
        for raw in ("0", -3):
            block = {"type": "block", "repeat": raw, "exercises": [_work("30 sec")]}
            result = cw.map_session(_session([block]), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "bad_repeat"), raw

    def test_flat_repeat_outside_range_is_bad_repeat(self):
        for raw in (0, "-1", 99):
            result = cw.map_session(_session([_work("1 min", repeat=raw)]), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "bad_repeat"), raw

    def test_nan_or_infinite_block_repeat_is_bad_repeat(self):
        from decimal import Decimal
        for raw in (float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity")):
            block = {"type": "block", "repeat": raw, "exercises": [_work("30 sec")]}
            result = cw.map_session(_session([block]), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "bad_repeat"), raw

    def test_nan_flat_repeat_is_bad_repeat(self):
        result = cw.map_session(_session([_work("1 min", repeat=float("nan"))]), guid=GUID)
        assert (result.encodable, result.reason_code) == (False, "bad_repeat")

    def test_non_integer_block_repeat_is_bad_repeat(self):
        for raw in ("abc", 2.5, None, True):
            block = {"type": "block", "repeat": raw, "exercises": [_work("30 sec")]}
            result = cw.map_session(_session([block]), guid=GUID)
            assert (result.encodable, result.reason_code) == (False, "bad_repeat"), raw

    def test_non_integer_flat_repeat_is_bad_repeat(self):
        result = cw.map_session(_session([_work("1 min", repeat="x2")]), guid=GUID)
        assert result.reason_code == "bad_repeat"


class TestDurations:
    def _goal(self, duration):
        result, workout = _map(_session([_work(duration)]))
        return _only_step(workout)["goal"], result.metrics

    def test_seconds(self):
        goal, _ = self._goal("45 sec")
        assert goal["time"] == {"unit": "SECONDS", "value": 45.0}

    def test_whole_minutes(self):
        goal, _ = self._goal("12 min")
        assert goal["time"] == {"unit": "MINUTES", "value": 12.0}

    def test_minutes_and_seconds(self):
        goal, _ = self._goal("2:30 min")
        assert goal["time"] == {"unit": "SECONDS", "value": 150.0}

    def test_hours_spellings(self):
        for text in ("2 h", "1 hour", "2 hours"):
            goal, _ = self._goal(text)
            assert goal["time"]["unit"] == "HOURS", text
        assert self._goal("2 hours")[0]["time"]["value"] == 2.0

    def test_unparseable_is_open_with_metric(self):
        for text in ("10 km", "", "1:75 min", "0 min"):
            goal, metrics = self._goal(text)
            assert goal == {"kind": "OPEN"}, text
            assert metrics == {cw.METRIC_OPEN_FALLBACK: 1}, text

    def test_reps_only_strength_step_is_open_without_metric(self):
        result, workout = _map(_session([_work("", name="Squat", reps="10")], sport="ppg"))
        assert _only_step(workout)["goal"] == {"kind": "OPEN"}
        assert result.metrics == {}

    def test_parse_duration_helper(self):
        assert cw.parse_duration_seconds("1:05 min") == 65
        assert cw.parse_duration_seconds("3 sec") == 3
        assert cw.parse_duration_seconds(None) is None
        assert cw.parse_duration_seconds("1:30 h") is None


class TestPaceAlerts:
    def _step(self, duration, pace, **extra):
        session_extra = extra.pop("session", {})
        result, workout = _map(_session([_work(duration, pace, **extra)], **session_extra))
        return _only_step(workout), result.metrics

    def test_default_mode_is_the_exact_target_value(self):
        assert cw.PACE_ALERT_MODE == "value"
        step, _ = self._step("10 min", "Seuil (4:20/km)")
        assert step["alert"]["metric"] == "CURRENT"
        assert step["alert"]["style"] == "VALUE"
        assert step["alert"]["target"] == pytest.approx(1000 / 260)
        assert "lower" not in step["alert"] and "upper" not in step["alert"]

    def test_range_mode_still_available(self, monkeypatch):
        monkeypatch.setattr(cw, "PACE_ALERT_MODE", "range")
        step, _ = self._step("10 min", "Seuil (4:20/km)")
        target = 1000 / 260
        assert step["alert"]["style"] == "RANGE"
        assert step["alert"]["lower"] == pytest.approx(target * (1 - cw.PACE_TOLERANCE))
        assert step["alert"]["upper"] == pytest.approx(target * (1 + cw.PACE_TOLERANCE))

    def test_lower_bound_is_slower_than_upper(self, monkeypatch):
        monkeypatch.setattr(cw, "PACE_ALERT_MODE", "range")
        step, _ = self._step("10 min", "Tempo (5:00/km)")
        assert step["alert"]["lower"] < step["alert"]["upper"]

    def test_race_target_value_uses_average(self):
        step, _ = self._step("40 min", "course (4:28/km)", session={"training_type": "Competition"})
        assert (step["alert"]["style"], step["alert"]["metric"]) == ("VALUE", "AVERAGE")
        assert step["alert"]["target"] == pytest.approx(1000 / 268)

    def test_threshold_is_180_seconds(self):
        assert cw.MIN_PACE_ALERT_SECONDS == 180
        assert "alert" not in self._step("179 sec", "Tempo (5:00/km)")[0]
        assert "alert" in self._step("3 min", "Tempo (5:00/km)")[0]

    def test_recovery_never_gets_alert(self):
        step, _ = self._step("10 min", "Tempo (5:00/km)", type="recovery")
        assert "alert" not in step

    def test_warmup_and_cooldown_never_get_alert(self):
        _, workout = _map(_session([
            _work("10 min", "Tempo (5:00/km)", type="warm-up"),
            _work("10 min", "EF (6:00/km)"),
            _work("10 min", "Tempo (5:00/km)", type="cool-down"),
        ]))
        assert "alert" not in workout["warmup"] and "alert" not in workout["cooldown"]

    def test_open_step_never_gets_alert(self):
        step, _ = self._step("10 km", "Tempo (5:00/km)")
        assert step["goal"] == {"kind": "OPEN"} and "alert" not in step

    def test_races_use_average(self):
        for kind in ("Competition", "low-priority-race"):
            step, _ = self._step("40 min", "course (4:28/km)", session={"training_type": kind})
            assert step["alert"]["metric"] == "AVERAGE", kind

    def test_every_quality_family_alerts(self):
        for family in ("Semi Marathon", "Tempo", "Seuil", "Course", "Allure", "Marathon"):
            step, metrics = self._step("10 min", f"{family} (4:30/km)")
            assert "alert" in step, family
            assert metrics == {}, family

    def test_no_alert_families_are_silent(self):
        for family in ("EF", "Lent", "Aérobie", "Rapide"):
            step, metrics = self._step("10 min", f"{family} (5:00/km)")
            assert "alert" not in step, family
            assert metrics == {}, family

    def test_unknown_family_no_alert_with_metric(self):
        step, metrics = self._step("10 min", "Fartlek (4:30/km)")
        assert "alert" not in step
        assert metrics == {cw.METRIC_UNKNOWN_PACE_FAMILY: 1}

    def test_punctuated_family_semi_marathon(self):
        step, _ = self._step("10 min", "Semi-Marathon (4:28/km)")
        assert step["alert"]["metric"] == "CURRENT"
        assert step["name"] == "Semi-Marathon 4:28"

    def test_normalize_family(self):
        assert cw.normalize_family("  Semi-Marathon ") == "semi marathon"
        assert cw.normalize_family("AÉROBIE") == "aerobie"
        assert cw.normalize_family("Seuil 2") == "seuil"
        assert cw.normalize_family("semi   marathon!") == "semi marathon"

    def test_quality_family_without_pace_has_no_alert(self):
        step, _ = self._step("10 min", "Tempo")
        assert "alert" not in step and step["name"] == "Tempo"

    def test_target_pace_too_fast_has_no_alert_and_metric(self):
        step, metrics = self._step("10 min", "Tempo (0:01/km)")
        assert "alert" not in step
        assert step["name"] == "Tempo"
        assert metrics == {cw.METRIC_PACE_OUT_OF_RANGE: 1}

    def test_target_pace_too_slow_has_no_alert_and_metric(self):
        step, metrics = self._step("10 min", "Tempo (15:01/km)")
        assert "alert" not in step
        assert metrics == {cw.METRIC_PACE_OUT_OF_RANGE: 1}

    def test_target_pace_range_bounds_are_inclusive(self):
        assert (cw.MIN_TARGET_SEC_PER_KM, cw.MAX_TARGET_SEC_PER_KM) == (120, 900)
        for pace in ("Tempo (2:00/km)", "Tempo (15:00/km)"):
            step, metrics = self._step("10 min", pace)
            assert "alert" in step, pace
            assert metrics == {}, pace

    def test_tolerance_constant_pinned(self):
        assert cw.PACE_TOLERANCE == 0.025


class TestNames:
    def test_running_step_name_family_and_pace(self):
        _, workout = _map(_session([_work("10 min", "Marathon (4:50/km)")]))
        assert _only_step(workout)["name"] == "Marathon 4:50"

    def test_strength_name_with_reps(self):
        _, workout = _map(_session([_work("", name="Squat sauté", reps=8)], sport="ppg"))
        assert _only_step(workout)["name"] == "Squat sauté x8 rép."

    def test_workout_name_title_and_week(self):
        _, workout = _map(_session([_work("10 min")], title="Fractionné court", week_date_iso="2026-W07"))
        assert workout["name"] == "Fractionné court W07"

    def test_names_never_contain_campus_or_ppg(self):
        session = _session(
            [_work("", name="Gainage PPG campus", reps=3), _work("30 sec", name="Campus planche")],
            sport="ppg", title="PPG Campus Renfo",
        )
        _, workout = _map(session)
        for name in _all_names(workout):
            assert "campus" not in name.lower() and "ppg" not in name.lower(), name
        assert workout["name"] == "Renfo W50"

    def test_title_only_banned_words_falls_back(self):
        _, workout = _map(_session([_work("10 min")], title="PPG Campus"))
        assert workout["name"] == "Séance W50"

    def test_abbreviation_avec_charge_additionnelle(self):
        _, workout = _map(_session(
            [_work("", name="Fente bulgare avec charge additionnelle", reps=6)], sport="ppg",
        ))
        assert _only_step(workout)["name"] == "Fente bulgare lestée x6 rép."

    def test_abbreviated_participle_stays_masculine_after_masculine_noun(self):
        _, workout = _map(_session(
            [_work("", name="Squat bulgare avec charge additionnelle", reps=6)], sport="ppg",
        ))
        assert _only_step(workout)["name"] == "Squat bulgare lesté x6 rép."

    def test_abbreviation_avec_charge_agrees_in_gender(self):
        _, workout = _map(_session(
            [_work("", name="Montée sur banc avec charge", reps=10)], sport="ppg",
        ))
        assert _only_step(workout)["name"] == "Montée sur banc chargée x10 rép."

    def test_jambe_tendue_keeps_its_meaning(self):
        _, workout = _map(_session([_work("", name="Soulevé de terre jambe tendue", reps=8)], sport="ppg"))
        name = _only_step(workout)["name"]
        assert name == "SDT j. tendue x8 rép."
        assert len(name) <= cw.MAX_STEP_NAME_CHARS

    def test_jambe_tendue_alone_when_it_is_enough(self):
        _, workout = _map(_session([_work("", name="Pont fessier jambe tendue", reps=10)], sport="ppg"))
        assert _only_step(workout)["name"] == "Pont fessier j. tendue x10 rép."

    def test_abbreviation_only_applied_when_too_long(self):
        _, workout = _map(_session([_work("1 min", name="Récupération", type="recovery")], sport="ppg"))
        assert _only_step(workout)["name"] == "Récupération"

    def test_step_name_capped_at_32_chars(self):
        long_name = "Soulevé de terre jambe tendue unilatéral sur banc"
        _, workout = _map(_session([_work("", name=long_name, reps=12)], sport="ppg"))
        name = _only_step(workout)["name"]
        assert len(name) <= cw.MAX_STEP_NAME_CHARS == 32
        assert name.endswith(" x12 rép.")
        assert not name.startswith(" ")

    def test_workout_name_capped_at_32_chars(self):
        _, workout = _map(_session([_work("10 min")], title="Une très longue séance de récupération active"))
        assert len(workout["name"]) <= cw.MAX_WORKOUT_NAME_CHARS
        assert workout["name"].endswith(" W50")

    def test_names_are_utf8_on_the_wire(self):
        result, _ = _map(_session([_work("", name="Montée genou", reps=4)], sport="ppg"))
        assert "Montée genou x4 rép.".encode("utf-8") in result.bytes

    def test_abbreviation_table_pinned(self):
        assert cw.STEP_NAME_ABBREVIATIONS[0] == ("avec charge additionnelle", "lesté")
        assert ("jambe tendue", "j. tendue") in cw.STEP_NAME_ABBREVIATIONS
        assert "fente" in cw.FEMININE_HEAD_NOUNS


class TestNeverRaises:
    """map_session returns a refusal for any malformed row, it never raises."""

    def _refused(self, session, reason="bad_shape"):
        result = cw.map_session(session, guid=GUID)
        assert (result.encodable, result.reason_code, result.bytes) == (False, reason, None)

    def test_non_dict_session(self):
        for session in (None, "x", 3, ["sport"]):
            self._refused(session)

    def test_list_sport(self):
        self._refused(_session([_work("10 min")], sport=["road"]))

    def test_number_sport(self):
        self._refused(_session([_work("10 min")], sport=3))

    def test_list_training_type(self):
        self._refused(_session([_work("10 min")], training_type=["Competition"]))

    def test_number_training_type(self):
        self._refused(_session([_work("10 min")], training_type=4))

    def test_non_string_pace(self):
        for pace in (5.5, {"value": "4:30"}, ["Tempo (4:30/km)"]):
            self._refused(_session([_work("10 min", pace)]))

    def test_non_string_duration(self):
        from decimal import Decimal
        for duration in (Decimal(30), 600, ["10 min"]):
            self._refused(_session([_work(duration)]))

    def test_non_string_duration_with_reps(self):
        from decimal import Decimal
        self._refused(_session([_work(Decimal(30), name="Squat", reps="10")], sport="ppg"))

    def test_non_string_name(self):
        self._refused(_session([_work("", name=12, reps="10")], sport="ppg"))

    def test_non_string_title(self):
        self._refused(_session([_work("10 min")], title={"fr": "x"}))

    def test_nan_or_infinite_reps(self):
        for reps in (float("nan"), float("inf")):
            self._refused(_session([_work("", name="Squat", reps=reps)], sport="ppg"))

    def test_non_integer_reps(self):
        for reps in ("dix", 2.5, 0):
            self._refused(_session([_work("", name="Squat", reps=reps)], sport="ppg"))

    def test_lone_surrogate_in_title(self):
        self._refused(_session([_work("10 min")], title="Footing \ud800"))

    def test_lone_surrogate_in_step_name(self):
        self._refused(_session([_work("", name="Squat \udfff", reps="5")], sport="ppg"))

    def test_lone_surrogate_in_pace_family(self):
        self._refused(_session([_work("10 min", "Tempo\ud800 (5:00/km)")]))

    def test_unexpected_error_inside_encoding_is_internal(self, monkeypatch):
        # An unanticipated failure is not a malformed row: it is reported as internal.
        def boom(*_args, **_kwargs):
            raise OverflowError("simulated")
        monkeypatch.setattr(cw.wf, "workout_file", boom)
        self._refused(_session([_work("10 min")]), reason="internal")

    def test_bad_caller_guid_raises_instead_of_hiding_as_row_error(self):
        for guid in ("eb04f3b5-6c4e-4f8f-bb9d-276d50d7e2a8", "6FA459EA-EE8A-11E3-AC10-0800200C9A66"):
            with pytest.raises(ValueError):
                cw.map_session(_session([_work("10 min")]), guid=guid)

    def test_reps_above_cap_is_bad_shape(self):
        ok = _session([_work("", name="Squat", reps=str(cw.MAX_REPS))], sport="ppg")
        assert cw.map_session(ok, guid=GUID).encodable
        self._refused(_session([_work("", name="Squat", reps=str(cw.MAX_REPS + 1))], sport="ppg"))
        self._refused(_session([_work("", name="Squat", reps=10**40)], sport="ppg"))

    def test_plural_head_noun_agrees_in_number(self):
        long_fem = "Fentes bulgares avec charge additionnelle"
        long_masc = "Squats sautés avec charge additionnelle"
        _, w1 = _map(_session([_work("", name=long_fem, reps="6")], sport="ppg"))
        _, w2 = _map(_session([_work("", name=long_masc, reps="6")], sport="ppg"))
        assert _only_step(w1)["name"].startswith("Fentes bulgares lestées")
        assert _only_step(w2)["name"].startswith("Squats sautés lestés")


class TestLimits:
    def test_more_than_30_steps_in_one_block(self):
        block = {"type": "block", "repeat": 2, "exercises": [_work("10 sec") for _ in range(31)]}
        result = cw.map_session(_session([block]), guid=GUID)
        assert (result.encodable, result.reason_code) == (False, "too_many_steps")

    def test_exactly_30_steps_in_one_block_is_fine(self):
        block = {"type": "block", "repeat": 2, "exercises": [_work("10 sec") for _ in range(30)]}
        assert cw.map_session(_session([block]), guid=GUID).encodable

    def test_total_steps_cap(self):
        block = {"type": "block", "repeat": 2, "exercises": [_work("10 sec") for _ in range(30)]}
        result = cw.map_session(_session([block, _work("1 min", type="recovery"), block]), guid=GUID)
        assert result.reason_code == "too_many_steps"
        assert cw.MAX_TOTAL_STEPS_PER_WORKOUT == 60

    def test_byte_cap(self, monkeypatch):
        session = _session([_work("10 min", "Tempo (5:00/km)")])
        size = len(cw.map_session(session, guid=GUID).bytes)
        monkeypatch.setattr(cw, "MAX_WORKOUT_BYTES", size - 1)
        result = cw.map_session(session, guid=GUID)
        assert (result.encodable, result.reason_code, result.bytes) == (False, "too_large", None)


class TestGuidAndSummary:
    def test_fresh_guid_each_export(self):
        session = _session([_work("10 min")])
        first = _decode(cw.map_session(session).bytes)["guid"]
        second = _decode(cw.map_session(session).bytes)["guid"]
        assert first != second
        assert first == first.upper() and first[14] == "4"

    def test_fixed_guid_is_deterministic(self):
        session = _session([_work("10 min")])
        assert cw.map_session(session, guid=GUID).bytes == cw.map_session(session, guid=GUID).bytes

    def test_summary_open_and_seconds(self):
        result, _ = _map(_session([_work("10 km", type="work"), _work("45 sec", type="recovery")]))
        assert result.summary == 'libre + 45"'

    def test_refused_item_has_no_bytes_or_summary(self):
        result = cw.map_session(_session([_work("1 min", repeat=4)]), guid=GUID)
        assert result.bytes is None and result.summary is None


class TestFilename:
    def test_ascii_slug(self):
        name = cw.workout_filename({"week_date_iso": "2026-W50", "training_index": 2, "title": "Séance Côtes PPG"})
        assert name == "2026-W50-2-seance-cotes.workout"
        name.encode("ascii")

    def test_capped_at_60_chars(self):
        name = cw.workout_filename({"week_date_iso": "2026-W50", "training_index": 12, "title": "x" * 200})
        assert len(name) <= cw.MAX_FILENAME_CHARS == 60
        assert name.endswith(".workout")

    def test_missing_fields(self):
        assert cw.workout_filename({}) == "week-0-seance.workout"

    def test_huge_index_is_clamped_and_extension_kept(self):
        name = cw.workout_filename({"week_date_iso": "2026-W50", "training_index": 10 ** 60, "title": "x" * 80})
        assert name.startswith("2026-W50-99-")
        assert name.endswith(".workout") and len(name) <= cw.MAX_FILENAME_CHARS

    def test_negative_index_is_clamped_to_zero(self):
        name = cw.workout_filename({"week_date_iso": "2026-W50", "training_index": -1, "title": "Footing"})
        assert name == "2026-W50-0-footing.workout"

    def test_nan_index_falls_back_to_zero(self):
        name = cw.workout_filename({"week_date_iso": "2026-W50", "training_index": float("nan"), "title": "Footing"})
        assert name == "2026-W50-0-footing.workout"

    def test_non_string_title_and_surrogate_never_raise(self):
        assert cw.workout_filename({"title": ["x"], "week_date_iso": 7}) == "week-0-seance.workout"
        assert cw.workout_filename({"title": "Foot\ud800ing"}) == "week-0-footing.workout"


# ------------------------------------------- Campus pace kinds (campus-paces.md C)

# Family -> (pace_kind, pace_slug) of the structured twin of a legacy golden step.
_TWIN_KINDS = {
    "ef": ("range", "ef"),
    "aerobie": ("single-value", "aerobie"),
    "lent": ("abstract", "slow"),
    "semi marathon": ("single-value", "half-marathon"),
    "tempo": ("single-value", "tempo"),
    "course": ("single-value", "race"),
}


def _twin_entry(entry):
    if entry.get("type") == "block":
        return {**entry, "exercises": [_twin_entry(e) for e in entry["exercises"]]}
    pace = entry.get("pace") or ""
    family = cw.normalize_family(cw._family_text(pace))
    if family not in _TWIN_KINDS:
        return dict(entry)
    kind, slug = _TWIN_KINDS[family]
    twin = {**entry, "pace_kind": kind, "pace_slug": slug, "pace_zone": slug}
    target = cw._target_sec_per_km(pace)
    if target is not None:
        twin["pace_value_s"] = target
    return twin


def _twin(session, estimated=None):
    """Structured twin of a legacy golden session: what the new sync writes for it."""
    twin = {**session, "intervals": [_twin_entry(e) for e in session["intervals"]]}
    if estimated is not None:
        twin["estimated_paces"] = estimated
    return twin


LEGACY_GOLDENS = ("ef_45", "intensity_semi", "sl_tempo", "ppg_renfo", "race_semi")


class TestStructuredParity:
    """Switch off, a structured row maps to the same bytes as its legacy golden."""

    def test_twins_of_every_golden_are_byte_identical_switch_off(self):
        for case in LEGACY_GOLDENS:
            spec, golden = _gate0(case)
            twin = _twin(spec["session"], estimated={"ef": {"value": 355.4, "dvalue": 12.4}})
            assert twin != spec["session"] or case == "ppg_renfo", case
            result = cw.map_session(twin, guid=spec["guid"])
            assert result.bytes == golden, case

    def test_twins_switch_on_without_estimated_paces(self):
        """The range comes from the step's pace_value_s alone: estimated_paces is not needed.

        Twins without an EF step keep their bytes. An EF twin gets its RANGE alert
        (5:57 -> 5:57-6:27) with no metric.
        """
        for case in ("ppg_renfo", "race_semi"):
            spec, golden = _gate0(case)
            result = cw.map_session(_twin(spec["session"]), guid=spec["guid"], range_alerts=True)
            assert result.bytes == golden, case
        for case in ("ef_45", "intensity_semi", "sl_tempo"):
            spec, golden = _gate0(case)
            result = cw.map_session(_twin(spec["session"]), guid=spec["guid"], range_alerts=True)
            assert result.bytes != golden, case
            assert result.metrics == {}, case
            workout = _decode(result.bytes)["workout"]
            ef = workout["warmup"] if "warmup" in workout else _only_step(workout)
            assert ef["alert"]["style"] == "RANGE", case
            assert ef["alert"]["lower"] == 1000.0 / 387, case
            assert ef["alert"]["upper"] == 1000.0 / 357, case
            assert ef["name"] == "EF 5:57-6:27", case

    def test_single_value_target_comes_from_pace_value_s(self):
        step = _work("10 min", "Tempo (5:00/km)", pace_kind="single-value", pace_value_s=290)
        workout = _map(_session([step]))[1]
        assert _only_step(workout)["alert"]["target"] == pytest.approx(1000 / 290)
        assert _only_step(workout)["name"] == "Tempo 4:50"

    def test_ef_range_golden_needs_the_switch(self):
        spec, golden = _gate0("ef_range")
        assert spec["range_alerts"] is True
        assert cw.map_session(spec["session"], guid=spec["guid"]).bytes != golden


class TestRangeAlerts:
    EST = {"ef": {"value": Decimal("355.4"), "dvalue": Decimal("12.4")}}

    def _range(self, duration="30 min", type_="work", **extra):
        entry = {"type": type_, "duration": duration, "pace": "EF (5:55/km)",
                 "pace_kind": "range", "pace_slug": "ef", "pace_value_s": 355}
        entry.update(extra)
        return entry

    def _map_on(self, intervals, estimated=None, **session_extra):
        session = _session(intervals, estimated_paces=self.EST if estimated is None else estimated,
                           **session_extra)
        result = cw.map_session(session, guid=GUID, range_alerts=True)
        assert result.encodable, result.reason_code
        return result, _decode(result.bytes)["workout"]

    def test_ef_range_golden(self):
        spec, golden = _gate0("ef_range")
        result = cw.map_session(spec["session"], guid=spec["guid"], range_alerts=spec["range_alerts"])
        assert result.bytes == golden
        workout = _decode(golden)["workout"]
        for step in (workout["warmup"], _only_step(workout), workout["cooldown"]):
            assert step["alert"]["style"] == "RANGE" and step["alert"]["metric"] == "CURRENT"
            assert step["alert"]["lower"] == 1000.0 / 385
            assert step["alert"]["upper"] == 1000.0 / 355
            assert step["name"] == "EF 5:55-6:25"
        assert result.summary == "WU 15' · 30' EF 5:55-6:25 · CD 10'"
        assert result.metrics == {}

    def test_switch_off_range_step_follows_todays_rules(self):
        session = _session([self._range()], estimated_paces=self.EST)
        step = _only_step(_decode(cw.map_session(session, guid=GUID).bytes)["workout"])
        assert "alert" not in step and step["name"] == "EF 5:55"

    def test_range_is_value_to_value_plus_30_as_the_campus_app_shows(self):
        """EF 346 -> "5:46 - 6:16" on the Campus app (6 screens, 2026-10-17)."""
        entry = self._range(pace="EF (5:46/km)", pace_value_s=346)
        step = _only_step(self._map_on([entry])[1])
        assert step["alert"]["style"] == "RANGE"
        assert step["alert"]["lower"] == 1000.0 / 376
        assert step["alert"]["upper"] == 1000.0 / 346
        assert step["alert"]["lower"] < step["alert"]["upper"]
        assert step["name"] == "EF 5:46-6:16"

    def test_range_ignores_estimated_paces(self):
        """Same bytes with the session's estimated_paces, without it, or with junk in it."""
        reference = self._map_on([self._range()])[0].bytes
        for est in ({}, {"ef": {"value": 348.8, "dvalue": 13.3}}, {"ef": "junk"}):
            result, _ = self._map_on([self._range()], est)
            assert result.bytes == reference, est
            assert result.metrics == {}, est

    def test_short_range_step_has_no_alert_but_the_range_name(self):
        step = _only_step(self._map_on([self._range("179 sec")])[1])
        assert "alert" not in step and step["name"] == "EF 5:55-6:25"
        assert "alert" in _only_step(self._map_on([self._range("3 min")])[1])

    def test_short_range_warmup_and_cooldown_still_alert(self):
        """The 180 s floor is for non-edge WORK steps only (spec C, review cr1)."""
        intervals = [self._range("179 sec", type_="warm-up"), self._range(),
                     self._range("179 sec", type_="cool-down")]
        workout = self._map_on(intervals)[1]
        for edge in ("warmup", "cooldown"):
            assert workout[edge]["alert"]["style"] == "RANGE", edge
            assert workout[edge]["alert"]["lower"] == 1000.0 / 385, edge
            assert workout[edge]["name"] == "EF 5:55-6:25", edge

    def test_short_range_edges_switch_off_keep_todays_no_alert(self):
        intervals = [self._range("179 sec", type_="warm-up"), self._range(),
                     self._range("179 sec", type_="cool-down")]
        session = _session(intervals, estimated_paces=self.EST)
        workout = _decode(cw.map_session(session, guid=GUID).bytes)["workout"]
        assert "alert" not in workout["warmup"] and "alert" not in workout["cooldown"]

    def test_recovery_range_step_never_alerts(self):
        intervals = [self._range(), self._range("5 min", type_="recovery")]
        rec = self._map_on(intervals)[1]["blocks"][0]["steps"][1]
        assert rec["purpose"] == "RECOVERY" and "alert" not in rec

    def test_race_uses_average(self):
        step = _only_step(self._map_on([self._range()], training_type="Competition")[1])
        assert step["alert"]["metric"] == "AVERAGE"

    def test_intensity_semi_cool_down_range_switch_on(self):
        """EF warm-up / cool-down get a RANGE alert, the Semi block keeps its VALUE alert."""
        spec, _ = _gate0("intensity_semi")
        result = cw.map_session(_twin(spec["session"], {k: dict(v) for k, v in self.EST.items()}),
                                guid=spec["guid"], range_alerts=True)
        workout = _decode(result.bytes)["workout"]
        assert workout["warmup"]["alert"]["style"] == "RANGE"
        assert workout["cooldown"]["alert"]["style"] == "RANGE"
        work, rec = workout["blocks"][0]["steps"]
        assert work["alert"]["style"] == "VALUE" and work["alert"]["target"] == pytest.approx(1000 / 268)
        assert "alert" not in rec

    def test_invalid_range_data_no_alert_with_metric_never_refused(self):
        cases = (
            (119, cw.METRIC_PACE_OUT_OF_RANGE),
            (871, cw.METRIC_PACE_OUT_OF_RANGE),
            ("nan", cw.METRIC_PACE_INVALID),
            (float("nan"), cw.METRIC_PACE_INVALID),
            (True, cw.METRIC_PACE_INVALID),
            ({"v": 1}, cw.METRIC_PACE_INVALID),
            (None, cw.METRIC_PACE_INVALID),
        )
        for value, metric in cases:
            result, workout = self._map_on([self._range(pace_value_s=value)])
            step = _only_step(workout)
            assert "alert" not in step, value
            assert step["name"] == "EF 5:55", value
            assert result.metrics == {metric: 1}, value

    def test_range_bounds_are_inclusive(self):
        """fast >= 120 s/km and slow = value + 30 <= 900 s/km."""
        for value in (120, 870):
            result, workout = self._map_on([self._range(pace_value_s=value)])
            assert "alert" in _only_step(workout), value
            assert result.metrics == {}

    def test_decimal_string_and_int_inputs_are_converted(self):
        for value in (Decimal("355"), "355", 355, 355.0):
            step = _only_step(self._map_on([self._range(pace_value_s=value)])[1])
            assert step["alert"]["upper"] == 1000.0 / 355, value


class TestPaceKinds:
    def test_abstract_never_alerts(self):
        step = _work("10 min", "Tempo (5:00/km)", pace_kind="abstract")
        result, workout = _map(_session([step]))
        assert "alert" not in _only_step(workout) and result.metrics == {}

    def test_unknown_kind_follows_legacy_string_rules_with_metric(self):
        """A kind Campus adds later must not silence a quality step that alerts today.

        Same bytes as the legacy row (no pace_kind): target from the pace string, so
        a pace_value_s that disagrees with it is ignored.
        """
        legacy = _session([_work("10 min", "Tempo (5:00/km)")])
        legacy_bytes = cw.map_session(legacy, guid=GUID).bytes
        for kind in ("zone", 3, ""):
            step = _work("10 min", "Tempo (5:00/km)", pace_kind=kind, pace_value_s=290)
            result = cw.map_session(_session([step]), guid=GUID)
            assert result.bytes == legacy_bytes, kind
            alert = _only_step(_decode(result.bytes)["workout"])["alert"]
            assert alert["target"] == pytest.approx(1000 / 300), kind
            assert result.metrics == {cw.METRIC_UNKNOWN_PACE_KIND: 1}, kind
            switch_on = cw.map_session(_session([step]), guid=GUID, range_alerts=True)
            assert switch_on.bytes == legacy_bytes, kind

    def test_single_value_without_value_no_alert_with_metric(self):
        for bad in (None, "x", float("nan"), {"v": 1}):
            step = _work("10 min", "Tempo (5:00/km)", pace_kind="single-value", pace_value_s=bad)
            result, workout = _map(_session([step]))
            assert "alert" not in _only_step(workout), bad
            assert _only_step(workout)["name"] == "Tempo", bad
            assert result.metrics == {cw.METRIC_PACE_INVALID: 1}, bad

    def test_single_value_out_of_range_metric(self):
        step = _work("10 min", "Tempo (5:00/km)", pace_kind="single-value", pace_value_s=950)
        result, workout = _map(_session([step]))
        assert "alert" not in _only_step(workout)
        assert result.metrics == {cw.METRIC_PACE_OUT_OF_RANGE: 1}

    def test_bad_pace_slug_type_is_not_a_refusal(self):
        step = {"type": "work", "duration": "30 min", "pace": "EF (5:55/km)",
                "pace_kind": "range", "pace_slug": ["ef"]}
        result = cw.map_session(_session([step], estimated_paces={"ef": {"value": 351, "dvalue": 12}}),
                                guid=GUID, range_alerts=True)
        assert result.encodable and result.metrics == {cw.METRIC_PACE_INVALID: 1}
