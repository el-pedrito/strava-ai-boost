"""Unit tests for the coach_chat runtime tools (coach-figures-integrity WP1/WP2/WP2b).

The coach_chat runtime is deployed with ``direct_code_deploy`` bundling only
``src/coach_chat/``, so it CANNOT import ``lambda_functions/shared/``. The proven
pattern (see ``_effective_status`` and its
``test_matches_shared_effective_status``) is a LOCAL MIRROR + an anti-drift test
that locks the mirror to the canonical shared implementation. This module adds:

  * WP1 — ``iso_week_label`` mirror + ``iso_week`` on every compact activity,
    locked to ``shared.iso_week.iso_week_label`` by ``test_matches_shared_iso_week_label``.
  * WP2 — ``get_weekly_totals`` code-computed per-ISO-week totals, locked to
    ``coach_generator.build_week_overview`` on shared fixtures.
  * WP2b — ``get_strength_sessions`` totals computed in code (never counted from
    the raw description), and the removed false "muscu progression" promise.

No test-case expansion (``@pytest.mark`` fan-out) here on purpose: ``test_docs_sync``
derives the unit-suite size by counting ``def test_`` lines and assumes one def
equals one collected case in ``tests/unit/``.
"""

import importlib.util
import inspect
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# --- Import the (deploy-only) coach_chat module via local stubs ---------------
#
# Same mechanism as tests/unit/test_coach_week_disambiguation.py: stub the heavy
# deploy-only deps only when absent, so a CI venv with the real packages still
# exercises the real code.


def _stub_package(top: str, submodules: tuple = ()) -> None:
    if top in sys.modules:
        return
    try:
        if importlib.util.find_spec(top) is not None:
            return
    except (ValueError, ModuleNotFoundError):
        pass
    for name in (top, *submodules):
        if name not in sys.modules:
            mod = MagicMock(name=name)
            mod.__path__ = []
            sys.modules[name] = mod


_stub_package("ag_ui", ("ag_ui.core", "ag_ui.encoder"))
_stub_package("ag_ui_strands")
_stub_package("fastapi", ("fastapi.responses",))
_stub_package("uvicorn")
_stub_package("strands", ("strands.models",))

# coach_generator lives under lambda_functions/; stub the deploy-only agents pkg.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))
sys.modules.setdefault("agents", MagicMock())
sys.modules.setdefault("agents.coach_agent", MagicMock())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "coach_chat"))

import coach_chat_agent as cca  # noqa: E402
import processing.coach_generator as cg  # noqa: E402
from shared.iso_week import iso_week_label as shared_iso_week_label  # noqa: E402


# --------------------------------------------------------------------------- #
# Test fixtures — activity items shaped like DynamoDB rows
# --------------------------------------------------------------------------- #
def _activity_item(activity_id: str, atype: str, start_local: str, distance_m: float = 0) -> dict:
    """A DynamoDB activity row whose blob mirrors what both counters read."""
    blob = {"type": atype, "start_date_local": start_local}
    if distance_m:
        blob["distance"] = distance_m
    return {"activity_id": activity_id, "activity_data_json": json.dumps(blob)}


def _monday(iso_year: int, iso_week: int) -> date:
    return date.fromisocalendar(iso_year, iso_week, 1)


# --------------------------------------------------------------------------- #
# WP1 — iso_week_label local mirror
# --------------------------------------------------------------------------- #
class TestIsoWeekLabelMirror:
    def test_returns_zero_padded_iso_string(self):
        # 2026-01-01 is a Thursday -> ISO week 1 -> zero-padded "W01".
        assert cca.iso_week_label("2026-01-01T00:00:00") == "2026-W01"

    def test_matches_iso_format_and_is_str(self):
        label = cca.iso_week_label("2026-08-06T10:00:00Z")
        assert isinstance(label, str)
        assert re.match(r"^\d{4}-W\d{2}$", label)

    def test_accepts_date_only_string(self):
        # _compact_activity feeds a truncated 'YYYY-MM-DD' date.
        assert cca.iso_week_label("2026-08-06") == "2026-W32"

    def test_empty_or_unparseable_returns_empty(self):
        assert cca.iso_week_label("") == ""
        assert cca.iso_week_label(None) == ""
        assert cca.iso_week_label("not-a-date") == ""

    def test_matches_shared_iso_week_label(self):
        """Local mirror must agree with the canonical shared helper."""
        cases = [
            "2026-01-01T00:00:00",
            "2026-08-06T10:00:00Z",
            "2026-12-31T23:00:00",
            "2025-06-15",
            "",
            None,
            "not-a-date",
        ]
        for case in cases:
            assert cca.iso_week_label(case) == shared_iso_week_label(case)


class TestCompactActivityIsoWeek:
    def test_compact_activity_carries_iso_week(self):
        item = _activity_item("a1", "Run", "2026-08-06T10:00:00Z", distance_m=10000)
        record = cca._compact_activity(item)
        assert record["iso_week"] == "2026-W32"
        assert record["date"] == "2026-08-06"

    def test_iso_week_empty_when_no_date(self):
        record = cca._compact_activity({"activity_id": "a2", "activity_data_json": "{}"})
        assert record["iso_week"] == ""


