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
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise": "Développé couché", "sets": 4, "reps": 8, "weight_kg": 80},'
            '{"exercise": "Tractions", "sets": 4, "reps": 10, "weight_kg": null}]'
        )
        result = _extract_strength_sets("DC 4x8 @80kg, Tractions 4x10")
        assert len(result) == 2
        assert result[0] == {"exercise": "Développé couché", "sets": 4, "reps": 8, "weight_kg": 80.0}
        assert result[1]["weight_kg"] is None

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
        assert result == [{"exercise": "Squat", "sets": 5, "reps": 5, "weight_kg": 100.0}]

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
        mock_runtime.return_value.converse.return_value = _converse_response(
            '[{"exercise": "Squat", "sets": "5", "reps": "5", "weight_kg": "100"},'
            '{"sets": 3},'  # no exercise → skipped
            '"garbage",'      # not a dict → skipped
            '{"exercise": "Gainage", "sets": null, "reps": null, "weight_kg": null}]'
        )
        result = _extract_strength_sets("Squat 5x5 100kg, gainage")
        assert len(result) == 2
        assert result[0] == {"exercise": "Squat", "sets": 5, "reps": 5, "weight_kg": 100.0}
        assert result[1] == {"exercise": "Gainage", "sets": None, "reps": None, "weight_kg": None}


class TestTrackStrengthHistory:
    """Regression (live incident 2026-07-18/20): parsed_sets carried float
    weight_kg — boto3 rejected the DynamoDB write ('Float types are not
    supported') and strength history entries were silently dropped."""

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

        mock_table.update_item.assert_called_once()
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
