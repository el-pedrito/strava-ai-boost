"""
Data Models for Strava AI Boost

Comprehensive Pydantic models for type safety and validation across the system.
Implements Requirements 2.6, 2.7, 2.8 for complete Strava data handling.
"""

from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, ConfigDict, field_serializer, field_validator
from datetime import datetime, UTC
import re


class LatLng(BaseModel):
    """Latitude/Longitude coordinate pair"""
    latitude: float = Field(ge=-90, le=90, description="Latitude in degrees")
    longitude: float = Field(ge=-180, le=180, description="Longitude in degrees")


class PolylineMap(BaseModel):
    """Strava polyline map data"""
    id: str
    polyline: Optional[str] = None
    summary_polyline: Optional[str] = None
    resource_state: int = Field(ge=1, le=3, description="Resource state level")


class Gear(BaseModel):
    """Strava gear information"""
    id: str
    name: str
    nickname: Optional[str] = None
    resource_state: int = Field(ge=1, le=3)
    retired: bool = False
    distance: Optional[float] = None  # Total distance in meters
    brand_name: Optional[str] = None
    model_name: Optional[str] = None
    frame_type: Optional[int] = None
    description: Optional[str] = None


class SplitMetric(BaseModel):
    """Split metrics for activities"""
    distance: float = Field(ge=0, description="Split distance in meters")
    elapsed_time: int = Field(ge=0, description="Elapsed time in seconds")
    elevation_difference: Optional[float] = None
    moving_time: int = Field(ge=0, description="Moving time in seconds")
    split: int = Field(ge=1, description="Split number")
    average_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    pace_zone: Optional[int] = None


class Lap(BaseModel):
    """Activity lap data"""
    id: int
    name: str
    activity: Dict[str, Any]  # Reference to parent activity
    athlete: Dict[str, Any]   # Reference to athlete
    elapsed_time: int = Field(ge=0)
    moving_time: int = Field(ge=0)
    start_date: datetime
    start_date_local: datetime
    distance: float = Field(ge=0)
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    total_elevation_gain: Optional[float] = None
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    lap_index: int = Field(ge=0)
    split: int = Field(ge=1)
    
    @field_serializer('start_date', 'start_date_local')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()


