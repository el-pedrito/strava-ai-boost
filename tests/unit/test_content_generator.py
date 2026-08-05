"""Unit tests for content_generator Lambda"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from processing.content_generator import (
    handler,
    retrieve_activity_data_from_dynamodb,
    get_user_configuration,
    build_user_profile_from_config,
    store_generated_content,
    _parse_agent_response,
    _process_agent_response,
    _extract_strength_sets,
    _STRENGTH_EXTRACTION_SYSTEM_PROMPT,
    mark_campus_session_done,
)


class TestHandler:
    """Test handler input validation and error handling"""

    @patch('processing.content_generator.store_generated_content')
    @patch('processing.content_generator.generate_enhanced_content')
    @patch('processing.content_generator.apply_module_processing', return_value=[])
    @patch('processing.content_generator.get_active_modules', return_value=[])
    @patch('processing.content_generator.extract_enduraw_report', return_value=None)
    @patch('processing.content_generator.get_user_configuration')
    @patch('processing.content_generator.retrieve_activity_data_from_dynamodb')
    def test_successful_generation(self, mock_retrieve, mock_config, mock_enduraw,
                                   mock_modules, mock_apply, mock_generate, mock_store):
        mock_retrieve.return_value = {
            'activity_data': {'name': 'Morning Run', 'type': 'Run', 'distance': 5000},
            'laps_data': None,
            'athlete_stats': None,
            'athlete_profile': None,
            'intervals_icu_data': None,
        }
        mock_config.return_value = {'user_id': 'user1', 'modules_config': {}}
        mock_generate.return_value = {
            'title': 'Great Run',
            'description': 'AI description',
            'confidence': 0.9,
            'modules_used': [],
            'style_elements': [],
            'patterns_detected': [],
            'analysis_type': 'agentcore_memory',
            'memory_used': False,
            'expressions_avoided': [],
        }

        response = handler({'activity_id': '123', 'user_id': 'user1'}, None)
        assert response['statusCode'] == 200
        assert response['activity_id'] == '123'
        mock_store.assert_called_once()

    def test_missing_activity_id(self):
        response = handler({'user_id': 'user1'}, None)
        assert response['statusCode'] == 500
        assert 'Missing required' in response['error']

    def test_missing_user_id(self):
        response = handler({'activity_id': '123'}, None)
        assert response['statusCode'] == 500
        assert 'Missing required' in response['error']

    def test_empty_event(self):
        response = handler({}, None)
        assert response['statusCode'] == 500

    @patch('processing.content_generator.retrieve_activity_data_from_dynamodb', return_value=None)
    def test_activity_not_found(self, mock_retrieve):
        response = handler({'activity_id': '999', 'user_id': 'user1'}, None)
        assert response['statusCode'] == 500
        assert 'not found' in response['error']


class TestRetrieveActivityData:
    """Test DynamoDB activity retrieval"""

    @patch('processing.content_generator.dynamodb')
    def test_successful_retrieval(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'activity_id': '123',
                'activity_data_json': json.dumps({'name': 'Run', 'distance': 5000}),
                'laps_json': None,
                'athlete_stats_json': None,
            }
        }
        mock_dynamo.Table.return_value = mock_table

        result = retrieve_activity_data_from_dynamodb('123')
        assert result is not None
        assert result['activity_data']['name'] == 'Run'
        assert result['activity_data']['distance'] == 5000

    @patch('processing.content_generator.dynamodb')
    def test_not_found_returns_none(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamo.Table.return_value = mock_table

        result = retrieve_activity_data_from_dynamodb('999')
        assert result is None

    @patch('processing.content_generator.dynamodb')
    def test_numeric_string_conversion(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'activity_id': '123',
                'activity_data_json': json.dumps({
                    'distance': '5000.5',
                    'moving_time': '1800',
                    'name': 'Run',
                }),
            }
        }
        mock_dynamo.Table.return_value = mock_table

        result = retrieve_activity_data_from_dynamodb('123')
        assert result['activity_data']['distance'] == 5000.5
        assert result['activity_data']['moving_time'] == 1800
        assert result['activity_data']['name'] == 'Run'  # Strings preserved

    @patch('processing.content_generator.dynamodb')
    def test_dynamo_error_returns_none(self, mock_dynamo):
        mock_dynamo.Table.return_value.get_item.side_effect = Exception("timeout")
        result = retrieve_activity_data_from_dynamodb('123')
        assert result is None


class TestGetUserConfiguration:
    """Test user config retrieval"""

    @patch('processing.content_generator.dynamodb')
    def test_existing_user(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {
                'user_id': 'user1',
                'enhancement_enabled': True,
                'modules_config': {'campus_coach': {'enabled': True}},
            }
        }
        mock_dynamo.Table.return_value = mock_table

        config = get_user_configuration('user1')
        assert config['user_id'] == 'user1'
        assert config['modules_config']['campus_coach']['enabled'] is True

    @patch('processing.content_generator.dynamodb')
    def test_new_user_gets_defaults(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item
        mock_dynamo.Table.return_value = mock_table

        config = get_user_configuration('new_user')
        assert config['user_id'] == 'new_user'
        assert config['modules_config'] == {}
        assert config['enhancement_enabled'] is True

    @patch('processing.content_generator.dynamodb')
    def test_missing_modules_config_added(self, mock_dynamo):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            'Item': {'user_id': 'user1', 'enhancement_enabled': True}
        }
        mock_dynamo.Table.return_value = mock_table

        config = get_user_configuration('user1')
        assert 'modules_config' in config
        assert config['modules_config'] == {}

    @patch('processing.content_generator.dynamodb')
    def test_error_returns_defaults(self, mock_dynamo):
        mock_dynamo.Table.return_value.get_item.side_effect = Exception("boom")
        config = get_user_configuration('user1')
        assert config['enhancement_enabled'] is True


class TestBuildUserProfile:
    """Test user profile construction"""

    def test_full_preferences(self):
        config = {
            'user_preferences': {
                'age_range': '36-45',
                'interests': ['trail', 'marathon'],
                'sport_approach': 'performance',
                'content_length': 'long',
                'content_tone': 'analytical',
                'emoji_usage': 'none',
                'technical_detail': 'advanced',
                'content_language': 'english',
                'pace_zones': {'ef': {'min': '5:30', 'max': '6:20'}},
            }
        }
        profile = build_user_profile_from_config(config)
        assert profile is not None
        assert profile['age_range'] == '36-45'
        assert profile['content_preferences']['tone'] == 'analytical'
        assert profile['pace_zones'] == {'ef': {'min': '5:30', 'max': '6:20'}}

    def test_no_preferences_returns_none(self):
        assert build_user_profile_from_config({}) is None
        assert build_user_profile_from_config({'user_preferences': {}}) is None

    def test_defaults_applied(self):
        config = {'user_preferences': {'age_range': '26-35'}}
        profile = build_user_profile_from_config(config)
        assert profile['content_preferences']['length'] == 'medium'
        assert profile['content_preferences']['language'] == 'french'

    def test_no_pace_zones(self):
        config = {'user_preferences': {'age_range': '26-35'}}
        profile = build_user_profile_from_config(config)
        assert 'pace_zones' not in profile


class TestParseAgentResponse:
    """Test AgentCore response parsing"""

    def test_generated_content_format(self):
        completion = json.dumps({
            'generated_content': {
                'title': 'Great Morning Run',
                'description': 'What a fantastic workout',
            },
            'content_metadata': {
                'confidence': 0.92,
                'tone_used': 'motivational',
            },
        })
        result = _parse_agent_response(completion, None, [])
        assert result['title'] == 'Great Morning Run'
        assert '@Generated by Strava AI Boost' in result['description']
        assert result['confidence'] == 0.92

    def test_flat_title_description_format(self):
        completion = json.dumps({
            'title': 'Run Title',
            'description': 'Run description here',
            'confidence': 0.85,
        })
        result = _parse_agent_response(completion, None, [])
        assert result['title'] == 'Run Title'
        assert result['confidence'] == 0.85

    def test_title_truncated_to_50_chars(self):
        long_title = 'A' * 100
        completion = json.dumps({'title': long_title, 'description': 'desc'})
        result = _parse_agent_response(completion, None, [])
        assert len(result['title']) == 50

    def test_signature_not_duplicated(self):
        completion = json.dumps({
            'title': 'Run',
            'description': 'Already signed\n\n@Generated by Strava AI Boost',
        })
        result = _parse_agent_response(completion, None, [])
        assert result['description'].count('@Generated by Strava AI Boost') == 1

    def test_markdown_code_blocks_stripped(self):
        raw = '```json\n{"title": "Run", "description": "desc"}\n```'
        completion = json.dumps({'response': raw})
        result = _parse_agent_response(completion, None, [])
        assert result['title'] == 'Run'

    def test_interval_title_corrected_for_non_interval_workout(self):
        completion = json.dumps({
            'title': 'Fractionné matinal',
            'description': 'Great steady run',
        })
        classification = {'type': 'steady', 'label': 'Sortie Reguliere'}
        result = _parse_agent_response(completion, classification, [])
        # Title should be corrected because classification is 'steady', not 'intervals'
        assert 'fractionn' not in result['title'].lower()

    def test_interval_title_kept_for_interval_workout(self):
        completion = json.dumps({
            'title': 'Fractionné explosif',
            'description': 'Hard intervals',
        })
        classification = {'type': 'intervals', 'label': 'Intervalles'}
        result = _parse_agent_response(completion, classification, [])
        # intervals classification → title should not be corrected
        assert 'ractionn' in result['title'].lower() or 'Intervalles' in result['title']

    def test_missing_title_raises(self):
        completion = json.dumps({'description': 'only description'})
        with pytest.raises(ValueError, match="Missing title"):
            _parse_agent_response(completion, None, [])

    def test_no_json_raises(self):
        completion = json.dumps({'response': 'Just plain text with no JSON'})
        with pytest.raises((ValueError, json.JSONDecodeError)):
            _parse_agent_response(completion, None, [])

    def test_modules_tracked(self):
        completion = json.dumps({'title': 'Run', 'description': 'desc'})
        modules = [{'name': 'campus_coach'}, {'name': 'enduraw'}]
        result = _parse_agent_response(completion, None, modules)
        assert result['modules_used'] == ['campus_coach', 'enduraw']

    def test_memory_operations_extracted(self):
        completion = json.dumps({
            'title': 'Run',
            'description': 'desc',
            'memory_operations': {
                'retrieved': True,
                'stored': False,
                'expressions_avoided': ['super run', 'belle sortie'],
            },
        })
        result = _parse_agent_response(completion, None, [])
        assert result['memory_used'] is True
        assert result['expressions_avoided'] == ['super run', 'belle sortie']


class TestProcessAgentResponse:
    """Test agent response processing"""

    def test_event_stream_response(self):
        lines = [b'data: {"title": "Run"}', b'data: ', b'']
        mock_response = {
            'contentType': 'text/event-stream',
            'response': MagicMock(iter_lines=MagicMock(return_value=iter(lines))),
        }
        result = _process_agent_response(mock_response)
        assert '{"title": "Run"}' in result

    def test_json_response(self):
        chunks = [b'{"title":', b' "Run"}']
        mock_response = {
            'contentType': 'application/json',
            'response': chunks,
        }
        result = _process_agent_response(mock_response)
        assert result == '{"title": "Run"}'

    def test_empty_response_raises(self):
        mock_response = {
            'contentType': 'application/json',
            'response': [],
        }
        with pytest.raises(ValueError, match="Empty response"):
            _process_agent_response(mock_response)

    def test_fallback_string_response(self):
        mock_response = {
            'contentType': 'text/plain',
            'response': '{"title": "Run"}',
        }
        result = _process_agent_response(mock_response)
        assert 'Run' in result


class TestStoreGeneratedContent:
    """Test content storage in DynamoDB"""

    @patch('processing.content_generator.dynamodb')
    def test_successful_store(self, mock_dynamo):
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        content = {
            'title': 'Run Title',
            'description': 'Description',
            'confidence': 0.9,
            'style_elements': ['motivational'],
            'modules_used': ['campus_coach'],
            'patterns_detected': [],
            'analysis_type': 'agentcore_memory',
        }

        store_generated_content('123', content)
        mock_table.update_item.assert_called_once()

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs['Key'] == {'activity_id': '123'}
        assert ':title' in call_kwargs['ExpressionAttributeValues']

    @patch('processing.content_generator.dynamodb')
    def test_float_to_decimal_conversion(self, mock_dynamo):
        mock_table = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        content = {
            'title': 'Run',
            'description': 'Desc',
            'confidence': 0.85,
            'style_elements': [],
            'modules_used': [],
            'patterns_detected': [],
            'analysis_type': 'test',
        }

        store_generated_content('123', content)
        call_kwargs = mock_table.update_item.call_args[1]
        meta = call_kwargs['ExpressionAttributeValues'][':meta']
        assert isinstance(meta['confidence'], Decimal)

    @patch('processing.content_generator.dynamodb')
    def test_store_error_does_not_raise(self, mock_dynamo):
        mock_dynamo.Table.return_value.update_item.side_effect = Exception("write error")
        # Should not raise — errors are logged
        store_generated_content('123', {'title': 'x', 'description': 'y'})


def _converse_response(text: str) -> dict:
    """Build a minimal Bedrock Converse response wrapping the given text."""
    return {"output": {"message": {"content": [{"text": text}]}}}


class TestExtractStrengthSets:
    """Test the best-effort LLM extraction of structured strength sets."""

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_valid_extraction(self, mock_runtime):
        # Uniform exercises emitted by the model in the legacy flat shape (no
        # sets_detail): the parser must rebuild sets_detail so downstream
        # consumers only ever handle one shape. A uniform 4x8@80 expands to four
        # identical per-set entries.
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise": "Développé couché", "sets": 4, "reps": 8, "weight_kg": 80},'
            '{"exercise": "Tractions", "sets": 4, "reps": 10, "weight_kg": null}]'
        )
        result = _extract_strength_sets("DC 4x8 @80kg, Tractions 4x10")
        assert len(result) == 2
        assert result[0] == {
            "exercise": "Développé couché", "sets": 4, "reps": 8, "weight_kg": 80.0,
            "sets_detail": [{"reps": 8, "weight_kg": 80.0}] * 4,
        }
        assert result[1]["weight_kg"] is None
        # Bodyweight sets still get a rebuilt per-set view (weight None per entry).
        assert result[1]["sets_detail"] == [{"reps": 10, "weight_kg": None}] * 4

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_canonicalizes_known_aliases_before_storage(self, mock_runtime):
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise": "Facepull", "sets": 4, "reps": 12, "weight_kg": 20},'
            '{"exercise": "Élévation latérale", "sets": 4, "reps": 15, "weight_kg": 8},'
            '{"exercise": "DC halt", "sets": 3, "reps": 10, "weight_kg": 24}]'
        )

        result = _extract_strength_sets("Facepull, élévation latérale, DC halt")

        assert [item['exercise'] for item in result] == [
            'Face pull',
            'Élévations latérales',
            'Développé couché haltères',
        ]

    def test_prompt_contains_closed_vocabulary_and_equipment_guard(self):
        assert 'use EXACTLY one canonical name' in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        assert "Facepull -> 'Face pull'" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        assert "'Écartés pectoraux à la poulie'" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        assert 'loads are not comparable' in _STRENGTH_EXTRACTION_SYSTEM_PROMPT

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_code_fence_stripped(self, mock_runtime):
        mock_runtime.return_value.converse.return_value = _converse_response(
            '```json\n[{"exercise": "Squat", "sets": 5, "reps": 5, "weight_kg": 100}]\n```'
        )
        result = _extract_strength_sets("Squat 5x5 100kg")
        # Fence stripping unchanged; the parsed item now also carries the rebuilt
        # per-set view (5 identical entries for a uniform 5x5@100).
        assert result == [{
            "exercise": "Squat", "sets": 5, "reps": 5, "weight_kg": 100.0,
            "sets_detail": [{"reps": 5, "weight_kg": 100.0}] * 5,
        }]

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_non_json_returns_empty(self, mock_runtime):
        mock_runtime.return_value.converse.return_value = _converse_response("désolé, pas de sets")
        assert _extract_strength_sets("une belle séance") == []

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_non_list_json_returns_empty(self, mock_runtime):
        mock_runtime.return_value.converse.return_value = _converse_response('{"exercise": "Squat"}')
        assert _extract_strength_sets("Squat") == []

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_bedrock_error_returns_empty(self, mock_runtime):
        mock_runtime.return_value.converse.side_effect = Exception("throttled")
        assert _extract_strength_sets("DC 4x8 @80kg") == []

    def test_short_description_skips_call(self):
        # Too short → no bedrock call, returns [] (no mock needed).
        assert _extract_strength_sets("") == []
        assert _extract_strength_sets("hi") == []

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_malformed_items_filtered_and_coerced(self, mock_runtime):
        # The schema gained sets_detail, but the malformed-input contract is
        # unchanged and still enforced: items with no exercise or that are not
        # dicts are dropped, and string numerics are coerced to int/float.
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise": "Squat", "sets": "5", "reps": "5", "weight_kg": "100"},'
            '{"sets": 3},'  # no exercise → skipped
            '"garbage",'      # not a dict → skipped
            '{"exercise": "Gainage", "sets": null, "reps": null, "weight_kg": null}]'
        )
        result = _extract_strength_sets("Squat 5x5 100kg, gainage")
        assert len(result) == 2
        # Coercion "5"/"5"/"100" -> 5/5/100.0, then sets_detail rebuilt from the
        # coerced flat values.
        assert result[0] == {
            "exercise": "Squat", "sets": 5, "reps": 5, "weight_kg": 100.0,
            "sets_detail": [{"reps": 5, "weight_kg": 100.0}] * 5,
        }
        # All-null Gainage: sets is falsy so nothing is rebuilt; sets_detail stays
        # empty and the flat summary stays None (no fabricated set).
        assert result[1] == {
            "exercise": "Gainage", "sets": None, "reps": None, "weight_kg": None,
            "sets_detail": [],
        }

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_variable_series_preserved_per_set(self, mock_runtime):
        """Regression (real session, tonnage error -33%): 'low row mach 10x80 8x90
        8x90' is three distinct sets, not 3x8@90. Collapsing to the flat summary
        reported 24 reps at 90kg instead of the 26 reps actually done with the
        first set at 80kg. sets_detail is authoritative and must survive parsing
        verbatim."""
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Tirage horizontal machine","sets":3,"reps":8,"weight_kg":90,'
            '"sets_detail":[{"reps":10,"weight_kg":80},{"reps":8,"weight_kg":90},'
            '{"reps":8,"weight_kg":90}]}]'
        )
        result = _extract_strength_sets("low row mach 10x80 8x90 8x90")
        assert len(result) == 1
        assert result[0]["sets_detail"] == [
            {"reps": 10, "weight_kg": 80.0},
            {"reps": 8, "weight_kg": 90.0},
            {"reps": 8, "weight_kg": 90.0},
        ]
        # sets is derived from sets_detail length, not the model's flat "sets".
        assert result[0]["sets"] == 3
        # The whole point: the true rep count is 26, not the 24 a naive 3x8@90
        # would give.
        assert sum(s["reps"] for s in result[0]["sets_detail"]) == 26

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_trailing_multiplier_is_a_total_not_an_increment(self, mock_runtime):
        """'80x10 x2' is TWO sets at 80, never three.

        The athlete's notation uses a trailing xN as the total count for the
        weight/reps pair it follows. Reading it as "one set plus N more" inflated a
        real session from 25 sets to 26 and its tonnage by 800 kg (16170 instead of
        15370). Confirmed by the athlete: "x2 ca veut dire 2 series de 10".
        """
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Tirage vertical machine","sets":3,"reps":10,"weight_kg":80,'
            '"sets_detail":[{"reps":10,"weight_kg":75},{"reps":10,"weight_kg":80},'
            '{"reps":10,"weight_kg":80}]}]'
        )
        out = _extract_strength_sets('tirage vert mach 75x10 80x10 x2')
        assert len(out) == 1
        detail = out[0]["sets_detail"]
        assert len(detail) == 3, f"trailing x2 must yield 3 sets total, got {detail}"
        assert [d["weight_kg"] for d in detail] == [75.0, 80.0, 80.0]
        assert sum(d["reps"] for d in detail) == 30

    def test_prompt_states_the_trailing_multiplier_is_a_total(self):
        """Anti-drift: the rule must stay in the extraction prompt."""
        assert "TRAILING MULTIPLIER" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        assert "TOTAL number of sets" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        assert "never three" in _STRENGTH_EXTRACTION_SYSTEM_PROMPT

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_repeat_shorthand_expanded_per_set(self, mock_runtime):
        """Regression companion: '75x10 80x10 x2' means one set at 75 then two at
        80 -> [{10,75},{10,80},{10,80}]. The 'x2' repeat must be expanded into two
        separate entries, never folded into a single set that hides the load
        change."""
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Développé couché","sets":3,"reps":10,"weight_kg":80,'
            '"sets_detail":[{"reps":10,"weight_kg":75},{"reps":10,"weight_kg":80},'
            '{"reps":10,"weight_kg":80}]}]'
        )
        result = _extract_strength_sets("75x10 80x10 x2")
        assert result[0]["sets"] == 3
        assert result[0]["sets_detail"] == [
            {"reps": 10, "weight_kg": 75.0},
            {"reps": 10, "weight_kg": 80.0},
            {"reps": 10, "weight_kg": 80.0},
        ]

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_per_side_load_is_doubled_in_every_entry(self, mock_runtime):
        """Regression: '4x8 55/c' is 55kg PER SIDE, so 110kg is actually moved.
        Storing 55 halved the tonnage. The doubled load must appear in every
        sets_detail entry and in the flat summary — the per-side figure must never
        leak through."""
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Développé machine","sets":4,"reps":8,"weight_kg":110,'
            '"sets_detail":[{"reps":8,"weight_kg":110},{"reps":8,"weight_kg":110},'
            '{"reps":8,"weight_kg":110},{"reps":8,"weight_kg":110}]}]'
        )
        result = _extract_strength_sets("dc machine 4x8 55/c")
        assert result[0]["sets"] == 4
        assert result[0]["weight_kg"] == 110.0
        assert all(s["weight_kg"] == 110.0 for s in result[0]["sets_detail"])
        # No entry may keep the raw per-side 55.
        assert all(s["weight_kg"] != 55.0 for s in result[0]["sets_detail"])

    def test_prompt_documents_per_side_and_variable_series_and_pairs(self):
        """The parser trusts the model's JSON, so the notations themselves are
        handled by the extraction prompt. Guard that the prompt keeps instructing
        the model on the exact regressions that motivated the schema change: the
        per-side markers (all variants), variable series, and paired supersets."""
        p = _STRENGTH_EXTRACTION_SYSTEM_PROMPT
        # Per-side markers — every variant the athlete actually writes.
        for marker in ("'/c'", "'/cote'", "'par cote'", "'/side'"):
            assert marker in p, f"missing per-side marker {marker}"
        assert 'DOUBLE' in p
        assert "'4x8 55/c' -> four entries at weight_kg 110" in p
        # Variable series must not be collapsed.
        assert "'10x80 8x90 8x90' is three entries" in p
        assert 'Never collapse' in p
        # Paired notation must keep the first value of each pair.
        assert 'PAIRED notation' in p
        assert 'Never' in p and 'drop the first value of a pair.' in p

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_paired_superset_keeps_first_pair_value(self, mock_runtime):
        """Regression: 'elev lat - face pull 3x10-10 15-35' is a superset of two
        exercises. The bug dropped the first load (15) and left both at 35. The
        parser must keep both objects with their own load: 15 for A, 35 for B."""
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Élévations latérales","sets":3,"reps":10,"weight_kg":15,'
            '"sets_detail":[{"reps":10,"weight_kg":15},{"reps":10,"weight_kg":15},'
            '{"reps":10,"weight_kg":15}]},'
            '{"exercise":"Face pull","sets":3,"reps":10,"weight_kg":35,'
            '"sets_detail":[{"reps":10,"weight_kg":35},{"reps":10,"weight_kg":35},'
            '{"reps":10,"weight_kg":35}]}]'
        )
        result = _extract_strength_sets("elev lat - face pull 3x10-10 15-35")
        assert [item["exercise"] for item in result] == [
            "Élévations latérales", "Face pull",
        ]
        # The first pair value (15) is preserved, not overwritten by the second.
        assert result[0]["weight_kg"] == 15.0
        assert all(s["weight_kg"] == 15.0 for s in result[0]["sets_detail"])
        assert result[1]["weight_kg"] == 35.0
        assert all(s["weight_kg"] == 35.0 for s in result[1]["sets_detail"])

    @patch('processing.content_generator._get_bedrock_runtime')
    def test_sets_detail_rebuilt_from_flat_and_capped(self, mock_runtime):
        """Fallback contract: when the model omits sets_detail but gives a flat
        sets/reps/weight_kg, the parser rebuilds one entry per set by repetition
        so consumers never branch on shape. The rebuild is capped at 20 entries to
        bound a runaway/hallucinated set count."""
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise":"Squat","sets":4,"reps":6,"weight_kg":90},'
            '{"exercise":"Gainage","sets":25,"reps":1,"weight_kg":null}]'
        )
        result = _extract_strength_sets("Squat 4x6 90kg puis gainage")
        assert result[0]["sets_detail"] == [{"reps": 6, "weight_kg": 90.0}] * 4
        assert result[0]["sets"] == 4
        # 25 requested sets are capped at 20 rebuilt entries; sets follows the
        # rebuilt length so the count never exceeds the cap either.
        assert len(result[1]["sets_detail"]) == 20
        assert result[1]["sets"] == 20
        assert result[1]["sets_detail"][0] == {"reps": 1, "weight_kg": None}


class TestTrackStrengthHistory:
    """Regression (live incident 2026-07-18/20): parsed_sets carried float
    weight_kg — boto3 rejected the DynamoDB write ('Float types are not
    supported') and strength history entries were silently dropped."""

    def test_first_write_initialises_the_parent_map(self):
        """Reproduces the production failure: no strength_history yet.

        `SET user_preferences.strength_history.entries = ...` raises
        ValidationException ("document path provided in the update expression is
        invalid") when the parent map is absent -- which was every athlete. The
        exception was swallowed as a warning, so the history stayed empty and the
        coach lost its only persisted source of strength progression.
        """
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {}}
        calls = []

        def record(**kwargs):
            expr = kwargs["UpdateExpression"]
            calls.append(expr)
            # Emulate DynamoDB: appending into a map that was never created fails.
            if "strength_history.entries" in expr and not any(
                "if_not_exists(user_preferences.strength_history, :init)" in c for c in calls[:-1]
            ):
                raise Exception("ValidationException: The document path provided in the update expression is invalid")
            return {}

        mock_table.update_item.side_effect = record
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table

        with patch("processing.content_generator.dynamodb", mock_dynamo), \
             patch("processing.content_generator._extract_strength_sets", return_value=[]):
            from processing.content_generator import _track_strength_history
            _track_strength_history(
                "user1", "act-first",
                {"description": "Trac 10-10-10 puis low row 3x10 @80kg",
                 "start_date_local": "2026-08-05T12:00:00Z", "moving_time": 2880},
            )

        assert len(calls) == 2, f"expected init + append, got {calls}"
        assert "if_not_exists(user_preferences.strength_history, :init)" in calls[0]
        assert "strength_history.entries" in calls[1]

    @patch('processing.content_generator._extract_strength_sets')
    @patch('processing.content_generator.dynamodb')
    def test_float_weights_written_as_decimal(self, mock_dynamodb, mock_extract):
        from decimal import Decimal
        from processing.content_generator import _track_strength_history

        mock_extract.return_value = [
            {"exercise": "DC haltères", "sets": 4, "reps": 8, "weight_kg": 22.5},
        ]
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {}}
        mock_dynamodb.Table.return_value = mock_table

        _track_strength_history("user1", "act1", {
            "description": "DC haltères 4x8 @22.5kg",
            "start_date_local": "2026-07-18T12:00:00Z",
            "moving_time": "1886",  # string numerics happen on manual activities
        })

        # Two calls: the parent map is initialised first, then the entry appended.
        # DynamoDB rejects `SET a.b.c` when `a.b` is absent and forbids updating
        # overlapping paths in one expression, so the init cannot be merged.
        assert mock_table.update_item.call_count == 2
        init_expr = mock_table.update_item.call_args_list[0].kwargs["UpdateExpression"]
        assert "if_not_exists(user_preferences.strength_history, :init)" in init_expr
        values = mock_table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        entry = values[":entry"][0]

        def _no_floats(obj):
            if isinstance(obj, float):
                return False
            if isinstance(obj, dict):
                return all(_no_floats(v) for v in obj.values())
            if isinstance(obj, list):
                return all(_no_floats(v) for v in obj)
            return True

        assert _no_floats(entry), f"float leaked into DynamoDB write: {entry}"
        assert entry["parsed_sets"][0]["weight_kg"] == Decimal("22.5")
        assert entry["duration_min"] == 31  # string moving_time coerced


