"""
Feedback Analyzer Lambda Function

Analyzes user modifications on Strava to learn content preferences.
Runs nightly to compare generated content vs final content.

V2 (Memory Strategy):
- Writes before/after diffs as conversational events to AgentCore Memory
- Uses actor_id=user_id (not "system") for per-user preference isolation
- AgentCore's UserPreferenceStrategy handles extraction & consolidation automatically
- No more manual pattern extraction/aggregation/validation in Lambda
"""

import json
import os
from typing import Dict, Any, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, UTC
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import difflib
from shared.logger import get_logger, metrics, MetricUnit

logger = get_logger("feedback_analyzer")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
_secretsmanager = None


def _get_secretsmanager():
    global _secretsmanager
    if _secretsmanager is None:
        _secretsmanager = boto3.client('secretsmanager')
    return _secretsmanager

# Environment variables
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
STRAVA_OAUTH_SECRET = os.environ.get('STRAVA_OAUTH_SECRET', 'strava-ai-boost-oauth-tokens')
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# HTTP session with retry for Strava API
_http_session = None


def _get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        _http_session.mount("https://", HTTPAdapter(max_retries=retry))
    return _http_session
MEMORY_ID = os.environ.get('BEDROCK_AGENTCORE_MEMORY_ID', '')

# Configuration
ANALYSIS_WINDOW_HOURS = 24  # Minimum delay before analyzing (give user time to edit)
MAX_CONTENT_LENGTH = 4000   # Max chars per message written to memory (AgentCore limit ~9000)


def lambda_handler(event, context):
    """
    Main handler for feedback analysis.

    Triggered nightly by EventBridge. For each modified activity:
    1. Detects user edits by comparing enhanced vs final Strava description
    2. Writes before/after as a conversational event to AgentCore Memory
    3. AgentCore's UserPreferenceStrategy handles extraction & consolidation
    """
    try:
        logger.info("=== Feedback Analyzer V2 Started ===")

        # Get all completed activities not yet analyzed (with min delay for user to edit)
        activities = get_unanalyzed_activities(min_age_hours=ANALYSIS_WINDOW_HOURS)
        logger.info(f"Found {len(activities)} activities to analyze")

        if not activities:
            logger.info("No activities to analyze")
            return {'statusCode': 200, 'message': 'No activities to analyze'}

        # Get Strava access token
        access_token = get_access_token()

        # Initialize AgentCore client for memory writes
        agentcore_client = None
        if MEMORY_ID:
            agentcore_client = boto3.client(
                'bedrock-agentcore',
                region_name=os.getenv('AWS_REGION', 'eu-west-1')
            )

        # Process each activity
        modified_count = 0
        memory_writes = 0
        for activity in activities:
            activity_id = activity['activity_id']
            user_id = str(activity.get('user_id', 'default_user'))

            # Fetch final description from Strava
            final_description = fetch_final_description(activity_id, access_token)

            if final_description is None:
                logger.warning(f"Failed to fetch final description for {activity_id}")
                continue

            # Compare and detect modification
            enhanced = activity['enhanced_description']
            is_modified, similarity = detect_modification(enhanced, final_description)

            # Update DynamoDB with final description
            update_activity_feedback(
                activity_id=activity_id,
                final_description=final_description,
                is_modified=is_modified,
                similarity=similarity
            )

            if is_modified:
                modified_count += 1
                logger.info(f"Activity {activity_id} was modified (similarity: {similarity:.2%})")

                # Write before/after diff as conversational event to AgentCore Memory
                if agentcore_client:
                    success = write_feedback_to_memory(
                        client=agentcore_client,
                        user_id=user_id,
                        activity_id=activity_id,
                        enhanced=enhanced,
                        final=final_description,
                        activity_data=activity
                    )
                    if success:
                        memory_writes += 1
            else:
                logger.info(f"Activity {activity_id} not modified (similarity: {similarity:.2%})")

        # Calculate quality metrics
        metrics_data = calculate_quality_metrics(activities)

        logger.info("=== Feedback Analyzer V2 Completed ===")
        logger.info(f"Activities analyzed: {len(activities)}")
        logger.info(f"Modifications detected: {modified_count}")
        logger.info(f"Memory events written: {memory_writes}")
        logger.info(f"Modification rate: {metrics_data['modification_rate']:.1%}")

        # Publish business metrics
        metrics.add_metric(name="FeedbackAnalyzed", unit=MetricUnit.Count, value=len(activities))
        if modified_count > 0:
            metrics.add_metric(name="FeedbackModified", unit=MetricUnit.Count, value=modified_count)

        return {
            'statusCode': 200,
            'message': 'Feedback analysis completed',
            'activities_analyzed': len(activities),
            'modifications_detected': modified_count,
            'memory_events_written': memory_writes,
            'metrics': metrics_data
        }

    except (ClientError, requests.RequestException) as e:
        logger.error(f"Feedback analyzer failed: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e)
        }
    except (ValueError, KeyError) as e:
        logger.error(f"Feedback analyzer data error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e)
        }


