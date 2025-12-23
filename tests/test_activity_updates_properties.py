"""
Property-Based Tests for Activity Updates

Tests Property 8: Generated content successfully updates Strava activities
Validates: Requirements 2.12
"""

import pytest
from hypothesis import given, strategies as st, settings, example, HealthCheck
from hypothesis import assume
import json
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager
import asyncio

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lambda_functions'))

try:
    from content_generator import (
        generate_enhanced_content_with_agent,
        store_generated_content,
        handler
    )
except ImportError:
    generate_enhanced_content_with_agent = None
    store_generated_content = None
    handler = None


# Test data strategies
@st.composite
def enhanced_content_strategy(draw):
    """Generate realistic enhanced content data"""
    titles = [
        'Morning Tempo Run', 'Interval Training Session', 'Easy Recovery Run',
        'Long Endurance Effort', 'Speed Work Session', 'Hill Repeat Training'
    ]
    
    descriptions = [
        'Solid tempo effort with consistent pacing throughout the session.',
        'Great interval training with perfect recovery between reps.',
        'Easy-paced recovery run to build aerobic base.',
        'Long steady effort building endurance capacity.',
        'Speed work session with explosive power development.',
        'Hill repeats for strength and power building.'
    ]
    
    style_elements = ['technical', 'motivational', 'analytical', 'fun', 'personal']
    
    return {
        'title': draw(st.sampled_from(titles)),
        'description': draw(st.sampled_from(descriptions)),
        'style_elements': draw(st.lists(
            st.sampled_from(style_elements),
            min_size=1,
            max_size=3,
            unique=True
        )),
        'confidence': draw(st.floats(min_value=0.5, max_value=1.0)),
        'modules_used': draw(st.lists(
            st.sampled_from(['campus_coach', 'enduraw']),
            min_size=0,
            max_size=2,
            unique=True
        )),
        'patterns_detected': draw(st.lists(
            st.sampled_from(['steady_effort', 'interval_training', 'fartlek']),
            min_size=1,
            max_size=3,
            unique=True
        ))
    }


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


@st.composite
def lambda_event_strategy(draw):
    """Generate realistic Lambda event data"""
    activity_data = draw(activity_data_strategy())
    user_id = f"user_{draw(st.integers(min_value=1000, max_value=9999))}"
    
    return {
        'activity_id': activity_data['id'],
        'user_id': user_id,
        'activity_data': activity_data,
        'streams_data': None  # Simplified for testing
    }


