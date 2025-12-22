"""
Strava API Client with Rate Limiting and Retry Logic

Comprehensive Strava API client with automatic rate limiting, retry logic,
and exponential backoff. Implements Requirements 8.1, 8.4, 10.1, 10.2.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List, Optional, Any, Union
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from .rate_limiter import StravaRateLimiter, create_rate_limiter_from_env
from .oauth_handler import StravaOAuthHandler, create_oauth_handler_from_env
from .data_models import ActivityData, StreamsData

logger = logging.getLogger(__name__)


class StravaAPIError(Exception):
    """Base exception for Strava API errors"""
    pass


class StravaRateLimitError(StravaAPIError):
    """Exception for rate limit exceeded"""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class StravaAuthenticationError(StravaAPIError):
    """Exception for authentication failures"""
    pass


class StravaNotFoundError(StravaAPIError):
    """Exception for resource not found"""
    pass


@dataclass
class StravaAPIResponse:
    """Wrapper for Strava API responses"""
    data: Any
    status_code: int
    headers: Dict[str, str]
    rate_limit_usage: Optional[Dict[str, int]] = None
    
    @property
    def is_success(self) -> bool:
        """Check if response was successful"""
        return 200 <= self.status_code < 300


class StreamType(Enum):
    """Available Strava stream types"""
    TIME = "time"
    DISTANCE = "distance"
    LATLNG = "latlng"
    ALTITUDE = "altitude"
    VELOCITY_SMOOTH = "velocity_smooth"
    HEARTRATE = "heartrate"
    CADENCE = "cadence"
    WATTS = "watts"
    TEMP = "temp"
    MOVING = "moving"
    GRADE_SMOOTH = "grade_smooth"


class StravaAPIClient:
    """
    Comprehensive Strava API client with rate limiting and retry logic.
    
    Features:
    - Automatic OAuth token management
    - Rate limiting with DynamoDB persistence
    - Exponential backoff retry logic
    - Comprehensive error handling
    - Activity and streams data fetching
    """
    
    BASE_URL = "https://www.strava.com/api/v3"
    
    def __init__(self, 
                 oauth_handler: Optional[StravaOAuthHandler] = None,
                 rate_limiter: Optional[StravaRateLimiter] = None,
                 user_id: str = "default",
                 timeout: int = 30,
                 max_retries: int = 3):
        """
        Initialize Strava API client.
        
        Args:
            oauth_handler: OAuth handler for token management
            rate_limiter: Rate limiter for API calls
            user_id: User identifier for token storage
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.oauth_handler = oauth_handler or create_oauth_handler_from_env()
        self.rate_limiter = rate_limiter or create_rate_limiter_from_env()
        self.user_id = user_id
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Configure requests session with retry strategy
        self.session = requests.Session()
        
        # Configure retry strategy for connection issues
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1,
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': 'Strava-AI-Boost/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers with valid access token.
        
        Returns:
            Dictionary with Authorization header
            
        Raises:
            StravaAuthenticationError: If no valid token available
        """
        access_token = self.oauth_handler.get_valid_access_token(self.user_id)
        
        if not access_token:
            raise StravaAuthenticationError("No valid access token available. Please re-authenticate.")
        
        return {'Authorization': f'Bearer {access_token}'}
    
    def _parse_rate_limit_headers(self, headers: Dict[str, str]) -> Dict[str, int]:
        """
        Parse rate limit information from response headers.
        
        Args:
            headers: Response headers
            
        Returns:
            Dictionary with rate limit information
        """
        rate_limit_info = {}
        
        # Strava rate limit headers
        if 'X-RateLimit-Limit' in headers:
            rate_limit_info['short_term_limit'] = int(headers['X-RateLimit-Limit'].split(',')[0])
            rate_limit_info['daily_limit'] = int(headers['X-RateLimit-Limit'].split(',')[1])
        
        if 'X-RateLimit-Usage' in headers:
            rate_limit_info['short_term_usage'] = int(headers['X-RateLimit-Usage'].split(',')[0])
            rate_limit_info['daily_usage'] = int(headers['X-RateLimit-Usage'].split(',')[1])
        
        return rate_limit_info
    
    def _handle_response(self, response: requests.Response) -> StravaAPIResponse:
        """
        Handle API response and extract rate limit information.
        
        Args:
            response: Raw requests response
            
        Returns:
            StravaAPIResponse object
            
        Raises:
            StravaAPIError: For various API errors
        """
        # Parse rate limit headers
        rate_limit_usage = self._parse_rate_limit_headers(response.headers)
        
        # Handle different status codes
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                data = response.text
            
            return StravaAPIResponse(
                data=data,
                status_code=response.status_code,
                headers=dict(response.headers),
                rate_limit_usage=rate_limit_usage
            )
        
        elif response.status_code == 401:
            raise StravaAuthenticationError("Authentication failed. Token may be expired or invalid.")
        
        elif response.status_code == 403:
            raise StravaAuthenticationError("Access forbidden. Check token permissions.")
        
        elif response.status_code == 404:
            raise StravaNotFoundError("Resource not found.")
        
        elif response.status_code == 429:
            # Rate limit exceeded
            retry_after = response.headers.get('Retry-After')
            retry_after_int = int(retry_after) if retry_after else None
            
            raise StravaRateLimitError(
                f"Rate limit exceeded. Retry after: {retry_after}",
                retry_after=retry_after_int
            )
        
        elif response.status_code >= 500:
            raise StravaAPIError(f"Server error: {response.status_code} - {response.text}")
        
        else:
            raise StravaAPIError(f"API error: {response.status_code} - {response.text}")
    
    def _make_request(self, 
                     method: str, 
                     endpoint: str, 
                     params: Optional[Dict] = None,
                     data: Optional[Dict] = None,
                     **kwargs) -> StravaAPIResponse:
        """
        Make authenticated API request with rate limiting.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (without base URL)
            params: Query parameters
            data: Request body data
            **kwargs: Additional request arguments
            
        Returns:
            StravaAPIResponse object
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        # Get authentication headers
        headers = self._get_auth_headers()
        headers.update(kwargs.pop('headers', {}))
        
        # Execute with rate limiting
        def make_api_call():
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                headers=headers,
                timeout=self.timeout,
                **kwargs
            )
            return self._handle_response(response)
        
        try:
            return self.rate_limiter.execute_with_rate_limiting(
                make_api_call,
                max_retries=self.max_retries
            )
        except StravaRateLimitError as e:
            # Handle rate limit errors specifically
            logger.warning(f"Rate limit error: {e}")
            if e.retry_after:
                time.sleep(e.retry_after)
                return make_api_call()
            raise
    
    def get_athlete(self) -> StravaAPIResponse:
        """
        Get authenticated athlete information.
        
        Returns:
            StravaAPIResponse with athlete data
        """
        return self._make_request('GET', '/athlete')
    
    def get_activity(self, activity_id: str, include_all_efforts: bool = False) -> StravaAPIResponse:
        """
        Get detailed activity information.
        
        Args:
            activity_id: Strava activity ID
            include_all_efforts: Include all segment efforts
            
        Returns:
            StravaAPIResponse with activity data
        """
        params = {}
        if include_all_efforts:
            params['include_all_efforts'] = 'true'
        
        return self._make_request('GET', f'/activities/{activity_id}', params=params)
    
    def get_activities(self, 
                      before: Optional[datetime] = None,
                      after: Optional[datetime] = None,
                      page: int = 1,
                      per_page: int = 30) -> StravaAPIResponse:
        """
        Get list of activities for authenticated athlete.
        
        Args:
            before: Return activities before this date
            after: Return activities after this date
            page: Page number
            per_page: Number of activities per page (max 200)
            
        Returns:
            StravaAPIResponse with activities list
        """
        params = {
            'page': page,
            'per_page': min(per_page, 200)
        }
        
        if before:
            params['before'] = int(before.timestamp())
        
        if after:
            params['after'] = int(after.timestamp())
        
        return self._make_request('GET', '/athlete/activities', params=params)
    
    def get_activity_streams(self, 
                           activity_id: str,
                           stream_types: List[StreamType],
                           resolution: str = "high") -> StravaAPIResponse:
        """
        Get activity streams data.
        
        Args:
            activity_id: Strava activity ID
            stream_types: List of stream types to fetch
            resolution: Data resolution ("low", "medium", "high")
            
        Returns:
            StravaAPIResponse with streams data
        """
        # Convert stream types to comma-separated string
        keys = ",".join([st.value for st in stream_types])
        
        params = {
            'keys': keys,
            'key_by_type': 'true',
            'resolution': resolution
        }
        
        return self._make_request('GET', f'/activities/{activity_id}/streams', params=params)
    
    def update_activity(self, 
                       activity_id: str,
                       name: Optional[str] = None,
                       description: Optional[str] = None,
                       activity_type: Optional[str] = None,
                       gear_id: Optional[str] = None) -> StravaAPIResponse:
        """
        Update activity information.
        
        Args:
            activity_id: Strava activity ID
            name: New activity name
            description: New activity description
            activity_type: New activity type
            gear_id: Gear ID
            
        Returns:
            StravaAPIResponse with updated activity data
        """
        data = {}
        
        if name is not None:
            data['name'] = name
        
        if description is not None:
            data['description'] = description
        
        if activity_type is not None:
            data['type'] = activity_type
        
        if gear_id is not None:
            data['gear_id'] = gear_id
        
        return self._make_request('PUT', f'/activities/{activity_id}', data=data)
    
    def get_activity_with_streams(self, 
                                 activity_id: str,
                                 stream_types: Optional[List[StreamType]] = None) -> Dict[str, Any]:
        """
        Get activity data with streams in a single call.
        
        Args:
            activity_id: Strava activity ID
            stream_types: Stream types to fetch (defaults to common ones)
            
        Returns:
            Dictionary with activity and streams data
        """
        if stream_types is None:
            stream_types = [
                StreamType.TIME,
                StreamType.DISTANCE,
                StreamType.ALTITUDE,
                StreamType.VELOCITY_SMOOTH,
                StreamType.HEARTRATE
            ]
        
        # Get activity data
        activity_response = self.get_activity(activity_id)
        
        # Get streams data
        try:
            streams_response = self.get_activity_streams(activity_id, stream_types)
            streams_data = streams_response.data
        except StravaAPIError as e:
            logger.warning(f"Failed to get streams for activity {activity_id}: {e}")
            streams_data = {}
        
        return {
            'activity': activity_response.data,
            'streams': streams_data,
            'activity_response': activity_response,
            'streams_available': bool(streams_data)
        }
    
    def parse_activity_data(self, raw_activity: Dict[str, Any]) -> ActivityData:
        """
        Parse raw Strava activity data into ActivityData model.
        
        Args:
            raw_activity: Raw activity data from Strava API
            
        Returns:
            ActivityData object
        """
        # Convert start_date string to datetime
        start_date = datetime.fromisoformat(raw_activity['start_date'].replace('Z', '+00:00'))
        start_date_local = None
        if raw_activity.get('start_date_local'):
            start_date_local = datetime.fromisoformat(raw_activity['start_date_local'].replace('Z', '+00:00'))
        
        return ActivityData(
            id=str(raw_activity['id']),
            name=raw_activity.get('name', ''),
            description=raw_activity.get('description'),
            type=raw_activity.get('type', 'Run'),
            distance=raw_activity.get('distance', 0.0),
            moving_time=raw_activity.get('moving_time', 0),
            elapsed_time=raw_activity.get('elapsed_time', 0),
            total_elevation_gain=raw_activity.get('total_elevation_gain', 0.0),
            start_date=start_date,
            start_date_local=start_date_local,
            timezone=raw_activity.get('timezone'),
            start_latitude=raw_activity.get('start_latlng', [None, None])[0],
            start_longitude=raw_activity.get('start_latlng', [None, None])[1],
            end_latitude=raw_activity.get('end_latlng', [None, None])[0],
            end_longitude=raw_activity.get('end_latlng', [None, None])[1],
            average_speed=raw_activity.get('average_speed'),
            max_speed=raw_activity.get('max_speed'),
            average_heartrate=raw_activity.get('average_heartrate'),
            max_heartrate=raw_activity.get('max_heartrate'),
            suffer_score=raw_activity.get('suffer_score'),
            kudos_count=raw_activity.get('kudos_count', 0),
            comment_count=raw_activity.get('comment_count', 0),
            athlete_count=raw_activity.get('athlete_count', 1),
            gear_id=raw_activity.get('gear_id'),
            average_temp=raw_activity.get('average_temp'),
            achievement_count=raw_activity.get('achievement_count', 0),
            pr_count=raw_activity.get('pr_count', 0),
            calories=raw_activity.get('calories'),
            device_watts=raw_activity.get('device_watts'),
            has_heartrate=raw_activity.get('has_heartrate', False),
            has_kudoed=raw_activity.get('has_kudoed', False)
        )
    
    def parse_streams_data(self, raw_streams: Dict[str, Any]) -> StreamsData:
        """
        Parse raw Strava streams data into StreamsData model.
        
        Args:
            raw_streams: Raw streams data from Strava API
            
        Returns:
            StreamsData object
        """
        # Extract stream arrays
        velocity_smooth = raw_streams.get('velocity_smooth', {}).get('data', [])
        heartrate = raw_streams.get('heartrate', {}).get('data', [])
        time_data = raw_streams.get('time', {}).get('data', [])
        distance = raw_streams.get('distance', {}).get('data', [])
        altitude = raw_streams.get('altitude', {}).get('data', [])
        
        # Optional streams
        cadence = raw_streams.get('cadence', {}).get('data') if 'cadence' in raw_streams else None
        watts = raw_streams.get('watts', {}).get('data') if 'watts' in raw_streams else None
        temp = raw_streams.get('temp', {}).get('data') if 'temp' in raw_streams else None
        
        return StreamsData(
            velocity_smooth=velocity_smooth,
            heartrate=heartrate,
            time=time_data,
            distance=distance,
            altitude=altitude,
            cadence=cadence,
            watts=watts,
            temp=temp
        )
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.
        
        Returns:
            Dictionary with rate limit information
        """
        return self.rate_limiter.get_comprehensive_status()
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test API connection and authentication.
        
        Returns:
            Dictionary with connection test results
        """
        try:
            # Test authentication
            athlete_response = self.get_athlete()
            
            # Get rate limit status
            rate_status = self.get_rate_limit_status()
            
            return {
                'connected': True,
                'authenticated': True,
                'athlete_id': athlete_response.data.get('id'),
                'athlete_name': f"{athlete_response.data.get('firstname', '')} {athlete_response.data.get('lastname', '')}".strip(),
                'rate_limits': rate_status,
                'message': 'Connection successful'
            }
            
        except StravaAuthenticationError as e:
            return {
                'connected': False,
                'authenticated': False,
                'message': f'Authentication failed: {str(e)}'
            }
        except Exception as e:
            return {
                'connected': False,
                'authenticated': False,
                'message': f'Connection failed: {str(e)}'
            }


def create_strava_client_from_env(user_id: str = "default") -> StravaAPIClient:
    """
    Create Strava API client from environment variables.
    
    Args:
        user_id: User identifier for token storage
        
    Returns:
        Configured StravaAPIClient instance
    """
    oauth_handler = create_oauth_handler_from_env()
    rate_limiter = create_rate_limiter_from_env()
    
    return StravaAPIClient(
        oauth_handler=oauth_handler,
        rate_limiter=rate_limiter,
        user_id=user_id
    )