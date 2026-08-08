"""Unit tests for the authoritative weekly figures sent to the coach.

The coach wrote "35km sur la semaine vs 26,5 la semaine dernière" for an activity
on the Monday that *opened* ISO week 2026-W32. The real figures were 6.4km for
W32 and 26.5km for W31. It had summed a rolling 7-day window (28/07 to 03/08,
33km), labelled it "la semaine", compared it against a real ISO week, and derived
a bogus "+32%, above the recommended 10%" ramp-rate alert from that comparison.

`weekly_breakdown` already carried the correct per-ISO-week figures, so the fix is
to remove the competing ambiguous sources and to hand the coach numbers it must
not recompute:

* `weekly_km` was keyed by a bare week number (31, 32), a second and ambiguous
  notion of "week" that violates the ISO-string contract.
* the count of remaining plan sessions was left to the model, which answered 2
  when 4 were still to do.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

os.environ.setdefault('AWS_REGION', 'eu-west-1')
os.environ.setdefault('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')
os.environ.setdefault('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
os.environ.setdefault('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
sys.modules.setdefault('agents', MagicMock())
sys.modules.setdefault('agents.coach_agent', MagicMock())

from shared.coach_context import format_weekly_breakdown  # noqa: E402
from processing import coach_generator as cg  # noqa: E402


class TestWeeklyBreakdownIsIsoWeekNotRolling:
    """The helper must bucket by ISO week, so Monday opens a fresh week."""

    def test_monday_activity_opens_a_new_week(self):
        activities = [
            # W32 opens on Monday 03/08 with a single 6.4km run.
            {'activity_type': 'Run', 'distance': 6420, 'start_date': '2026-08-03T17:21:26Z'},
            # W31: 4 runs totalling 26.5km, plus 2 strength sessions.
            {'activity_type': 'Run', 'distance': 8579, 'start_date': '2026-08-02T08:43:20Z'},
            {'activity_type': 'Run', 'distance': 6796, 'start_date': '2026-08-01T17:39:17Z'},
            {'activity_type': 'Run', 'distance': 5700, 'start_date': '2026-07-30T19:15:42Z'},
            {'activity_type': 'Run', 'distance': 5400, 'start_date': '2026-07-28T18:59:09Z'},
            {'activity_type': 'WeightTraining', 'distance': 0, 'start_date': '2026-08-01T13:59:14Z'},
            {'activity_type': 'WeightTraining', 'distance': 0, 'start_date': '2026-07-29T04:56:47Z'},
        ]
        out = format_weekly_breakdown(activities)

        assert out, "breakdown must not be empty"
        lines = [line for line in out.splitlines() if line.strip()]
        # The rolling 28/07-03/08 total is 33km; it must never appear as a week.
        assert '33' not in out and '35' not in out, (
            f"a rolling-window total leaked into the weekly breakdown:\n{out}"
        )
        assert any('6.4km' in line for line in lines), (
            f"the ISO week that just opened must report its real 6.4km:\n{out}"
        )

    def test_full_timestamps_are_accepted(self):
        """coach_generator passes full ISO timestamps, not YYYY-MM-DD."""
        activities = [
            {'activity_type': 'Run', 'distance': 10000, 'start_date': '2026-08-03T17:21:26Z'},
        ]
        assert '10.0km' in format_weekly_breakdown(activities)

    def test_empty_input_reports_no_volume(self):
        out = format_weekly_breakdown([])
        assert 'km' not in out, (
            f"no activity must not produce a distance figure: {out!r}"
        )


class TestConsolidatedWeeklyFields:
    """weekly_km is gone; the surviving week fields carry ISO labels only.

    The consolidation removes the competing week notions: the activity's own week
    is owned by week_overview, and the past weeks by weekly_breakdown, with no
    overlap. weekly_km (a second, redundant per-week dict) and the ambiguous
    avg_weekly_km name are removed.
    """

    @staticmethod
    def _item(aid, start, dist, atype='Run'):
        import json as _json
        return {
            'activity_id': aid,
            'created_at': start,
            'activity_data_json': _json.dumps({
                'type': atype, 'distance': dist, 'moving_time': 2402,
                'average_speed': 2.7, 'start_date': start,
            }),
        }

    def _summary(self, items, activity_week=None):
        table = MagicMock()
        table.query.return_value = {'Items': items}
        table.get_item.return_value = {'Item': {}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            return cg.build_historical_summary('u1', 'not-in-list', activity_week)

    def test_weekly_km_dict_is_removed(self):
        summary = self._summary([
            self._item('a1', '2026-08-03T17:21:26Z', 6420),
            self._item('a2', '2026-08-02T08:43:20Z', 8579),
        ])
        assert 'weekly_km' not in summary, (
            "weekly_km reintroduced a per-week dict competing with "
            "weekly_breakdown for the same question"
        )

    def test_average_is_renamed_to_flag_it_as_a_baseline(self):
        summary = self._summary([self._item('a1', '2026-08-03T17:21:26Z', 6420)])
        assert 'avg_weekly_km' not in summary, (
            "the bare name read like a weekly total; it must be renamed"
        )
        assert 'avg_weekly_km_last_4_weeks' in summary

    def test_volume_ramp_labels_are_iso_weeks(self):
        summary = self._summary([
            self._item('a1', '2026-08-03T17:21:26Z', 6420),   # W32
            self._item('a2', '2026-07-30T19:15:42Z', 5700),   # W31
        ])
        ramp = summary.get('volume_ramp')
        assert ramp, f"expected a ramp across two weeks, got {summary.get('error')}"
        assert '-W' in ramp['from_week'] and '-W' in ramp['to_week'], (
            "ramp weeks must be ISO labels 'YYYY-Www', never bare numbers"
        )
        assert ramp['from_week'] == '2026-W31'
        assert ramp['to_week'] == '2026-W32'

    def test_activity_week_is_excluded_from_past_fields(self):
        """week_overview owns the activity's week, so it must not double up here."""
        summary = self._summary(
            [
                self._item('a1', '2026-08-03T17:21:26Z', 6420),   # W32 (activity week)
                self._item('a2', '2026-07-30T19:15:42Z', 5700),   # W31
            ],
            activity_week='2026-W32',
        )
        breakdown = summary['weekly_breakdown']
        assert '6.4km' not in breakdown, (
            "the activity's own week must not appear in the past-week breakdown"
        )
        assert '5.7km' in breakdown
        # Only W31 remains a complete past week, so no ramp can be computed.
        assert 'volume_ramp' not in summary


