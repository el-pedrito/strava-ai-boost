"""
Tests for utility class integration functionality.
Validates Requirements 8.1, 8.4, 10.1, 10.2, 10.3, 10.4 from Task 7.2
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
import asyncio

from src.utils.integration import IntegratedStravaClient, SystemMonitor
from src.utils.data_transformers import StravaDataTransformer
from src.utils.monitoring import CloudWatchMetrics, SystemHealthMonitor
from src.utils.data_models import ActivityData, StreamsData, ProcessingError


class TestIntegratedStravaClient:
    """Test integrated Strava client with rate limiting and OAuth"""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing"""
        oauth_handler = Mock()
        rate_limiter = AsyncMock()
        strava_client = AsyncMock()
        
        return oauth_handler, rate_limiter, strava_client
    
    @pytest.fixture
    def integrated_client(self, mock_dependencies):
        """Create integrated client with mocked dependencies"""
        oauth_handler, rate_limiter, strava_client = mock_dependencies
        
        with patch('src.utils.integration.StravaOAuthHandler', return_value=oauth_handler), \
             patch('src.utils.integration.StravaRateLimiter', return_value=rate_limiter), \
             patch('src.utils.integration.StravaAPIClient', return_value=strava_client):
            
            client = IntegratedStravaClient()
            return client, oauth_handler, rate_limiter, strava_client
    
    @pytest.mark.asyncio
    async def test_get_activity_with_rate_limiting(self, integrated_client):
        """Test activity retrieval with rate limiting"""
        client, oauth_handler, rate_limiter, strava_client = integrated_client
        
        # Setup mocks
        rate_limiter.check_and_wait.return_value = True
        strava_client.get_activity.return_value = {
            "id": "12345",
            "name": "Test Run",
            "type": "Run",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "total_elevation_gain": 100.0,
            "start_date": "2023-12-01T10:00:00Z"
        }
        
        # Test activity retrieval
        activity = await client.get_activity("12345")
        
        # Verify rate limiting was checked
        rate_limiter.check_and_wait.assert_called_once()
        
        # Verify activity was retrieved
        strava_client.get_activity.assert_called_once_with("12345")
        assert activity["id"] == "12345"
        assert activity["name"] == "Test Run"
    
    @pytest.mark.asyncio
    async def test_get_activity_streams_with_validation(self, integrated_client):
        """Test streams retrieval with data validation"""
        client, oauth_handler, rate_limiter, strava_client = integrated_client
        
        # Setup mocks
        rate_limiter.check_and_wait.return_value = True
        strava_client.get_activity_streams.return_value = {
            "velocity_smooth": [2.5, 2.7, 2.8],
            "heartrate": [140, 145, 150],
            "time": [0, 1, 2],
            "distance": [0.0, 2.5, 5.2],
            "altitude": [100.0, 101.0, 102.0]
        }
        
        # Test streams retrieval
        streams = await client.get_activity_streams("12345")
        
        # Verify rate limiting was checked
        rate_limiter.check_and_wait.assert_called_once()
        
        # Verify streams were retrieved
        strava_client.get_activity_streams.assert_called_once_with("12345")
        assert len(streams["velocity_smooth"]) == 3
        assert streams["heartrate"] == [140, 145, 150]
    
    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, integrated_client):
        """Test error handling and retry logic"""
        client, oauth_handler, rate_limiter, strava_client = integrated_client
        
        # Setup mocks - first call fails, second succeeds
        rate_limiter.check_and_wait.return_value = True
        strava_client.get_activity.side_effect = [
            Exception("Temporary error"),
            {
                "id": "12345",
                "name": "Test Run",
                "type": "Run",
                "distance": 5000.0,
                "moving_time": 1800,
                "elapsed_time": 1900,
                "total_elevation_gain": 100.0,
                "start_date": "2023-12-01T10:00:00Z"
            }
        ]
        
        # Test with retry logic
        activity = await client.get_activity_with_retry("12345", max_retries=2)
        
        # Verify retry was attempted
        assert strava_client.get_activity.call_count == 2
        assert activity["id"] == "12345"


