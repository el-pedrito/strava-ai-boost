"""
Activity Fetcher Lambda Function

Fetches complete activity data, laps, and athlete context from Strava API.
Handles comprehensive data retrieval for analysis.
"""

import json
import os
from decimal import Decimal
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta
from shared.logger import get_logger
from shared.strava_oauth import refresh_access_token as shared_refresh_access_token

logger = get_logger("activity-fetcher")

# Initialize AWS clients with region
REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

# HTTP session with retry for external API calls
_http_session = None


def _get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        _http_session.mount("https://", HTTPAdapter(max_retries=retry))
    return _http_session


# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']

# Strava API configuration
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Body weight bounds (kg), mirrored from user_preferences_api validation
BODY_WEIGHT_MIN_KG = 30
BODY_WEIGHT_MAX_KG = 250


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for fetching activity data from Strava API

    Fetches activity data, laps, athlete context, and optional integrations.
    """
    try:
        activity_id = event.get('activity_id')
        user_id = event.get('user_id')

        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")

        logger.info(f"Fetching activity data for activity {activity_id}")

        # Get OAuth tokens
        access_token = get_access_token(user_id)

        # Fetch activity data
        activity_data = fetch_activity_data(activity_id, access_token)

        # Fetch laps data (device-recorded intervals/auto-laps)
        laps_data = fetch_laps_data(activity_id, access_token)

        # Fetch the per-activity HR zone distribution (Strava Summit feature).
        # This is the authoritative source for which HR zone the session was in.
        # It is computed once here and stored on activity_data so downstream
        # consumers (content agent, coach) READ it and never invent a zone number.
        hr_zone = compute_hr_zone(fetch_activity_zones(activity_id, access_token))
        if hr_zone:
            activity_data['_strava_hr_zone'] = hr_zone
            logger.info(
                f"HR zone (Strava): {hr_zone['label']} "
                f"({hr_zone['dominant_pct']}% of time)"
            )

        # Fetch athlete stats for context (yearly totals, records, etc.)
        athlete_id = activity_data.get('athlete', {}).get('id') or user_id
        athlete_stats = fetch_athlete_stats(athlete_id, access_token)

        # Fetch athlete profile for FTP, weight
        athlete_profile = fetch_athlete_profile(access_token)

        # Fetch user configuration for module decisions
        user_config = fetch_user_configuration(user_id)

        # Opportunistically seed body weight from the Strava profile (no extra API
        # call), without ever overwriting a manual entry.
        persist_body_weight_from_strava(user_id, athlete_profile, user_config)

        # Fetch Intervals.icu data if module is enabled
        intervals_icu_data = fetch_intervals_icu_data(activity_data, user_config)

        # Store ALL data in DynamoDB to avoid Step Functions 256KB payload limit
        store_activity_data(
            activity_id=activity_id,
            activity_data=activity_data,
            athlete_stats=athlete_stats,
            athlete_profile=athlete_profile,
            user_config=user_config,
            intervals_icu_data=intervals_icu_data,
            laps_data=laps_data
        )
        
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
        
        logger.info(f"Attempting to refresh token with client_id: {client_id}")

        # Single implementation of the token exchange lives in
        # shared/strava_oauth.py (validates the response and stamps
        # timezone-aware obtained_at/last_refreshed metadata).
        return shared_refresh_access_token(
            refresh_token,
            client_id,
            client_secret,
            http_session=_get_http_session(),
        )

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
        
        response = _get_http_session().get(url, headers=headers, timeout=30)
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


def fetch_laps_data(activity_id: str, access_token: str) -> Optional[list]:
    """
    Fetch activity laps from Strava API.

    Returns the laps recorded by the device (auto-lap or manual lap button).
    Each lap includes average_speed, max_speed, distance, elapsed_time,
    moving_time, average_cadence, pace_zone, total_elevation_gain, etc.

    Available to all users (no premium requirement). Requires activity:read scope.
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/activities/{activity_id}/laps"

        response = _get_http_session().get(url, headers=headers, timeout=30)

        if response.status_code == 404:
            logger.info(f"No laps data available for activity {activity_id}")
            return None

        response.raise_for_status()
        laps = response.json()

        if not laps:
            logger.info(f"Empty laps response for activity {activity_id}")
            return None

        logger.info(f"Fetched {len(laps)} laps for activity {activity_id}")
        for i, lap in enumerate(laps):
            avg_speed = lap.get('average_speed', 0)
            pace = f"{int(1000/(avg_speed*60))}:{int((1000/(avg_speed*60) % 1)*60):02d}/km" if avg_speed > 0 else "N/A"
            logger.debug(f"  Lap {i+1}: {lap.get('distance', 0):.0f}m in {lap.get('moving_time', 0)}s ({pace})")

        return laps

    except requests.exceptions.RequestException as e:
        logger.warning(f"Laps API request failed: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch laps data: {str(e)}")
        return None


