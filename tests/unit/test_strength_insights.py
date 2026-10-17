"""Unit tests for shared.strength_insights: weeks, counting, e1RM, records,
push/pull, notation mix."""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared.strength_insights import (  # noqa: E402
    build_strength_insights,
    exercise_flags,
    per_day_e1rm,
    _epley_1rm,
    _set_count,
    _window_weeks,
)

TODAY = date(2026, 10, 17)  # Paris week 2026-W42, a Saturday


def _session(d, exercise, detail, source='athlete_text', description='', per_ex=None):
    entry = {
        'date': d,
        'activity_id': f'a-{d}',
        'sets_source': source,
        'description': description,
        'parsed_sets': [{'exercise': exercise, 'sets_detail': detail}],
    }
    if per_ex is not None:
        entry['per_exercise'] = per_ex
    return entry


class TestWeeks:
    def test_eight_consecutive_weeks_zero_filled(self):
        ins = build_strength_insights([], today=TODAY)
        assert len(ins['weeks']) == 8
        labels = [w['week'] for w in ins['weeks']]
        assert labels == [
            '2026-W35', '2026-W36', '2026-W37', '2026-W38',
            '2026-W39', '2026-W40', '2026-W41', '2026-W42',
        ]

    def test_current_week_is_partial(self):
        ins = build_strength_insights([], today=TODAY)
        assert ins['weeks'][-1]['partial'] is True
        assert all(not w['partial'] for w in ins['weeks'][:-1])

    def test_all_ten_groups_present_zero_filled(self):
        ins = build_strength_insights([], today=TODAY)
        groups = ins['weeks'][0]['groups']
        assert set(groups) == {
            'pectoraux', 'dos', 'epaules', 'biceps', 'triceps',
            'quadriceps', 'ischios', 'fessiers', 'mollets', 'abdos',
        }
        for seg in groups.values():
            assert seg == {'logged': 0.0, 'campus_plan': 0.0}

    def test_current_paris_week_matches_now(self):
        """The default window ends at the Europe/Paris current week."""
        ins = build_strength_insights([])
        now_paris = datetime.now(ZoneInfo('Europe/Paris')).date()
        iso = now_paris.isocalendar()
        assert ins['weeks'][-1]['week'] == f"{iso[0]}-W{iso[1]:02d}"

    def test_window_helper(self):
        assert _window_weeks(TODAY, 3) == ['2026-W40', '2026-W41', '2026-W42']


class TestSetCounting:
    def test_detail_rows_counted(self):
        assert _set_count({'sets_detail': [
            {'reps': 10}, {'reps': 8}, {'reps': 6},
        ]}) == 3

    def test_hold_with_duration_counts(self):
        assert _set_count({'sets_detail': [{'duration_s': 30}]}) == 1

    def test_zero_reps_row_not_counted(self):
        assert _set_count({'sets_detail': [{'reps': 0}, {'reps': 8}]}) == 1

    def test_negative_reps_not_counted(self):
        assert _set_count({'sets_detail': [{'reps': -5}]}) == 0

    def test_non_integer_reps_still_counts_if_positive(self):
        # Counting rule is reps > 0, not integer; e1RM has the integer rule.
        assert _set_count({'sets_detail': [{'reps': 2.5}]}) == 1

    def test_nan_reps_not_counted(self):
        assert _set_count({'sets_detail': [{'reps': float('nan')}]}) == 0

    def test_inf_duration_not_counted(self):
        assert _set_count({'sets_detail': [{'duration_s': float('inf')}]}) == 0

    def test_flat_fallback_only_when_reps_positive(self):
        assert _set_count({'sets': 4, 'reps': 10}) == 4
        assert _set_count({'sets': 4, 'reps': 0}) == 0
        assert _set_count({'sets': 4}) == 0

    def test_flat_fallback_with_duration(self):
        assert _set_count({'sets': 3, 'duration_s': 30}) == 3

    def test_empty_detail_falls_back_to_flat(self):
        assert _set_count({'sets_detail': [], 'sets': 2, 'reps': 10}) == 2

    def test_detail_present_but_uncountable_no_flat_fallback(self):
        # Detail present with only reps-less, duration-less rows: no flat fallback.
        assert _set_count({'sets_detail': [{'reps': None}], 'sets': 4, 'reps': 10}) == 0