class TestMarkCampusSessionDone:
    """P0.5: local completion is stored separately from provider state, while
    the legacy status=Fait marker is preserved for back-compat consumers."""

    @patch('processing.content_generator.dynamodb')
    def test_writes_local_execution_fields(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        session = {'session_date': 'week-2026-W21', 'session_id': '456_0', 'title': 'Tempo'}
        mark_campus_session_done(session, 'act-123', match_score=0.82)

        mock_table.put_item.assert_not_called()
        mock_table.update_item.assert_called_once()
        kwargs = mock_table.update_item.call_args.kwargs
        assert kwargs['Key'] == {'session_date': 'week-2026-W21', 'session_id': '456_0'}

        values = kwargs['ExpressionAttributeValues']
        # Legacy completion marker preserved for dashboard_api + modules_processing
        assert values[':done'] == 'Fait'
        assert kwargs['ExpressionAttributeNames']['#s'] == 'status'
        # New separated local execution state
        assert values[':local_done'] == 'done'
        assert values[':aid'] == 'act-123'
        assert ':ts' in values
        assert values[':score'] == Decimal('0.82')
        assert 'match_score = :score' in kwargs['UpdateExpression']

    @patch('processing.content_generator.dynamodb')
    def test_match_score_omitted_when_none(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        session = {'session_date': 'week-2026-W21', 'session_id': '456_0'}
        mark_campus_session_done(session, 'act-123')

        kwargs = mock_table.update_item.call_args.kwargs
        assert 'match_score' not in kwargs['UpdateExpression']
        assert ':score' not in kwargs['ExpressionAttributeValues']

    @patch('processing.content_generator.dynamodb')
    def test_missing_keys_no_write(self, mock_dynamodb):
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        mark_campus_session_done({'title': 'no keys'}, 'act-123')
        mock_table.update_item.assert_not_called()