class TestRemainingSessionsAreCounted:
    """Remaining plan sessions come from week_overview.campus_remaining alone.

    The separate campus_week_remaining field was strictly redundant with it, and
    two fields answering "how many sessions are left" is the multiplicity that
    let the coach quote a wrong number. It is removed.
    """

    def _run_handler(self, plan_sessions):
        captured = {}

        def _fake_invoke(activity_data, user_config, historical_summary):
            captured['hs'] = historical_summary
            return {'strava_block': 'ok'}

        coach_table = MagicMock()
        coach_table.get_item.return_value = {'Item': {}}
        coach_table.query.return_value = {'Items': []}
        coach_table.scan.side_effect = [{'Items': plan_sessions}, {'Items': []}]
        coach_dynamo = MagicMock()
        coach_dynamo.Table.return_value = coach_table

        match_table = MagicMock()
        match_table.query.return_value = {'Items': []}
        match_table.scan.return_value = {'Items': []}
        match_dynamo = MagicMock()
        match_dynamo.Table.return_value = match_table

        with patch.object(cg, 'dynamodb', coach_dynamo), \
                patch('processing.modules_processing.dynamodb', match_dynamo), \
                patch.object(cg, 'COACH_AGENT_ARN', 'arn:aws:bedrock-agentcore:eu-west-1:1:runtime/c'), \
                patch.object(cg, 'retrieve_activity_data',
                             return_value={'start_date_local': '2026-08-03T17:21:26Z',
                                           'moving_time': 2402, 'type': 'Run', '_laps': []}), \
                patch.object(cg, 'build_historical_summary', return_value={}), \
                patch.object(cg, 'extract_and_store_prs'), \
                patch.object(cg, 'store_coach_feedback'), \
                patch.object(cg, 'write_coaching_observation'), \
                patch.object(cg, '_invoke_coach_agent', side_effect=_fake_invoke):
            response = cg.handler(
                {'activity_id': '19586436692', 'user_id': 'u1', 'user_config': {}}, None
            )
        assert response['statusCode'] == 200
        return captured['hs']

    @staticmethod
    def _session(title, provider_status='todo', **extra):
        return {
            'title': title,
            'week_date_iso': '2026-W32',
            'status': 'todo',
            'provider_status': provider_status,
            'is_current_week': True,
            'is_future': False,
            'intervals': [],
            'sport': 'road',
            'expected_duration_min': 40,
            **extra,
        }

    def test_no_separate_remaining_field(self):
        hs = self._run_handler([self._session('Endurance de Force')])
        assert 'campus_week_remaining' not in hs, (
            "the redundant campus_week_remaining field must be gone"
        )
        assert 'campus_remaining' in hs['week_overview']

    def test_counts_only_sessions_not_done_or_skipped(self):
        """The real W32 case: one EF done at the provider, four still to do."""
        plan = [
            self._session('Renforcement'),
            self._session('Endurance Fondamentale', provider_status='done'),
            self._session('Endurance de Force'),
            self._session('Endurance Fondamentale'),
            self._session('Sortie Longue & Active'),
        ]
        hs = self._run_handler(plan)
        remaining = hs['week_overview']['campus_remaining']

        assert remaining['count'] == 4, (
            "the coach said 2 remaining when 4 were still to do"
        )
        assert hs['week_overview']['week'] == '2026-W32'
        assert 'Endurance Fondamentale' in remaining['titles']
        assert len(remaining['titles']) == 4

    def test_skipped_sessions_are_not_remaining(self):
        plan = [
            self._session('Renforcement', provider_status='skip'),
            self._session('Endurance de Force'),
        ]
        remaining = self._run_handler(plan)['week_overview']['campus_remaining']
        assert remaining['count'] == 1
        assert remaining['titles'] == ['Endurance de Force']

    def test_all_done_yields_zero(self):
        plan = [self._session('Renforcement', provider_status='done')]
        remaining = self._run_handler(plan)['week_overview']['campus_remaining']
        assert remaining['count'] == 0
        assert remaining['titles'] == []


