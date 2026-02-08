"""
Activity Fetcher Lambda Function

Fetches complete activity data from Strava API including streams data.
Handles rate limiting and comprehensive data retrieval for analysis.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError
import requests
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with region
REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
RATE_LIMITS_TABLE = os.environ['RATE_LIMITS_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']

# Strava API configuration
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for fetching activity data from Strava API
    
    Fetches complete activity data and streams for comprehensive analysis
    """
    try:
        activity_id = event.get('activity_id')
        user_id = event.get('user_id')
        
        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")
        
        logger.info(f"Fetching activity data for activity {activity_id}")
        
        # Check rate limits before making API calls
        if not check_rate_limits():
            raise Exception("Strava API rate limits exceeded")
        
        # Get OAuth tokens
        access_token = get_access_token(user_id)
        
        # Fetch activity data
        activity_data = fetch_activity_data(activity_id, access_token)
        
        # Fetch streams data for detailed analysis
        streams_data = fetch_streams_data(activity_id, access_token)
        
        # Fetch athlete stats for context (yearly totals, records, etc.)
        athlete_id = activity_data.get('athlete', {}).get('id') or user_id
        athlete_stats = fetch_athlete_stats(athlete_id, access_token)
        
        # Fetch athlete profile for FTP, weight, and gear details
        athlete_profile = fetch_athlete_profile(access_token)
        
        # Fetch gear details if gear_id is present
        gear_id = activity_data.get('gear_id')
        gear_details = fetch_gear_details(gear_id, access_token) if gear_id else None
        
        # Fetch user configuration for module decisions
        user_config = fetch_user_configuration(user_id)
        
        # Store ALL data in DynamoDB to avoid Step Functions 256KB payload limit
        store_activity_data(
            activity_id=activity_id,
            activity_data=activity_data,
            streams_data=streams_data,
            athlete_stats=athlete_stats,
            athlete_profile=athlete_profile,
            gear_details=gear_details,
            user_config=user_config
        )
        
        # Update rate limit usage
        update_rate_limits(5)  # Activity + streams + stats + profile + gear API calls
        
        # Return minimal payload - only references, no large data
        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'user_id': user_id,
            'user_config': user_config,  # Keep user_config for workflow decisions
            'fetched_at': datetime.utcnow().isoformat(),
            'data_stored_in_dynamodb': True
        }
        
    except Exception as e:
        logger.error(f"Activity fetcher error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'activity_id': event.get('activity_id'),
            'user_id': event.get('user_id')
        }