def get_unanalyzed_activities(min_age_hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get completed activities that haven't been feedback-analyzed yet.

    Only includes activities older than min_age_hours to give the user
    time to edit their description before we analyze it.
    """
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)

        # Only analyze activities created at least min_age_hours ago
        cutoff = datetime.now(UTC) - timedelta(hours=min_age_hours)
        cutoff_str = cutoff.isoformat()

        # Scan for completed, unanalyzed activities older than cutoff
        response = table.scan(
            FilterExpression='processing_status = :completed AND (attribute_not_exists(feedback_analyzed) OR feedback_analyzed = :false) AND attribute_exists(enhanced_description) AND created_at < :cutoff',
            ExpressionAttributeValues={
                ':completed': 'completed',
                ':false': False,
                ':cutoff': cutoff_str
            }
        )

        activities = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression='processing_status = :completed AND (attribute_not_exists(feedback_analyzed) OR feedback_analyzed = :false) AND attribute_exists(enhanced_description) AND created_at < :cutoff',
                ExpressionAttributeValues={
                    ':completed': 'completed',
                    ':false': False,
                    ':cutoff': cutoff_str
                },
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            activities.extend(response.get('Items', []))

        return activities

    except ClientError as e:
        logger.error(f"Failed to get unanalyzed activities: {str(e)}")
        return []


def get_access_token() -> str:
    """Get Strava access token from Secrets Manager with automatic refresh"""
    try:
        # Get OAuth tokens directly from Secrets Manager
        response = _get_secretsmanager().get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
        tokens = json.loads(response['SecretString'])
        
        # Check if token needs refresh
        if is_token_expired(tokens):
            logger.info("Access token expired, attempting refresh")
            
            # Refresh token
            new_tokens = refresh_access_token(tokens['refresh_token'])
            if not new_tokens:
                raise ValueError("Failed to refresh access token - user needs to reconnect")
            
            # Store refreshed tokens
            new_tokens['user_id'] = tokens.get('user_id', 'default')
            _get_secretsmanager().update_secret(
                SecretId=STRAVA_OAUTH_SECRET,
                SecretString=json.dumps(new_tokens)
            )
            
            return new_tokens['access_token']
        
        return tokens['access_token']
        
    except (ClientError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to get access token: {str(e)}")
        raise


def is_token_expired(tokens: Dict[str, Any]) -> bool:
    """Check if access token is expired or will expire soon"""
    try:
        expires_at = tokens.get('expires_at')
        if not expires_at:
            return True
        
        # Parse expiry time
        if isinstance(expires_at, (int, float)):
            expiry_time = datetime.fromtimestamp(expires_at, UTC)
        else:
            expiry_time = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
        
        # Check if expired or expires within 5 minutes
        current_time = datetime.now(UTC)
        return expiry_time <= (current_time + timedelta(minutes=5))
        
    except (ValueError, TypeError, OSError) as e:
        logger.warning(f"Error checking token expiry: {e}")
        return True


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh access token using refresh token"""
    try:
        # Get client credentials from app config
        app_secret_name = 'strava-ai-boost-app-config'
        response = _get_secretsmanager().get_secret_value(SecretId=app_secret_name)
        app_config = json.loads(response['SecretString'])
        
        client_id = app_config.get('client_id')
        client_secret = app_config.get('client_secret')
        
        if not client_id or not client_secret:
            logger.error("Missing client credentials for token refresh")
            return None
        
        # Request new token
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        
        response = _get_http_session().post("https://www.strava.com/oauth/token", data=token_data, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code}")
            return None
        
        new_tokens = response.json()
        
        if 'access_token' not in new_tokens:
            logger.error("Invalid token refresh response")
            return None
        
        # Add metadata
        new_tokens['obtained_at'] = datetime.now(UTC).isoformat()
        new_tokens['last_refreshed'] = datetime.now(UTC).isoformat()
        
        logger.info("Successfully refreshed access token")
        return new_tokens
        
    except (ClientError, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error refreshing token: {e}")
        return None


def fetch_final_description(activity_id: str, access_token: str) -> Optional[str]:
    """Fetch final description from Strava API"""
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/activities/{activity_id}"
        
        response = _get_http_session().get(url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            logger.warning(f"Activity {activity_id} not found on Strava")
            return None
        
        response.raise_for_status()
        activity_data = response.json()
        
        return activity_data.get('description', '')
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Strava API request failed for {activity_id}: {str(e)}")
        return None
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Failed to parse final description for {activity_id}: {str(e)}")
        return None


def detect_modification(enhanced: str, final: str) -> Tuple[bool, float]:
    """
    Detect if description was modified
    
    Returns: (is_modified, similarity_score)
    """
    # Normalize for comparison
    enhanced_norm = enhanced.strip().lower()
    final_norm = final.strip().lower()
    
    # Calculate similarity
    similarity = difflib.SequenceMatcher(None, enhanced_norm, final_norm).ratio()
    
    # Consider modified if similarity < 98% (capture even small edits for memory learning)
    is_modified = similarity < 0.98
    
    return is_modified, similarity


def update_activity_feedback(
    activity_id: str,
    final_description: str,
    is_modified: bool,
    similarity: float
) -> None:
    """Update activity with feedback data"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="""
                SET final_description = :final,
                    description_modified = :modified,
                    description_modified_at = :timestamp,
                    feedback_analyzed = :analyzed,
                    feedback_analyzed_at = :timestamp,
                    similarity_score = :similarity
            """,
            ExpressionAttributeValues={
                ':final': final_description,
                ':modified': is_modified,
                ':timestamp': datetime.now(UTC).isoformat(),
                ':analyzed': True,
                ':similarity': str(round(similarity, 4))
            }
        )
        
    except ClientError as e:
        logger.error(f"Failed to update activity feedback: {str(e)}")


def write_feedback_to_memory(
    client,
    user_id: str,
    activity_id: str,
    enhanced: str,
    final: str,
    activity_data: Dict
) -> bool:
    """
    Write before/after diff as conversational event to AgentCore Memory.

    The UserPreferenceStrategy will automatically extract and consolidate
    preferences from these conversational diffs.

    Format:
    - ASSISTANT message: the AI-generated description (with context)
    - USER message: the user's edited version (with context about what changed)
    """
    try:
        # Build context-rich ASSISTANT message (what was generated)
        sport_type = activity_data.get('sport_type', 'Run')
        distance_km = float(activity_data.get('distance', 0)) / 1000
        moving_time = int(activity_data.get('moving_time', 0))
        duration_min = moving_time / 60

        assistant_msg = (
            f"[Activity: {sport_type}, {distance_km:.1f}km, {duration_min:.0f}min]\n"
            f"Generated description:\n{enhanced[:MAX_CONTENT_LENGTH]}"
        )

        # Build USER message (what the user changed it to)
        user_msg = (
            f"I edited the description to:\n{final[:MAX_CONTENT_LENGTH]}"
        )

        # Write as conversational event with user's actual actor_id
        response = client.create_event(
            memoryId=MEMORY_ID,
            actorId=user_id,
            sessionId=f"feedback-{activity_id}",
            eventTimestamp=datetime.now(UTC),
            payload=[
                {
                    'conversational': {
                        'content': {'text': assistant_msg},
                        'role': 'ASSISTANT'
                    }
                },
                {
                    'conversational': {
                        'content': {'text': user_msg},
                        'role': 'USER'
                    }
                }
            ]
        )

        status = response.get('ResponseMetadata', {}).get('HTTPStatusCode')
        logger.info(f"Wrote feedback event for activity {activity_id} (user={user_id}, status={status})")
        return True

    except ClientError as e:
        logger.error(f"Failed to write feedback to memory for {activity_id}: {e}")
        return False


def calculate_quality_metrics(activities: List[Dict]) -> Dict:
    """
    Calculate quality metrics for feedback loop
    
    Best Practice: Monitor business impact metrics
    """
    total = len(activities)
    modified = sum(1 for a in activities if a.get('description_modified'))
    
    # Calculate trend (compare recent vs older activities)
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get activities from 30-60 days ago for comparison
        cutoff_recent = datetime.now(UTC) - timedelta(days=30)
        cutoff_old = datetime.now(UTC) - timedelta(days=60)
        
        response_old = table.scan(
            FilterExpression='feedback_analyzed = :true AND feedback_analyzed_at BETWEEN :old AND :recent',
            ExpressionAttributeValues={
                ':true': True,
                ':old': cutoff_old.isoformat(),
                ':recent': cutoff_recent.isoformat()
            }
        )
        
        old_activities = response_old.get('Items', [])
        old_modified = sum(1 for a in old_activities if a.get('description_modified'))
        old_rate = old_modified / len(old_activities) if old_activities else 0
        
        # Current rate
        current_rate = modified / total if total > 0 else 0
        
        # Determine trend
        if old_rate == 0:
            trend = 'stable'
        elif current_rate < old_rate * 0.9:
            trend = 'improving'
        elif current_rate > old_rate * 1.1:
            trend = 'degrading'
        else:
            trend = 'stable'
        
        improvement_percent = ((old_rate - current_rate) / old_rate * 100) if old_rate > 0 else 0
        
    except (ClientError, ValueError, TypeError, ZeroDivisionError) as e:
        logger.warning(f"Failed to calculate trend: {e}")
        trend = 'unknown'
        old_rate = 0
        current_rate = modified / total if total > 0 else 0
        improvement_percent = 0
    
    return {
        'modification_rate': modified / total if total > 0 else 0,
        'total_activities': total,
        'modified_activities': modified,
        'quality_trend': trend,
        'recent_30d_rate': current_rate,
        'old_30d_rate': old_rate,
        'improvement_percent': round(improvement_percent, 1),
        'timestamp': datetime.now(UTC).isoformat()
    }


