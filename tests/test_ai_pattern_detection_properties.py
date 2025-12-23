"""
Property-Based Tests for AI Pattern Detection

Tests Property 6: Bedrock AI detects effort patterns and workout classification
Validates: Requirements 2.9, 3.2
"""

import pytest
from hypothesis import given, strategies as st, settings, example
from hypothesis import assume
import json
import sys
import os
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from agents.content_generation_agent import ContentGenerationAgent
except ImportError:
    ContentGenerationAgent = None


# Test data strategies
@st.composite
def streams_data_strategy(draw):
    """Generate realistic streams data for testing"""
    length = draw(st.integers(min_value=10, max_value=100))
    
    # Generate velocity data (m/s, typical running speeds 2-6 m/s)
    velocity_smooth = draw(st.lists(
        st.floats(min_value=2.0, max_value=6.0), 
        min_size=length, 
        max_size=length
    ))
    
    # Generate heart rate data (bpm, typical range 120-180)
    heartrate = draw(st.lists(
        st.integers(min_value=120, max_value=180), 
        min_size=length, 
        max_size=length
    ))
    
    # Generate time data (seconds)
    time = list(range(0, length * 10, 10))  # 10-second intervals
    
    # Generate distance data (cumulative meters)
    distance = []
    cumulative = 0
    for i, velocity in enumerate(velocity_smooth):
        cumulative += velocity * 10  # 10 seconds * velocity
        distance.append(cumulative)
    
    # Generate altitude data (meters, typical range 0-500m variation)
    base_altitude = draw(st.floats(min_value=0, max_value=1000))
    altitude = draw(st.lists(
        st.floats(min_value=base_altitude, max_value=base_altitude + 500), 
        min_size=length, 
        max_size=length
    ))
    
    return {
        'velocity_smooth': velocity_smooth,
        'heartrate': heartrate,
        'time': time,
        'distance': distance,
        'altitude': altitude
    }


@st.composite
def activity_data_strategy(draw):
    """Generate realistic activity data for testing"""
    activity_types = ['Run', 'Ride', 'Swim', 'Workout']
    activity_type = draw(st.sampled_from(activity_types))
    
    # Generate realistic distances based on activity type
    if activity_type == 'Run':
        distance = draw(st.floats(min_value=1000, max_value=50000))  # 1-50km in meters
    elif activity_type == 'Ride':
        distance = draw(st.floats(min_value=5000, max_value=200000))  # 5-200km in meters
    else:
        distance = draw(st.floats(min_value=500, max_value=10000))  # 0.5-10km in meters
    
    # Generate realistic duration (seconds)
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


@contextmanager
def mock_bedrock_client():
    """Context manager for mocking Bedrock client"""
    mock_client = Mock()
    
    # Mock successful pattern analysis response
    mock_response = {
        'body': Mock()
    }
    mock_response['body'].read.return_value = json.dumps({
        'content': [{
            'text': json.dumps({
                'patterns': ['steady_effort', 'interval_detected'],
                'classification': 'tempo_run',
                'effort_zones': ['zone2', 'zone3'],
                'intervals_count': 3,
                'insights': ['Good pacing consistency', 'Well-executed intervals']
            })
        }]
    }).encode()
    
    mock_client.invoke_model.return_value = mock_response
    
    with patch('boto3.client', return_value=mock_client):
        yield mock_client


