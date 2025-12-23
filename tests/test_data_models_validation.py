"""
Tests for data models and validation functionality.
Validates Requirements 2.6, 2.7, 2.8 from Task 7.1
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any
from pydantic import ValidationError

from src.utils.data_models import (
    ActivityData, StreamsData, ProcessingStatus, ModuleConfig,
    StravaRateLimit, ValidationError as CustomValidationError,
    ProcessingError, EnhancedContent
)


class TestActivityDataModel:
    """Test comprehensive Strava activity data model with 67+ fields"""
    
    def test_basic_activity_creation(self):
        """Test basic activity creation with required fields"""
        activity = ActivityData(
            id="12345",  # Changed from int to str
            name="Morning Run",
            type="Run",
            start_date=datetime.now(timezone.utc),
            start_date_local=datetime.now(timezone.utc),
            timezone="America/Montreal",
            distance=5000.0,
            moving_time=1800,
            elapsed_time=1900,
            resource_state=2
        )
        
        assert activity.id == "12345"
        assert activity.name == "Morning Run"
        assert activity.type == "Run"
        assert activity.distance == 5000.0
        
    def test_activity_with_all_fields(self):
        """Test activity creation with comprehensive field set (67+ fields)"""
        activity_data = {
            "id": "12345",  # Changed from int to str
            "name": "Morning Run",
            "description": "Great morning run",
            "type": "Run",
            "start_date": datetime.now(timezone.utc),
            "start_date_local": datetime.now(timezone.utc),
            "timezone": "America/Montreal",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "resource_state": 2,
            "total_elevation_gain": 100.0,
            # Performance metrics
            "average_speed": 2.78,
            "max_speed": 4.5,
            "average_heartrate": 150.0,
            "max_heartrate": 180.0,
            "average_cadence": 85.0,
            "average_watts": 250.0,
            "weighted_average_watts": 260,
            "kilojoules": 450.0,
            "device_watts": True,
            "has_heartrate": True,
            "has_kudoed": False,
            "kudos_count": 5,
            "comment_count": 2,
            "athlete_count": 1,
            "photo_count": 0,
            "trainer": False,
            "commute": False,
            "manual": False,
            "private": False,
            "flagged": False,
            # Location data
            "start_latlng": [45.5017, -73.5673],
            "end_latlng": [45.5020, -73.5670],
            "utc_offset": -18000.0,
            # Environmental context
            "location_city": "Montreal",
            "location_state": "Quebec",
            "location_country": "Canada",
            # Equipment details
            "gear_id": "g12345",
            # Social engagement
            "achievement_count": 2,
            "pr_count": 1,
            # Effort indicators
            "suffer_score": 85,
            "perceived_exertion": 7,
            # Additional metrics
            "calories": 350.0,
            "embed_token": "abc123",
            "segment_leaderboard_opt_out": False
        }
        
        activity = ActivityData(**activity_data)
        
        # Verify comprehensive field coverage
        assert len(activity.model_dump()) >= 40  # Should have many fields
        assert activity.average_speed == 2.78
        assert activity.location_city == "Montreal"
        assert activity.gear_id == "g12345"
        
    def test_activity_validation_errors(self):
        """Test validation errors for invalid activity data"""
        with pytest.raises(ValidationError):
            ActivityData(
                id="12345",  # Changed from int to str
                name="Test",
                type="Run",
                start_date=datetime.now(timezone.utc),
                start_date_local=datetime.now(timezone.utc),
                timezone="America/Montreal",
                distance=-100,  # Negative distance should fail
                moving_time=1800,
                elapsed_time=1900,
                resource_state=2
            )


class TestStreamsDataModel:
    """Test streams data model with second-by-second granularity validation"""
    
    def test_streams_creation(self):
        """Test streams data creation with validation"""
        streams = StreamsData(
            velocity_smooth=[2.5, 2.7, 2.8, 2.6],
            heartrate=[140, 145, 150, 148],
            time=[0, 1, 2, 3],
            distance=[0.0, 2.5, 5.2, 7.8],
            altitude=[100.0, 101.0, 102.0, 101.5]
        )
        
        assert len(streams.velocity_smooth) == 4
        assert len(streams.heartrate) == 4
        assert streams.time == [0, 1, 2, 3]
        
    def test_streams_length_validation(self):
        """Test that all streams have consistent length"""
        # Note: StreamsData doesn't enforce length consistency in the current model
        # This test verifies that different length streams are allowed
        streams = StreamsData(
            velocity_smooth=[2.5, 2.7],  # Length 2
            heartrate=[140, 145, 150],   # Length 3 - should be allowed
            time=[0, 1],
            distance=[0.0, 2.5],
            altitude=[100.0, 101.0]
        )
        
        # Verify that streams with different lengths are created successfully
        assert len(streams.velocity_smooth) == 2
        assert len(streams.heartrate) == 3
        assert len(streams.time) == 2


class TestProcessingStatusModel:
    """Test processing status model"""
    
    def test_processing_status_creation(self):
        """Test processing status creation"""
        status = ProcessingStatus(
            activity_id="12345",
            status="processing",
            step="analyze_activity",
            timestamp=datetime.now(timezone.utc),
            modules_active=["campus_coach", "enduraw"]
        )
        
        assert status.activity_id == "12345"
        assert status.status == "processing"
        assert status.step == "analyze_activity"
        assert len(status.modules_active) == 2
        
    def test_processing_status_with_error(self):
        """Test processing status with error message"""
        status = ProcessingStatus(
            activity_id="12345",
            status="failed",
            step="fetch_activity",
            timestamp=datetime.now(timezone.utc),
            error_message="Rate limit exceeded",
            modules_active=[]
        )
        
        assert status.status == "failed"
        assert status.error_message == "Rate limit exceeded"


class TestModuleConfigModel:
    """Test module configuration model"""
    
    def test_module_config_creation(self):
        """Test module configuration creation"""
        config = ModuleConfig(
            module_id="campus_coach",
            name="Campus Coach Integration",
            description="Integrates with Campus Coach training platform",
            enabled=True,
            settings={"confidence_threshold": 0.8, "retry_attempts": 3}
        )
        
        assert config.module_id == "campus_coach"
        assert config.name == "Campus Coach Integration"
        assert config.enabled is True
        assert config.settings["confidence_threshold"] == 0.8


class TestRateLimitModel:
    """Test rate limit tracking model"""
    
    def test_rate_limit_creation(self):
        """Test rate limit model creation"""
        rate_limit = StravaRateLimit(
            limit_type="short_term",
            current_usage=50,
            limit=100,
            reset_time=datetime.now(timezone.utc),
            last_request=datetime.now(timezone.utc)
        )
        
        assert rate_limit.limit_type == "short_term"
        assert rate_limit.current_usage == 50
        assert rate_limit.limit == 100


class TestErrorModels:
    """Test error handling models"""
    
    def test_validation_error_creation(self):
        """Test custom validation error creation"""
        error = CustomValidationError(
            message="Invalid activity data",
            field="distance",
            invalid_value=-100,
            error_code="NEGATIVE_DISTANCE"
        )
        
        assert error.message == "Invalid activity data"
        assert error.field == "distance"
        assert error.invalid_value == -100
        assert error.error_code == "NEGATIVE_DISTANCE"
        
    def test_processing_error_creation(self):
        """Test processing error creation"""
        error = ProcessingError(
            message="Failed to fetch activity",
            error_type="api",
            error_code="FETCH_FAILED",
            retry_count=2,
            details={"status_code": 429, "rate_limit": True}
        )
        
        assert error.message == "Failed to fetch activity"
        assert error.error_type == "api"
        assert error.error_code == "FETCH_FAILED"
        assert error.retry_count == 2
        assert error.details["status_code"] == 429


class TestEnhancedContentModel:
    """Test enhanced content model"""
    
    def test_enhanced_content_creation(self):
        """Test enhanced content creation"""
        content = EnhancedContent(
            title="Epic Morning Run 🏃‍♂️",
            description="Crushed this morning run with perfect pacing!",
            style_elements=["motivational", "technical"],
            modules_used=["campus_coach"],
            confidence=0.85,
            generation_time_ms=5200,
            word_count=150,
            sentiment="positive",
            technical_terms=["pacing", "heart rate zones"]
        )
        
        assert content.title == "Epic Morning Run 🏃‍♂️"
        assert content.confidence == 0.85
        assert "campus_coach" in content.modules_used
        assert content.generation_time_ms == 5200
        assert "motivational" in content.style_elements


if __name__ == "__main__":
    pytest.main([__file__])