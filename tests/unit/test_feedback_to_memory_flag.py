"""FEEDBACK_TO_MEMORY gate (reliability lot 4, step 1).

The feedback analyzer used to write every description diff as a conversational
event into the AgentCore memory shared with the coach. The semantic/episodic
strategies then extracted "observations" about editing AI text, which polluted the
coach. The writes are now off by default; the DynamoDB feedback update and the
metrics are unchanged.
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda_functions'))

from support import feedback_analyzer  # noqa: E402

ACTIVITY = {
    'activity_id': '123',
    'user_id': '138362426',
    'enhanced_description': 'Sortie facile 10 km a 5:36/km.',
    'sport_type': 'Run',
    'distance': 10000,
    'moving_time': 3360,
}
EDITED = 'Sortie facile, 10 km, jambes lourdes.'


def _run_handler(monkeypatch, flag):
    """Run the handler with all I/O mocked; return (result, boto3.client mock, update mock)."""
    if flag is None:
        monkeypatch.delenv('FEEDBACK_TO_MEMORY', raising=False)
    else:
        monkeypatch.setenv('FEEDBACK_TO_MEMORY', flag)
    agentcore = MagicMock()
    agentcore.create_event.return_value = {'ResponseMetadata': {'HTTPStatusCode': 200}}
    with patch.object(feedback_analyzer, 'MEMORY_ID', 'mem-test'), \
            patch.object(feedback_analyzer, 'get_unanalyzed_activities', return_value=[dict(ACTIVITY)]), \
            patch.object(feedback_analyzer, 'get_access_token', return_value='tok'), \
            patch.object(feedback_analyzer, 'fetch_final_description', return_value=EDITED), \
            patch.object(feedback_analyzer, 'update_activity_feedback') as update, \
            patch.object(feedback_analyzer, 'calculate_quality_metrics',
                         return_value={'modification_rate': 1.0}), \
            patch.object(feedback_analyzer.boto3, 'client', return_value=agentcore) as client_factory:
        result = feedback_analyzer.lambda_handler({}, None)
    return result, client_factory, agentcore, update


class TestFlagParsing:
    def test_values(self, monkeypatch):
        cases = [
            (None, False), ('false', False), ('', False), ('0', False), ('no', False),
            ('true', True), ('TRUE', True), (' true ', True), ('1', True), ('yes', True),
        ]
        for value, expected in cases:
            if value is None:
                monkeypatch.delenv('FEEDBACK_TO_MEMORY', raising=False)
            else:
                monkeypatch.setenv('FEEDBACK_TO_MEMORY', value)
            assert feedback_analyzer.feedback_to_memory_enabled() is expected, value


class TestDefaultWritesNothing:
    def test_handler_default_no_agentcore_call(self, monkeypatch):
        result, client_factory, agentcore, update = _run_handler(monkeypatch, None)
        assert result['statusCode'] == 200
        assert result['modifications_detected'] == 1
        assert result['memory_events_written'] == 0
        agentcore.create_event.assert_not_called()
        # No bedrock-agentcore client is even built when the flag is off.
        assert not any(c.args and c.args[0] == 'bedrock-agentcore'
                       for c in client_factory.call_args_list)

    def test_handler_explicit_false(self, monkeypatch):
        result, _, agentcore, _ = _run_handler(monkeypatch, 'false')
        assert result['memory_events_written'] == 0
        agentcore.create_event.assert_not_called()

    def test_dynamodb_feedback_still_written(self, monkeypatch):
        _, _, _, update = _run_handler(monkeypatch, None)
        update.assert_called_once()
        kwargs = update.call_args.kwargs
        assert kwargs['activity_id'] == '123'
        assert kwargs['final_description'] == EDITED
        assert kwargs['is_modified'] is True

    def test_write_function_is_noop_when_disabled(self, monkeypatch):
        monkeypatch.delenv('FEEDBACK_TO_MEMORY', raising=False)
        client = MagicMock()
        ok = feedback_analyzer.write_feedback_to_memory(
            client=client, user_id='u', activity_id='1',
            enhanced='a', final='b', activity_data=ACTIVITY)
        assert ok is False
        client.create_event.assert_not_called()


class TestEnabledKeepsOldBehaviour:
    def test_handler_true_writes_event(self, monkeypatch):
        result, _, agentcore, update = _run_handler(monkeypatch, 'true')
        assert result['memory_events_written'] == 1
        update.assert_called_once()
        agentcore.create_event.assert_called_once()
        kwargs = agentcore.create_event.call_args.kwargs
        assert kwargs['memoryId'] == 'mem-test'
        assert kwargs['actorId'] == '138362426'
        assert kwargs['sessionId'] == 'feedback-123'
        roles = [p['conversational']['role'] for p in kwargs['payload']]
        assert roles == ['ASSISTANT', 'USER']
        assert EDITED in kwargs['payload'][1]['conversational']['content']['text']

    def test_unmodified_activity_never_writes(self, monkeypatch):
        monkeypatch.setenv('FEEDBACK_TO_MEMORY', 'true')
        agentcore = MagicMock()
        with patch.object(feedback_analyzer, 'MEMORY_ID', 'mem-test'), \
                patch.object(feedback_analyzer, 'get_unanalyzed_activities', return_value=[dict(ACTIVITY)]), \
                patch.object(feedback_analyzer, 'get_access_token', return_value='tok'), \
                patch.object(feedback_analyzer, 'fetch_final_description',
                             return_value=ACTIVITY['enhanced_description']), \
                patch.object(feedback_analyzer, 'update_activity_feedback'), \
                patch.object(feedback_analyzer, 'calculate_quality_metrics',
                             return_value={'modification_rate': 0.0}), \
                patch.object(feedback_analyzer.boto3, 'client', return_value=agentcore):
            result = feedback_analyzer.lambda_handler({}, None)
        assert result['memory_events_written'] == 0
        agentcore.create_event.assert_not_called()


class TestStackSetsFlag:
    def test_stack_declares_flag_false(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'stacks', 'feedback_loop_stack.py')
        with open(path, encoding='utf-8') as f:
            src = f.read()
        assert "'FEEDBACK_TO_MEMORY': 'false'" in src