class TestAIPatternDetection:
    """
    **Feature: strava-ai-boost, Property 6: Bedrock AI detects effort patterns and workout classification**
    
    Property-based tests for AI pattern detection functionality
    """
    
    @given(
        streams_data=streams_data_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(max_examples=100, deadline=None)
    @example(
        streams_data={
            'velocity_smooth': [3.5, 4.0, 3.8, 4.2, 3.6],
            'heartrate': [140, 150, 145, 155, 142],
            'time': [0, 10, 20, 30, 40],
            'distance': [35, 75, 113, 155, 191],
            'altitude': [100, 102, 101, 103, 100]
        },
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
    def test_pattern_analysis_returns_valid_structure(
        self, 
        streams_data: Dict[str, Any], 
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any valid streams data and activity data, 
        pattern analysis should return a structured result with required fields
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(len(streams_data['velocity_smooth']) >= 5)
        assume(len(streams_data['heartrate']) >= 5)
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        
        with mock_bedrock_client() as mock_client:
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_client
            
            # Test pattern analysis
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    agent.analyze_patterns(streams_data, activity_data)
                )
                
                # Verify required structure
                assert isinstance(result, dict)
                assert 'patterns' in result
                assert 'classification' in result
                assert 'effort_zones' in result
                assert 'intervals_count' in result
                
                # Verify data types
                assert isinstance(result['patterns'], list)
                assert isinstance(result['classification'], str)
                assert isinstance(result['effort_zones'], list)
                assert isinstance(result['intervals_count'], int)
                
                # Verify reasonable values
                assert result['intervals_count'] >= 0
                assert len(result['patterns']) > 0
                assert len(result['effort_zones']) > 0
                
            finally:
                loop.close()
    
    @given(
        streams_data=streams_data_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(max_examples=100, deadline=None)
    def test_pattern_analysis_handles_bedrock_errors(
        self, 
        streams_data: Dict[str, Any], 
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any streams data, pattern analysis should gracefully handle Bedrock errors
        and return fallback analysis
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(len(streams_data['velocity_smooth']) >= 5)
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        
        # Mock Bedrock client that raises an exception
        mock_client = Mock()
        mock_client.invoke_model.side_effect = Exception("Bedrock service error")
        
        with patch('boto3.client', return_value=mock_client):
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_client
            
            # Test pattern analysis with error
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    agent.analyze_patterns(streams_data, activity_data)
                )
                
                # Should return fallback analysis, not raise exception
                assert isinstance(result, dict)
                assert 'patterns' in result
                assert 'classification' in result
                assert result['analysis_type'] == 'basic'  # Fallback analysis
                
            finally:
                loop.close()
    
    @given(activity_data=activity_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_basic_pattern_analysis_without_streams(
        self, 
        activity_data: Dict[str, Any]
    ):
        """
        Property: For any activity data without streams, 
        basic pattern analysis should classify workout type based on pace
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        assume(activity_data['type'] in ['Run', 'Ride', 'Swim', 'Workout'])
        
        with patch('boto3.client'):
            agent = ContentGenerationAgent(region='eu-west-1')
            
            # Test basic analysis (no streams data)
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(
                    agent.analyze_patterns(None, activity_data)
                )
                
                # Verify basic analysis structure
                assert isinstance(result, dict)
                assert 'patterns' in result
                assert 'classification' in result
                assert 'analysis_type' in result
                assert result['analysis_type'] == 'basic'
                
                # For running activities, classification should be pace-based
                if activity_data['type'] == 'Run':
                    pace_per_km = activity_data['moving_time'] / 60 / (activity_data['distance'] / 1000)
                    
                    if pace_per_km < 4.0:
                        assert result['classification'] == 'speed_work'
                    elif pace_per_km < 5.0:
                        assert result['classification'] == 'tempo_run'
                    elif pace_per_km < 6.0:
                        assert result['classification'] == 'moderate_run'
                    else:
                        assert result['classification'] == 'easy_run'
                
            finally:
                loop.close()
    
    @given(
        streams_data=streams_data_strategy(),
        activity_data=activity_data_strategy()
    )
    @settings(max_examples=50, deadline=None)
    def test_pattern_analysis_consistency(
        self, 
        streams_data: Dict[str, Any], 
        activity_data: Dict[str, Any]
    ):
        """
        Property: For the same input data, pattern analysis should return consistent results
        """
        if not ContentGenerationAgent:
            pytest.skip("ContentGenerationAgent not available")
        
        # Assume valid data constraints
        assume(len(streams_data['velocity_smooth']) >= 5)
        assume(activity_data['distance'] > 0)
        assume(activity_data['moving_time'] > 0)
        
        with mock_bedrock_client() as mock_client:
            agent = ContentGenerationAgent(region='eu-west-1')
            agent.bedrock = mock_client
            
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Run analysis twice with same data
                result1 = loop.run_until_complete(
                    agent.analyze_patterns(streams_data, activity_data)
                )
                result2 = loop.run_until_complete(
                    agent.analyze_patterns(streams_data, activity_data)
                )
                
                # Results should be consistent
                assert result1['patterns'] == result2['patterns']
                assert result1['classification'] == result2['classification']
                assert result1['effort_zones'] == result2['effort_zones']
                assert result1['intervals_count'] == result2['intervals_count']
                
            finally:
                loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])