class TestActivityDetailIsGroupedByWeek:
    """A flat list of dated distances is what let the coach invent a total.

    The coach summed a rolling 7-day window across a week boundary and called it
    "cette semaine": 6.4km (Mon 03/08, W32) plus 8.6km (Sun 02/08, W31) reported
    as "2 courses (15km) cette semaine" when W32 held a single 6.4km run. Prompt
    rules did not hold, so the ISO week became the structure of the data.
    """

    def _summary(self, items):
        table = MagicMock()
        table.query.return_value = {'Items': items}
        table.get_item.return_value = {'Item': {}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            return cg.build_historical_summary('u1', 'not-in-list')

    @staticmethod
    def _item(aid, start, atype, dist):
        import json as _json
        return {
            'activity_id': aid,
            'created_at': start,
            'activity_data_json': _json.dumps({
                'type': atype, 'distance': dist, 'moving_time': 2400,
                'average_speed': 2.7, 'start_date': start,
            }),
        }

    def test_activities_are_bucketed_by_iso_week(self):
        summary = self._summary([
            self._item('a1', '2026-08-03T17:21:26Z', 'Run', 6420),   # Mon, W32
            self._item('a2', '2026-08-02T08:43:20Z', 'Run', 8579),   # Sun, W31
        ])
        buckets = summary['recent_activities_by_week']

        assert set(buckets) == {'2026-W31', '2026-W32'}, (
            f"the week boundary must split these two runs: {list(buckets)}"
        )
        assert len(buckets['2026-W32']) == 1
        assert len(buckets['2026-W31']) == 1

    def test_flat_dated_list_is_no_longer_exposed(self):
        """The old shape is what made the bogus 15km total assemblable."""
        summary = self._summary([
            self._item('a1', '2026-08-03T17:21:26Z', 'Run', 6420),
        ])
        assert 'recent_activities' not in summary, (
            "a flat list of dated distances must not be sent to the coach"
        )

    def test_each_entry_carries_its_own_iso_week(self):
        summary = self._summary([
            self._item('a1', '2026-08-03T17:21:26Z', 'Run', 6420),
        ])
        entry = summary['recent_activities_by_week']['2026-W32'][0]
        assert entry['iso_week'] == '2026-W32'

    def test_session_detail_is_preserved(self):
        """Grouping must not cost the detail used to discuss a given session."""
        summary = self._summary([
            self._item('a1', '2026-08-04T10:28:28Z', 'WeightTraining', 0),
        ])
        entry = summary['recent_activities_by_week']['2026-W32'][0]
        for field in ('date', 'type', 'name', 'distance_km', 'duration_min'):
            assert field in entry, f"{field} was dropped from the detail"

    def test_most_recent_week_reads_first(self):
        summary = self._summary([
            self._item('a1', '2026-07-28T18:59:09Z', 'Run', 5400),   # W31
            self._item('a2', '2026-08-03T17:21:26Z', 'Run', 6420),   # W32
        ])
        assert list(summary['recent_activities_by_week'])[0] == '2026-W32'


class TestMergedWeekOverview:
    """One code-computed view: Campus plan + own program, current activity in.

    The coach reported "2 séances muscu" on a week holding one, because
    build_historical_summary skips the activity being processed: weekly_breakdown
    said "1 course" with no strength session, and the coach had to add the current
    one itself. It also only ever saw the Campus plan, while the real week is
    Campus running sessions plus the athlete's own Upper A / Upper B / Rappel.
    """

    PROGRAM = {'sessions': [
        {'id': 'upper_a', 'name': 'Upper A', 'frequency': '1x/semaine'},
        {'id': 'upper_b', 'name': 'Upper B', 'frequency': '1x/semaine'},
        {'id': 'rappel', 'name': 'Rappel', 'frequency': '1x/semaine'},
    ]}

    @staticmethod
    def _item(aid, start, atype, dist=0):
        import json as _json
        return {
            'activity_id': aid,
            'activity_data_json': _json.dumps({
                'type': atype, 'distance': dist, 'start_date': start,
            }),
        }

    def _overview(self, items, campus, program=None, activity_start='2026-08-04T10:28:28Z'):
        table = MagicMock()
        table.query.return_value = {'Items': items}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            return cg.build_week_overview(
                'u1', {'start_date': activity_start}, campus, program
            )

    def _campus(self):
        def s(title, sport='road', provider='todo'):
            return {'title': title, 'sport': sport, 'week_date_iso': '2026-W32',
                    'status': 'todo', 'provider_status': provider}
        return [
            s('Renforcement', sport='ppg'),
            s('Endurance Fondamentale', provider='done'),
            s('Endurance de Force'),
            s('Endurance Fondamentale'),
            s('Sortie Longue & Active'),
        ]

    def test_current_activity_is_counted(self):
        """The muscu being processed must already appear in done_this_week."""
        items = [
            self._item('a1', '2026-08-03T17:21:26Z', 'Run', 6420),
            self._item('a2', '2026-08-04T10:28:28Z', 'WeightTraining'),
        ]
        done = self._overview(items, self._campus())['done_this_week']
        assert done['runs'] == 1
        assert done['run_km'] == 6.4
        assert done['strength'] == 1, "the current strength session must be counted once"
        assert done['total'] == 2
        assert done['includes_current_activity'] is True

    def test_previous_week_activities_are_excluded(self):
        """02/08 is a Sunday in W31 and must not leak into W32."""
        items = [
            self._item('a1', '2026-08-03T17:21:26Z', 'Run', 6420),
            self._item('a2', '2026-08-02T08:43:20Z', 'Run', 8579),
        ]
        done = self._overview(items, self._campus())['done_this_week']
        assert done['runs'] == 1 and done['run_km'] == 6.4

    def test_uses_the_activity_week_not_today(self):
        """A Sunday session processed on Monday belongs to the Sunday's week."""
        items = [self._item('a2', '2026-08-02T08:43:20Z', 'Run', 8579)]
        ov = self._overview(items, [], activity_start='2026-08-02T08:43:20Z')
        assert ov['week'] == '2026-W31'
        assert ov['done_this_week']['runs'] == 1

    def test_campus_remaining_separates_running_from_ppg(self):
        ov = self._overview([], self._campus())
        rem = ov['campus_remaining']
        assert rem['count'] == 4
        assert rem['running_count'] == 3, "the ppg session is not a running session"
        assert 'Renforcement' in rem['titles']

    def test_own_program_is_merged_not_confused_with_campus(self):
        items = [self._item('a2', '2026-08-04T10:28:28Z', 'WeightTraining')]
        ov = self._overview(items, self._campus(), self.PROGRAM)
        own = ov['own_strength_program']
        assert own['planned_per_week'] == 3
        assert own['done_this_week'] == 1
        assert own['remaining'] == 2
        # The Campus PPG stays a separate, still-to-do session.
        assert 'Renforcement' in ov['campus_remaining']['titles']

    def test_absent_program_yields_no_key(self):
        ov = self._overview([], self._campus(), None)
        assert 'own_strength_program' not in ov

    def test_query_failure_is_flagged_not_guessed(self):
        table = MagicMock()
        table.query.side_effect = RuntimeError('DynamoDB down')
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            ov = cg.build_week_overview(
                'u1', {'start_date': '2026-08-04T10:28:28Z'}, self._campus(), None
            )
        assert ov['counts_incomplete'] is True
        assert ov['done_this_week']['total'] == 0


class TestWeekOverviewCarriesAHumanLabel:
    """week_overview was the only weekly field without a readable label.

    `weekly_breakdown` carries friendly labels ("Semaine derniere", "Il y a 2
    semaines"). Once the current week was removed from it, its first line became
    "Semaine derniere" while a surviving prompt rule still said 'Cette semaine =
    la première ligne de weekly_breakdown'. The coach followed that rule and
    reported "1 course (6,4km) + 2 muscu": the runs from week_overview, the
    strength count from the PREVIOUS week's line. Labelling both sources removes
    the asymmetry that made the labelled one look authoritative.
    """

    def _overview(self, activity_start):
        table = MagicMock()
        table.query.return_value = {'Items': []}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            return cg.build_week_overview(
                'u1', {'start_date': activity_start}, [], None
            )

    def test_label_names_the_current_week_with_its_dates(self):
        ov = self._overview('2026-08-04T10:28:28Z')
        assert ov['week'] == '2026-W32'
        assert ov['label'] == 'Cette semaine (03/08-09/08)', ov['label']

    def test_label_follows_the_activity_week_not_today(self):
        """A Sunday session processed later keeps its own week's dates."""
        ov = self._overview('2026-08-02T08:43:20Z')
        assert ov['week'] == '2026-W31'
        assert ov['label'] == 'Cette semaine (27/07-02/08)', ov['label']

    def test_unparseable_date_still_yields_a_label(self):
        ov = self._overview('not-a-date')
        assert ov['label'] == 'Cette semaine'

    def test_monday_helper_handles_iso_year_boundary(self):
        from datetime import date as _date
        assert cg._monday_of_iso_week('2026-W01') == _date.fromisocalendar(2026, 1, 1)
        assert cg._monday_of_iso_week('') is None
        assert cg._monday_of_iso_week('2026') is None
        assert cg._monday_of_iso_week('bad-Wxx') is None


class TestWeeklyFieldsDoNotOverlap:
    """The two weekly fields must never describe the same ISO week."""

    def test_breakdown_excludes_the_activity_week(self):
        import json as _json
        items = [
            {'activity_id': 'a1', 'created_at': '2026-08-03T17:21:26Z',
             'activity_data_json': _json.dumps({
                 'type': 'Run', 'distance': 6420, 'moving_time': 2402,
                 'start_date': '2026-08-03T17:21:26Z'})},
            {'activity_id': 'a2', 'created_at': '2026-08-02T08:43:20Z',
             'activity_data_json': _json.dumps({
                 'type': 'Run', 'distance': 8579, 'moving_time': 3172,
                 'start_date': '2026-08-02T08:43:20Z'})},
        ]
        table = MagicMock()
        table.query.return_value = {'Items': items}
        table.get_item.return_value = {'Item': {}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            # The handler passes the activity's ISO week as third argument; that
            # is what excludes the current week from the breakdown.
            summary = cg.build_historical_summary('u1', 'not-in-list', '2026-W32')

        breakdown = summary.get('weekly_breakdown') or ''
        assert 'Cette semaine' not in breakdown, (
            "weekly_breakdown must not describe the current week; the coach reads "
            f"its first line as 'this week':\n{breakdown}"
        )
        # 6.4km is the current week and belongs to week_overview only.
        assert '6.4km' not in breakdown, breakdown
        # The previous week must still be there.
        assert '8.6km' in breakdown, breakdown

    def test_omitting_the_week_argument_excludes_nothing(self):
        """Documents the permissive default: a caller that forgets the third
        argument gets the overlap back, silently. Only the handler path is safe."""
        import json as _json
        items = [{'activity_id': 'a1', 'created_at': '2026-08-03T17:21:26Z',
                  'activity_data_json': _json.dumps({
                      'type': 'Run', 'distance': 6420, 'moving_time': 2402,
                      'start_date': '2026-08-03T17:21:26Z'})}]
        table = MagicMock()
        table.query.return_value = {'Items': items}
        table.get_item.return_value = {'Item': {}}
        dynamo = MagicMock()
        dynamo.Table.return_value = table
        with patch.object(cg, 'dynamodb', dynamo):
            summary = cg.build_historical_summary('u1', 'not-in-list')
        assert '6.4km' in (summary.get('weekly_breakdown') or '')