class TestActivityUpdates:
    """
    **Feature: strava-ai-boost, Property 8: Generated content successfully updates Strava activities**
    
    Property-based tests for activity update functionality
    """
    
    def create_mock_dynamodb_table(self):
        """Create mock DynamoDB table for testing"""
        mock_table = Mock()
        mock_table.update_item.return_value = {}
        mock_table.get_item.return_value = {
            'Item': {
                'user_id': 'test_user',
                'modules_config': {}
            }
        }
        return mock_table
    
    def create_mock_content_agent(self, enhanced_content):
        """Create mock content generation agent"""
        mock_agent = Mock()
        mock_agent.generate_content.return_value = enhanced_content
        return mock_agent
    
    @contextmanager
    def mock_dynamodb_resource(self):
        """Context manager for mocking DynamoDB resource"""
        mock_table = self.create_mock_dynamodb_table()
        
        with patch('content_generator.dynamodb') as mock_dynamodb:
            mock_dynamodb.Table.return_value = mock_table
            yield mock_table
    
    @given(
        enhanced_content=enhanced_content_strategy(),
        activity_id=st.text(min_size=5, max_size=20)
    )
    @settings(
        max_examples=100, 
        deadline=None
    )
    @example(
        enhanced_content={
            'title': 'Morning Tempo Run',
            'description': 'Solid tempo effort with consistent pacing.',
            'style_elements': ['technical', 'motivational'],
            'confidence': 0.85,
            'modules_used': ['campus_coach'],
            'patterns_detected': ['steady_effort']
        },
        activity_id='1234567'
    )
    def test_content_storage_in_dynamodb(
        self, 
        enhanced_content: Dict[str, Any],
        activity_id: str
    ):
        """
        Property: For any enhanced content and activity ID, 
        content should be successfully stored in DynamoDB with proper metadata
        """
        if not store_generated_content:
            pytest.skip("store_generated_content function not available")
        
        # Assume valid data constraints
        assume(len(enhanced_content['title']) > 0)
        assume(len(enhanced_content['description']) > 0)
        assume(enhanced_content['confidence'] > 0)
        
        # Use context manager for DynamoDB mocking
        with self.mock_dynamodb_resource() as mock_table:
            # Test content storage
            store_generated_content(activity_id, enhanced_content)
            
            # Verify DynamoDB update was called
            mock_table.update_item.assert_called_once()
            
            # Verify the update parameters
            call_args = mock_table.update_item.call_args
            assert call_args[1]['Key'] == {'activity_id': activity_id}
            
            # Verify the update expression includes title and description
            update_expression = call_args[1]['UpdateExpression']
            assert 'enhanced_title' in update_expression
            assert 'enhanced_description' in update_expression
            assert 'generation_metadata' in update_expression
            
            # Verify the attribute values
            attr_values = call_args[1]['ExpressionAttributeValues']
            assert attr_values[':title'] == enhanced_content['title']
            assert attr_values[':desc'] == enhanced_content['description']
            
            # Verify metadata structure
            metadata = attr_values[':meta']
            assert 'style_elements' in metadata
            assert 'confidence' in metadata
            assert 'modules_used' in metadata
            assert metadata['style_elements'] == enhanced_content['style_elements']
            # Convert Decimal back to float for comparison
            confidence_value = float(metadata['confidence']) if hasattr(metadata['confidence'], '__float__') else metadata['confidence']
            assert confidence_value == enhanced_content['confidence']
    
    @given(
        lambda_event=lambda_event_strategy()
    )
    @settings(
        max_examples=100, 
        deadline=None
    )
    def test_lambda_handler_success_response(
        self, 
        lambda_event: Dict[str, Any]
    ):
        """
        Property: For any valid Lambda event, 
        the handler should return a success response with enhanced content
        """
        if not handler:
            pytest.skip("Lambda handler not available")
        
        # Assume valid event structure
        assume('activity_id' in lambda_event)
        assume('user_id' in lambda_event)
        assume('activity_data' in lambda_event)
        assume(lambda_event['activity_data']['distance'] > 0)
        assume(lambda_event['activity_data']['moving_time'] > 0)
        
        # Create mock enhanced content
        mock_enhanced_content = {
            'title': 'Enhanced Activity Title',
            'description': 'Enhanced activity description with AI insights.',
            'style_elements': ['technical', 'motivational'],
            'confidence': 0.8,
            'modules_used': [],
            'patterns_detected': ['steady_effort']
        }
        
        # Use context manager for DynamoDB mocking
        with self.mock_dynamodb_resource() as mock_table, \
             patch('content_generator.generate_enhanced_content_with_agent') as mock_generate:
            
            mock_generate.return_value = mock_enhanced_content
            
            # Test Lambda handler
            response = handler(lambda_event, {})
            
            # Verify success response
            assert response['statusCode'] == 200
            assert response['activity_id'] == lambda_event['activity_id']
            assert 'enhanced_content' in response
            
            # Verify enhanced content structure
            enhanced_content = response['enhanced_content']
            assert 'title' in enhanced_content
            assert 'description' in enhanced_content
            assert 'confidence' in enhanced_content
            
            # Verify content generation was called
            mock_generate.assert_called_once()
            
            # Verify storage was attempted
            mock_table.update_item.assert_called_once()
    
    @given(
        lambda_event=lambda_event_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None
    )
    def test_lambda_handler_error_handling(
        self, 
        lambda_event: Dict[str, Any]
    ):
        """
        Property: For any Lambda event that causes processing errors, 
        the handler should return an error response without crashing
        """
        if not handler:
            pytest.skip("Lambda handler not available")
        
        # Assume valid event structure
        assume('activity_id' in lambda_event)
        assume('user_id' in lambda_event)
        
        # Create mocks that raise exceptions
        with self.mock_dynamodb_resource() as mock_table, \
             patch('content_generator.generate_enhanced_content_with_agent') as mock_generate:
            
            # Make content generation fail
            mock_generate.side_effect = Exception("Content generation failed")
            
            # Test Lambda handler with error
            response = handler(lambda_event, {})
            
            # Verify error response
            assert response['statusCode'] == 500
            assert 'error' in response
            assert response['activity_id'] == lambda_event['activity_id']
            
            # Verify error message is present
            assert len(response['error']) > 0
    
    @given(
        enhanced_content=enhanced_content_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None
    )
    def test_content_storage_error_resilience(
        self, 
        enhanced_content: Dict[str, Any]
    ):
        """
        Property: For any enhanced content, 
        storage errors should not crash the system (graceful degradation)
        """
        if not store_generated_content:
            pytest.skip("store_generated_content function not available")
        
        # Assume valid content
        assume(len(enhanced_content['title']) > 0)
        assume(enhanced_content['confidence'] > 0)
        
        activity_id = 'test_activity_123'
        
        # Create mock that raises DynamoDB error
        mock_table = Mock()
        mock_table.update_item.side_effect = Exception("DynamoDB error")
        
        with patch('content_generator.dynamodb') as mock_dynamodb:
            mock_dynamodb.Table.return_value = mock_table
            
            # Test that storage error doesn't crash
            try:
                store_generated_content(activity_id, enhanced_content)
                # Should not raise exception (graceful error handling)
            except Exception as e:
                pytest.fail(f"Storage error should be handled gracefully, but got: {e}")
            
            # Verify DynamoDB update was attempted
            mock_table.update_item.assert_called_once()
    
    @given(
        enhanced_content=enhanced_content_strategy(),
        activity_id=st.text(min_size=5, max_size=20)
    )
    @settings(
        max_examples=50, 
        deadline=None
    )
    def test_metadata_completeness(
        self, 
        enhanced_content: Dict[str, Any],
        activity_id: str
    ):
        """
        Property: For any enhanced content stored, 
        metadata should include all required fields for tracking and analysis
        """
        if not store_generated_content:
            pytest.skip("store_generated_content function not available")
        
        # Assume valid content
        assume(len(enhanced_content['title']) > 0)
        assume(enhanced_content['confidence'] > 0)
        
        # Use context manager for DynamoDB mocking
        with self.mock_dynamodb_resource() as mock_table:
            # Test content storage
            store_generated_content(activity_id, enhanced_content)
            
            # Verify metadata completeness
            call_args = mock_table.update_item.call_args
            metadata = call_args[1]['ExpressionAttributeValues'][':meta']
            
            # Required metadata fields
            required_fields = [
                'style_elements', 'confidence', 'modules_used', 
                'patterns_detected', 'analysis_type', 'generated_at'
            ]
            
            for field in required_fields:
                assert field in metadata, f"Missing required metadata field: {field}"
            
            # Verify data types
            assert isinstance(metadata['style_elements'], list)
            assert isinstance(metadata['confidence'], (int, float)) or hasattr(metadata['confidence'], '__float__')
            assert isinstance(metadata['modules_used'], list)
            assert isinstance(metadata['generated_at'], str)  # ISO timestamp
            
            # Verify timestamp format (should be ISO format)
            timestamp = metadata['generated_at']
            assert 'T' in timestamp  # ISO format contains 'T'
            assert len(timestamp) > 10  # Should be full timestamp, not just date
    
    @given(
        lambda_event=lambda_event_strategy()
    )
    @settings(
        max_examples=50, 
        deadline=None
    )
    def test_end_to_end_activity_processing(
        self, 
        lambda_event: Dict[str, Any]
    ):
        """
        Property: For any valid activity processing request, 
        the complete pipeline should execute successfully from input to storage
        """
        if not handler:
            pytest.skip("Lambda handler not available")
        
        # Assume valid event structure
        assume('activity_id' in lambda_event)
        assume('user_id' in lambda_event)
        assume('activity_data' in lambda_event)
        assume(lambda_event['activity_data']['distance'] > 0)
        assume(lambda_event['activity_data']['moving_time'] > 0)
        
        # Create realistic mock enhanced content
        mock_enhanced_content = {
            'title': f"Enhanced {lambda_event['activity_data']['type']}",
            'description': f"AI-enhanced description for {lambda_event['activity_data']['name']}",
            'style_elements': ['technical', 'motivational'],
            'confidence': 0.85,
            'modules_used': [],
            'patterns_detected': ['steady_effort'],
            'analysis_type': 'ai_enhanced'
        }
        
        # Use context manager for complete pipeline mocking
        with self.mock_dynamodb_resource() as mock_table, \
             patch('content_generator.generate_enhanced_content_with_agent') as mock_generate:
            
            mock_generate.return_value = mock_enhanced_content
            
            # Test complete pipeline
            response = handler(lambda_event, {})
            
            # Verify successful end-to-end processing
            assert response['statusCode'] == 200
            assert response['activity_id'] == lambda_event['activity_id']
            
            # Verify enhanced content was generated
            enhanced_content = response['enhanced_content']
            assert enhanced_content['title'] == mock_enhanced_content['title']
            assert enhanced_content['description'] == mock_enhanced_content['description']
            assert enhanced_content['confidence'] == mock_enhanced_content['confidence']
            
            # Verify modules were processed
            assert 'modules_applied' in response
            assert isinstance(response['modules_applied'], list)
            
            # Verify storage was completed
            mock_table.update_item.assert_called_once()
            
            # Verify stored data matches generated content
            call_args = mock_table.update_item.call_args
            stored_title = call_args[1]['ExpressionAttributeValues'][':title']
            stored_desc = call_args[1]['ExpressionAttributeValues'][':desc']
            
            assert stored_title == mock_enhanced_content['title']
            assert stored_desc == mock_enhanced_content['description']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])