class ActivityData(BaseModel):
    """
    Comprehensive Strava activity data model with 67+ fields.
    
    Covers all major Strava activity fields including performance metrics,
    environmental context, social engagement, and equipment details.
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='allow'  # Allow additional fields from Strava API
    )
    
    # === CORE ACTIVITY FIELDS ===
    id: str = Field(description="Unique Strava activity ID")  # Changed from int to str
    external_id: Optional[str] = Field(None, description="External activity ID from device")
    upload_id: Optional[int] = Field(None, description="Upload ID")
    name: str = Field(description="Activity name/title")
    description: Optional[str] = Field(None, description="Activity description")
    type: str = Field(description="Activity type (Run, Ride, Swim, etc.)")
    sport_type: Optional[str] = Field(None, description="Specific sport type")
    workout_type: Optional[int] = Field(None, description="Workout type code")
    
    # === TIMING FIELDS ===
    start_date: datetime = Field(description="Activity start time (UTC)")
    start_date_local: datetime = Field(description="Activity start time (local)")
    timezone: str = Field(description="Timezone string")
    utc_offset: Optional[float] = Field(None, description="UTC offset in seconds")
    
    # === DISTANCE AND DURATION ===
    distance: float = Field(ge=0, description="Total distance in meters")
    moving_time: int = Field(ge=0, description="Moving time in seconds")
    elapsed_time: int = Field(ge=0, description="Total elapsed time in seconds")
    
    # === ELEVATION ===
    total_elevation_gain: Optional[float] = Field(None, ge=0, description="Total elevation gain in meters")
    elev_high: Optional[float] = Field(None, description="Highest elevation in meters")
    elev_low: Optional[float] = Field(None, description="Lowest elevation in meters")
    
    # === SPEED METRICS ===
    average_speed: Optional[float] = Field(None, ge=0, description="Average speed in m/s")
    max_speed: Optional[float] = Field(None, ge=0, description="Maximum speed in m/s")
    
    # === HEART RATE ===
    has_heartrate: bool = Field(False, description="Activity has heart rate data")
    average_heartrate: Optional[float] = Field(None, ge=0, le=300, description="Average heart rate in BPM")
    max_heartrate: Optional[float] = Field(None, ge=0, le=300, description="Maximum heart rate in BPM")
    heartrate_opt_out: Optional[bool] = Field(None, description="Heart rate data opt-out")
    display_hide_heartrate_option: Optional[bool] = Field(None, description="Hide heart rate option")
    
    # === POWER DATA ===
    has_kudoed: bool = Field(False, description="Current user has kudoed this activity")
    device_watts: Optional[bool] = Field(None, description="Activity recorded with power meter")
    average_watts: Optional[float] = Field(None, ge=0, description="Average power in watts")
    weighted_average_watts: Optional[int] = Field(None, ge=0, description="Weighted average power")
    kilojoules: Optional[float] = Field(None, ge=0, description="Total energy in kilojoules")
    
    # === CADENCE ===
    average_cadence: Optional[float] = Field(None, ge=0, description="Average cadence")
    
    # === TEMPERATURE ===
    average_temp: Optional[int] = Field(None, description="Average temperature in Celsius")
    
    # === LOCATION DATA ===
    start_latlng: Optional[List[float]] = Field(None, description="Start coordinates [lat, lng]")
    end_latlng: Optional[List[float]] = Field(None, description="End coordinates [lat, lng]")
    location_city: Optional[str] = Field(None, description="Activity city")
    location_state: Optional[str] = Field(None, description="Activity state/region")
    location_country: Optional[str] = Field(None, description="Activity country")
    
    # === SOCIAL ENGAGEMENT ===
    kudos_count: int = Field(0, ge=0, description="Number of kudos received")
    comment_count: int = Field(0, ge=0, description="Number of comments")
    athlete_count: int = Field(1, ge=1, description="Number of athletes (for group activities)")
    photo_count: int = Field(0, ge=0, description="Number of photos")
    
    # === ACHIEVEMENTS ===
    achievement_count: int = Field(0, ge=0, description="Number of achievements earned")
    pr_count: int = Field(0, ge=0, description="Number of personal records set")
    segment_efforts: Optional[List[Dict[str, Any]]] = Field(None, description="Segment effort data")
    
    # === EFFORT AND TRAINING ===
    suffer_score: Optional[int] = Field(None, ge=0, description="Strava suffer score")
    perceived_exertion: Optional[int] = Field(None, ge=1, le=10, description="Rate of perceived exertion")
    calories: Optional[float] = Field(None, ge=0, description="Estimated calories burned")
    
    # === EQUIPMENT ===
    gear_id: Optional[str] = Field(None, description="Associated gear ID")
    gear: Optional[Gear] = Field(None, description="Gear details")
    
    # === PRIVACY AND VISIBILITY ===
    private: bool = Field(False, description="Activity is private")
    visibility: Optional[str] = Field(None, description="Activity visibility setting")
    flagged: bool = Field(False, description="Activity has been flagged")
    
    # === TRAINING DATA ===
    trainer: bool = Field(False, description="Activity was done on trainer")
    commute: bool = Field(False, description="Activity was a commute")
    manual: bool = Field(False, description="Activity was manually entered")
    
    # === MAPS AND ROUTES ===
    map: Optional[PolylineMap] = Field(None, description="Activity map data")
    
    # === SPLITS ===
    splits_metric: Optional[List[SplitMetric]] = Field(None, description="Metric splits (km)")
    splits_standard: Optional[List[SplitMetric]] = Field(None, description="Standard splits (miles)")
    
    # === LAPS ===
    laps: Optional[List[Lap]] = Field(None, description="Activity laps")
    
    # === BEST EFFORTS ===
    best_efforts: Optional[List[Dict[str, Any]]] = Field(None, description="Best effort segments")
    
    # === RESOURCE STATE ===
    resource_state: int = Field(ge=1, le=3, description="Resource detail level")
    
    # === ADDITIONAL METADATA ===
    embed_token: Optional[str] = Field(None, description="Embed token for sharing")
    from_accepted_tag: Optional[bool] = Field(None, description="Created from accepted tag")
    segment_leaderboard_opt_out: Optional[bool] = Field(None, description="Opted out of segment leaderboards")
    leaderboard_opt_out: Optional[bool] = Field(None, description="Opted out of leaderboards")
    
    # === INSTAGRAM AND SOCIAL ===
    instagram_primary_photo: Optional[str] = Field(None, description="Primary Instagram photo")
    partner_logo_url: Optional[str] = Field(None, description="Partner logo URL")
    partner_brand_tag: Optional[str] = Field(None, description="Partner brand tag")
    
    # === DEVICE INFO ===
    device_name: Optional[str] = Field(None, description="Recording device name")
    
    # === WEATHER (if available) ===
    weather_conditions: Optional[str] = Field(None, description="Weather conditions")
    wind_speed: Optional[float] = Field(None, description="Wind speed")
    wind_direction: Optional[int] = Field(None, description="Wind direction in degrees")
    humidity: Optional[float] = Field(None, description="Humidity percentage")
    
    @field_validator('start_latlng', 'end_latlng')
    @classmethod
    def validate_latlng(cls, v):
        """Validate lat/lng coordinates"""
        if v is not None:
            if len(v) != 2:
                raise ValueError("Coordinates must be [latitude, longitude]")
            lat, lng = v
            if not (-90 <= lat <= 90):
                raise ValueError("Latitude must be between -90 and 90")
            if not (-180 <= lng <= 180):
                raise ValueError("Longitude must be between -180 and 180")
        return v
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v):
        """Validate timezone format"""
        if v and not re.match(r'^\([A-Z]{3,4}\)\s+[A-Za-z_/]+$', v):
            # Allow flexible timezone formats from Strava
            pass
        return v
    
    @field_serializer('start_date', 'start_date_local')
    def serialize_datetime(self, value: datetime) -> str:
        """Serialize datetime to ISO format"""
        return value.isoformat()
    
    @property
    def start_latitude(self) -> Optional[float]:
        """Get start latitude from start_latlng"""
        return self.start_latlng[0] if self.start_latlng else None
    
    @property
    def start_longitude(self) -> Optional[float]:
        """Get start longitude from start_latlng"""
        return self.start_latlng[1] if self.start_latlng else None
    
    @property
    def end_latitude(self) -> Optional[float]:
        """Get end latitude from end_latlng"""
        return self.end_latlng[0] if self.end_latlng else None
    
    @property
    def end_longitude(self) -> Optional[float]:
        """Get end longitude from end_latlng"""
        return self.end_latlng[1] if self.end_latlng else None
    
    @property
    def pace_per_km(self) -> Optional[float]:
        """Calculate pace in minutes per kilometer"""
        if self.distance and self.moving_time and self.distance > 0:
            return (self.moving_time / 60) / (self.distance / 1000)
        return None
    
    @property
    def pace_per_mile(self) -> Optional[float]:
        """Calculate pace in minutes per mile"""
        if self.distance and self.moving_time and self.distance > 0:
            return (self.moving_time / 60) / (self.distance / 1609.34)
        return None
    
    @property
    def speed_kmh(self) -> Optional[float]:
        """Get average speed in km/h"""
        return self.average_speed * 3.6 if self.average_speed else None
    
    @property
    def speed_mph(self) -> Optional[float]:
        """Get average speed in mph"""
        return self.average_speed * 2.237 if self.average_speed else None
    
    @property
    def distance_km(self) -> float:
        """Get distance in kilometers"""
        return self.distance / 1000
    
    @property
    def distance_miles(self) -> float:
        """Get distance in miles"""
        return self.distance / 1609.34
    
    @property
    def moving_time_formatted(self) -> str:
        """Get moving time in HH:MM:SS format"""
        hours = self.moving_time // 3600
        minutes = (self.moving_time % 3600) // 60
        seconds = self.moving_time % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def has_location_data(self) -> bool:
        """Check if activity has GPS location data"""
        return bool(self.start_latlng or self.end_latlng)
    
    def has_power_data(self) -> bool:
        """Check if activity has power meter data"""
        return bool(self.device_watts and (self.average_watts or self.weighted_average_watts))
    
    def is_indoor_activity(self) -> bool:
        """Check if activity was performed indoors"""
        return self.trainer or not self.has_location_data()
    
    def get_activity_summary(self) -> Dict[str, Any]:
        """Get a summary of key activity metrics"""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'distance_km': round(self.distance_km, 2),
            'moving_time': self.moving_time_formatted,
            'average_speed_kmh': round(self.speed_kmh, 1) if self.speed_kmh else None,
            'elevation_gain': self.total_elevation_gain,
            'average_heartrate': self.average_heartrate,
            'kudos_count': self.kudos_count,
            'start_date_local': self.start_date_local.isoformat(),
            'has_power': self.has_power_data(),
            'is_indoor': self.is_indoor_activity()
        }


class StreamsData(BaseModel):
    """
    Comprehensive Strava streams data model for second-by-second analysis.
    
    Supports all major stream types with validation for data consistency
    and granular performance analysis.
    """
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra='allow'  # Allow additional stream types
    )
    
    # === CORE STREAMS (most common) ===
    time: List[int] = Field(description="Time in seconds from start", min_length=1)
    distance: List[float] = Field(description="Cumulative distance in meters", min_length=1)
    velocity_smooth: List[float] = Field(description="Smoothed velocity in m/s", min_length=1)
    
    # === LOCATION STREAMS ===
    latlng: Optional[List[List[float]]] = Field(None, description="GPS coordinates [[lat, lng], ...]")
    altitude: List[float] = Field(description="Altitude in meters", min_length=1)
    grade_smooth: Optional[List[float]] = Field(None, description="Smoothed grade percentage")
    
    # === PHYSIOLOGICAL STREAMS ===
    heartrate: Optional[List[int]] = Field(None, description="Heart rate in BPM")
    cadence: Optional[List[int]] = Field(None, description="Cadence (steps/min for running, RPM for cycling)")
    
    # === POWER STREAMS ===
    watts: Optional[List[int]] = Field(None, description="Power output in watts")
    watts_calc: Optional[List[int]] = Field(None, description="Calculated power in watts")
    
    # === ENVIRONMENTAL STREAMS ===
    temp: Optional[List[float]] = Field(None, description="Temperature in Celsius")
    
    # === MOVEMENT STREAMS ===
    moving: Optional[List[bool]] = Field(None, description="Moving state (true/false)")
    velocity: Optional[List[float]] = Field(None, description="Raw velocity in m/s")
    
    # === ADDITIONAL STREAMS ===
    left_right_balance: Optional[List[float]] = Field(None, description="Left/right power balance")
    left_torque_effectiveness: Optional[List[float]] = Field(None, description="Left leg torque effectiveness")
    right_torque_effectiveness: Optional[List[float]] = Field(None, description="Right leg torque effectiveness")
    left_pedal_smoothness: Optional[List[float]] = Field(None, description="Left pedal smoothness")
    right_pedal_smoothness: Optional[List[float]] = Field(None, description="Right pedal smoothness")
    
    @field_validator('time')
    @classmethod
    def validate_time_sequence(cls, v):
        """Validate time sequence is monotonically increasing"""
        if len(v) > 1:
            for i in range(1, len(v)):
                if v[i] < v[i-1]:
                    raise ValueError("Time sequence must be monotonically increasing")
        return v
    
    @field_validator('distance')
    @classmethod
    def validate_distance_sequence(cls, v):
        """Validate distance sequence is monotonically increasing"""
        if len(v) > 1:
            for i in range(1, len(v)):
                if v[i] < v[i-1]:
                    raise ValueError("Distance sequence must be monotonically increasing")
        return v
    
    @field_validator('latlng')
    @classmethod
    def validate_latlng_coordinates(cls, v):
        """Validate GPS coordinates"""
        if v is not None:
            for coord in v:
                if len(coord) != 2:
                    raise ValueError("Each coordinate must be [latitude, longitude]")
                lat, lng = coord
                if not (-90 <= lat <= 90):
                    raise ValueError(f"Invalid latitude: {lat}")
                if not (-180 <= lng <= 180):
                    raise ValueError(f"Invalid longitude: {lng}")
        return v
    
    @field_validator('heartrate')
    @classmethod
    def validate_heartrate(cls, v):
        """Validate heart rate values"""
        if v is not None:
            for hr in v:
                if hr < 0 or hr > 300:
                    raise ValueError(f"Invalid heart rate: {hr}")
        return v
    
    @field_validator('cadence')
    @classmethod
    def validate_cadence(cls, v):
        """Validate cadence values"""
        if v is not None:
            for cad in v:
                if cad < 0 or cad > 300:  # Reasonable upper bound
                    raise ValueError(f"Invalid cadence: {cad}")
        return v
    
    @field_validator('watts', 'watts_calc')
    @classmethod
    def validate_power(cls, v):
        """Validate power values"""
        if v is not None:
            for power in v:
                if power < 0 or power > 3000:  # Reasonable upper bound
                    raise ValueError(f"Invalid power: {power}")
        return v
    
    def __len__(self) -> int:
        """Return the number of data points"""
        return len(self.time)
    
    @property
    def duration_seconds(self) -> int:
        """Get total duration in seconds"""
        return max(self.time) if self.time else 0
    
    @property
    def total_distance_meters(self) -> float:
        """Get total distance in meters"""
        return max(self.distance) if self.distance else 0.0
    
    @property
    def has_gps_data(self) -> bool:
        """Check if streams contain GPS data"""
        return self.latlng is not None and len(self.latlng) > 0
    
    @property
    def has_heartrate_data(self) -> bool:
        """Check if streams contain heart rate data"""
        return self.heartrate is not None and len(self.heartrate) > 0
    
    @property
    def has_power_data(self) -> bool:
        """Check if streams contain power data"""
        return (self.watts is not None and len(self.watts) > 0) or \
               (self.watts_calc is not None and len(self.watts_calc) > 0)
    
    @property
    def has_cadence_data(self) -> bool:
        """Check if streams contain cadence data"""
        return self.cadence is not None and len(self.cadence) > 0
    
    @property
    def has_elevation_data(self) -> bool:
        """Check if streams contain elevation data"""
        return len(self.altitude) > 0
    
    @property
    def sample_rate_hz(self) -> Optional[float]:
        """Calculate average sample rate in Hz"""
        if len(self.time) < 2:
            return None
        
        total_time = self.time[-1] - self.time[0]
        if total_time <= 0:
            return None
        
        return (len(self.time) - 1) / total_time
    
    def get_data_quality_metrics(self) -> Dict[str, Any]:
        """Get data quality metrics for the streams"""
        metrics = {
            'total_points': len(self),
            'duration_seconds': self.duration_seconds,
            'sample_rate_hz': self.sample_rate_hz,
            'has_gps': self.has_gps_data,
            'has_heartrate': self.has_heartrate_data,
            'has_power': self.has_power_data,
            'has_cadence': self.has_cadence_data,
            'has_elevation': self.has_elevation_data
        }
        
        # Calculate data completeness
        if self.has_heartrate_data:
            valid_hr = sum(1 for hr in self.heartrate if hr and hr > 0)
            metrics['heartrate_completeness'] = valid_hr / len(self.heartrate)
        
        if self.has_power_data:
            power_data = self.watts or self.watts_calc
            valid_power = sum(1 for p in power_data if p and p > 0)
            metrics['power_completeness'] = valid_power / len(power_data)
        
        return metrics
    
    def get_time_slice(self, start_time: int, end_time: int) -> 'StreamsData':
        """
        Extract a time slice of the streams data.
        
        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
            
        Returns:
            New StreamsData object with sliced data
        """
        # Find indices for time range
        start_idx = None
        end_idx = None
        
        for i, t in enumerate(self.time):
            if start_idx is None and t >= start_time:
                start_idx = i
            if t <= end_time:
                end_idx = i + 1
        
        if start_idx is None or end_idx is None:
            raise ValueError(f"Time range {start_time}-{end_time} not found in data")
        
        # Slice all available streams
        sliced_data = {
            'time': self.time[start_idx:end_idx],
            'distance': self.distance[start_idx:end_idx],
            'velocity_smooth': self.velocity_smooth[start_idx:end_idx],
            'altitude': self.altitude[start_idx:end_idx]
        }
        
        # Add optional streams if present
        if self.latlng:
            sliced_data['latlng'] = self.latlng[start_idx:end_idx]
        if self.heartrate:
            sliced_data['heartrate'] = self.heartrate[start_idx:end_idx]
        if self.cadence:
            sliced_data['cadence'] = self.cadence[start_idx:end_idx]
        if self.watts:
            sliced_data['watts'] = self.watts[start_idx:end_idx]
        if self.temp:
            sliced_data['temp'] = self.temp[start_idx:end_idx]
        if self.moving:
            sliced_data['moving'] = self.moving[start_idx:end_idx]
        
        return StreamsData(**sliced_data)
    
    def calculate_intervals(self, min_duration: int = 30) -> List[Dict[str, Any]]:
        """
        Detect intervals in the activity based on pace/power changes.
        
        Args:
            min_duration: Minimum interval duration in seconds
            
        Returns:
            List of detected intervals with metrics
        """
        if len(self.time) < 2:
            return []
        
        intervals = []
        # This is a simplified interval detection - could be enhanced
        # with more sophisticated algorithms
        
        # For now, return basic segments based on time
        segment_duration = max(min_duration, self.duration_seconds // 10)
        
        for i in range(0, self.duration_seconds, segment_duration):
            start_time = i
            end_time = min(i + segment_duration, self.duration_seconds)
            
            if end_time - start_time >= min_duration:
                try:
                    segment = self.get_time_slice(start_time, end_time)
                    
                    # Calculate segment metrics
                    avg_speed = sum(segment.velocity_smooth) / len(segment.velocity_smooth)
                    avg_hr = None
                    if segment.has_heartrate_data:
                        valid_hr = [hr for hr in segment.heartrate if hr > 0]
                        avg_hr = sum(valid_hr) / len(valid_hr) if valid_hr else None
                    
                    intervals.append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'duration': end_time - start_time,
                        'average_speed': avg_speed,
                        'average_heartrate': avg_hr,
                        'distance': segment.total_distance_meters - (segment.distance[0] if segment.distance else 0)
                    })
                except ValueError:
                    continue
        
        return intervals


class ValidationError(BaseModel):
    """Validation error details"""
    field: str
    message: str
    invalid_value: Any
    error_code: str


class ProcessingError(BaseModel):
    """Processing error information"""
    error_type: Literal['validation', 'api', 'timeout', 'rate_limit', 'authentication', 'system'] = 'system'
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    retry_count: int = 0
    max_retries: int = 3
    is_retryable: bool = True
    
    @field_serializer('timestamp')
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()
    
    @property
    def can_retry(self) -> bool:
        """Check if error can be retried"""
        return self.is_retryable and self.retry_count < self.max_retries


class ProcessingStatus(BaseModel):
    """Activity processing status tracking with comprehensive error handling"""
    
    model_config = ConfigDict(
        validate_assignment=True
    )
    
    activity_id: str
    user_id: str = "default"
    status: Literal['queued', 'processing', 'completed', 'failed', 'paused'] = 'queued'
    step: str = 'initial'
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
    # Error handling
    error_message: Optional[str] = None
    error_details: Optional[ProcessingError] = None
    validation_errors: List[ValidationError] = []
    
    # Processing metadata
    modules_active: List[str] = []
    processing_time_ms: Optional[int] = None
    retry_count: int = 0
    
    # Step tracking
    steps_completed: List[str] = []
    current_step_start: Optional[datetime] = None
    
    # Performance metrics
    api_calls_made: int = 0
    tokens_used: Optional[int] = None
    cost_estimate: Optional[float] = None
    
    @field_serializer('timestamp', 'current_step_start')
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize timestamp to ISO format"""
        return value.isoformat() if value else None
    
    def start_step(self, step_name: str):
        """Mark the start of a processing step"""
        self.step = step_name
        self.current_step_start = datetime.now(UTC)
        self.status = 'processing'
    
    def complete_step(self, step_name: str):
        """Mark completion of a processing step"""
        if step_name not in self.steps_completed:
            self.steps_completed.append(step_name)
        
        if self.current_step_start:
            step_duration = (datetime.now(UTC) - self.current_step_start).total_seconds() * 1000
            if self.processing_time_ms is None:
                self.processing_time_ms = 0
            self.processing_time_ms += int(step_duration)
    
    def add_error(self, error: ProcessingError):
        """Add a processing error"""
        self.error_details = error
        self.error_message = error.message
        self.status = 'failed'
    
    def add_validation_error(self, field: str, message: str, invalid_value: Any, error_code: str = "VALIDATION_ERROR"):
        """Add a validation error"""
        validation_error = ValidationError(
            field=field,
            message=message,
            invalid_value=invalid_value,
            error_code=error_code
        )
        self.validation_errors.append(validation_error)
    
    @property
    def has_errors(self) -> bool:
        """Check if processing has errors"""
        return bool(self.error_details or self.validation_errors)
    
    @property
    def is_complete(self) -> bool:
        """Check if processing is complete"""
        return self.status == 'completed'
    
    @property
    def is_failed(self) -> bool:
        """Check if processing has failed"""
        return self.status == 'failed'
    
    @property
    def can_retry(self) -> bool:
        """Check if processing can be retried"""
        return (self.error_details and self.error_details.can_retry) if self.error_details else False


