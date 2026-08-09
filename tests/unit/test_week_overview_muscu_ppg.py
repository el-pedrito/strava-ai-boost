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
