"""
Data Transformation and Validation Utilities

Provides comprehensive data transformation, validation, and utility functions
for converting between different data formats and ensuring data quality.
Implements Requirements 8.1, 8.4 for data transformation and validation.
"""

from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timezone
import re
import json
import logging
from dataclasses import dataclass

from .data_models import (
    ActivityData, StreamsData, ProcessingStatus, ModuleConfig,
    ValidationError, ProcessingError
)

logger = logging.getLogger(__name__)


@dataclass
class DataQualityReport:
    """Data quality assessment report"""
    overall_score: float  # 0-1 scale
    issues: List[str]
    warnings: List[str]
    recommendations: List[str]
    field_completeness: Dict[str, float]
    data_consistency: Dict[str, bool]


class StravaDataTransformer:
    """
    Transforms raw Strava API data into structured models.
    
    Handles data cleaning, validation, and format conversion for all
    Strava data types including activities, streams, and metadata.
    """
    
    def transform_activity_data(self, raw_data: Dict[str, Any]) -> ActivityData:
        """
        Transform raw Strava activity data into ActivityData model.
        Instance method wrapper for transform_raw_activity.
        
        Args:
            raw_data: Raw activity data from Strava API
            
        Returns:
            ActivityData object with validated and cleaned data
        """
        return self.transform_raw_activity(raw_data)
    
    def transform_streams_data(self, raw_streams: Dict[str, Any]) -> StreamsData:
        """
        Transform raw Strava streams data into StreamsData model.
        Instance method wrapper for transform_raw_streams.
        
        Args:
            raw_streams: Raw streams data from Strava API
            
        Returns:
            StreamsData object with validated streams
        """
        return self.transform_raw_streams(raw_streams)
    
    def validate_and_sanitize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize raw data before transformation.
        
        Args:
            raw_data: Raw data to validate and sanitize
            
        Returns:
            Cleaned and validated data dictionary
        """
        if not isinstance(raw_data, dict):
            raise ValueError("Input data must be a dictionary")
        
        # Create a copy to avoid modifying original
        sanitized = raw_data.copy()
        
        # Remove null bytes and clean text fields
        for key, value in sanitized.items():
            if isinstance(value, str):
                sanitized[key] = self._clean_text(value)
            elif isinstance(value, (int, float)) and value < 0 and key in ['distance', 'moving_time', 'elapsed_time']:
                sanitized[key] = 0  # Ensure non-negative values for these fields
        
        return sanitized
    
    @staticmethod
    def transform_raw_activity(raw_data: Dict[str, Any]) -> ActivityData:
        """
        Transform raw Strava activity data into ActivityData model.
        
        Args:
            raw_data: Raw activity data from Strava API
            
        Returns:
            ActivityData object with validated and cleaned data
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        try:
            # Handle datetime fields
            start_date = StravaDataTransformer._parse_datetime(raw_data.get('start_date'))
            start_date_local = StravaDataTransformer._parse_datetime(raw_data.get('start_date_local'))
            
            if not start_date:
                raise ValueError("start_date is required")
            
            # Handle coordinate arrays
            start_latlng = raw_data.get('start_latlng')
            end_latlng = raw_data.get('end_latlng')
            
            # Clean and validate numeric fields
            distance = max(0, float(raw_data.get('distance', 0)))
            moving_time = max(0, int(raw_data.get('moving_time', 0)))
            elapsed_time = max(0, int(raw_data.get('elapsed_time', 0)))
            
            # Handle optional numeric fields
            total_elevation_gain = StravaDataTransformer._safe_float(raw_data.get('total_elevation_gain'))
            average_speed = StravaDataTransformer._safe_float(raw_data.get('average_speed'))
            max_speed = StravaDataTransformer._safe_float(raw_data.get('max_speed'))
            
            # Handle heart rate data
            average_heartrate = StravaDataTransformer._safe_float(
                raw_data.get('average_heartrate'), min_val=0, max_val=300
            )
            max_heartrate = StravaDataTransformer._safe_float(
                raw_data.get('max_heartrate'), min_val=0, max_val=300
            )
            
            # Handle power data
            average_watts = StravaDataTransformer._safe_float(
                raw_data.get('average_watts'), min_val=0, max_val=3000
            )
            weighted_average_watts = StravaDataTransformer._safe_int(
                raw_data.get('weighted_average_watts'), min_val=0, max_val=3000
            )
            
            # Create ActivityData object
            activity_data = ActivityData(
                id=str(raw_data['id']),  # Convert to string as expected by tests
                external_id=raw_data.get('external_id'),
                upload_id=StravaDataTransformer._safe_int(raw_data.get('upload_id')),
                name=str(raw_data.get('name', '')).strip(),
                description=StravaDataTransformer._clean_text(raw_data.get('description')),
                type=str(raw_data.get('type', 'Run')),
                sport_type=raw_data.get('sport_type'),
                workout_type=StravaDataTransformer._safe_int(raw_data.get('workout_type')),
                
                # Timing
                start_date=start_date,
                start_date_local=start_date_local or start_date,
                timezone=str(raw_data.get('timezone', '')),
                utc_offset=StravaDataTransformer._safe_float(raw_data.get('utc_offset')),
                
                # Distance and duration
                distance=distance,
                moving_time=moving_time,
                elapsed_time=elapsed_time,
                
                # Elevation
                total_elevation_gain=total_elevation_gain,
                elev_high=StravaDataTransformer._safe_float(raw_data.get('elev_high')),
                elev_low=StravaDataTransformer._safe_float(raw_data.get('elev_low')),
                
                # Speed
                average_speed=average_speed,
                max_speed=max_speed,
                
                # Heart rate
                has_heartrate=bool(raw_data.get('has_heartrate', False)),
                average_heartrate=average_heartrate,
                max_heartrate=max_heartrate,
                heartrate_opt_out=raw_data.get('heartrate_opt_out'),
                display_hide_heartrate_option=raw_data.get('display_hide_heartrate_option'),
                
                # Power
                has_kudoed=bool(raw_data.get('has_kudoed', False)),
                device_watts=raw_data.get('device_watts'),
                average_watts=average_watts,
                weighted_average_watts=weighted_average_watts,
                kilojoules=StravaDataTransformer._safe_float(raw_data.get('kilojoules')),
                
                # Other metrics
                average_cadence=StravaDataTransformer._safe_float(raw_data.get('average_cadence')),
                average_temp=StravaDataTransformer._safe_int(raw_data.get('average_temp')),
                
                # Location
                start_latlng=start_latlng,
                end_latlng=end_latlng,
                location_city=StravaDataTransformer._clean_text(raw_data.get('location_city')),
                location_state=StravaDataTransformer._clean_text(raw_data.get('location_state')),
                location_country=StravaDataTransformer._clean_text(raw_data.get('location_country')),
                
                # Social
                kudos_count=max(0, int(raw_data.get('kudos_count', 0))),
                comment_count=max(0, int(raw_data.get('comment_count', 0))),
                athlete_count=max(1, int(raw_data.get('athlete_count', 1))),
                photo_count=max(0, int(raw_data.get('photo_count', 0))),
                
                # Achievements
                achievement_count=max(0, int(raw_data.get('achievement_count', 0))),
                pr_count=max(0, int(raw_data.get('pr_count', 0))),
                
                # Training
                suffer_score=StravaDataTransformer._safe_int(raw_data.get('suffer_score')),
                perceived_exertion=StravaDataTransformer._safe_int(
                    raw_data.get('perceived_exertion'), min_val=1, max_val=10
                ),
                calories=StravaDataTransformer._safe_float(raw_data.get('calories')),
                
                # Equipment and settings
                gear_id=raw_data.get('gear_id'),
                private=bool(raw_data.get('private', False)),
                visibility=raw_data.get('visibility'),
                flagged=bool(raw_data.get('flagged', False)),
                trainer=bool(raw_data.get('trainer', False)),
                commute=bool(raw_data.get('commute', False)),
                manual=bool(raw_data.get('manual', False)),
                
                # Metadata
                resource_state=int(raw_data.get('resource_state', 1)),
                embed_token=raw_data.get('embed_token'),
                from_accepted_tag=raw_data.get('from_accepted_tag'),
                segment_leaderboard_opt_out=raw_data.get('segment_leaderboard_opt_out'),
                leaderboard_opt_out=raw_data.get('leaderboard_opt_out'),
                
                # Social media
                instagram_primary_photo=raw_data.get('instagram_primary_photo'),
                partner_logo_url=raw_data.get('partner_logo_url'),
                partner_brand_tag=raw_data.get('partner_brand_tag'),
                
                # Device
                device_name=StravaDataTransformer._clean_text(raw_data.get('device_name'))
            )
            
            logger.debug(f"Transformed activity data for ID: {activity_data.id}")
            return activity_data
            
        except Exception as e:
            logger.error(f"Error transforming activity data: {e}")
            raise ValueError(f"Failed to transform activity data: {str(e)}")
    
    @staticmethod
    def transform_raw_streams(raw_streams: Dict[str, Any]) -> StreamsData:
        """
        Transform raw Strava streams data into StreamsData model.
        
        Args:
            raw_streams: Raw streams data from Strava API
            
        Returns:
            StreamsData object with validated streams
            
        Raises:
            ValueError: If required streams are missing or invalid
        """
        try:
            # Extract required streams
            time_data = raw_streams.get('time', {}).get('data', [])
            distance_data = raw_streams.get('distance', {}).get('data', [])
            velocity_data = raw_streams.get('velocity_smooth', {}).get('data', [])
            altitude_data = raw_streams.get('altitude', {}).get('data', [])
            
            if not time_data:
                raise ValueError("Time stream is required")
            
            # Ensure all required streams have the same length
            expected_length = len(time_data)
            if len(distance_data) != expected_length:
                distance_data = StravaDataTransformer._pad_or_truncate(distance_data, expected_length)
            if len(velocity_data) != expected_length:
                velocity_data = StravaDataTransformer._pad_or_truncate(velocity_data, expected_length)
            if len(altitude_data) != expected_length:
                altitude_data = StravaDataTransformer._pad_or_truncate(altitude_data, expected_length)
            
            # Extract optional streams
            latlng_data = raw_streams.get('latlng', {}).get('data')
            heartrate_data = raw_streams.get('heartrate', {}).get('data')
            cadence_data = raw_streams.get('cadence', {}).get('data')
            watts_data = raw_streams.get('watts', {}).get('data')
            temp_data = raw_streams.get('temp', {}).get('data')
            moving_data = raw_streams.get('moving', {}).get('data')
            grade_data = raw_streams.get('grade_smooth', {}).get('data')
            
            # Validate and clean optional streams
            if heartrate_data:
                heartrate_data = [max(0, min(300, int(hr))) for hr in heartrate_data if hr is not None]
                if len(heartrate_data) != expected_length:
                    heartrate_data = StravaDataTransformer._pad_or_truncate(heartrate_data, expected_length)
            
            if watts_data:
                watts_data = [max(0, min(3000, int(w))) for w in watts_data if w is not None]
                if len(watts_data) != expected_length:
                    watts_data = StravaDataTransformer._pad_or_truncate(watts_data, expected_length)
            
            # Create StreamsData object
            streams_data = StreamsData(
                time=[int(t) for t in time_data],
                distance=[float(d) for d in distance_data],
                velocity_smooth=[float(v) for v in velocity_data],
                altitude=[float(a) for a in altitude_data],
                latlng=latlng_data,
                heartrate=heartrate_data,
                cadence=cadence_data,
                watts=watts_data,
                temp=temp_data,
                moving=moving_data,
                grade_smooth=grade_data
            )
            
            logger.debug(f"Transformed streams data with {len(streams_data)} points")
            return streams_data
            
        except Exception as e:
            logger.error(f"Error transforming streams data: {e}")
            raise ValueError(f"Failed to transform streams data: {str(e)}")
    
    @staticmethod
    def _parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string from Strava API"""
        if not date_str:
            return None
        
        try:
            # Handle ISO format with Z suffix
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            
            return datetime.fromisoformat(date_str)
        except ValueError:
            logger.warning(f"Failed to parse datetime: {date_str}")
            return None
    
    @staticmethod
    def _safe_float(value: Any, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Optional[float]:
        """Safely convert value to float with optional bounds"""
        if value is None:
            return None
        
        try:
            float_val = float(value)
            
            if min_val is not None and float_val < min_val:
                return min_val
            if max_val is not None and float_val > max_val:
                return max_val
            
            return float_val
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _safe_int(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Optional[int]:
        """Safely convert value to int with optional bounds"""
        if value is None:
            return None
        
        try:
            int_val = int(value)
            
            if min_val is not None and int_val < min_val:
                return min_val
            if max_val is not None and int_val > max_val:
                return max_val
            
            return int_val
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _clean_text(text: Optional[str]) -> Optional[str]:
        """Clean and validate text fields"""
        if not text:
            return None
        
        # Strip whitespace and normalize
        cleaned = str(text).strip()
        
        # Remove null bytes and control characters
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
        
        # Remove HTML/script tags for security
        cleaned = re.sub(r'<[^>]*>', '', cleaned)
        
        return cleaned if cleaned else None
    
    @staticmethod
    def _pad_or_truncate(data: List[Any], target_length: int) -> List[Any]:
        """Pad or truncate list to target length"""
        if len(data) == target_length:
            return data
        elif len(data) < target_length:
            # Pad with last value or zero
            pad_value = data[-1] if data else 0
            return data + [pad_value] * (target_length - len(data))
        else:
            # Truncate to target length
            return data[:target_length]


class DataValidator:
    """
    Comprehensive data validation utilities.
    
    Provides validation functions for all data models and quality assessment.
    """
    
    @staticmethod
    def validate_activity_data(activity: ActivityData) -> List[ValidationError]:
        """
        Validate ActivityData object and return any validation errors.
        
        Args:
            activity: ActivityData object to validate
            
        Returns:
            List of ValidationError objects
        """
        errors = []
        
        # Validate required fields
        if not activity.name:
            errors.append(ValidationError(
                field="name",
                message="Activity name is required",
                invalid_value=activity.name,
                error_code="REQUIRED_FIELD_MISSING"
            ))
        
        # Validate numeric ranges
        if activity.distance < 0:
            errors.append(ValidationError(
                field="distance",
                message="Distance cannot be negative",
                invalid_value=activity.distance,
                error_code="INVALID_RANGE"
            ))
        
        if activity.moving_time < 0:
            errors.append(ValidationError(
                field="moving_time",
                message="Moving time cannot be negative",
                invalid_value=activity.moving_time,
                error_code="INVALID_RANGE"
            ))
        
        # Validate heart rate if present
        if activity.average_heartrate is not None:
            if not (0 <= activity.average_heartrate <= 300):
                errors.append(ValidationError(
                    field="average_heartrate",
                    message="Average heart rate must be between 0 and 300 BPM",
                    invalid_value=activity.average_heartrate,
                    error_code="INVALID_RANGE"
                ))
        
        # Validate coordinates if present
        if activity.start_latlng:
            lat, lng = activity.start_latlng
            if not (-90 <= lat <= 90):
                errors.append(ValidationError(
                    field="start_latlng",
                    message="Start latitude must be between -90 and 90",
                    invalid_value=lat,
                    error_code="INVALID_COORDINATES"
                ))
            if not (-180 <= lng <= 180):
                errors.append(ValidationError(
                    field="start_latlng",
                    message="Start longitude must be between -180 and 180",
                    invalid_value=lng,
                    error_code="INVALID_COORDINATES"
                ))
        
        # Validate time consistency
        if activity.moving_time > activity.elapsed_time:
            errors.append(ValidationError(
                field="moving_time",
                message="Moving time cannot exceed elapsed time",
                invalid_value=activity.moving_time,
                error_code="INCONSISTENT_DATA"
            ))
        
        return errors
    
    @staticmethod
    def validate_streams_data(streams: StreamsData) -> List[ValidationError]:
        """
        Validate StreamsData object and return any validation errors.
        
        Args:
            streams: StreamsData object to validate
            
        Returns:
            List of ValidationError objects
        """
        errors = []
        
        # Validate required streams
        if not streams.time:
            errors.append(ValidationError(
                field="time",
                message="Time stream is required",
                invalid_value=None,
                error_code="REQUIRED_FIELD_MISSING"
            ))
            return errors  # Can't validate further without time data
        
        expected_length = len(streams.time)
        
        # Validate stream lengths
        if len(streams.distance) != expected_length:
            errors.append(ValidationError(
                field="distance",
                message=f"Distance stream length ({len(streams.distance)}) doesn't match time stream ({expected_length})",
                invalid_value=len(streams.distance),
                error_code="INCONSISTENT_LENGTH"
            ))
        
        # Validate time sequence
        for i in range(1, len(streams.time)):
            if streams.time[i] < streams.time[i-1]:
                errors.append(ValidationError(
                    field="time",
                    message=f"Time sequence not monotonic at index {i}",
                    invalid_value=streams.time[i],
                    error_code="INVALID_SEQUENCE"
                ))
                break
        
        # Validate distance sequence
        if len(streams.distance) > 1:
            for i in range(1, len(streams.distance)):
                if streams.distance[i] < streams.distance[i-1]:
                    errors.append(ValidationError(
                        field="distance",
                        message=f"Distance sequence not monotonic at index {i}",
                        invalid_value=streams.distance[i],
                        error_code="INVALID_SEQUENCE"
                    ))
                    break
        
        # Validate heart rate data if present
        if streams.heartrate:
            for i, hr in enumerate(streams.heartrate):
                if hr < 0 or hr > 300:
                    errors.append(ValidationError(
                        field="heartrate",
                        message=f"Invalid heart rate at index {i}: {hr}",
                        invalid_value=hr,
                        error_code="INVALID_RANGE"
                    ))
                    break
        
        return errors
    
    @staticmethod
    def assess_data_quality(activity: ActivityData, streams: Optional[StreamsData] = None) -> DataQualityReport:
        """
        Assess overall data quality for an activity.
        
        Args:
            activity: ActivityData object
            streams: Optional StreamsData object
            
        Returns:
            DataQualityReport with quality assessment
        """
        issues = []
        warnings = []
        recommendations = []
        field_completeness = {}
        data_consistency = {}
        
        # Assess activity data completeness
        total_fields = 0
        complete_fields = 0
        
        for field_name, field_value in activity.model_dump().items():
            total_fields += 1
            if field_value is not None:
                complete_fields += 1
        
        activity_completeness = complete_fields / total_fields if total_fields > 0 else 0
        field_completeness['activity'] = activity_completeness
        
        # Check for critical missing data
        if not activity.has_location_data():
            warnings.append("No GPS location data available")
            recommendations.append("Consider enabling GPS for future activities")
        
        if not activity.has_heartrate:
            warnings.append("No heart rate data available")
            recommendations.append("Consider using a heart rate monitor")
        
        # Assess streams data if available
        if streams:
            streams_completeness = 1.0  # Base completeness for required streams
            
            optional_streams = ['heartrate', 'cadence', 'watts', 'temp']
            available_optional = sum(1 for stream in optional_streams if getattr(streams, stream) is not None)
            streams_completeness = (4 + available_optional) / (4 + len(optional_streams))
            
            field_completeness['streams'] = streams_completeness
            
            # Check data quality
            if streams.sample_rate_hz and streams.sample_rate_hz < 0.5:
                warnings.append("Low sample rate in streams data")
            
            data_consistency['streams_length'] = len(streams) > 10
        else:
            field_completeness['streams'] = 0.0
            warnings.append("No streams data available")
            recommendations.append("Enable detailed recording for better analysis")
        
        # Calculate overall score
        completeness_scores = list(field_completeness.values())
        overall_score = sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0
        
        # Adjust score based on issues
        if len(issues) > 0:
            overall_score *= 0.8
        if len(warnings) > 2:
            overall_score *= 0.9
        
        return DataQualityReport(
            overall_score=overall_score,
            issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            field_completeness=field_completeness,
            data_consistency=data_consistency
        )


class DataExporter:
    """
    Export data models to various formats.
    
    Supports JSON, CSV, and other export formats for data analysis.
    """
    
    @staticmethod
    def activity_to_json(activity: ActivityData, include_metadata: bool = True) -> str:
        """
        Export ActivityData to JSON format.
        
        Args:
            activity: ActivityData object
            include_metadata: Include computed properties and metadata
            
        Returns:
            JSON string representation
        """
        data = activity.model_dump()
        
        if include_metadata:
            data['_metadata'] = {
                'distance_km': activity.distance_km,
                'distance_miles': activity.distance_miles,
                'speed_kmh': activity.speed_kmh,
                'speed_mph': activity.speed_mph,
                'pace_per_km': activity.pace_per_km,
                'pace_per_mile': activity.pace_per_mile,
                'moving_time_formatted': activity.moving_time_formatted,
                'has_location_data': activity.has_location_data(),
                'has_power_data': activity.has_power_data(),
                'is_indoor_activity': activity.is_indoor_activity()
            }
        
        return json.dumps(data, indent=2, default=str)
    
    @staticmethod
    def streams_to_csv(streams: StreamsData) -> str:
        """
        Export StreamsData to CSV format.
        
        Args:
            streams: StreamsData object
            
        Returns:
            CSV string representation
        """
        if not streams.time:
            return ""
        
        # Determine available columns
        columns = ['time', 'distance', 'velocity_smooth', 'altitude']
        
        if streams.latlng:
            columns.extend(['latitude', 'longitude'])
        if streams.heartrate:
            columns.append('heartrate')
        if streams.cadence:
            columns.append('cadence')
        if streams.watts:
            columns.append('watts')
        if streams.temp:
            columns.append('temp')
        
        # Create CSV content
        csv_lines = [','.join(columns)]
        
        for i in range(len(streams.time)):
            row = [
                str(streams.time[i]),
                str(streams.distance[i]),
                str(streams.velocity_smooth[i]),
                str(streams.altitude[i])
            ]
            
            if streams.latlng:
                lat, lng = streams.latlng[i] if i < len(streams.latlng) else [0, 0]
                row.extend([str(lat), str(lng)])
            
            if streams.heartrate:
                hr = streams.heartrate[i] if i < len(streams.heartrate) else 0
                row.append(str(hr))
            
            if streams.cadence:
                cad = streams.cadence[i] if i < len(streams.cadence) else 0
                row.append(str(cad))
            
            if streams.watts:
                power = streams.watts[i] if i < len(streams.watts) else 0
                row.append(str(power))
            
            if streams.temp:
                temperature = streams.temp[i] if i < len(streams.temp) else 0
                row.append(str(temperature))
            
            csv_lines.append(','.join(row))
        
        return '\n'.join(csv_lines)
    
    @staticmethod
    def processing_status_to_dict(status: ProcessingStatus) -> Dict[str, Any]:
        """
        Export ProcessingStatus to dictionary format.
        
        Args:
            status: ProcessingStatus object
            
        Returns:
            Dictionary representation
        """
        data = status.model_dump()
        
        # Add computed properties
        data['has_errors'] = status.has_errors
        data['is_complete'] = status.is_complete
        data['is_failed'] = status.is_failed
        data['can_retry'] = status.can_retry
        
        return data


def create_data_transformer() -> StravaDataTransformer:
    """Create a configured data transformer instance"""
    return StravaDataTransformer()


def create_data_validator() -> DataValidator:
    """Create a configured data validator instance"""
    return DataValidator()


def create_data_exporter() -> DataExporter:
    """Create a configured data exporter instance"""
    return DataExporter()