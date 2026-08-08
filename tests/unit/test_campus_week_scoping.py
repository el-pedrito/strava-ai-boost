"""Unit tests for Campus Coach candidate week scoping and planned duration.

Covers the review findings that followed the week-disambiguation fix:

* ``_get_recent_campus_sessions`` used to accept ``activity_date`` and ignore it,
  always scanning on the ``is_current_week`` flag. Any activity not processed
  inside its own week (a Sunday run handled on Monday, a DLQ replay) was scored
  against the wrong week's plan, and the scorer discriminates weeks poorly.
* ``_score_session_match`` derived the planned duration from the interval list
  instead of using the provider's authoritative ``expected_duration_min``.
* ``repeat`` expansion had no upper bound.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

os.environ.setdefault('AWS_REGION', 'eu-west-1')
os.environ.setdefault('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')

from shared.iso_week import iso_week_label  # noqa: E402
from processing import modules_processing as mp  # noqa: E402


def _mock_table(query_results, scan_results=None):
    """Mock a DynamoDB table.

    The week-scoped read is a Query on the ``session_date`` partition key; only
    the current-week fallback is a Scan.
    """
    table = MagicMock()
    table.query.side_effect = [{'Items': items} for items in query_results]
    table.scan.side_effect = [
        {'Items': items} for items in (scan_results or [])
    ]
    dynamo = MagicMock()
    dynamo.Table.return_value = table
    return table, dynamo


class TestIsoWeekLabel:
    def test_zero_padded_iso_string(self):
        assert iso_week_label('2026-01-01T00:00:00') == '2026-W01'

    def test_handles_trailing_z(self):
        assert iso_week_label('2026-08-03T17:21:26Z') == '2026-W32'

    def test_unknown_week_is_empty_not_current(self):
        assert iso_week_label('') == ''
        assert iso_week_label(None) == ''
        assert iso_week_label('not-a-date') == ''


class TestCandidateWeekScoping:
    def test_queries_the_activity_week_partition(self):
        session = {'title': 'Seuil 30', 'week_date_iso': '2026-W31', 'status': 'todo'}
        table, dynamo = _mock_table([[session]])

        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions('2026-08-01T17:39:17Z')

        table.query.assert_called_once_with(
            KeyConditionExpression='session_date = :sd',
            ExpressionAttributeValues={':sd': 'week-2026-W31'},
        )
        table.scan.assert_not_called()
        assert len(sessions) == 1

    def test_sunday_activity_processed_on_monday_keeps_its_own_week(self):
        """2026-08-02 is a Sunday in W31; the Monday after starts W32."""
        table, dynamo = _mock_table([[]], [[]])

        with patch('processing.modules_processing.dynamodb', dynamo):
            mp._get_recent_campus_sessions('2026-08-02T08:43:20Z')

        assert table.query.call_args_list[0].kwargs['ExpressionAttributeValues'] == {
            ':sd': 'week-2026-W31'
        }

    def test_falls_back_to_current_week_when_activity_week_unsynced(self):
        fallback = {'title': 'Endurance Fondamentale', 'status': 'todo'}
        table, dynamo = _mock_table([[]], [[fallback]])

        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions('2019-01-07T10:00:00Z')

        table.scan.assert_called_once_with(
            FilterExpression='is_current_week = :cw',
            ExpressionAttributeValues={':cw': True},
        )
        assert len(sessions) == 1

    def test_falls_back_when_date_unparseable(self):
        fallback = {'title': 'Sortie Longue', 'status': 'todo'}
        table, dynamo = _mock_table([], [[fallback]])

        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions('not-a-date')

        table.query.assert_not_called()
        table.scan.assert_called_once_with(
            FilterExpression='is_current_week = :cw',
            ExpressionAttributeValues={':cw': True},
        )
        assert len(sessions) == 1

    def test_done_sessions_excluded_from_scoped_week(self):
        """provider_status='done' with a stale legacy status must be dropped."""
        done = {
            'title': 'Endurance Fondamentale',
            'week_date_iso': '2026-W32',
            'status': 'todo',
            'provider_status': 'done',
        }
        todo = {
            'title': 'Endurance de Force',
            'week_date_iso': '2026-W32',
            'status': 'todo',
            'provider_status': 'todo',
        }
        table, dynamo = _mock_table([[done, todo]])

        with patch('processing.modules_processing.dynamodb', dynamo):
            sessions = mp._get_recent_campus_sessions('2026-08-03T17:21:26Z')

        assert [s['title'] for s in sessions] == ['Endurance de Force']


class TestPlannedDuration:
    LEGACY_SEUIL_30 = [
        {'type': 'warm-up', 'duration': '15 min', 'pace': 'EF'},
        {'type': 'work', 'repeat': 9, 'duration': '1 min', 'pace': 'Seuil'},
        {'type': 'recovery', 'duration': '1 min', 'pace': 'Lent'},
        {'type': 'cool-down', 'duration': '5 min', 'pace': 'EF'},
    ]

    def test_prefers_provider_value_over_lossy_derivation(self):
        """Legacy rows derive 30min for a session the provider reports as 38min."""
        derived = mp._extract_session_duration(self.LEGACY_SEUIL_30)
        assert round(derived) == 30

        session = {
            'intervals': self.LEGACY_SEUIL_30,
            'expected_duration_min': 38,
        }
        assert mp._session_target_duration_min(session) == 38.0

    def test_derives_when_provider_value_absent(self):
        session = {'intervals': self.LEGACY_SEUIL_30}
        assert round(mp._session_target_duration_min(session)) == 30

    def test_derives_when_provider_value_unusable(self):
        for bad in (None, 0, '', 'n/a'):
            session = {'intervals': self.LEGACY_SEUIL_30, 'expected_duration_min': bad}
            assert round(mp._session_target_duration_min(session)) == 30

    def test_strength_session_without_durations_uses_provider_value(self):
        """PPG intervals carry repetitions, not durations, so derivation is ~0."""
        ppg = [{'type': 'work', 'duration': '', 'pace': ''} for _ in range(8)]
        assert mp._extract_session_duration(ppg) == 0
        session = {'intervals': ppg, 'expected_duration_min': 30}
        assert mp._session_target_duration_min(session) == 30.0

    def test_accepts_string_provider_value(self):
        session = {'intervals': [], 'expected_duration_min': '48'}
        assert mp._session_target_duration_min(session) == 48.0


class TestRepeatCap:
    def test_absurd_repeat_is_clamped(self):
        assert mp._as_int(10 ** 9) == mp.MAX_INTERVAL_REPEAT

    def test_realistic_repeat_untouched(self):
        assert mp._as_int(9) == 9
        assert mp._as_int('5') == 5

    def test_non_positive_and_invalid_fall_back_to_default(self):
        assert mp._as_int(0) == 1
        assert mp._as_int(-3) == 1
        assert mp._as_int(None) == 1
        assert mp._as_int('abc') == 1

    def test_expansion_is_bounded(self):
        block = {
            'type': 'block',
            'repeat': 10 ** 6,
            'exercises': [{'type': 'work', 'duration': '1 min', 'pace': 'Seuil'}],
        }
        occurrences = mp._normalize_intervals([block])
        assert len(occurrences) == mp.MAX_INTERVAL_REPEAT
