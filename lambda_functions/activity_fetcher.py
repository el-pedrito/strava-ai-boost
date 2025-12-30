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
        
        # Fetch user configuration for module decisions
        user_config = fetch_user_configuration(user_id)
        
        # Store original description backup
        store_activity_backup(activity_id, activity_data)
        
        # Update rate limit usage
        update_rate_limits(2)  # Activity + streams API calls
        
        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'user_id': user_id,
            'activity_data': activity_data,
            'streams_data': streams_data,
            'user_config': user_config,
            'fetched_at': datetime.utcnow().isoformat()
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
        
        logger.info(f"Fetched activity data: {len(activity_data)} fields")
        
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


def store_activity_backup(activity_id: str, activity_data: Dict[str, Any]) -> None:
    """Store original activity description in DynamoDB for backup"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        original_description = activity_data.get('description', '')
        original_name = activity_data.get('name', '')
        
        table.put_item(
            Item={
                'activity_id': activity_id,
                'original_name': original_name,
                'original_description': original_description,
                'activity_type': activity_data.get('type', 'Unknown'),
                'distance': activity_data.get('distance', 0),
                'moving_time': activity_data.get('moving_time', 0),
                'total_elevation_gain': activity_data.get('total_elevation_gain', 0),
                'start_date': activity_data.get('start_date', ''),
                'processing_status': 'fetched',
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
        )
        
        logger.info(f"Stored activity backup for {activity_id}")
        
    except Exception as e:
        logger.error(f"Failed to store activity backup: {str(e)}")
        # Don't raise - backup is important but not critical for processing


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