class ModuleCredentials(BaseModel):
    """Secure module credentials model"""
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    token: Optional[str] = None
    additional_fields: Dict[str, str] = {}
    
    def mask_sensitive_data(self) -> Dict[str, str]:
        """Return masked version of credentials for logging"""
        masked = {}
        if self.username:
            masked['username'] = self.username
        if self.password:
            masked['password'] = '*' * len(self.password)
        if self.api_key:
            masked['api_key'] = f"{self.api_key[:4]}...{self.api_key[-4:]}" if len(self.api_key) > 8 else "***"
        if self.token:
            masked['token'] = f"{self.token[:4]}...{self.token[-4:]}" if len(self.token) > 8 else "***"
        
        for key, value in self.additional_fields.items():
            if 'password' in key.lower() or 'secret' in key.lower() or 'key' in key.lower():
                masked[key] = '*' * len(value)
            else:
                masked[key] = value
        
        return masked


class ModuleConfig(BaseModel):
    """Comprehensive module configuration model"""
    
    model_config = ConfigDict(
        validate_assignment=True
    )
    
    # Basic module info
    module_id: str = Field(description="Unique module identifier")
    name: str = Field(description="Human-readable module name")
    description: str = Field(description="Module description")
    version: str = Field(default="1.0.0", description="Module version")
    
    # Status and configuration
    enabled: bool = Field(default=False, description="Module is enabled")
    configured: bool = Field(default=False, description="Module is properly configured")
    requires_credentials: bool = Field(default=False, description="Module requires credentials")
    
    # Credentials (stored separately in Secrets Manager)
    credentials_secret_name: Optional[str] = Field(None, description="AWS Secrets Manager secret name")
    credentials_configured: bool = Field(default=False, description="Credentials are configured")
    
    # Module settings
    settings: Dict[str, Any] = Field(default_factory=dict, description="Module-specific settings")
    
    # Metadata
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used: Optional[datetime] = None
    usage_count: int = Field(default=0, description="Number of times module was used")
    
    # Performance tracking
    average_processing_time_ms: Optional[float] = None
    success_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Success rate (0-1)")
    last_error: Optional[str] = None
    error_count: int = Field(default=0, description="Total error count")
    
    # Dependencies and requirements
    dependencies: List[str] = Field(default_factory=list, description="Required dependencies")
    min_python_version: Optional[str] = Field(None, description="Minimum Python version")
    aws_services_required: List[str] = Field(default_factory=list, description="Required AWS services")
    
    @field_serializer('last_updated', 'last_used')
    def serialize_datetime(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format"""
        return value.isoformat() if value else None
    
    @field_validator('module_id')
    @classmethod
    def validate_module_id(cls, v):
        """Validate module ID format"""
        if not re.match(r'^[a-z][a-z0-9_-]*$', v):
            raise ValueError("Module ID must start with lowercase letter and contain only lowercase letters, numbers, hyphens, and underscores")
        return v
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v):
        """Validate semantic version format"""
        if not re.match(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$', v):
            raise ValueError("Version must follow semantic versioning (e.g., 1.0.0)")
        return v
    
    def update_usage_stats(self, processing_time_ms: int, success: bool):
        """Update module usage statistics"""
        self.usage_count += 1
        self.last_used = datetime.now(UTC)
        
        # Update average processing time
        if self.average_processing_time_ms is None:
            self.average_processing_time_ms = float(processing_time_ms)
        else:
            # Exponential moving average
            alpha = 0.1
            self.average_processing_time_ms = (
                alpha * processing_time_ms + 
                (1 - alpha) * self.average_processing_time_ms
            )
        
        # Update success rate
        if success:
            self.success_rate = (self.success_rate * (self.usage_count - 1) + 1.0) / self.usage_count
        else:
            self.error_count += 1
            self.success_rate = (self.success_rate * (self.usage_count - 1)) / self.usage_count
    
    def set_error(self, error_message: str):
        """Set last error message"""
        self.last_error = error_message
        self.error_count += 1
    
    @property
    def is_healthy(self) -> bool:
        """Check if module is in healthy state"""
        return (
            self.enabled and 
            self.configured and 
            (not self.requires_credentials or self.credentials_configured) and
            self.success_rate > 0.5  # At least 50% success rate
        )
    
    @property
    def needs_attention(self) -> bool:
        """Check if module needs attention"""
        return (
            self.enabled and (
                not self.configured or
                (self.requires_credentials and not self.credentials_configured) or
                self.success_rate < 0.8 or
                self.error_count > 10
            )
        )
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get module status summary"""
        return {
            'module_id': self.module_id,
            'name': self.name,
            'enabled': self.enabled,
            'configured': self.configured,
            'healthy': self.is_healthy,
            'needs_attention': self.needs_attention,
            'usage_count': self.usage_count,
            'success_rate': round(self.success_rate * 100, 1),
            'average_processing_time_ms': self.average_processing_time_ms,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'last_error': self.last_error
        }


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
    last_request: datetime = Field(default_factory=lambda: datetime.now(UTC))
    
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
    """Comprehensive Campus Coach training session model"""
    
    model_config = ConfigDict(
        validate_assignment=True
    )
    
    # Session identification
    session_id: str = Field(description="Unique session identifier")
    session_date: str = Field(description="Session date in YYYY-MM-DD format")
    week_number: str = Field(description="Training week number")
    session_type: str = Field(description="Type of training session")
    
    # Session details
    duration: Optional[str] = Field(None, description="Planned session duration")
    description: str = Field(description="Session description")
    instructions: Optional[str] = Field(None, description="Detailed instructions")
    
    # Training structure
    intervals: Optional[str] = Field(None, description="Interval structure")
    target_pace: Optional[str] = Field(None, description="Target pace")
    target_heart_rate: Optional[str] = Field(None, description="Target heart rate")
    intensity: Optional[str] = Field(None, description="Session intensity level")
    
    # Metadata
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_url: Optional[str] = Field(None, description="Source URL from Campus Coach")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="Raw extracted data")
    
    # Matching and analysis
    matched_activities: List[str] = Field(default_factory=list, description="Activity IDs matched to this session")
    confidence_scores: Dict[str, float] = Field(default_factory=dict, description="Confidence scores for matched activities")
    
    @field_serializer('extracted_at')
    def serialize_extracted_at(self, value: datetime) -> str:
        """Serialize extracted_at to ISO format"""
        return value.isoformat()
    
    @field_validator('session_date')
    @classmethod
    def validate_session_date(cls, v):
        """Validate session date format"""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Session date must be in YYYY-MM-DD format")
        return v
    
    @field_validator('week_number')
    @classmethod
    def validate_week_number(cls, v):
        """Validate week number format (flexible)"""
        # Support various formats: "15", "15-12", "S50", etc.
        if not re.match(r'^[A-Za-z0-9-]+$', v):
            raise ValueError("Week number must contain only alphanumeric characters and hyphens")
        return v
    
    def add_matched_activity(self, activity_id: str, confidence: float):
        """Add a matched activity with confidence score"""
        if activity_id not in self.matched_activities:
            self.matched_activities.append(activity_id)
        self.confidence_scores[activity_id] = confidence
    
    def get_best_match_confidence(self) -> Optional[float]:
        """Get the highest confidence score for matched activities"""
        return max(self.confidence_scores.values()) if self.confidence_scores else None
    
    @property
    def has_intervals(self) -> bool:
        """Check if session includes interval training"""
        return bool(self.intervals and ('interval' in self.intervals.lower() or 'x' in self.intervals.lower()))
    
    @property
    def is_recent(self, days: int = 7) -> bool:
        """Check if session is recent (within specified days)"""
        session_datetime = datetime.strptime(self.session_date, '%Y-%m-%d')
        return (datetime.now() - session_datetime).days <= days
    
    def parse_target_pace(self) -> Optional[Dict[str, float]]:
        """Parse target pace into structured format"""
        if not self.target_pace:
            return None
        
        # Try to extract pace in various formats (min/km, min/mile)
        pace_patterns = [
            r'(\d+):(\d+)/km',
            r'(\d+):(\d+) min/km',
            r'(\d+)\'(\d+)"/km'
        ]
        
        for pattern in pace_patterns:
            match = re.search(pattern, self.target_pace)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                return {
                    'minutes_per_km': minutes + seconds / 60,
                    'seconds_per_km': minutes * 60 + seconds,
                    'original': self.target_pace
                }
        
        return {'original': self.target_pace}


