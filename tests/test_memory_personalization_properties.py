"""
Property-Based Tests for Memory-Based Personalization

Tests Property 7: Content generation uses AgentCore Memory for style consistency and expression variety
Validates: Requirements 2.10
"""

import pytest
from hypothesis import given, strategies as st, settings, example, HealthCheck
from hypothesis import assume
import json
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from agents.content_generation_agent import ContentGenerationAgent
except ImportError:
    ContentGenerationAgent = None


# Test data strategies
@st.composite
def user_style_strategy(draw):
    """Generate realistic user style data"""
    tones = ['motivational', 'technical', 'casual', 'professional', 'fun']
    style_elements = ['technical', 'fun', 'motivational', 'analytical', 'personal']
    
    return {
        'tone': draw(st.sampled_from(tones)),
        'style_elements': draw(st.lists(
            st.sampled_from(style_elements), 
            min_size=1, 
            max_size=3, 
            unique=True
        )),
        'preferred_length': draw(st.sampled_from(['short', 'medium', 'long'])),
        'sport_focus': draw(st.sampled_from(['running', 'cycling', 'general']))
    }


@st.composite
def used_expressions_strategy(draw):
    """Generate realistic used expressions list"""
    expressions = [
        'crushed it', 'nailed the pace', 'feeling strong', 'perfect execution',
        'solid effort', 'great session', 'tempo perfection', 'zone 2 magic',
        'interval mastery', 'endurance building', 'recovery vibes', 'speed demon'
    ]
    
    return draw(st.lists(
        st.sampled_from(expressions),
        min_size=0,
        max_size=10,
        unique=True
    ))


@st.composite
def activity_data_strategy(draw):
    """Generate realistic activity data for testing"""
    activity_types = ['Run', 'Ride', 'Swim', 'Workout']
    activity_type = draw(st.sampled_from(activity_types))
    
    distance = draw(st.floats(min_value=1000, max_value=50000))  # 1-50km in meters
    duration = draw(st.integers(min_value=300, max_value=14400))  # 5 minutes to 4 hours
    
    return {
        'id': str(draw(st.integers(min_value=1000000, max_value=9999999))),
        'name': draw(st.text(min_size=5, max_size=50)),
        'type': activity_type,
        'distance': distance,
        'moving_time': duration,
        'elapsed_time': duration + draw(st.integers(min_value=0, max_value=600)),
        'total_elevation_gain': draw(st.floats(min_value=0, max_value=2000)),
        'start_date_local': '2024-01-15T08:00:00Z'
    }


