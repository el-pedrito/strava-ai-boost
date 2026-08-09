"""Regression test: a Campus PPG (a WeightTraining matched to the plan) must not be
counted as the athlete's own muscu. The coach stated "3 muscu + 1 PPG = 8" for a
week that was 2 muscu + 1 PPG = 7 (the renfo WeightTraining counted once as muscu
AND once as PPG).
"""
import os
import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing import coach_generator
from processing.coach_generator import build_week_overview


def _make_items():
    items = []
    for d in ['2026-08-03', '2026-08-05', '2026-08-07', '2026-08-09']:
        items.append({"activity_data_json": json.dumps(
            {"type": "Run", "start_date_local": d + "T10:00:00", "distance": 10000})})
    for d in ['2026-08-04', '2026-08-08', '2026-08-08']:  # 2 own muscu + 1 renfo PPG
        items.append({"activity_data_json": json.dumps(
            {"type": "WeightTraining", "start_date_local": d + "T10:00:00"})})
    return items


class TestWeekOverviewMuscuPpgSplit:
    @patch.object(coach_generator, 'dynamodb')
    def test_ppg_not_counted_as_muscu(self, mock_ddb):
        table = MagicMock()
        table.query.return_value = {"Items": _make_items()}
        mock_ddb.Table.return_value = table

        campus = [{"sport": "ppg", "matched_activity_id": "19655889544", "completed_at": "2026-08-08T14:00:00"}]
        activity_data = {"start_date_local": "2026-08-09T07:18:00"}

        ov = build_week_overview("138362426", activity_data, campus, None)
        dw = ov["done_this_week"]
        assert dw["runs"] == 4, dw
        assert dw["strength"] == 3, dw          # total strength sessions
        assert dw["ppg"] == 1, dw               # Campus PPG done
        assert dw["muscu"] == 2, dw             # own program only (not the PPG)
        assert dw["total"] == 7, dw             # 4 runs + 3 strength, PPG not double counted

    @patch.object(coach_generator, 'dynamodb')
    def test_own_strength_program_excludes_ppg(self, mock_ddb):
        table = MagicMock()
        table.query.return_value = {"Items": _make_items()}
        mock_ddb.Table.return_value = table
        campus = [{"sport": "ppg", "matched_activity_id": "19655889544", "completed_at": "2026-08-08T14:00:00"}]
        strength_program = {"sessions": [{"name": "Upper A", "frequency": "1x"},
                                         {"name": "Upper B", "frequency": "1x"}]}
        ov = build_week_overview("138362426", {"start_date_local": "2026-08-09T07:18:00"},
                                 campus, strength_program)
        osp = ov["own_strength_program"]
        assert osp["done_this_week"] == 2, osp  # 2 muscu, not 3 (PPG excluded)
        assert osp["remaining"] == 0, osp       # planned 2 - done 2

    @patch.object(coach_generator, 'dynamodb')
    def test_recap_line_built_from_computed_figures(self, mock_ddb):
        table = MagicMock()
        table.query.return_value = {"Items": _make_items()}
        mock_ddb.Table.return_value = table
        campus = [{"sport": "ppg", "matched_activity_id": "19655889544", "completed_at": "2026-08-08T14:00:00"}]
        ov = build_week_overview("138362426", {"start_date_local": "2026-08-09T07:18:00"}, campus, None)
        line = ov.get("recap_line", "")
        assert line == ("Cette semaine : 4 courses (40 km), 2 muscu, 1 PPG, "
                        "soit 7 séances au total."), line


class TestInjectRecapLine:
    """The weekly recap must ALWAYS reach the published block: injected in code,
    not left to the model (which chose 'say nothing' over 'copy verbatim')."""

    WO = {"recap_line": "Cette semaine : 4 courses (30,5 km), 2 muscu, 1 PPG, soit 7 séances au total."}

    def test_prepended_when_absent(self):
        from processing.coach_generator import _inject_recap_line
        fb = {"strava_block": "Ton cardio encaisse bien la charge."}
        _inject_recap_line(fb, self.WO)
        assert fb["strava_block"].startswith("Cette semaine : 4 courses"), fb
        assert fb["strava_block"].endswith("la charge."), fb

    def test_no_duplicate_when_model_copied_it(self):
        from processing.coach_generator import _inject_recap_line
        fb = {"strava_block": self.WO["recap_line"] + " Belle régularité."}
        _inject_recap_line(fb, self.WO)
        assert fb["strava_block"].count("Cette semaine :") == 1, fb

    def test_noop_without_recap_or_block(self):
        from processing.coach_generator import _inject_recap_line
        fb = {"strava_block": "Texte."}
        _inject_recap_line(fb, {})
        assert fb["strava_block"] == "Texte."
        fb2 = {}
        _inject_recap_line(fb2, self.WO)
        assert "strava_block" not in fb2