def check_rate_limits() -> bool:
    """Check if we're within Strava API rate limits"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Check short-term limit (100/15min)
        response = table.get_item(Key={'limit_type': 'short_term'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            reset_time = response['Item'].get('reset_time')
            
            # Check if reset time has passed
            if reset_time and datetime.fromisoformat(reset_time) <= datetime.utcnow():
                # Reset the counter
                table.update_item(
                    Key={'limit_type': 'short_term'},
                    UpdateExpression="SET current_usage = :zero, reset_time = :reset",
                    ExpressionAttributeValues={
                        ':zero': 0,
                        ':reset': (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                    }
                )
                usage = 0
            
            if usage >= 95:  # Leave buffer for other operations
                logger.warning(f"Short-term rate limit near threshold: {usage}/100")
                return False
        
        # Check daily limit (1000/day)
        response = table.get_item(Key={'limit_type': 'daily'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            reset_time = response['Item'].get('reset_time')
            
            # Check if reset time has passed (daily reset)
            if reset_time and datetime.fromisoformat(reset_time) <= datetime.utcnow():
                # Reset the counter
                table.update_item(
                    Key={'limit_type': 'daily'},
                    UpdateExpression="SET current_usage = :zero, reset_time = :reset",
                    ExpressionAttributeValues={
                        ':zero': 0,
                        ':reset': (datetime.utcnow() + timedelta(days=1)).isoformat()
                    }
                )
                usage = 0
            
            if usage >= 950:  # Leave buffer for other operations
                logger.warning(f"Daily rate limit near threshold: {usage}/1000")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Rate limit check error: {str(e)}")
        # Assume we're at limit if we can't check
        return False


def get_access_token(user_id: str) -> str:
    """Get Strava access token from Secrets Manager with automatic refresh"""
    try:
        # Get OAuth tokens directly from Secrets Manager
        response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
        tokens = json.loads(response['SecretString'])
        
        # Handle missing or None user_id in stored tokens
        stored_user_id = tokens.get('user_id')
        if stored_user_id is None:
            logger.info(f"No user_id in stored tokens, using default: {user_id}")
            tokens['user_id'] = user_id
        elif stored_user_id != user_id:
            logger.warning(f"User ID mismatch: expected {user_id}, got {stored_user_id}")
            # For single-user applications, allow fallback to default
            if user_id == "default" or stored_user_id == "default":
                logger.info("Allowing fallback for single-user application")
            else:
                raise ValueError(f"User ID mismatch: expected {user_id}, got {stored_user_id}")
        
        # Check if token needs refresh
        if is_token_expired(tokens):
            logger.info("Access token expired, attempting refresh")
            
            # Refresh token
            new_tokens = refresh_access_token(tokens['refresh_token'])
            if not new_tokens:
                raise ValueError("Failed to refresh access token - user needs to reconnect")
            
            # Store refreshed tokens
            new_tokens['user_id'] = user_id
            secretsmanager.update_secret(
                SecretId=STRAVA_OAUTH_SECRET,
                SecretString=json.dumps(new_tokens)
            )
            
            return new_tokens['access_token']
        
        return tokens['access_token']
        
    except Exception as e:
        logger.error(f"Failed to get access token: {str(e)}")
        raise


def is_token_expired(tokens: Dict[str, Any]) -> bool:
    """Check if access token is expired or will expire soon"""
    try:
        expires_at = tokens.get('expires_at')
        if not expires_at:
            return True
        
        # Convert to datetime (handle both timestamp and ISO format)
        if isinstance(expires_at, (int, float)):
            expiry_time = datetime.fromtimestamp(expires_at)
        else:
            try:
                # Try ISO format first
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if expiry_time.tzinfo is None:
                    expiry_time = expiry_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
            except ValueError:
                # Fallback to timestamp parsing
                try:
                    expiry_time = datetime.fromtimestamp(float(expires_at))
                except (ValueError, TypeError):
                    logger.error(f"Unable to parse expires_at: {expires_at}")
                    return True
        
        # Check if expires within 5 minutes (buffer for safety)
        buffer_time = datetime.now() + timedelta(minutes=5)
        
        is_expired = expiry_time <= buffer_time
        
        if is_expired:
            logger.info(f"Token expires at {expiry_time}, current time + buffer: {buffer_time}")
        
        return is_expired
        
    except Exception as e:
        logger.error(f"Error checking token expiry: {e}")
        return True  # Assume expired on error


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh access token using refresh token"""
    try:
        # Get client_id and client_secret from Secrets Manager
        try:
            # First, try to get client_id from OAuth tokens
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            oauth_data = json.loads(response['SecretString'])
            client_id = oauth_data.get('client_id')
        except Exception as e:
            logger.error(f"Failed to get client_id from OAuth tokens: {e}")
            client_id = None
        
        # Get client_secret from app config secret
        try:
            app_secret_name = os.environ.get('STRAVA_APP_SECRET', 'strava-ai-boost-app-config')
            response = secretsmanager.get_secret_value(SecretId=app_secret_name)
            app_config = json.loads(response['SecretString'])
            client_secret = app_config.get('client_secret')
            # Also get client_id from app config if not found in OAuth tokens
            if not client_id:
                client_id = app_config.get('client_id')
        except Exception as e:
            logger.error(f"Failed to get client_secret from app config: {e}")
            client_secret = None
        
        if not client_id or not client_secret:
            logger.error(f"Missing credentials for token refresh - client_id: {client_id is not None}, client_secret: {client_secret is not None}")
            return None
        
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        logger.info(f"Attempting to refresh token with client_id: {client_id}")
        
        response = requests.post("https://www.strava.com/oauth/token", data=token_data, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
            return None
        
        new_tokens = response.json()
        
        # Validate response
        if 'access_token' not in new_tokens:
            logger.error(f"Invalid token refresh response: {new_tokens}")
            return None
        
        # Add metadata
        new_tokens['obtained_at'] = datetime.utcnow().isoformat()
        new_tokens['last_refreshed'] = datetime.utcnow().isoformat()
        
        logger.info("Successfully refreshed access token")
        
        return new_tokens
        
    except requests.RequestException as e:
        logger.error(f"HTTP error during token refresh: {e}")
        return None
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return None


def fetch_activity_data(activity_id: str, access_token: str) -> Dict[str, Any]:
    """
    Fetch complete activity data from Strava API
    
    Retrieves all 67+ available Strava fields for comprehensive analysis
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/activities/{activity_id}"
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        activity_data = response.json()
        
        # Log activity title and description (CRITICAL for content generation)
        activity_name = activity_data.get('name', 'Untitled')
        activity_description = activity_data.get('description', '')
        logger.info(f"📝 Activity Title: {activity_name}")
        
        # Log location data for debugging
        location_city = activity_data.get('location_city')
        location_country = activity_data.get('location_country')
        start_latlng = activity_data.get('start_latlng', [])
        logger.info(f"Location data - City: {location_city}, Country: {location_country}")
        
        # Log available fields for debugging
        logger.debug(f"Activity fields: {list(activity_data.keys())}")
        
        return activity_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Strava API request failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch activity data: {str(e)}")
        raise


def fetch_streams_data(activity_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch complete Strava streams data with second-by-second granularity
    
    Retrieves velocity_smooth, heartrate, time, distance, altitude streams
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        
        # Request all available stream types for maximum precision
        stream_types = [
            'velocity_smooth',  # Smoothed velocity data
            'heartrate',        # Heart rate data
            'time',            # Time series
            'distance',        # Distance series
            'altitude',        # Elevation data
            'cadence',         # Cadence (if available)
            'watts',           # Power data (if available)
            'temp',            # Temperature (if available)
            'moving',          # Moving/stopped indicator
            'grade_smooth'     # Smoothed grade data
        ]
        
        url = f"{STRAVA_API_BASE}/activities/{activity_id}/streams"
        params = {
            'keys': ','.join(stream_types),
            'key_by_type': 'true'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 404:
            logger.info(f"No streams data available for activity {activity_id}")
            return None
        
        response.raise_for_status()
        streams_data = response.json()
        
        logger.info(f"Fetched streams data: {list(streams_data.keys())} streams")
        
        # Log stream lengths for debugging
        for stream_type, stream_data in streams_data.items():
            if isinstance(stream_data, dict) and 'data' in stream_data:
                logger.debug(f"{stream_type}: {len(stream_data['data'])} points")
        
        return streams_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Streams API request failed: {str(e)}")
        # Don't raise - streams data is optional
        return None
    except Exception as e:
        logger.error(f"Failed to fetch streams data: {str(e)}")
        # Don't raise - streams data is optional
        return None


def fetch_athlete_stats(athlete_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch athlete statistics from Strava API
    
    Returns yearly totals, all-time totals, recent totals, and records
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/athletes/{athlete_id}/stats"
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        stats_data = response.json()
        
        logger.info(f"Fetched athlete stats for {athlete_id}")
        
        # Log key stats for debugging
        ytd_run = stats_data.get('ytd_run_totals', {})
        if ytd_run:
            ytd_distance = ytd_run.get('distance', 0) / 1000  # Convert to km
            ytd_count = ytd_run.get('count', 0)
            logger.info(f"YTD Run Stats: {ytd_distance:.0f} km in {ytd_count} activities")
        
        return stats_data
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Athlete stats API request failed: {str(e)}")
        # Don't raise - stats data is optional
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch athlete stats: {str(e)}")
        # Don't raise - stats data is optional
        return None


def fetch_athlete_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch athlete profile from Strava API
    
    Returns FTP, weight, bikes, shoes for context
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/athlete"
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        profile_data = response.json()
        
        logger.info(f"Fetched athlete profile")
        
        # Log key profile data
        ftp = profile_data.get('ftp')
        weight = profile_data.get('weight')
        if ftp:
            logger.info(f"Athlete FTP: {ftp}W")
        if weight:
            logger.info(f"Athlete Weight: {weight}kg")
        
        return profile_data
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Athlete profile API request failed: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch athlete profile: {str(e)}")
        return None


def fetch_gear_details(gear_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch gear details from Strava API
    
    Returns gear name, brand, model, and total distance
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/gear/{gear_id}"
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        gear_data = response.json()
        
        logger.info(f"Fetched gear details: {gear_data.get('name')}")
        
        # Log gear mileage
        gear_distance = gear_data.get('distance', 0) / 1000  # km
        logger.info(f"Gear mileage: {gear_distance:.0f} km")
        
        return gear_data
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Gear details API request failed: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch gear details: {str(e)}")
        return None


def store_activity_data(
    activity_id: str,
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    athlete_stats: Optional[Dict[str, Any]],
    athlete_profile: Optional[Dict[str, Any]],
    gear_details: Optional[Dict[str, Any]],
    user_config: Dict[str, Any]
) -> None:
    """
    Store ALL activity data in DynamoDB to avoid Step Functions 256KB payload limit
    
    This stores the complete fetched data so downstream Lambdas can retrieve it
    without passing large payloads through Step Functions
    """
    try:
        from decimal import Decimal
        import json
        
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        original_description = activity_data.get('description', '')
        original_name = activity_data.get('name', '')
        
        # Convert floats to Decimal for DynamoDB
        distance = activity_data.get('distance', 0)
        elevation = activity_data.get('total_elevation_gain', 0)
        
        # Extract location data
        location_city = activity_data.get('location_city')
        location_country = activity_data.get('location_country')
        start_latlng = activity_data.get('start_latlng', [])
        
        # If Strava didn't provide city/country but we have GPS, do reverse geocoding
        if not location_city and not location_country and start_latlng and len(start_latlng) >= 2:
            logger.info(f"Strava location empty, attempting reverse geocoding for GPS: {start_latlng}")
            geocoded = reverse_geocode_location(start_latlng[0], start_latlng[1])
            location_city = geocoded.get('city')
            location_country = geocoded.get('country')
            logger.info(f"Reverse geocoded result: {location_city}, {location_country}")
            
            # Update activity_data with enriched location
            if location_city:
                activity_data['location_city'] = location_city
            if location_country:
                activity_data['location_country'] = location_country
            
            # Also fetch weather data for outdoor activities with GPS
            start_date = activity_data.get('start_date')
            if start_date:
                weather_data = fetch_weather_data(start_latlng[0], start_latlng[1], start_date)
                # Store weather data in activity_data for content generation
                if weather_data:
                    activity_data['fetched_weather'] = weather_data
        
        # Helper function to convert floats to Decimal recursively
        def convert_floats(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: convert_floats(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats(item) for item in obj]
            return obj
        
        # Build DynamoDB item with ALL data
        item = {
            'activity_id': activity_id,
            'original_name': original_name,
            'original_description': original_description,
            'activity_type': activity_data.get('type', 'Unknown'),
            'distance': Decimal(str(distance)) if distance else Decimal('0'),
            'moving_time': activity_data.get('moving_time', 0),
            'total_elevation_gain': Decimal(str(elevation)) if elevation else Decimal('0'),
            'start_date': activity_data.get('start_date', ''),
            'processing_status': 'fetched',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            # Store complete data as JSON strings to avoid DynamoDB item size limits
            'activity_data_json': json.dumps(convert_floats(activity_data), default=str),
            'streams_data_json': json.dumps(convert_floats(streams_data), default=str) if streams_data else None,
            'athlete_stats_json': json.dumps(convert_floats(athlete_stats), default=str) if athlete_stats else None,
            'athlete_profile_json': json.dumps(convert_floats(athlete_profile), default=str) if athlete_profile else None,
            'gear_details_json': json.dumps(convert_floats(gear_details), default=str) if gear_details else None
        }
        
        # Add location data if available
        if location_city:
            item['location_city'] = location_city
        if location_country:
            item['location_country'] = location_country
        if start_latlng and len(start_latlng) >= 2:
            item['start_latitude'] = Decimal(str(start_latlng[0]))
            item['start_longitude'] = Decimal(str(start_latlng[1]))
        
        table.put_item(Item=item)
        
        logger.info(f"Stored complete activity data for {activity_id} in DynamoDB")
        
    except Exception as e:
        logger.error(f"Failed to store activity data: {str(e)}")
        # Raise because this is critical - downstream Lambdas need this data
        raise


def update_rate_limits(api_calls_made: int) -> None:
    """Update rate limit counters in DynamoDB"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        current_time = datetime.utcnow()
        
        # Update short-term limit
        table.update_item(
            Key={'limit_type': 'short_term'},
            UpdateExpression="ADD current_usage :calls SET last_request = :time",
            ExpressionAttributeValues={
                ':calls': api_calls_made,
                ':time': current_time.isoformat()
            }
        )
        
        # Update daily limit
        table.update_item(
            Key={'limit_type': 'daily'},
            UpdateExpression="ADD current_usage :calls SET last_request = :time",
            ExpressionAttributeValues={
                ':calls': api_calls_made,
                ':time': current_time.isoformat()
            }
        )
        
        logger.info(f"Updated rate limits: +{api_calls_made} API calls")
        
    except Exception as e:
        logger.error(f"Failed to update rate limits: {str(e)}")
        # Don't raise - rate limit tracking is important but not critical


def fetch_user_configuration(user_id: str) -> Dict[str, Any]:
    """Fetch user configuration from DynamoDB for module decisions"""
    try:
        # Get user configuration table name from environment
        user_config_table = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
        table = dynamodb.Table(user_config_table)
        
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in response:
            user_config = response['Item']
            
            # Migration: Convert old flat format to nested format if needed (one-time migration)
            if 'modules_config' not in user_config:
                user_config['modules_config'] = {}
                
                # Migrate campus_coach if exists
                if 'campus_coach_enabled' in user_config:
                    user_config['modules_config']['campus_coach'] = {
                        'enabled': user_config.get('campus_coach_enabled', False),
                        'configured': user_config.get('campus_coach_configured', False)
                    }
                
                # Migrate enduraw if exists
                if 'enduraw_enabled' in user_config:
                    user_config['modules_config']['enduraw'] = {
                        'enabled': user_config.get('enduraw_enabled', False),
                        'wait_time': user_config.get('enduraw_wait_time', '2 minutes')
                    }
                
                # Save migrated config back to DynamoDB
                try:
                    table.put_item(Item=user_config)
                    logger.info(f"Migrated user configuration to nested format for {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to save migrated config: {e}")
            
            logger.info(f"Retrieved user configuration for {user_id}")
            return user_config
        else:
            # Return default configuration if user config doesn't exist
            default_config = {
                'user_id': user_id,
                'modules_config': {
                    'campus_coach': {
                        'enabled': False
                    },
                    'enduraw': {
                        'enabled': False
                    }
                },
                'strava_connected': False,
                'created_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"No user configuration found for {user_id}, using defaults")
            return default_config
            
    except Exception as e:
        logger.error(f"Failed to fetch user configuration for {user_id}: {str(e)}")
        # Return minimal default config on error
        return {
            'user_id': user_id,
            'modules_config': {
                'campus_coach': {'enabled': False},
                'enduraw': {'enabled': False}
            },
            'strava_connected': False
        }



def reverse_geocode_location(latitude: float, longitude: float) -> Dict[str, Optional[str]]:
    """
    Reverse geocode coordinates to get city and country using Nominatim (OpenStreetMap)
    
    API Documentation: https://nominatim.org/release-docs/latest/api/Reverse/
    Usage Policy: https://operations.osmfoundation.org/policies/nominatim/
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        
    Returns:
        Dict with 'city' and 'country' keys
    """
    try:
        # Nominatim API endpoint (official OpenStreetMap service)
        url = "https://nominatim.openstreetmap.org/reverse"
        
        # Parameters according to Nominatim documentation
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 10  # City level
        }
        
        # Headers according to Nominatim usage policy
        headers = {
            'User-Agent': 'StravaAIBoost/1.0 (https://github.com/strava-ai-boost; contact@strava-ai-boost.com)'  # Required by Nominatim policy
        }
        
        # Make request with timeout
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            # Extract city (try multiple fields as per Nominatim docs)
            city = (
                address.get('city') or 
                address.get('town') or 
                address.get('village') or 
                address.get('municipality') or
                address.get('county')
            )
            
            # Extract country
            country = address.get('country')
            
            logger.info(f"Reverse geocoded: {city}, {country}")
            
            return {
                'city': city,
                'country': country
            }
        else:
            logger.warning(f"Nominatim returned status {response.status_code}")
            return {'city': None, 'country': None}
            
    except Exception as e:
        logger.error(f"Reverse geocoding failed: {str(e)}")
        return {'city': None, 'country': None}



def fetch_weather_data(latitude: float, longitude: float, date_time: str) -> Dict[str, Any]:
    """
    Fetch historical weather data using Open-Meteo API (free, no API key required)
    
    API Documentation: https://open-meteo.com/en/docs
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        date_time: ISO datetime string (e.g., "2025-12-30T10:00:00Z")
        
    Returns:
        Dict with weather data (temperature, wind_speed, humidity, etc.)
    """
    try:
        # Parse date from ISO string
        from datetime import datetime
        dt = datetime.fromisoformat(date_time.replace('Z', '+00:00'))
        date_str = dt.strftime('%Y-%m-%d')
        hour = dt.hour
        
        # Open-Meteo API endpoint
        url = "https://archive-api.open-meteo.com/v1/archive"
        
        # Parameters according to Open-Meteo documentation
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'start_date': date_str,
            'end_date': date_str,
            'hourly': 'temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m',
            'timezone': 'auto'
        }
        
        # Make request
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            hourly = data.get('hourly', {})
            
            # Get data for the specific hour
            if hourly and len(hourly.get('time', [])) > hour:
                weather = {
                    'temperature': hourly['temperature_2m'][hour] if 'temperature_2m' in hourly else None,
                    'humidity': hourly['relative_humidity_2m'][hour] if 'relative_humidity_2m' in hourly else None,
                    'wind_speed': hourly['wind_speed_10m'][hour] if 'wind_speed_10m' in hourly else None,
                    'wind_direction': hourly['wind_direction_10m'][hour] if 'wind_direction_10m' in hourly else None
                }
                
                logger.info(f"Weather data: {weather['temperature']}°C, wind {weather['wind_speed']}km/h")
                return weather
            else:
                logger.warning("No hourly data available for this time")
                return {}
        else:
            logger.warning(f"Open-Meteo returned status {response.status_code}")
            return {}
            
    except Exception as e:
        logger.error(f"Weather fetch failed: {str(e)}")
        return {}