class EndurawData(BaseModel):
    """Enduraw enhanced analytics data model"""
    
    model_config = ConfigDict(
        validate_assignment=True
    )
    
    activity_id: str = Field(description="Associated Strava activity ID")
    
    # Enhanced metrics
    pace_without_wind: Optional[float] = Field(None, description="Pace adjusted for wind resistance")
    weather_impact: Optional[float] = Field(None, description="Weather impact factor")
    elevation_cost: Optional[float] = Field(None, description="Energy cost of elevation changes")
    
    # Weather data
    temperature: Optional[float] = Field(None, description="Temperature in Celsius")
    humidity: Optional[float] = Field(None, description="Humidity percentage")
    wind_speed: Optional[float] = Field(None, description="Wind speed in m/s")
    wind_direction: Optional[int] = Field(None, description="Wind direction in degrees")
    
    # Analysis metadata
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processing_time_minutes: Optional[float] = Field(None, description="Time taken for Enduraw processing")
    data_quality: Optional[str] = Field(None, description="Data quality assessment")
    
    @field_serializer('processed_at')
    def serialize_processed_at(self, value: datetime) -> str:
        return value.isoformat()
    
    @property
    def has_weather_data(self) -> bool:
        """Check if weather data is available"""
        return any([
            self.temperature is not None,
            self.humidity is not None,
            self.wind_speed is not None
        ])
    
    @property
    def weather_summary(self) -> Dict[str, Any]:
        """Get weather summary"""
        return {
            'temperature': self.temperature,
            'humidity': self.humidity,
            'wind_speed': self.wind_speed,
            'wind_direction': self.wind_direction,
            'has_data': self.has_weather_data
        }


