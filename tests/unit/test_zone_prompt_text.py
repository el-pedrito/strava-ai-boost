"""The coach prompt shows a single-value zone (min == max) as one pace."""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'lambda_functions'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src', 'agents'))

import coach_agent  # noqa: E402


def _system_and_user(pace_zones):
    config = {'user_preferences': {'athlete_profile': 'Runner', 'pace_zones': pace_zones}}
    return ' '.join(coach_agent._build_prompt_parts({'name': 'run'}, config))


def test_single_value_zone_reads_as_one_pace():
    text = _system_and_user({'tempo': {'min': '5:15', 'max': '5:15'}})
    assert 'tempo: 5:15' in text
    assert '5:15-5:15' not in text


def test_range_zone_keeps_both_bounds():
    text = _system_and_user({'ef': {'min': '5:46', 'max': '6:16'}})
    assert 'ef: 5:46-6:16' in text