class TestWeeklyGroups:
    def test_primary_and_secondary_credit(self):
        # One DC session of 3 counted sets in the current week.
        entry = _session('2026-10-13', 'Développé couché',
                         [{'reps': 5, 'weight_kg': 100}] * 3)
        ins = build_strength_insights([entry], today=TODAY)
        wk = ins['weeks'][-1]['groups']
        assert wk['pectoraux']['logged'] == 3.0      # 3 sets x 1.0
        assert wk['triceps']['logged'] == 1.5        # 3 sets x 0.5
        assert wk['epaules']['logged'] == 1.5

    def test_campus_plan_lands_in_campus_segment(self):
        entry = _session('2026-10-13', 'Squat',
                         [{'reps': 10, 'weight_kg': 60}] * 4, source='campus_plan')
        ins = build_strength_insights([entry], today=TODAY)
        wk = ins['weeks'][-1]['groups']['quadriceps']
        assert wk['campus_plan'] == 4.0
        assert wk['logged'] == 0.0

    def test_explosivite_segment(self):
        entry = _session('2026-10-13', 'Bond sur place', [{'reps': 5}] * 2)
        ins = build_strength_insights([entry], today=TODAY)
        assert ins['weeks'][-1]['explosivite']['logged'] == 2.0

    def test_unmapped_listed_with_reason(self):
        entry = _session('2026-10-13', 'Flexion tibiale', [{'reps': 10}] * 3)
        ins = build_strength_insights([entry], today=TODAY)
        assert {'exercise': 'Flexion tibiale', 'reason': 'unknown'} in ins['unmapped_exercises']
        assert ins['weeks'][-1]['autre']['logged'] == 3.0

    def test_flexion_de_genou_credits_hamstrings(self):
        entry = _session('2026-10-13', 'Flexion de genou', [{'reps': 10}] * 3)
        ins = build_strength_insights([entry], today=TODAY)
        groups = ins['weeks'][-1]['groups']
        assert groups['ischios']['logged'] == 3.0
        assert groups['fessiers']['logged'] == 1.5
        assert groups['dos']['logged'] == 1.5
        assert ins['unmapped_exercises'] == []

    def test_decimal_and_string_inputs(self):
        entry = _session('2026-10-13', 'Développé couché',
                         [{'reps': Decimal('5'), 'weight_kg': '100'}] * 2)
        ins = build_strength_insights([entry], today=TODAY)
        assert ins['weeks'][-1]['groups']['pectoraux']['logged'] == 2.0


class TestE1RM:
    def test_epley_formula(self):
        assert _epley_1rm(100, 5) == 116.5   # 100*(1+5/30)=116.667 -> 116.5
        assert _epley_1rm(80, 8) == 101.5

    def test_reps_one_is_load(self):
        assert _epley_1rm(120, 1) == 120.0

    def test_round_half(self):
        # 90*(1+3/30)=99.0
        assert _epley_1rm(90, 3) == 99.0

    def test_reps_above_ten_excluded(self):
        entry = _session('2026-10-13', 'Squat', [{'reps': 12, 'weight_kg': 100}] * 3)
        prev = _session('2026-10-06', 'Squat', [{'reps': 12, 'weight_kg': 100}] * 3)
        e = per_day_e1rm([entry, prev])
        assert e == {}

    def test_eligible_lift_e1rm_present(self):
        entry = _session('2026-10-13', 'Squat', [{'reps': 5, 'weight_kg': 100}])
        e = per_day_e1rm([entry])
        assert e['Squat']['2026-10-13'] == 116.5

    def test_campus_excluded_from_e1rm(self):
        entry = _session('2026-10-13', 'Squat', [{'reps': 5, 'weight_kg': 100}],
                         source='campus_plan')
        assert per_day_e1rm([entry]) == {}

    def test_non_eligible_exercise_no_e1rm(self):
        entry = _session('2026-10-13', 'Curl barre', [{'reps': 5, 'weight_kg': 30}])
        assert per_day_e1rm([entry]) == {}

    def test_decimal_reps_integer_eligible(self):
        entry = _session('2026-10-13', 'Squat', [{'reps': Decimal('5'), 'weight_kg': Decimal('100')}])
        e = per_day_e1rm([entry])
        assert e['Squat']['2026-10-13'] == 116.5