# HR zone labels, indexed by Strava zone number (buckets are ordered Z1..Zn).
_HR_ZONE_LABELS = {
    1: "Zone 1 (recuperation)",
    2: "Zone 2 (endurance fondamentale)",
    3: "Zone 3 (tempo / seuil bas)",
    4: "Zone 4 (seuil)",
    5: "Zone 5 (VO2max / anaerobie)",
}


def fetch_activity_zones(activity_id: str, access_token: str) -> Optional[list]:
    """
    Fetch the per-activity HR zone distribution from Strava.

    Endpoint: GET /activities/{id}/zones (getZonesByActivityId). This is a
    Strava Summit (subscriber) feature but requires no OAuth scope beyond the
    activity:read already used for laps.

    The response is a list of ActivityZone objects; we return the
    distribution_buckets of the 'heartrate' entry (ordered Z1..Zn, each
    {min, max, time}). Returns None when zones are unavailable (404 / non-Summit
    403 / no HR sensor / any error) so the caller degrades gracefully.
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/activities/{activity_id}/zones"

        response = _get_http_session().get(url, headers=headers, timeout=30)

        if response.status_code in (403, 404):
            logger.info(
                f"Activity zones unavailable ({response.status_code}) for {activity_id}"
            )
            return None

        response.raise_for_status()
        zones = response.json()

        if not isinstance(zones, list):
            return None

        for zone in zones:
            if isinstance(zone, dict) and zone.get('type') == 'heartrate':
                buckets = zone.get('distribution_buckets')
                if buckets:
                    logger.info(
                        f"Fetched {len(buckets)} HR zone buckets for activity {activity_id}"
                    )
                    return buckets

        logger.info(f"No heartrate zones in activity zones for {activity_id}")
        return None

    except requests.exceptions.RequestException as e:
        logger.warning(f"Activity zones API request failed: {str(e)}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch activity zones: {str(e)}")
        return None


def compute_hr_zone(buckets: Optional[list]) -> Optional[Dict[str, Any]]:
    """
    Reduce Strava HR zone buckets to the dominant zone (by time spent).

    Pure function (unit-tested). `buckets` is the ordered Z1..Zn list from
    fetch_activity_zones. Returns {zone, label, dominant_pct, range_bpm} for the
    zone where the athlete spent the most time, or None if there is no usable
    data. Dominant-by-time answers "which zone was this session", which is what
    the narrative needs, and is robust to a stray second in an adjacent bucket.
    """
    if not buckets or not isinstance(buckets, list):
        return None

    times = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            return None
        try:
            times.append(float(bucket.get('time', 0) or 0))
        except (TypeError, ValueError):
            times.append(0.0)

    total = sum(times)
    if total <= 0:
        return None

    dom_idx = max(range(len(times)), key=lambda i: times[i])
    zone_num = dom_idx + 1
    dominant = buckets[dom_idx]

    return {
        'zone': zone_num,
        'label': _HR_ZONE_LABELS.get(zone_num, f"Zone {zone_num}"),
        'dominant_pct': round(times[dom_idx] / total * 100, 1),
        'range_bpm': [dominant.get('min'), dominant.get('max')],
    }


def fetch_athlete_stats(athlete_id: str, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch athlete statistics from Strava API
    
    Returns yearly totals, all-time totals, recent totals, and records
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/athletes/{athlete_id}/stats"
        
        response = _get_http_session().get(url, headers=headers, timeout=30)
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
        
        response = _get_http_session().get(url, headers=headers, timeout=30)
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


def persist_body_weight_from_strava(
    user_id: str,
    athlete_profile: Optional[Dict[str, Any]],
    user_config: Dict[str, Any],
) -> None:
    """Seed body_weight_kg in user_preferences from the Strava athlete profile.

    The weight already comes back in the /athlete response (kg, structured,
    maintained by the athlete), so no extra API call is made. We persist it only
    when the athlete has no value yet: an explicit manual entry is authoritative
    because Strava can be stale or empty. An existing value (manual or previously
    seeded) is never overwritten.
    """
    if not athlete_profile:
        return

    weight = athlete_profile.get('weight')
    if weight is None:
        return

    try:
        weight_value = Decimal(str(weight))
    except (ArithmeticError, ValueError, TypeError):
        logger.warning("Athlete weight from Strava is not a number, skipping persistence")
        return

    if not (BODY_WEIGHT_MIN_KG <= weight_value <= BODY_WEIGHT_MAX_KG):
        logger.warning(f"Athlete weight {weight_value}kg out of bounds, skipping persistence")
        return

    preferences = user_config.get('user_preferences')
    if not isinstance(preferences, dict):
        preferences = {}

    if preferences.get('body_weight_kg') is not None:
        # Manual or already-seeded value is authoritative, never overwrite.
        return

    user_config_table = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
    table = dynamodb.Table(user_config_table)

    try:
        if user_config.get('user_preferences') is None:
            # No preferences map yet: create it with the seeded value. Nothing to
            # wipe, and this avoids the invalid nested-path update on a missing map.
            table.update_item(
                Key={'user_id': user_id},
                UpdateExpression='SET user_preferences = :prefs',
                ExpressionAttributeValues={':prefs': {'body_weight_kg': weight_value}},
                ConditionExpression='attribute_not_exists(user_preferences)',
            )
        else:
            table.update_item(
                Key={'user_id': user_id},
                UpdateExpression='SET user_preferences.body_weight_kg = :w',
                ExpressionAttributeValues={':w': weight_value},
                ConditionExpression='attribute_not_exists(user_preferences.body_weight_kg)',
            )
        logger.info(f"Seeded body_weight_kg={weight_value} from Strava for {user_id}")
        # Keep the in-memory copy consistent for downstream use in this invocation.
        preferences['body_weight_kg'] = weight_value
        user_config['user_preferences'] = preferences
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            logger.info("body_weight_kg already set (concurrent write), not overwriting")
        else:
            logger.warning(f"Failed to seed body_weight_kg from Strava: {str(e)}")


def _compute_wellness_trends(wellness_history: list, activity_date: str) -> Dict[str, Any]:
    """Compute 30-day trends from wellness history for key metrics."""
    trends = {}
    metric_keys = {
        'vo2max': 'vo2max',
        'hrv': 'hrv',
        'restingHR': 'resting_hr',
        'ctl': 'ctl',
        'sleepSecs': 'sleep_duration',
        'sleepQuality': 'sleep_quality',
    }

    for api_key, trend_key in metric_keys.items():
        values = [
            (entry.get('id', ''), entry.get(api_key))
            for entry in wellness_history
            if entry.get(api_key) is not None
        ]
        if len(values) < 2:
            continue

        values.sort(key=lambda x: x[0])
        all_vals = [v for _, v in values]

        current = all_vals[-1]
        avg_30d = round(sum(all_vals) / len(all_vals), 1)

        # Compare last 7 days vs previous 7 days for short-term trend
        last_7 = [v for d, v in values if d >= (datetime.strptime(activity_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')]
        prev_7 = [v for d, v in values if (datetime.strptime(activity_date, '%Y-%m-%d') - timedelta(days=14)).strftime('%Y-%m-%d') <= d < (datetime.strptime(activity_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')]

        delta = None
        direction = 'stable'
        if last_7 and prev_7:
            avg_last = sum(last_7) / len(last_7)
            avg_prev = sum(prev_7) / len(prev_7)
            delta = round(avg_last - avg_prev, 1)
            if abs(delta) < 0.5:
                direction = 'stable'
            elif delta > 0:
                direction = 'up'
            else:
                direction = 'down'

        trends[trend_key] = {
            'current': current,
            'avg_30d': avg_30d,
            'delta_7d': delta,
            'direction': direction,
            'data_points': len(all_vals),
        }

    return trends


def fetch_intervals_icu_data(activity_data: Dict[str, Any], user_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fetch fitness/fatigue context from Intervals.icu API.

    Only fetches data that is unique and differentiating vs Strava/Enduraw/Campus Coach:
    - CTL (fitness), ATL (fatigue), TSB (form) — training load balance
    - Ramp rate — progression speed
    - HRV — recovery indicator
    - Resting HR — baseline heart rate
    - VO2max — estimated aerobic capacity
    - Sleep data — duration, quality
    - Decoupling — aerobic efficiency (from activity endpoint)

    Returns None if module is not enabled or API call fails.
    """
    modules_config = user_config.get('modules_config', {})
    intervals_config = modules_config.get('intervals_icu', {})
    if not intervals_config.get('enabled', False):
        logger.info("Intervals.icu module not enabled, skipping")
        return None

    intervals_secret_name = os.environ.get('INTERVALS_ICU_SECRET', 'strava-ai-boost-intervals-icu-credentials')
    try:
        response = secretsmanager.get_secret_value(SecretId=intervals_secret_name)
        secret_data = json.loads(response['SecretString'])
        api_key = secret_data.get('api_key', '')
        if not api_key:
            logger.warning("Intervals.icu API key is empty in Secrets Manager")
            return None
    except ClientError as e:
        logger.warning(f"Failed to get Intervals.icu credentials: {e}")
        return None

    start_date_str = activity_data.get('start_date', '')
    if not start_date_str:
        logger.warning("No start_date in activity_data, cannot fetch Intervals.icu data")
        return None

    try:
        activity_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        logger.warning(f"Invalid start_date format: {start_date_str}")
        return None

    base_url = "https://intervals.icu/api/v1/athlete/0"
    auth = ("API_KEY", api_key)
    result = {}

    # 1. Wellness day-of: CTL/ATL/Form + tracker metrics (sleep, HRV, restingHR, VO2max)
    try:
        resp = _get_http_session().get(f"{base_url}/wellness/{activity_date}", auth=auth, timeout=10)
        if resp.status_code == 200:
            w = resp.json()
            ctl = w.get('ctl')
            atl = w.get('atl')
            result['fitness'] = {
                'ctl': ctl,
                'atl': atl,
                'form': round(ctl - atl, 1) if ctl is not None and atl is not None else None,
                'ramp_rate': w.get('rampRate'),
                'hrv': w.get('hrv'),
                'resting_hr': w.get('restingHR'),
                'vo2max': w.get('vo2max'),
            }
            sleep_time = w.get('sleepSecs')
            sleep_quality = w.get('sleepQuality')
            if sleep_time is not None or sleep_quality is not None:
                result['sleep'] = {
                    'duration_seconds': sleep_time,
                    'quality': sleep_quality,
                }
            logger.info(f"Intervals.icu day-of ({activity_date}): CTL={ctl}, ATL={atl}, Form={result['fitness']['form']}, HRV={w.get('hrv')}, VO2max={w.get('vo2max')}, Sleep={sleep_time}")
        elif resp.status_code == 404:
            logger.info(f"No Intervals.icu wellness data for {activity_date}")
        else:
            logger.warning(f"Intervals.icu wellness API returned {resp.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Intervals.icu wellness API request failed: {e}")

    # 1b. Fallback J-1: tracker data may not be synced yet on activity day
    try:
        prev_date = (datetime.fromisoformat(start_date_str.replace('Z', '+00:00')) - timedelta(days=1)).strftime('%Y-%m-%d')
        resp = _get_http_session().get(f"{base_url}/wellness/{prev_date}", auth=auth, timeout=10)
        if resp.status_code == 200:
            w_prev = resp.json()
            # No sleep fallback to J-1: it would show the wrong night (2 nights before activity)
            # Sleep data for day J = night before J. If not synced yet, skip rather than show stale data.
            # Fallback HRV/restingHR/VO2max if day-of is null
            if result.get('fitness'):
                for key, api_key in [('hrv', 'hrv'), ('resting_hr', 'restingHR'), ('vo2max', 'vo2max')]:
                    if result['fitness'].get(key) is None and w_prev.get(api_key) is not None:
                        result['fitness'][key] = w_prev.get(api_key)
                        logger.info(f"Intervals.icu {key} fallback from {prev_date}: {w_prev.get(api_key)}")
        else:
            logger.info(f"No Intervals.icu wellness data for previous day {prev_date}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Intervals.icu previous day wellness request failed: {e}")

    # 2. Wellness range (30 days): trends for VO2max, HRV, resting HR, sleep
    try:
        oldest = (datetime.fromisoformat(start_date_str.replace('Z', '+00:00')) - timedelta(days=30)).strftime('%Y-%m-%d')
        resp = _get_http_session().get(
            f"{base_url}/wellness",
            params={"oldest": oldest, "newest": activity_date},
            auth=auth, timeout=15,
        )
        if resp.status_code == 200:
            wellness_history = resp.json()
            result['trends'] = _compute_wellness_trends(wellness_history, activity_date)
            logger.info(f"Intervals.icu trends computed from {len(wellness_history)} days of wellness data")
        else:
            logger.warning(f"Intervals.icu wellness range API returned {resp.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Intervals.icu wellness range API request failed: {e}")

    # 3. Activity: decoupling + training load (unique vs Strava/Enduraw)
    try:
        activities_url = f"{base_url}/activities?oldest={activity_date}&newest={activity_date}&fields=decoupling,icu_training_load,icu_intensity"
        resp = _get_http_session().get(activities_url, auth=auth, timeout=10)
        if resp.status_code == 200:
            activities = resp.json()
            if activities:
                act = activities[0]
                decoupling = act.get('decoupling')
                if decoupling is not None:
                    result['decoupling'] = decoupling
                    logger.info(f"Intervals.icu decoupling: {decoupling}%")
                training_load = act.get('icu_training_load')
                if training_load is not None:
                    result['training_load'] = training_load
                intensity = act.get('icu_intensity')
                if intensity is not None:
                    result['intensity_pct'] = intensity
        else:
            logger.warning(f"Intervals.icu activities API returned {resp.status_code}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Intervals.icu activities API request failed: {e}")

    if not result:
        logger.info("No Intervals.icu data retrieved")
        return None

    return result