# --------------------------------------------------------------------------- #
# WP2 — get_weekly_totals, locked to build_week_overview
# --------------------------------------------------------------------------- #
class TestWeeklyTotals:
    def _mock_dynamo(self, items: list) -> MagicMock:
        table = MagicMock()
        table.query.return_value = {"Items": items}  # no LastEvaluatedKey -> one page
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        return dynamo

    def _current_and_last_week_items(self):
        now = datetime.now(timezone.utc)
        iso = now.isocalendar()
        cur_mon = _monday(iso[0], iso[1])
        last_mon = cur_mon - timedelta(days=7)
        cur_day = (cur_mon + timedelta(days=2)).isoformat()
        last_day = (last_mon + timedelta(days=2)).isoformat()
        items = [
            _activity_item("r1", "Run", f"{cur_day}T10:00:00", distance_m=10000),
            _activity_item("r2", "Run", f"{cur_day}T18:00:00", distance_m=5000),
            _activity_item("w1", "WeightTraining", f"{cur_day}T20:00:00"),
            _activity_item("r3", "Run", f"{last_day}T10:00:00", distance_m=8000),
        ]
        cur_label = cca.iso_week_label(cur_day)
        last_label = cca.iso_week_label(last_day)
        return items, cur_label, last_label, cur_day

    def test_buckets_by_iso_week_with_expected_figures(self):
        items, cur_label, last_label, _ = self._current_and_last_week_items()
        with patch.object(cca, "dynamodb", self._mock_dynamo(items)):
            weeks = cca._get_weekly_totals_impl("u1", 4)

        by_week = {w["iso_week"]: w for w in weeks}
        cur = by_week[cur_label]
        assert (cur["runs"], cur["run_km"], cur["strength"], cur["other"], cur["total"]) == (2, 15.0, 1, 0, 3)
        assert cur["is_current"] is True

        last = by_week[last_label]
        assert (last["runs"], last["run_km"], last["strength"], last["other"], last["total"]) == (1, 8.0, 0, 0, 1)
        assert last["is_current"] is False

    def test_returns_zero_weeks_not_missing_entries(self):
        # No activities at all: still one entry per target week, all zeros.
        with patch.object(cca, "dynamodb", self._mock_dynamo([])):
            weeks = cca._get_weekly_totals_impl("u1", 4)
        assert len(weeks) == 4
        assert all(w["total"] == 0 for w in weeks)
        assert weeks[0]["is_current"] is True  # most recent first
        assert sum(1 for w in weeks if w["is_current"]) == 1

    def test_empty_user_id_returns_empty(self):
        assert cca._get_weekly_totals_impl("", 4) == []

    def test_weekly_totals_match_build_week_overview(self):
        """The chat's current-week figures must equal the pipeline's for the
        same activities — the whole point of WP2 (code-computed, not model-summed)."""
        items, cur_label, _, cur_day = self._current_and_last_week_items()

        # Pipeline: build_week_overview counts the ISO week of the activity.
        with patch.object(cg, "dynamodb", self._mock_dynamo(items)):
            overview = cg.build_week_overview(
                "u1",
                {"start_date_local": f"{cur_day}T10:00:00"},
                [],
                None,
            )
        done = overview["done_this_week"]

        # Chat tool.
        with patch.object(cca, "dynamodb", self._mock_dynamo(items)):
            weeks = cca._get_weekly_totals_impl("u1", 4)
        cur = {w["iso_week"]: w for w in weeks}[cur_label]

        assert overview["week"] == cur_label
        assert cur["runs"] == done["runs"]
        assert cur["run_km"] == done["run_km"]
        assert cur["strength"] == done["strength"]
        assert cur["other"] == done["other"]
        assert cur["total"] == done["total"]
        # The human-readable current-week label is mirrored verbatim too.
        assert cur["label"] == overview["label"]