class SystemStatus(BaseModel):
    """Comprehensive system status model"""
    
    model_config = ConfigDict(
        validate_assignment=True
    )
    
    # Connection status
    strava_connected: bool = Field(default=False, description="Strava OAuth connection status")
    strava_connection_details: Optional[Dict[str, Any]] = Field(None, description="Strava connection details")
    
    # AgentCore status
    agentcore_status: Literal['healthy', 'degraded', 'unhealthy', 'unknown'] = Field(default='unknown')
    agentcore_agents: Dict[str, str] = Field(default_factory=dict, description="Agent name -> status mapping")
    agentcore_memory_status: Optional[str] = Field(None, description="AgentCore Memory service status")
    
    # Processing queue
    processing_queue_depth: int = Field(default=0, ge=0, description="Number of activities in processing queue")
    failed_queue_depth: int = Field(default=0, ge=0, description="Number of failed activities")
    
    # Activity processing metrics
    last_activity_processed: Optional[datetime] = Field(None, description="Timestamp of last processed activity")
    activities_processed_24h: int = Field(default=0, ge=0, description="Activities processed in last 24 hours")
    success_rate_24h: float = Field(default=0.0, ge=0.0, le=100.0, description="Success rate in last 24 hours")
    average_processing_time_ms: Optional[float] = Field(None, description="Average processing time")
    
    # Enhancement control
    enhancement_enabled: bool = Field(default=True, description="Global enhancement toggle")
    enhancement_paused_at: Optional[datetime] = Field(None, description="When enhancement was paused")
    pause_reason: Optional[str] = Field(None, description="Reason for pausing enhancement")
    
    # Component health
    lambda_functions_healthy: bool = Field(default=True, description="Lambda functions health status")
    dynamodb_healthy: bool = Field(default=True, description="DynamoDB health status")
    step_functions_healthy: bool = Field(default=True, description="Step Functions health status")
    secrets_manager_healthy: bool = Field(default=True, description="Secrets Manager health status")
    sqs_healthy: bool = Field(default=True, description="SQS health status")
    
    # Rate limiting status
    rate_limit_status: Optional[Dict[str, Any]] = Field(None, description="Current rate limit status")
    
    # Module status
    active_modules: List[str] = Field(default_factory=list, description="Currently active modules")
    module_health: Dict[str, bool] = Field(default_factory=dict, description="Module health status")
    
    # Cost and usage
    estimated_daily_cost: Optional[float] = Field(None, description="Estimated daily cost in USD")
    api_calls_24h: int = Field(default=0, ge=0, description="API calls made in last 24 hours")
    
    # System metadata
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    system_version: Optional[str] = Field(None, description="System version")
    deployment_region: str = Field(default="eu-west-1", description="AWS deployment region")
    
    @field_serializer('last_activity_processed', 'enhancement_paused_at', 'last_updated')
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
            return (datetime.now(UTC) - self.enhancement_paused_at).total_seconds() / 3600
        return None
    
    @property
    def overall_health(self) -> Literal['healthy', 'degraded', 'unhealthy']:
        """Calculate overall system health"""
        health_checks = [
            self.strava_connected,
            self.agentcore_status in ['healthy', 'degraded'],
            self.lambda_functions_healthy,
            self.dynamodb_healthy,
            self.step_functions_healthy,
            self.secrets_manager_healthy,
            self.sqs_healthy
        ]
        
        healthy_count = sum(health_checks)
        total_checks = len(health_checks)
        
        if healthy_count == total_checks:
            return 'healthy'
        elif healthy_count >= total_checks * 0.7:  # 70% healthy
            return 'degraded'
        else:
            return 'unhealthy'
    
    @property
    def needs_attention(self) -> List[str]:
        """Get list of components that need attention"""
        issues = []
        
        if not self.strava_connected:
            issues.append("Strava connection")
        
        if self.agentcore_status == 'unhealthy':
            issues.append("AgentCore agents")
        
        if not self.lambda_functions_healthy:
            issues.append("Lambda functions")
        
        if not self.dynamodb_healthy:
            issues.append("DynamoDB")
        
        if not self.step_functions_healthy:
            issues.append("Step Functions")
        
        if self.processing_queue_depth > 10:
            issues.append("Processing queue backlog")
        
        if self.failed_queue_depth > 5:
            issues.append("Failed activities queue")
        
        if self.success_rate_24h < 80:
            issues.append("Low success rate")
        
        return issues
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary for dashboard display"""
        return {
            'overall_health': self.overall_health,
            'strava_connected': self.strava_connected,
            'enhancement_enabled': self.enhancement_enabled,
            'activities_processed_24h': self.activities_processed_24h,
            'success_rate_24h': round(self.success_rate_24h, 1),
            'processing_queue_depth': self.processing_queue_depth,
            'failed_queue_depth': self.failed_queue_depth,
            'active_modules': self.active_modules,
            'needs_attention': self.needs_attention,
            'last_activity_processed': self.last_activity_processed.isoformat() if self.last_activity_processed else None,
            'pause_duration_hours': self.pause_duration_hours,
            'estimated_daily_cost': self.estimated_daily_cost
        }