def store_activity_data(
    activity_id: str,
    activity_data: Dict[str, Any],
    athlete_stats: Optional[Dict[str, Any]],
    athlete_profile: Optional[Dict[str, Any]],
    user_config: Dict[str, Any],
    intervals_icu_data: Optional[Dict[str, Any]] = None,
    laps_data: Optional[list] = None
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

        # Preserve the athlete's TRUE original text across reprocesses.
        # On a reprocess, Strava's current description IS our previously generated
        # text (it carries our signature). Feeding it back as 'original_description'
        # is a self-reinforcing loop: any hallucinated detail (e.g. an invented load
        # like "kettlebell 12kg") gets treated as the athlete's own words and
        # preserved on every subsequent run, defeating prompt rules and Campus data.
        # If the fetched description looks generated, keep the first-seen stored
        # original instead of overwriting it.
        _GENERATED_MARKERS = ('@Generated by Strava AI Boost', 'Strava AI Boost Coach')

        def _looks_generated(text: str) -> bool:
            return any(marker in (text or '') for marker in _GENERATED_MARKERS)

        if _looks_generated(original_description):
            try:
                existing_item = table.get_item(Key={'activity_id': activity_id}).get('Item') or {}
            except Exception as exc:
                logger.warning(f"Could not read existing item to preserve original text for {activity_id}: {exc}")
                existing_item = {}
            stored_original = existing_item.get('original_description')
            if stored_original and not _looks_generated(stored_original):
                logger.info(
                    f"Reprocess of {activity_id}: fetched description is our own output; "
                    "preserving stored original_description instead of overwriting it"
                )
                original_description = stored_original
                stored_name = existing_item.get('original_name')
                if stored_name and not _looks_generated(stored_name):
                    original_name = stored_name
            else:
                logger.warning(
                    f"Reprocess of {activity_id}: both fetched and stored descriptions look generated; "
                    "the true original was already lost, agent will rely on structured data (Campus, laps)"
                )

        # Convert floats to Decimal for DynamoDB
        distance = activity_data.get('distance', 0)
        elevation = activity_data.get('total_elevation_gain', 0)

        # Extract location data (from Strava directly)
        location_city = activity_data.get('location_city')
        location_country = activity_data.get('location_country')
        start_latlng = activity_data.get('start_latlng', [])

        # Helper function to convert floats to Decimal recursively
        def convert_floats(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: convert_floats(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats(item) for item in obj]
            return obj

        # Resolve user_id (Strava athlete id) — required by GSI UserActivitiesIndex.
        # Source of truth order: user_config['user_id'], then athlete payload, then athlete_profile.
        athlete_block = activity_data.get('athlete') or {}
        athlete_id_raw = (
            user_config.get('user_id')
            or athlete_block.get('id')
            or (athlete_profile or {}).get('id')
        )
        user_id_str = str(athlete_id_raw) if athlete_id_raw is not None else None
        if not user_id_str:
            logger.warning(
                f"Could not resolve user_id for activity {activity_id} — item will not be indexed by UserActivitiesIndex"
            )

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
            # Store complete data as JSON strings
            'activity_data_json': json.dumps(convert_floats(activity_data), default=str),
            'athlete_stats_json': json.dumps(convert_floats(athlete_stats), default=str) if athlete_stats else None,
            'athlete_profile_json': json.dumps(convert_floats(athlete_profile), default=str) if athlete_profile else None,
            'intervals_icu_json': json.dumps(convert_floats(intervals_icu_data), default=str) if intervals_icu_data else None,
            'laps_json': json.dumps(convert_floats(laps_data), default=str) if laps_data else None
        }
        if user_id_str:
            item['user_id'] = user_id_str
        
        # Set TTL: expire after 365 days
        item['expires_at'] = int((datetime.utcnow() + timedelta(days=365)).timestamp())

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