class TestRecords:
    def _two_sessions(self, exercise, d1, detail1, d2, detail2, source='athlete_text',
                      desc1='', desc2='', vol1=None, vol2=None):
        s1 = _session(d1, exercise, detail1, source=source, description=desc1,
                      per_ex=[{'exercise': exercise, 'volume_kg': vol1,
                               'volume_incomplete': vol1 is None}] if vol1 is not None else None)
        s2 = _session(d2, exercise, detail2, source=source, description=desc2,
                      per_ex=[{'exercise': exercise, 'volume_kg': vol2,
                               'volume_incomplete': vol2 is None}] if vol2 is not None else None)
        return [s1, s2]

    def test_loaded_record_fields(self):
        entries = self._two_sessions(
            'Squat', '2026-10-06', [{'reps': 5, 'weight_kg': 100}],
            '2026-10-13', [{'reps': 3, 'weight_kg': 110}],
            vol1=1500, vol2=990,
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['kind'] == 'loaded'
        # No per-side session on this lift -> no "total load noted" label.
        assert rec['load_label'] is None
        assert rec['top_weight_kg'] == 110.0
        assert rec['top_weight_date'] == '2026-10-13'
        assert rec['e1rm_kg'] == max(_epley_1rm(100, 5), _epley_1rm(110, 3))
        assert rec['best_volume_kg'] == 1500.0
        assert rec['best_reps_bw'] is None
        assert rec['best_weighted_bw'] is None

    def test_single_session_excluded(self):
        entries = [_session('2026-10-13', 'Squat', [{'reps': 5, 'weight_kg': 100}])]
        ins = build_strength_insights(entries, today=TODAY)
        assert all(r['exercise'] != 'Squat' for r in ins['records'])

    def test_tie_keeps_earliest_date(self):
        entries = self._two_sessions(
            'Squat', '2026-10-06', [{'reps': 5, 'weight_kg': 100}],
            '2026-10-13', [{'reps': 5, 'weight_kg': 100}],
            vol1=1500, vol2=1500,
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_date'] == '2026-10-06'  # earliest wins the tie
        assert rec['best_volume_date'] == '2026-10-06'

    def test_volume_incomplete_excluded(self):
        s1 = _session('2026-10-06', 'Squat', [{'reps': 5, 'weight_kg': 100}],
                      per_ex=[{'exercise': 'Squat', 'volume_kg': 1500, 'volume_incomplete': True}])
        s2 = _session('2026-10-13', 'Squat', [{'reps': 5, 'weight_kg': 100}],
                      per_ex=[{'exercise': 'Squat', 'volume_kg': 1500, 'volume_incomplete': False}])
        ins = build_strength_insights([s1, s2], today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['best_volume_date'] == '2026-10-13'

    def test_campus_excluded_from_e1rm_but_keeps_top_weight(self):
        entries = self._two_sessions(
            'Squat', '2026-10-06', [{'reps': 5, 'weight_kg': 100}],
            '2026-10-13', [{'reps': 5, 'weight_kg': 110}],
            source='campus_plan', vol1=1500, vol2=1650,
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_kg'] == 110.0        # loads are the athlete's
        assert rec['e1rm_kg'] is None               # reps prescribed -> no e1RM

    def test_bodyweight_record_typing(self):
        entries = self._two_sessions(
            'Tractions', '2026-10-06', [{'reps': 8, 'weight_kg': None}],
            '2026-10-13', [{'reps': 10, 'weight_kg': None}, {'reps': 6, 'weight_kg': 20}],
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Tractions')
        assert rec['kind'] == 'bodyweight'
        assert rec['top_weight_kg'] is None
        assert rec['e1rm_kg'] is None
        assert rec['best_volume_kg'] is None
        assert rec['load_label'] is None
        assert rec['best_reps_bw'] == {'reps': 10, 'date': '2026-10-13'}
        assert rec['best_weighted_bw'] == {'reps': 6, 'added_weight_kg': 20.0, 'date': '2026-10-13'}

    def test_mixed_exercise_absent_from_records(self):
        """The mixed machine is kept off the records board entirely: no row,
        not even a volume record (a chest/shoulder-press volume PR is not
        comparable)."""
        entries = self._two_sessions(
            'Développé machine', '2026-10-06', [{'reps': 8, 'weight_kg': 55}],
            '2026-10-13', [{'reps': 8, 'weight_kg': 60}],
            vol1=1320, vol2=1440,
        )
        ins = build_strength_insights(entries, today=TODAY)
        assert all(r['exercise'] != 'Développé machine' for r in ins['records'])

    def test_notation_mixed_fixture(self):
        """Presse à cuisses "4x10 40/c" then "4x10 @100" -> notation mixed,
        no e1RM, no top-weight, no volume record, flag true."""
        entries = self._two_sessions(
            'Presse à cuisses',
            '2026-10-06', [{'reps': 10, 'weight_kg': 80}] * 4,
            '2026-10-13', [{'reps': 10, 'weight_kg': 100}] * 4,
            desc1='Presse à cuisses 4x10 40/c', desc2='Presse à cuisses 4x10 @100',
            vol1=3200, vol2=4000,
        )
        ins = build_strength_insights(entries, today=TODAY)
        # Nothing comparable is left, so the lift is off the board (the chart
        # carries the note).
        assert all(r['exercise'] != 'Presse à cuisses' for r in ins['records'])
        flags = exercise_flags(entries)
        assert flags['Presse à cuisses']['e1rm_eligible'] is False
        assert flags['Presse à cuisses']['notation_mixed'] is True
        assert per_day_e1rm(entries) == {}

    def test_per_side_load_does_not_taint_other_lifts_of_the_session(self):
        """Live case: 'dc 80x10' next to 'Press inc 3x10 40/c' (stored 80).

        A session-level "/c anywhere" rule marked the bench press as per-side
        and, with its plain sessions, as notation-mixed: no record, no e1RM.
        The bench must stay clean; the incline press is the per-side lift."""
        desc = 'dc 80x10 90x8\nPress inc 3x10 40/c'
        session = {
            'date': '2026-10-06', 'activity_id': 'a1', 'sets_source': 'athlete_text',
            'description': desc,
            'parsed_sets': [
                {'exercise': 'Développé couché',
                 'sets_detail': [{'reps': 10, 'weight_kg': 80}, {'reps': 8, 'weight_kg': 90}]},
                {'exercise': 'Développé incliné haltères',
                 'sets_detail': [{'reps': 10, 'weight_kg': 80}] * 3},
            ],
        }
        plain_bench = _session(
            '2026-10-13', 'Développé couché',
            [{'reps': 8, 'weight_kg': 90}] * 3, description='dc 3x8 90',
        )
        flags = exercise_flags([session, plain_bench])
        assert flags['Développé couché']['notation_mixed'] is False
        assert flags['Développé couché']['e1rm_eligible'] is True

    def test_reps_equal_to_doubled_load_on_same_line_stay_per_side(self):
        """'Curl 3x12 6/c' stores 12: the rep count 12 sits on the per-side line
        and must not read as a plain 12. Both sessions are per-side."""
        s1 = _session('2026-10-06', 'Curl biceps', [{'reps': 12, 'weight_kg': 12}] * 3,
                      description='Curl haltères 3x12 6/c')
        s2 = _session('2026-10-13', 'Curl biceps', [{'reps': 10, 'weight_kg': 16}] * 3,
                      description='Curl haltères 3x10 8/c')
        flags = exercise_flags([s1, s2])
        assert flags['Curl biceps']['notation_mixed'] is False
        assert flags['Curl biceps']['per_side_seen'] is True
        from shared.strength_insights import (
            _notation_state, _per_side_doubled_loads, _plain_numbers,
        )
        assert _notation_state(
            s1['parsed_sets'][0]['sets_detail'],
            _per_side_doubled_loads(s1), _plain_numbers(s1),
        ) == 'per_side'

    def test_load_written_plain_elsewhere_is_ambiguous_not_plain(self):
        """'dc 80x10' next to 'Press inc 40/c': the incline press stored at 80
        cannot be told apart. It must count as neither, so a later plain
        incline session does not hide that it was noted per side."""
        from shared.strength_insights import (
            _notation_state, _per_side_doubled_loads, _plain_numbers,
        )
        entry = {'description': 'dc 80x10 90x8\nPress inc 3x10 40/c'}
        doubled = _per_side_doubled_loads(entry)
        plain = _plain_numbers(entry)
        assert _notation_state([{'reps': 10, 'weight_kg': 80}] * 3, doubled, plain) == 'ambiguous'
        assert _notation_state(
            [{'reps': 10, 'weight_kg': 80}, {'reps': 8, 'weight_kg': 90}], doubled, plain,
        ) == 'plain'

    def test_prose_clauses_split_on_comma(self):
        """Live 2026-06-01 prose: the bench at 80 kg sits in the same sentence as
        a 40kg/côté pull-down. Split on ', ' so the bench reads as plain."""
        from shared.strength_insights import (
            _notation_state, _per_side_doubled_loads, _plain_numbers,
        )
        entry = {'description': (
            'tirages verts machine convergente 40kg/côté sur 3x10, puis le morceau '
            'de choix, développé couché barre à 80kg pour 4 séries de 8.'
        )}
        assert _notation_state(
            [{'reps': 8, 'weight_kg': 80}] * 4,
            _per_side_doubled_loads(entry), _plain_numbers(entry),
        ) == 'ambiguous'

    def test_unhashable_activity_id_keeps_insights(self):
        entries = [
            {**_session('2026-10-06', 'Squat', [{'reps': 5, 'weight_kg': 100}]),
             'activity_id': ['bad']},
            {**_session('2026-10-13', 'Squat', [{'reps': 5, 'weight_kg': 105}]),
             'activity_id': {'x': 1}},
        ]
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_kg'] == 105.0

    def test_legacy_flat_row_gives_a_top_weight_record(self):
        legacy = [
            {'date': d, 'activity_id': d, 'description': '',
             'parsed_sets': [{'exercise': 'Squat', 'sets': 3, 'reps': 5, 'weight_kg': w}]}
            for d, w in (('2026-10-06', 100), ('2026-10-13', 110))
        ]
        ins = build_strength_insights(legacy, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_kg'] == 110.0

    def test_load_written_plain_and_per_side_is_not_per_side(self):
        """'dc 4x8 80' plus 'Press inc 40/c': 80 is written plain, so a lift
        stored at 80 is not proven per-side."""
        from shared.strength_insights import (
            _notation_state, _per_side_doubled_loads, _plain_numbers,
        )
        entry = {'description': 'dc 4x8 80\nPress inc 3x10 40/c'}
        doubled = _per_side_doubled_loads(entry)
        plain = _plain_numbers(entry)
        assert 80.0 in doubled and 80.0 in plain
        assert _notation_state([{'reps': 8, 'weight_kg': 80}], doubled, plain) == 'ambiguous'

    def test_per_side_with_decimal_comma_and_kg_cote(self):
        from shared.strength_insights import (
            _notation_state, _per_side_doubled_loads, _plain_numbers,
        )
        entry = {'description': 'Press inc 3x10 37,5/c\nlow row 8x50kg par côté'}
        doubled = _per_side_doubled_loads(entry)
        plain = _plain_numbers(entry)
        assert _notation_state([{'reps': 10, 'weight_kg': 75}], doubled, plain) == 'per_side'
        assert _notation_state([{'reps': 8, 'weight_kg': 100}], doubled, plain) == 'per_side'

    def test_extractor_flag_wins_over_the_text(self):
        """One-line note: the text alone would mark the bench per-side (round-3
        C2). The extractor's own per_side flag decides instead."""
        bench = {'exercise': 'Développé couché', 'per_side': False,
                 'sets_detail': [{'reps': 10, 'weight_kg': 80}]}
        incline = {'exercise': 'Développé incliné haltères', 'per_side': True,
                   'sets_detail': [{'reps': 10, 'weight_kg': 80}] * 3}
        s1 = {'date': '2026-10-06', 'activity_id': 'a1', 'sets_source': 'athlete_text',
              'description': 'dc 80x10 + press inc 3x10 40/c', 'parsed_sets': [bench, incline]}
        s2 = _session('2026-10-13', 'Développé couché', [{'reps': 8, 'weight_kg': 90}] * 3,
                      description='dc 3x8 90')
        s2['parsed_sets'][0]['per_side'] = False
        flags = exercise_flags([s1, s2])
        assert flags['Développé couché']['notation_mixed'] is False
        assert flags['Développé couché']['e1rm_eligible'] is True
        assert flags['Développé incliné haltères']['per_side_seen'] is True

    def test_ambiguous_session_feeds_no_load_record(self):
        """Round-3 C1: 'dc 80x10' next to 'Press inc 40/c' leaves the incline at 80
        undecided. A later plain 60 must be the record, not the doubtful 80."""
        s1 = {'date': '2026-10-06', 'activity_id': 'a1', 'sets_source': 'athlete_text',
              'description': 'dc 80x10 90x8\nPress inc 3x10 40/c',
              'parsed_sets': [
                  {'exercise': 'Développé couché',
                   'sets_detail': [{'reps': 10, 'weight_kg': 80}, {'reps': 8, 'weight_kg': 90}]},
                  {'exercise': 'Développé incliné',
                   'sets_detail': [{'reps': 10, 'weight_kg': 80}] * 3},
              ]}
        s2 = _session('2026-10-13', 'Développé incliné', [{'reps': 10, 'weight_kg': 60}] * 3,
                      description='Press inc 3x10 60')
        ins = build_strength_insights([s1, s2], today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Développé incliné')
        assert rec['top_weight_kg'] == 60.0
        assert rec['e1rm_kg'] == 80.0  # Epley(60, 10) from the plain session only
        flags = exercise_flags([s1, s2])
        assert flags['Développé incliné']['ambiguous_dates'] == ['2026-10-06']
        assert '2026-10-06' not in per_day_e1rm([s1, s2]).get('Développé incliné', {})

    def test_rows_without_any_record_are_dropped(self):
        entries = self._two_sessions(
            'Gainage frontal',
            '2026-10-06', [{'duration_s': 40}] * 3,
            '2026-10-13', [{'duration_s': 45}] * 3,
        )
        ins = build_strength_insights(entries, today=TODAY)
        assert all(r['exercise'] != 'Gainage frontal' for r in ins['records'])

    def test_bodyweight_best_reps_ignores_weighted_sets(self):
        """Item 2: the unloaded set has FEWER reps than the weighted one; the
        bodyweight reps record still takes the unloaded set, and the weighted
        record takes the loaded one."""
        entries = self._two_sessions(
            'Tractions',
            '2026-10-06', [{'reps': 6, 'weight_kg': None}],
            '2026-10-13', [{'reps': 8, 'weight_kg': None}, {'reps': 12, 'weight_kg': 15}],
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Tractions')
        # 12 reps are at +15 kg -> they belong to the weighted record, not reps_bw.
        assert rec['best_reps_bw'] == {'reps': 8, 'date': '2026-10-13'}
        assert rec['best_weighted_bw'] == {'reps': 12, 'added_weight_kg': 15.0, 'date': '2026-10-13'}

    def test_invalid_set_never_a_top_weight(self):
        """Item 3: a {reps: 0, weight_kg: 999} row is not a lift and must not
        become a top weight. A real set in the other session is the record."""
        entries = self._two_sessions(
            'Squat',
            '2026-10-06', [{'reps': 0, 'weight_kg': 999}, {'reps': 5, 'weight_kg': 100}],
            '2026-10-13', [{'reps': 5, 'weight_kg': 105}],
            vol1=1500, vol2=1575,
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_kg'] == 105.0  # 999 is rejected, 105 wins

    def test_always_per_side_plus_no_load_session_is_not_notation_mixed(self):
        """Item 4: a lift always written per-side, plus one session with no load,
        is NOT notation_mixed (the no-load session is 'unknown', not 'plain')."""
        s1 = _session('2026-10-06', 'Presse à cuisses',
                      [{'reps': 10, 'weight_kg': 80}] * 4,
                      description='Presse à cuisses 4x10 40/c')
        s2 = _session('2026-10-13', 'Presse à cuisses',
                      [{'reps': 10, 'weight_kg': 100}] * 4,
                      description='Presse à cuisses 4x10 50/c')
        s3 = _session('2026-10-15', 'Presse à cuisses',
                      [{'reps': 12, 'weight_kg': None}] * 3,
                      description='Presse à cuisses 3x12 bodyweight test')
        flags = exercise_flags([s1, s2, s3])
        assert flags['Presse à cuisses']['notation_mixed'] is False
        assert flags['Presse à cuisses']['per_side_seen'] is True
        ins = build_strength_insights([s1, s2, s3], today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Presse à cuisses')
        assert rec['notation_mixed'] is False
        assert rec['top_weight_kg'] == 100.0
        assert rec['load_label'] == 'total_noted'

    def test_two_activities_same_day_count_as_two_sessions(self):
        """Item 5: eligibility counts distinct entries (activity_id), not distinct
        dates. Two activities on the same day are two sessions."""
        s1 = {'date': '2026-10-13', 'activity_id': 'a1', 'sets_source': 'athlete_text',
              'description': '', 'parsed_sets': [
                  {'exercise': 'Squat', 'sets_detail': [{'reps': 5, 'weight_kg': 100}]}],
              'per_exercise': [{'exercise': 'Squat', 'volume_kg': 500, 'volume_incomplete': False}]}
        s2 = {'date': '2026-10-13', 'activity_id': 'a2', 'sets_source': 'athlete_text',
              'description': '', 'parsed_sets': [
                  {'exercise': 'Squat', 'sets_detail': [{'reps': 5, 'weight_kg': 110}]}],
              'per_exercise': [{'exercise': 'Squat', 'volume_kg': 550, 'volume_incomplete': False}]}
        ins = build_strength_insights([s1, s2], today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['top_weight_kg'] == 110.0

    def test_load_label_none_without_per_side_session(self):
        """Item 7: a plain-only loaded lift gets load_label None, and
        exercise_flags reports per_side_seen False."""
        entries = self._two_sessions(
            'Squat', '2026-10-06', [{'reps': 5, 'weight_kg': 100}],
            '2026-10-13', [{'reps': 5, 'weight_kg': 105}],
            vol1=1500, vol2=1575,
        )
        ins = build_strength_insights(entries, today=TODAY)
        rec = next(r for r in ins['records'] if r['exercise'] == 'Squat')
        assert rec['load_label'] is None
        flags = exercise_flags(entries)
        assert flags['Squat']['per_side_seen'] is False

    def test_cap_at_fifteen_rows(self):
        exercises = [
            'Développé couché', 'Développé incliné', 'Squat', 'Soulevé de terre',
            'Hip thrust', 'Presse à cuisses', 'Tirage vertical machine',
            'Tirage horizontal', 'Développé militaire', 'Presse épaules',
            'Curl barre', 'Curl biceps', 'Leg curl', 'Leg extension',
            'Face pull', 'Pull-over', 'Crunch', 'Mollets',
        ]
        entries = []
        for i, ex in enumerate(exercises):
            entries += self._two_sessions(
                ex, '2026-10-06', [{'reps': 5, 'weight_kg': 50}],
                '2026-10-13', [{'reps': 5, 'weight_kg': 55}],
                vol1=250, vol2=275,
            )
        ins = build_strength_insights(entries, today=TODAY)
        assert len(ins['records']) == 15


class TestPushPull:
    def test_last_four_weeks_logged_only(self):
        ins = build_strength_insights([
            _session('2026-10-13', 'Développé couché', [{'reps': 5, 'weight_kg': 100}] * 3),
            _session('2026-10-13', 'Tractions', [{'reps': 8}] * 2),
        ], today=TODAY)
        assert len(ins['push_pull']) == 4
        wk = ins['push_pull'][-1]
        assert wk['week'] == '2026-W42'
        assert wk['push'] == 3.0
        assert wk['pull'] == 2.0

    def test_ratio_null_when_pull_zero(self):
        ins = build_strength_insights([
            _session('2026-10-13', 'Développé couché', [{'reps': 5, 'weight_kg': 100}] * 3),
        ], today=TODAY)
        wk = ins['push_pull'][-1]
        assert wk['pull'] == 0.0
        assert wk['ratio'] is None

    def test_campus_excluded_from_push_pull(self):
        ins = build_strength_insights([
            _session('2026-10-13', 'Développé couché', [{'reps': 5, 'weight_kg': 100}] * 3,
                     source='campus_plan'),
        ], today=TODAY)
        assert ins['push_pull'][-1]['push'] == 0.0

    def test_ratio_computed_when_both_present(self):
        ins = build_strength_insights([
            _session('2026-10-13', 'Développé couché', [{'reps': 5, 'weight_kg': 100}] * 4),
            _session('2026-10-13', 'Tractions', [{'reps': 8}] * 2),
        ], today=TODAY)
        wk = ins['push_pull'][-1]
        assert wk['ratio'] == 2.0


class TestContract:
    def test_counting_rule_is_string(self):
        ins = build_strength_insights([], today=TODAY)
        assert isinstance(ins['counting_rule'], str)

    def test_mixed_exercises_listed(self):
        ins = build_strength_insights([], today=TODAY)
        assert {'exercise': 'Développé machine', 'note_key': 'mixed_chest_shoulder_machine'} in ins['mixed_exercises']

    def test_malformed_entries_skipped(self):
        entries = ['abc', {}, None, {'date': 'not-a-date', 'parsed_sets': []},
                   {'date': '2026-10-13', 'parsed_sets': 'notalist'}]
        ins = build_strength_insights(entries, today=TODAY)
        assert len(ins['weeks']) == 8
        assert ins['records'] == []
        assert ins['push_pull'][-1]['ratio'] is None

    def test_entries_none(self):
        ins = build_strength_insights(None, today=TODAY)
        assert len(ins['weeks']) == 8