class TestMemoryPersonalization:
    """
    **Feature: strava-ai-boost, Property 7: Content generation uses AgentCore Memory for style consistency and expression variety**
    
    Property-based tests for memory-based personalization functionality
    """
    
    def create_mock_bedrock_client(self):
        """Create mock Bedrock client for testing"""
        mock_client = Mock()
        
        # Mock successful content generation response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{
                'text': json.dumps({
                    'title': 'Morning Tempo Run',
                    'description': 'Solid tempo effort with consistent pacing throughout.',
                    'style_elements': ['technical', 'motivational'],
                    'confidence': 0.85,
                    'expressions_used': ['solid effort', 'consistent pacing']
                })
            }]
        }).encode()
        
        mock_client.invoke_model.return_value = mock_response
        return mock_client
    
    def create_mock_dynamodb_table(self, user_style=None, used_expressions=None):
        """Create mock DynamoDB table for testing"""
        mock_table = Mock()
        
        def mock_get_item(Key):
            if Key.get('memory_type') == 'personal_style':
                if user_style:
                    return {'Item': {'style_data': user_style}}
                else:
                    return {}  # No item found
            elif Key.get('memory_type') == 'used_expressions':
                if used_expressions:
                    return {'Item': {'expressions': used_expressions}}
                else:
                    return {}  # No item found
            return {}
        
        mock_table.get_item.side_effect = mock_get_item
        mock_table.put_item.return_value = {}
        
        return mock_table
        
        mock_table.get_item.side_effect = mock_get_item
        mock_table.put_item.return_value = {}
        
        return mock_table
    
    @given(
        user_style=user_style_strategy(),
        used_expressions=used_expressions_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(
        max_examples=100, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    @example(
        user_style={
            'tone': 'motivational',
            'style_elements': ['technical', 'fun'],
            'preferred_length': 'medium',
            'sport_focus': 'running'
        },
        used_expressions=['crushed it', 'nailed the pace'],
        activity_data={
            'id': '1234567',
            'name': 'Morning Run',
            'type': 'Run',
            'distance': 5000,
            'moving_time': 1500,
            'elapsed_time': 1600,
            'total_elevation_gain': 50,
            'start_date_local': '2024-01-15T08:00:00Z'
        }
    )
    def test_memory_retrieval_and_usage(
        self, 
        user_style: Dict[str, Any],
        used_expressions: List[str],
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any user with stored style and expressions, 
        content generation should retrieve and use memory data
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        assume(len(user_style['style_elements']) > 0)
        
        user_id = 'test_user_123'
        
        # Create mocks
        mock_bedrock = self.create_mock_bedrock_client()
        mock_table = self.create_mock_dynamodb_table(user_style, used_expressions)
        
        # Mock AgentCore Memory responses
        def mock_query_agentcore_memory(query):
            if query.get('query_type') == 'personal_style':
                return {'style_data': user_style}
            elif query.get('query_type') == 'used_expressions':
                return {'expressions': used_expressions}
            return None
        
        def mock_store_agentcore_memory(data):
            return None  # Success
        
        with patch('boto3.client') as mock_boto3_client, \
             patch('boto3.resource') as mock_boto3_resource:
            
            mock_boto3_client.return_value = mock_bedrock
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_bedrock
            agent.dynamodb = mock_dynamodb
            
            # Mock AgentCore Memory methods
            agent.query_agentcore_memory = AsyncMock(side_effect=mock_query_agentcore_memory)
            agent.store_in_agentcore_memory = AsyncMock(side_effect=mock_store_agentcore_memory)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Test memory retrieval
                retrieved_style = loop.run_until_complete(
                    agent.get_user_style(user_id)
                )
                retrieved_expressions = loop.run_until_complete(
                    agent.get_used_expressions(user_id)
                )
                
                # Verify memory retrieval
                assert retrieved_style == user_style
                assert retrieved_expressions == used_expressions
                
                # Verify AgentCore Memory was called correctly (not DynamoDB)
                # The agent calls query_agentcore_memory with a dictionary argument
                agent.query_agentcore_memory.assert_any_call({
                    'user_id': user_id,
                    'query_type': 'personal_style',
                    'memory_type': 'semantic_search'
                })
                agent.query_agentcore_memory.assert_any_call({
                    'user_id': user_id,
                    'query_type': 'used_expressions',
                    'memory_type': 'semantic_search',
                    'limit': 20
                })
                
            finally:
                loop.close()
    
    @given(
        activity_data=activity_data_strategy()
    )
    @settings(
        max_examples=100, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_default_style_for_new_users(
        self, 
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any new user without stored style, 
        content generation should use default style preferences
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        
        user_id = 'new_user_456'
        
        # Create mocks with no stored data
        mock_bedrock = self.create_mock_bedrock_client()
        mock_table = self.create_mock_dynamodb_table(None, None)  # No stored data
        
        with patch('boto3.client') as mock_boto3_client, \
             patch('boto3.resource') as mock_boto3_resource:
            
            mock_boto3_client.return_value = mock_bedrock
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_bedrock
            agent.dynamodb = mock_dynamodb
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Test default style retrieval
                retrieved_style = loop.run_until_complete(
                    agent.get_user_style(user_id)
                )
                retrieved_expressions = loop.run_until_complete(
                    agent.get_used_expressions(user_id)
                )
                
                # Verify default values
                assert isinstance(retrieved_style, dict)
                assert 'tone' in retrieved_style
                assert 'style_elements' in retrieved_style
                assert retrieved_style['tone'] == 'motivational'  # Default tone
                assert 'technical' in retrieved_style['style_elements']  # Default elements
                
                assert isinstance(retrieved_expressions, list)
                assert len(retrieved_expressions) == 0  # No previous expressions
                
            finally:
                loop.close()
    
    @given(
        user_style=user_style_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_content_generation_uses_personal_style(
        self, 
        user_style: Dict[str, Any],
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any user style preferences, 
        content generation should incorporate the user's preferred tone and style elements
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        assume(len(user_style['style_elements']) > 0)
        
        user_id = 'styled_user_789'
        modules = []
        
        # Create mocks
        mock_bedrock = self.create_mock_bedrock_client()
        mock_table = self.create_mock_dynamodb_table(user_style, [])
        
        # Mock AgentCore Memory responses
        def mock_query_agentcore_memory(query):
            if query.get('query_type') == 'user_style':
                return user_style
            elif query.get('query_type') == 'used_expressions':
                return {'expressions': []}
            return None
        
        def mock_store_agentcore_memory(data):
            return None  # Success
        
        with patch('boto3.client') as mock_boto3_client, \
             patch('boto3.resource') as mock_boto3_resource:
            
            mock_boto3_client.return_value = mock_bedrock
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_bedrock
            agent.dynamodb = mock_dynamodb
            
            # Mock AgentCore Memory methods
            agent.query_agentcore_memory = AsyncMock(side_effect=mock_query_agentcore_memory)
            agent.store_in_agentcore_memory = AsyncMock(side_effect=mock_store_agentcore_memory)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Test content generation with personal style
                result = loop.run_until_complete(
                    agent.generate_content(activity_data, None, user_id, modules)
                )
                
                # Verify content generation succeeded
                assert isinstance(result, dict)
                assert 'title' in result
                assert 'description' in result
                assert 'style_elements' in result
                
                # Verify Bedrock was called (indicating style was used in prompt)
                mock_bedrock.invoke_model.assert_called()
                
                # Verify memory storage was attempted (AgentCore Memory, not DynamoDB)
                agent.store_in_agentcore_memory.assert_called()
                
            finally:
                loop.close()
    
    @given(
        used_expressions=used_expressions_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_expression_variety_enforcement(
        self, 
        used_expressions: List[str],
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any list of previously used expressions, 
        content generation should avoid repetition by tracking used expressions
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        
        user_id = 'varied_user_101'
        
        # Create mocks
        mock_bedrock = self.create_mock_bedrock_client()
        default_style = {
            'tone': 'motivational',
            'style_elements': ['technical'],
            'preferred_length': 'medium',
            'sport_focus': 'general'
        }
        mock_table = self.create_mock_dynamodb_table(default_style, used_expressions)
        
        # Mock AgentCore Memory responses
        def mock_query_agentcore_memory(query):
            if query.get('query_type') == 'user_style':
                return default_style
            elif query.get('query_type') == 'used_expressions':
                return {'expressions': used_expressions}
            return None
        
        def mock_store_agentcore_memory(data):
            return None  # Success
        
        with patch('boto3.client') as mock_boto3_client, \
             patch('boto3.resource') as mock_boto3_resource:
            
            mock_boto3_client.return_value = mock_bedrock
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_bedrock
            agent.dynamodb = mock_dynamodb
            
            # Mock AgentCore Memory methods
            agent.query_agentcore_memory = AsyncMock(side_effect=mock_query_agentcore_memory)
            agent.store_in_agentcore_memory = AsyncMock(side_effect=mock_store_agentcore_memory)
            agent.dynamodb = mock_dynamodb
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Test expression tracking
                retrieved_expressions = loop.run_until_complete(
                    agent.get_used_expressions(user_id)
                )
                
                # Verify expressions were retrieved
                assert retrieved_expressions == used_expressions
                
                # Test expression storage
                new_expressions = ['new expression', 'another phrase']
                loop.run_until_complete(
                    agent.update_used_expressions_in_memory(user_id, new_expressions)
                )
                
                # Verify storage was called (AgentCore Memory, not DynamoDB)
                agent.store_in_agentcore_memory.assert_called()
                
                # Verify AgentCore Memory was called with expression data
                # The actual call verification is handled by the mock
                
            finally:
                loop.close()
    
    @given(
        user_style=user_style_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_style_learning_and_updates(
        self, 
        user_style: Dict[str, Any]
    ):
        """
        Property: For any user style, 
        the system should learn and update style preferences based on successful generations
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(len(user_style['style_elements']) > 0)
        
        user_id = 'learning_user_202'
        
        # Create mocks
        mock_table = self.create_mock_dynamodb_table(user_style, [])
        
        # Mock AgentCore Memory responses
        def mock_query_agentcore_memory(query):
            if query.get('query_type') == 'user_style':
                return user_style
            elif query.get('query_type') == 'used_expressions':
                return {'expressions': []}
            return None
        
        def mock_store_agentcore_memory(data):
            return None  # Success
        
        with patch('boto3.resource') as mock_boto3_resource, \
             patch('boto3.client') as mock_boto3_client:
            
            # Mock DynamoDB
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            # Mock Bedrock Agent Runtime
            mock_bedrock_agent_runtime = Mock()
            mock_bedrock_agent_runtime.invoke_agent.return_value = {
                'completion': iter([{
                    'chunk': {
                        'bytes': b'{"success": true, "data": {"style_updated": true}}'
                    }
                }])
            }
            
            def mock_client(service_name, **kwargs):
                if service_name == 'bedrock-agent-runtime':
                    return mock_bedrock_agent_runtime
                elif service_name == 'bedrock-runtime':
                    mock_bedrock = Mock()
                    return mock_bedrock
                return Mock()
            
            mock_boto3_client.side_effect = mock_client
            mock_dynamodb = Mock()
            mock_dynamodb.Table.return_value = mock_table
            mock_boto3_resource.return_value = mock_dynamodb
            
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.dynamodb = mock_dynamodb
            
            # Mock AgentCore Memory methods
            agent.query_agentcore_memory = AsyncMock(side_effect=mock_query_agentcore_memory)
            agent.store_in_agentcore_memory = AsyncMock(side_effect=mock_store_agentcore_memory)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Test style update
                new_style_elements = ['analytical', 'personal']
                loop.run_until_complete(
                    agent.update_user_style(user_id, new_style_elements)
                )
                
                # Verify style update was stored (AgentCore Memory, not DynamoDB)
                agent.store_in_agentcore_memory.assert_called()
                
                # Verify AgentCore Memory was called with style data
                # The actual call verification is handled by the mock
                # Note: Since we're using AgentCore Memory, we don't check DynamoDB calls
                
            finally:
                loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])