# --------------------------------------------------------------------------- #
# WP2b — strength totals computed in code + the removed false promise
# --------------------------------------------------------------------------- #
class TestStrengthTotals:
    def test_flat_form_simple_tonnage(self):
        # 4x10 @80kg = 3200 kg, complete.
        totals = cca._compute_strength_totals(
            [{"exercise": "Développé couché", "sets": 4, "reps": 10, "weight_kg": 80}]
        )
        assert totals["total_sets"] == 4
        assert totals["total_reps"] == 40
        assert totals["volume_kg"] == 3200.0
        assert totals["volume_kg_incomplete"] is False

    def test_sets_detail_is_authoritative(self):
        # 10x80, 8x90, 8x90 -> 26 reps, 2240 kg (never 24 reps / flat summary).
        totals = cca._compute_strength_totals(
            [
                {
                    "exercise": "Tirage horizontal machine",
                    "sets": 3,
                    "reps": 8,
                    "weight_kg": 90,
                    "sets_detail": [
                        {"reps": 10, "weight_kg": 80},
                        {"reps": 8, "weight_kg": 90},
                        {"reps": 8, "weight_kg": 90},
                    ],
                }
            ]
        )
        assert totals["total_sets"] == 3
        assert totals["total_reps"] == 26
        assert totals["volume_kg"] == 2240.0
        assert totals["volume_kg_incomplete"] is False

    def test_missing_load_is_flagged_not_defaulted(self):
        # Bodyweight/unknown load: counted in reps, excluded from tonnage, flagged.
        totals = cca._compute_strength_totals(
            [
                {
                    "exercise": "Tractions",
                    "sets_detail": [
                        {"reps": 12, "weight_kg": None},
                        {"reps": 12, "weight_kg": None},
                    ],
                }
            ]
        )
        assert totals["total_reps"] == 24
        assert totals["volume_kg"] == 0.0
        assert totals["volume_kg_incomplete"] is True
        assert totals["per_exercise"][0]["volume_kg"] is None

    def test_reps_total_matches_description_count(self):
        # WP2b acceptance: reps come from stored sets, not counted from prose.
        # A 238-rep session must total 238, computed in code.
        parsed = [
            {"exercise": "A", "sets_detail": [{"reps": 100, "weight_kg": 50}]},
            {"exercise": "B", "sets_detail": [{"reps": 138, "weight_kg": 40}]},
        ]
        totals = cca._compute_strength_totals(parsed)
        assert totals["total_reps"] == 238

    def test_get_strength_sessions_reads_history_and_filters(self):
        recent = datetime.now(timezone.utc).date().isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
        item = {
            "Item": {
                "user_preferences": {
                    "strength_history": {
                        "entries": [
                            {
                                "activity_id": "s_recent",
                                "date": recent,
                                "duration_min": 60,
                                "parsed_sets": [
                                    {"exercise": "Squat", "sets": 4, "reps": 10, "weight_kg": 100}
                                ],
                            },
                            {
                                "activity_id": "s_old",
                                "date": old,
                                "duration_min": 55,
                                "parsed_sets": [
                                    {"exercise": "Squat", "sets": 3, "reps": 8, "weight_kg": 90}
                                ],
                            },
                        ]
                    }
                }
            }
        }
        table = MagicMock()
        table.get_item.return_value = item
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cca, "dynamodb", dynamo):
            sessions = cca._get_strength_sessions_impl("u1", 4)

        assert [s["activity_id"] for s in sessions] == ["s_recent"]  # old filtered out
        s = sessions[0]
        assert s["total_reps"] == 40
        assert s["volume_kg"] == 4000.0
        assert s["iso_week"] == cca.iso_week_label(recent)

    def test_get_strength_sessions_empty_when_no_history(self):
        table = MagicMock()
        table.get_item.return_value = {"Item": {"user_preferences": {}}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cca, "dynamodb", dynamo):
            assert cca._get_strength_sessions_impl("u1", 4) == []

    def test_coach_observations_no_longer_promises_strength_loads(self):
        """WP2b: the false 'progression des charges en musculation' promise is gone.

        The @tool wrapper may be a MagicMock under the deploy-only stubs, so we
        assert on the module source rather than the decorated docstring.
        """
        source = inspect.getsource(cca)
        assert "progression des charges en musculation" not in source
        assert "progression musculation charges" not in source


class TestStrengthFiguresComeFromThePipeline:
    """The chat must READ the tonnage, never recompute it.

    shared/strength_volume.py is the single definition: it applies the bodyweight
    coefficients and the unilateral doubling. This runtime cannot import it (its
    deploy bundles only src/coach_chat/), and a second local implementation
    reported a lower figure for the same session. Figures are therefore computed
    at write time and stored on the history entry.
    """

    def _entry(self, **extra):
        base = {
            "activity_id": "act-1",
            "date": "2026-08-04",
            "duration_min": 48,
            "parsed_sets": [
                {"exercise": "Tractions", "sets": 3, "reps": 10, "weight_kg": None,
                 "sets_detail": [{"reps": 10, "weight_kg": None}] * 3},
            ],
        }
        base.update(extra)
        return base

    def _run(self, entry):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"user_preferences": {"strength_history": {"entries": [entry]}}}
        }
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cca, "dynamodb", dynamo):
            return cca._get_strength_sessions_impl("u1", 4)

    def test_stored_figures_are_used_verbatim(self):
        out = self._run(self._entry(
            total_sets=25, total_reps=238, volume_kg=15370.0,
            body_weight_kg_used=92.0, volume_kg_incomplete=False,
            excluded_exercises=[],
        ))
        assert len(out) == 1
        s = out[0]
        assert s["total_reps"] == 238, s
        assert float(s["volume_kg"]) == 15370.0, s
        assert float(s["body_weight_kg_used"]) == 92.0
        assert s["volume_kg_incomplete"] is False
        assert s["figures_source"] == "pipeline"

    def test_legacy_row_without_stored_figures_is_flagged_incomplete(self):
        """Rows written before the wiring have no totals. The local fallback
        cannot apply bodyweight coefficients, so its tonnage is explicit-weight
        only and must never be presented as exact."""
        out = self._run(self._entry())
        s = out[0]
        assert s["figures_source"] == "legacy_local_fallback"
        assert s["volume_kg_incomplete"] is True
        # Reps are still countable without knowing any load.
        assert s["total_reps"] == 30, s
