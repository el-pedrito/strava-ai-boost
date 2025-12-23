"""
Data Models for Strava AI Boost

Pydantic models for type safety and validation across the system.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from datetime import datetime


class ActivityData(BaseModel):
    """Strava activity data model with 67+ fields"""
    
    model_config = ConfigDict()
    
    # Core activity fields
    id: str
    name: str
    description: Optional[str] = None
    type: Literal['Run', 'Ride', 'Swim', 'Workout', 'Hike', 'Walk'] = 'Run'
    
    # Performance metrics
    distance: float = Field(ge=0, description="Distance in meters")
    moving_time: int = Field(ge=0, description="Moving time in seconds")
    elapsed_time: int = Field(ge=0, description="Elapsed time in seconds")
    total_elevation_gain: float = Field(ge=0, description="Elevation gain in meters")
    
    # Timing
    start_date: datetime
    start_date_local: Optional[datetime] = None
    timezone: Optional[str] = None
    
    # Location
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    end_latitude: Optional[float] = None
    end_longitude: Optional[float] = None
    
    # Performance data
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    
    # Effort and zones
    suffer_score: Optional[int] = None
    perceived_exertion: Optional[int] = None
    
    # Social engagement
    kudos_count: int = 0
    comment_count: int = 0
    athlete_count: int = 1
    
    # Equipment and conditions
    gear_id: Optional[str] = None
    average_temp: Optional[float] = None
    
    # Additional Strava fields (67+ total)
    achievement_count: int = 0
    pr_count: int = 0
    calories: Optional[float] = None
    device_watts: Optional[bool] = None
    has_heartrate: bool = False
    has_kudoed: bool = False
    
    @field_serializer('start_date', 'start_date_local')
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format"""
        return value.isoformat() if value else None


class StreamsData(BaseModel):
    """Strava streams data model for second-by-second analysis"""
    
    velocity_smooth: List[float] = Field(description="Smoothed velocity in m/s")
    heartrate: List[int] = Field(description="Heart rate in BPM")
    time: List[int] = Field(description="Time in seconds from start")
    distance: List[float] = Field(description="Distance in meters")
    altitude: List[float] = Field(description="Altitude in meters")
    
    # Optional streams
    cadence: Optional[List[int]] = None
    watts: Optional[List[int]] = None
    temp: Optional[List[float]] = None
    
    def __len__(self) -> int:
        """Return the number of data points"""
        return len(self.time)
    
    @property
    def duration_seconds(self) -> int:
        """Get total duration in seconds"""
        return max(self.time) if self.time else 0


class ProcessingStatus(BaseModel):
    """Activity processing status tracking"""
    
    model_config = ConfigDict()
    
    activity_id: str
    user_id: str
    status: Literal['queued', 'processing', 'completed', 'failed'] = 'queued'
    step: str = 'initial'
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    modules_active: List[str] = []
    processing_time_ms: Optional[int] = None
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime) -> str:
        """Serialize timestamp to ISO format"""
        return value.isoformat()


class ModuleConfig(BaseModel):
    """Module configuration model"""
    
    model_config = ConfigDict()
    
    module_id: str
    name: str
    description: str
    enabled: bool = False
    configured: bool = False
    requires_credentials: bool = False
    credentials: Optional[Dict[str, str]] = None
    settings: Dict[str, Any] = {}
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    
    @field_serializer('last_updated')
    def serialize_last_updated(self, value: datetime) -> str:
        """Serialize last_updated to ISO format"""
        return value.isoformat()


class ModuleInsight(BaseModel):
    """Module analysis result"""
    
    module_id: str
    insights: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = {}
    processing_time_ms: Optional[int] = None
    
    def is_high_confidence(self, threshold: float = 0.7) -> bool:
        """Check if confidence is above threshold"""
        return self.confidence >= threshold


class EnhancedContent(BaseModel):
    """Generated enhanced content for Strava activity"""
    
    title: str
    description: str
    style_elements: List[str] = []
    modules_used: List[str] = []
    generation_time_ms: Optional[int] = None
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    
    # Content metadata
    word_count: Optional[int] = None
    sentiment: Optional[str] = None
    technical_terms: List[str] = []


class StravaRateLimit(BaseModel):
    """Strava API rate limit tracking"""
    
    model_config = ConfigDict()
    
    limit_type: Literal['short_term', 'daily'] = 'short_term'
    current_usage: int = Field(ge=0)
    limit: int = Field(gt=0)
    reset_time: datetime
    last_request: datetime = Field(default_factory=datetime.utcnow)
    
    @field_serializer('reset_time', 'last_request')
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime to ISO format"""
        return value.isoformat()
    
    @property
    def usage_percentage(self) -> float:
        """Get usage as percentage of limit"""
        return (self.current_usage / self.limit) * 100
    
    @property
    def is_near_limit(self, threshold: float = 80.0) -> bool:
        """Check if usage is near the limit"""
        return self.usage_percentage >= threshold


class CampusCoachSession(BaseModel):
    """Campus Coach training session model"""
    
    model_config = ConfigDict()
    
    session_id: str
    session_date: str  # YYYY-MM-DD format
    week_number: str
    session_type: str
    duration: Optional[str] = None
    description: str
    intervals: Optional[str] = None
    target_pace: Optional[str] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_serializer('extracted_at')
    def serialize_extracted_at(self, value: datetime) -> str:
        """Serialize extracted_at to ISO format"""
        return value.isoformat()


class SystemStatus(BaseModel):
    """Overall system status"""
    
    model_config = ConfigDict()
    
    strava_connected: bool = False
    agentcore_status: Literal['healthy', 'degraded', 'unhealthy'] = 'unhealthy'
    processing_queue_depth: int = 0
    last_activity_processed: Optional[datetime] = None
    success_rate_24h: float = Field(ge=0.0, le=100.0, default=0.0)
    
    # Enhancement control
    enhancement_enabled: bool = True
    enhancement_paused_at: Optional[datetime] = None
    
    # Component status
    lambda_functions_healthy: bool = True
    dynamodb_healthy: bool = True
    step_functions_healthy: bool = True
    
    @field_serializer('last_activity_processed', 'enhancement_paused_at')
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format"""
        return value.isoformat() if value else None
    
    @property
    def is_paused(self) -> bool:
        """Check if enhancement is currently paused"""
        return not self.enhancement_enabled
    
    @property
    def pause_duration_hours(self) -> Optional[float]:
        """Get duration in hours since enhancement was paused"""
        if self.enhancement_paused_at and not self.enhancement_enabled:
            return (datetime.utcnow() - self.enhancement_paused_at).total_seconds() / 3600
        return None