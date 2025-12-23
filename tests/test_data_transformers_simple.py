"""
Simple tests for data transformation functionality.
Validates Requirements 8.1, 8.4 from Task 7.2
"""

import pytest
from datetime import datetime, timezone
from src.utils.data_transformers import StravaDataTransformer, DataQualityReport
from src.utils.data_models import ActivityData, StreamsData


class TestStravaDataTransformer:
    """Test data transformation utilities"""
    
    @pytest.fixture
    def transformer(self):
        """Create data transformer instance"""
        return StravaDataTransformer()
    
    def test_data_quality_report_creation(self):
        """Test data quality report creation"""
        report = DataQualityReport(
            overall_score=0.85,
            issues=["Missing heart rate data"],
            warnings=["GPS accuracy low"],
            recommendations=["Enable heart rate monitor"],
            field_completeness={"distance": 1.0, "heartrate": 0.0},
            data_consistency={"time_sequence": True, "distance_monotonic": True}
        )
        
        assert report.overall_score == 0.85
        assert len(report.issues) == 1
        assert report.field_completeness["distance"] == 1.0
        assert report.data_consistency["time_sequence"] is True
    
    def test_transformer_initialization(self, transformer):
        """Test transformer initialization"""
        assert transformer is not None
        assert isinstance(transformer, StravaDataTransformer)


class TestDataValidation:
    """Test data validation functionality"""
    
    def test_activity_data_validation_success(self):
        """Test successful activity data validation"""
        valid_activity = ActivityData(
            id=12345,
            name="Test Run",
            type="Run",
            start_date=datetime.now(timezone.utc),
            start_date_local=datetime.now(timezone.utc),
            timezone="America/Montreal",
            distance=5000.0,
            moving_time=1800,
            elapsed_time=1900,
            resource_state=2
        )
        
        # Verify the activity is valid
        assert valid_activity.id == 12345
        assert valid_activity.distance == 5000.0
        assert valid_activity.type == "Run"
    
    def test_streams_data_validation_success(self):
        """Test successful streams data validation"""
        valid_streams = StreamsData(
            time=[0, 1, 2, 3],
            distance=[0.0, 10.0, 20.0, 30.0],
            velocity_smooth=[0.0, 2.5, 2.7, 2.8],
            altitude=[100.0, 101.0, 102.0, 103.0]
        )
        
        # Verify the streams are valid
        assert len(valid_streams.time) == 4
        assert len(valid_streams.distance) == 4
        assert valid_streams.velocity_smooth[1] == 2.5


if __name__ == "__main__":
    pytest.main([__file__])