class TestStravaDataTransformer:
    """Test data transformation and validation utilities"""
    
    @pytest.fixture
    def transformer(self):
        """Create data transformer instance"""
        return StravaDataTransformer()
    
    def test_transform_activity_data(self, transformer):
        """Test activity data transformation"""
        raw_data = {
            "id": 12345,  # Integer ID
            "name": "Test Run",
            "type": "Run",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "total_elevation_gain": 100.0,
            "start_date": "2023-12-01T10:00:00Z",  # String date
            "average_speed": None,  # Null value
            "description": ""  # Empty description
        }
        
        # Transform data
        activity = transformer.transform_activity_data(raw_data)
        
        # Verify transformations
        assert isinstance(activity, ActivityData)
        assert activity.id == "12345"  # Converted to string
        assert activity.description is None  # Empty string converted to None
        assert isinstance(activity.start_date, datetime)
    
    def test_transform_streams_data(self, transformer):
        """Test streams data transformation"""
        raw_streams = {
            "velocity_smooth": {"data": [2.5, 2.7, 2.8]},
            "heartrate": {"data": [140, 145, 150]},
            "time": {"data": [0, 1, 2]},
            "distance": {"data": [0.0, 2.5, 5.2]},
            "altitude": {"data": [100.0, 101.0, 102.0]}
        }
        
        # Transform streams
        streams = transformer.transform_streams_data(raw_streams)
        
        # Verify transformation
        assert isinstance(streams, StreamsData)
        assert streams.velocity_smooth == [2.5, 2.7, 2.8]
        assert streams.heartrate == [140, 145, 150]
    
    def test_validate_and_sanitize_data(self, transformer):
        """Test data validation and sanitization"""
        raw_data = {
            "id": "12345",
            "name": "Test Run",
            "type": "Run",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "total_elevation_gain": 100.0,
            "start_date": "2023-12-01T10:00:00Z",
            "malicious_field": "<script>alert('xss')</script>",  # Should be sanitized
            "null_field": None,
            "empty_field": ""
        }
        
        # Validate and sanitize
        clean_data = transformer.validate_and_sanitize(raw_data)
        
        # Verify sanitization
        assert "malicious_field" not in clean_data or "<script>" not in str(clean_data.get("malicious_field", ""))
        assert clean_data["id"] == "12345"
        assert clean_data["name"] == "Test Run"


class TestSystemMonitor:
    """Test system monitoring and health checks"""
    
    @pytest.fixture
    def mock_cloudwatch(self):
        """Create mock CloudWatch metrics"""
        return Mock()
    
    @pytest.fixture
    def system_monitor(self, mock_cloudwatch):
        """Create system monitor with mocked CloudWatch"""
        with patch('src.utils.integration.CloudWatchMetrics', return_value=mock_cloudwatch):
            monitor = SystemMonitor()
            return monitor, mock_cloudwatch
    
    @pytest.mark.asyncio
    async def test_health_check_all_services(self, system_monitor):
        """Test comprehensive health check"""
        monitor, mock_cloudwatch = system_monitor
        
        # Mock service health checks
        with patch.object(monitor, '_check_dynamodb_health', return_value=True), \
             patch.object(monitor, '_check_secrets_manager_health', return_value=True), \
             patch.object(monitor, '_check_bedrock_health', return_value=True), \
             patch.object(monitor, '_check_step_functions_health', return_value=True):
            
            health_status = await monitor.check_system_health()
            
            # Verify health check results
            assert health_status["overall_status"] == "healthy"
            assert health_status["services"]["dynamodb"] == "healthy"
            assert health_status["services"]["secrets_manager"] == "healthy"
            assert health_status["services"]["bedrock"] == "healthy"
            assert health_status["services"]["step_functions"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_health_check_with_failures(self, system_monitor):
        """Test health check with service failures"""
        monitor, mock_cloudwatch = system_monitor
        
        # Mock service health checks with failures
        with patch.object(monitor, '_check_dynamodb_health', return_value=False), \
             patch.object(monitor, '_check_secrets_manager_health', return_value=True), \
             patch.object(monitor, '_check_bedrock_health', return_value=True), \
             patch.object(monitor, '_check_step_functions_health', return_value=False):
            
            health_status = await monitor.check_system_health()
            
            # Verify health check results
            assert health_status["overall_status"] == "degraded"
            assert health_status["services"]["dynamodb"] == "unhealthy"
            assert health_status["services"]["step_functions"] == "unhealthy"
            assert health_status["services"]["secrets_manager"] == "healthy"
    
    def test_performance_metrics_collection(self, system_monitor):
        """Test performance metrics collection"""
        monitor, mock_cloudwatch = system_monitor
        
        # Test metrics collection
        metrics = monitor.collect_performance_metrics()
        
        # Verify metrics structure
        assert "timestamp" in metrics
        assert "memory_usage" in metrics
        assert "cpu_usage" in metrics
        assert "active_connections" in metrics
        
        # Verify CloudWatch integration
        mock_cloudwatch.put_metric.assert_called()


class TestMonitoringIntegration:
    """Test monitoring and alerting integration"""
    
    @pytest.fixture
    def health_monitor(self):
        """Create system health monitor instance"""
        return SystemHealthMonitor()
    
    @pytest.mark.asyncio
    async def test_error_alert_generation(self, health_monitor):
        """Test error alert generation"""
        error = ProcessingError(
            message="Failed to process activity",
            error_type="api",
            error_code="FETCH_FAILED",
            retry_count=3,
            details={"status_code": 500}
        )
        
        # Generate alert
        alert_created = health_monitor.create_alert(
            alert_id="test_error_123",
            severity=health_monitor.AlertSeverity.ERROR if hasattr(health_monitor, 'AlertSeverity') else "error",
            title="Processing Error",
            message=error.message,
            component="activity_processor",
            metadata={"error_code": error.error_code}
        )
        
        # Verify alert was created
        assert alert_created is True
    
    @pytest.mark.asyncio
    async def test_performance_metrics_collection(self, health_monitor):
        """Test performance metrics collection"""
        # Test basic health monitoring functionality
        health_summary = health_monitor.get_system_health_summary()
        
        # Verify health summary structure
        assert "overall_health" in health_summary
        assert "active_alerts_count" in health_summary
        assert "last_updated" in health_summary


if __name__ == "__main__":
    pytest.main([__file__])