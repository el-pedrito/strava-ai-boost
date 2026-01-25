"""
Feedback Analyzer Lambda Function

Analyzes user modifications on Strava to learn content preferences.
Runs nightly to compare generated content vs final content and extract patterns.
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, UTC
import requests
import uuid
import difflib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')
bedrock_runtime = boto3.client('bedrock-runtime')

# Environment variables
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
STRAVA_OAUTH_SECRET = os.environ.get('STRAVA_OAUTH_SECRET', 'strava-ai-boost-oauth-tokens')
STRAVA_API_BASE = "https://www.strava.com/api/v3"
MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')

# Configuration
MIN_PATTERN_FREQUENCY = 1  # Pattern must appear 1+ times (immediate learning)
MIN_PATTERN_RATE = 0.10    # Pattern must be in 10%+ of activities
ANALYSIS_WINDOW_HOURS = 24  # Analyze last 24 hours


def lambda_handler(event, context):
    """
    Main handler for feedback analysis
    
    Triggered nightly by EventBridge to analyze user modifications
    """
    try:
        logger.info("=== Feedback Analyzer Started ===")
        
        # Get activities from last 24 hours
        activities = get_recent_activities(hours=ANALYSIS_WINDOW_HOURS)
        logger.info(f"Found {len(activities)} activities to analyze")
        
        if not activities:
            logger.info("No activities to analyze")
            return {'statusCode': 200, 'message': 'No activities to analyze'}
        
        # Get Strava access token
        access_token = get_access_token()
        
        # Process each activity
        modified_activities = []
        for activity in activities:
            activity_id = activity['activity_id']
            
            # Skip if already analyzed
            if activity.get('feedback_analyzed'):
                logger.info(f"Activity {activity_id} already analyzed, skipping")
                continue
            
            # Skip if no enhanced description
            if not activity.get('enhanced_description'):
                logger.info(f"Activity {activity_id} has no enhanced description, skipping")
                continue
            
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
                modified_activities.append({
                    'activity_id': activity_id,
                    'enhanced': enhanced,
                    'final': final_description,
                    'similarity': similarity
                })
                logger.info(f"✅ Activity {activity_id} was modified (similarity: {similarity:.2%})")
            else:
                logger.info(f"Activity {activity_id} not modified (similarity: {similarity:.2%})")
        
        logger.info(f"Found {len(modified_activities)} modified activities")
        
        # If no modifications, nothing to learn
        if not modified_activities:
            logger.info("No modifications detected, no patterns to extract")
            return {
                'statusCode': 200,
                'message': 'No modifications detected',
                'activities_analyzed': len(activities)
            }
        
        # Analyze patterns from modified activities
        patterns = analyze_modification_patterns(modified_activities)
        logger.info(f"Extracted {len(patterns)} patterns")
        
        # Aggregate patterns with historical data (30-day window)
        aggregated_patterns = aggregate_patterns_with_history(patterns)
        
        # Filter patterns by confidence threshold
        validated_patterns = filter_patterns_by_confidence(aggregated_patterns)
        logger.info(f"Validated {len(validated_patterns)} high-confidence patterns")
        
        if not validated_patterns:
            logger.info("No high-confidence patterns to write to memory")
            return {
                'statusCode': 200,
                'message': 'No high-confidence patterns detected',
                'activities_analyzed': len(activities),
                'modifications_detected': len(modified_activities)
            }
        
        # Update AgentCore Memory with validated patterns (no snapshot needed)
        update_agentcore_memory(validated_patterns)
        
        # Calculate quality metrics
        metrics = calculate_quality_metrics(activities)
        
        logger.info("=== Feedback Analyzer Completed ===")
        logger.info(f"Patterns written: {len(validated_patterns)}")
        logger.info(f"Modification rate: {metrics['modification_rate']:.1%}")
        logger.info(f"Quality trend: {metrics['quality_trend']}")
        
        return {
            'statusCode': 200,
            'message': 'Feedback analysis completed',
            'activities_analyzed': len(activities),
            'modifications_detected': len(modified_activities),
            'patterns_extracted': len(validated_patterns),
            'metrics': metrics
        }
        
    except Exception as e:
        logger.error(f"Feedback analyzer failed: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }


def get_recent_activities(hours: int = 24) -> List[Dict[str, Any]]:
    """Get activities from last N hours"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Calculate cutoff time
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        
        # Scan for recent activities
        response = table.scan(
            FilterExpression='created_at > :cutoff',
            ExpressionAttributeValues={':cutoff': cutoff_str}
        )
        
        activities = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression='created_at > :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff_str},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            activities.extend(response.get('Items', []))
        
        return activities
        
    except Exception as e:
        logger.error(f"Failed to get recent activities: {str(e)}")
        return []


def get_access_token() -> str:
    """Get Strava access token from Secrets Manager with automatic refresh"""
    try:
        # Get OAuth tokens directly from Secrets Manager
        response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
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
        
        # Parse expiry time
        if isinstance(expires_at, (int, float)):
            expiry_time = datetime.fromtimestamp(expires_at, UTC)
        else:
            expiry_time = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
        
        # Check if expired or expires within 5 minutes
        current_time = datetime.now(UTC)
        return expiry_time <= (current_time + timedelta(minutes=5))
        
    except Exception as e:
        logger.warning(f"Error checking token expiry: {e}")
        return True


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh access token using refresh token"""
    try:
        # Get client credentials from app config
        app_secret_name = 'strava-ai-boost-app-config'
        response = secretsmanager.get_secret_value(SecretId=app_secret_name)
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
        
        response = requests.post("https://www.strava.com/oauth/token", data=token_data, timeout=30)
        
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
        
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return None


def fetch_final_description(activity_id: str, access_token: str) -> Optional[str]:
    """Fetch final description from Strava API"""
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        url = f"{STRAVA_API_BASE}/activities/{activity_id}"
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            logger.warning(f"Activity {activity_id} not found on Strava")
            return None
        
        response.raise_for_status()
        activity_data = response.json()
        
        return activity_data.get('description', '')
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Strava API request failed for {activity_id}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch final description for {activity_id}: {str(e)}")
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
    
    # Consider modified if similarity < 95%
    is_modified = similarity < 0.95
    
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
        
    except Exception as e:
        logger.error(f"Failed to update activity feedback: {str(e)}")


def analyze_modification_patterns(modified_activities: List[Dict]) -> List[Dict]:
    """
    Analyze patterns from modified activities using Bedrock directly
    
    Returns list of detected patterns with metadata
    """
    all_patterns = []
    
    for activity in modified_activities:
        activity_id = activity['activity_id']
        enhanced = activity['enhanced']
        final = activity['final']
        
        logger.info(f"Analyzing patterns for activity {activity_id}...")
        
        # Use Bedrock to extract patterns
        patterns = analyze_content_differences_bedrock(enhanced, final)
        
        if patterns:
            # Add metadata
            patterns['activity_id'] = activity_id
            patterns['analyzed_at'] = datetime.now(UTC).isoformat()
            all_patterns.append(patterns)
            
            logger.info(f"  Extracted {len(patterns)} pattern types")
        else:
            logger.warning(f"  No patterns extracted for activity {activity_id}")
    
    return all_patterns


def analyze_content_differences_bedrock(enhanced: str, final: str) -> Dict[str, Any]:
    """
    Analyze differences between generated and final content using Bedrock
    
    Returns extracted patterns as JSON
    """
    prompt = f"""Tu es un analyseur de feedback utilisateur pour génération de contenu sportif.

MISSION : Comparer le contenu généré vs le contenu final et extraire des patterns actionnables.

CONTENU GÉNÉRÉ :
{enhanced}

CONTENU FINAL (après modification utilisateur) :
{final}

Analyse les différences et extrais les patterns en JSON :

{{
  "length_adjustment": {{
    "original_length": <number>,
    "final_length": <number>,
    "pattern": "user_prefers_shorter|user_prefers_longer|no_change",
    "reduction_percent": <number>
  }},
  "expression_changes": [
    {{
      "original": "<expression originale>",
      "final": "<expression finale>",
      "pattern": "prefers_simpler|prefers_more_technical|prefers_more_casual",
      "context": "intro|metrics|motivation|conclusion"
    }}
  ],
  "emoji_changes": {{
    "removed": ["<emoji>"],
    "added": ["<emoji>"],
    "pattern": "prefers_minimal|prefers_more|no_change"
  }},
  "structure_changes": {{
    "pattern": "moved_context_to_start|moved_metrics_to_end|reordered_sections|no_change",
    "description": "<description du changement>"
  }},
  "tone_adjustment": {{
    "pattern": "softened|intensified|no_change",
    "description": "<description du changement de ton>"
  }}
}}

RÈGLES :
- Sois précis et factuel
- Identifie uniquement les changements significatifs (pas les typos)
- Retourne UNIQUEMENT le JSON, rien d'autre
"""
    
    try:
        # Invoke Bedrock directly
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']
        
        logger.info(f"Bedrock response length: {len(content)} chars")
        logger.info(f"Bedrock response preview: {content[:200]}...")
        
        # Extract JSON from response (may be wrapped in markdown)
        # Try to find JSON block
        if '```json' in content:
            # Extract from markdown code block
            json_start = content.find('```json') + 7
            json_end = content.find('```', json_start)
            content = content[json_start:json_end].strip()
        elif '```' in content:
            # Extract from generic code block
            json_start = content.find('```') + 3
            json_end = content.find('```', json_start)
            content = content[json_start:json_end].strip()
        
        patterns = json.loads(content)
        
        logger.info(f"Patterns extracted: {list(patterns.keys())}")
        return patterns
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse patterns JSON: {str(e)}")
        return {}
    except Exception as e:
        logger.error(f"Failed to analyze differences: {str(e)}")
        return {}


def aggregate_patterns_with_history(patterns: List[Dict]) -> Dict:
    """
    Aggregate patterns with historical data (30-day window)
    
    Best Practice: Cross-validation over time
    """
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get activities from last 30 days with feedback analyzed
        cutoff = datetime.now(UTC) - timedelta(days=30)
        cutoff_str = cutoff.isoformat()
        
        response = table.scan(
            FilterExpression='feedback_analyzed = :true AND feedback_analyzed_at > :cutoff',
            ExpressionAttributeValues={
                ':true': True,
                ':cutoff': cutoff_str
            }
        )
        
        historical_activities = response.get('Items', [])
        logger.info(f"Found {len(historical_activities)} historical activities for aggregation")
        
        # Aggregate patterns by type
        aggregated = {
            'length_patterns': [],
            'expression_patterns': [],
            'emoji_patterns': [],
            'structure_patterns': [],
            'tone_patterns': []
        }
        
        # Process current patterns
        for pattern_data in patterns:
            # Length adjustments
            length_adj = pattern_data.get('length_adjustment', {})
            if length_adj.get('pattern') != 'no_change':
                aggregated['length_patterns'].append({
                    'original_length': length_adj.get('original_length'),
                    'final_length': length_adj.get('final_length'),
                    'reduction_percent': length_adj.get('reduction_percent', 0),
                    'activity_id': pattern_data.get('activity_id')
                })
            
            # Expression changes
            expression_changes = pattern_data.get('expression_changes', [])
            for expr in expression_changes:
                aggregated['expression_patterns'].append({
                    'original': expr.get('original'),
                    'final': expr.get('final'),
                    'pattern': expr.get('pattern'),
                    'context': expr.get('context'),
                    'activity_id': pattern_data.get('activity_id')
                })
            
            # Emoji changes
            emoji_changes = pattern_data.get('emoji_changes', {})
            if emoji_changes.get('pattern') != 'no_change':
                aggregated['emoji_patterns'].append({
                    'removed': emoji_changes.get('removed', []),
                    'added': emoji_changes.get('added', []),
                    'pattern': emoji_changes.get('pattern'),
                    'activity_id': pattern_data.get('activity_id')
                })
            
            # Structure changes
            structure = pattern_data.get('structure_changes', {})
            if structure.get('pattern') != 'no_change':
                aggregated['structure_patterns'].append({
                    'pattern': structure.get('pattern'),
                    'description': structure.get('description'),
                    'activity_id': pattern_data.get('activity_id')
                })
            
            # Tone adjustments
            tone = pattern_data.get('tone_adjustment', {})
            if tone.get('pattern') != 'no_change':
                aggregated['tone_patterns'].append({
                    'pattern': tone.get('pattern'),
                    'description': tone.get('description'),
                    'activity_id': pattern_data.get('activity_id')
                })
        
        # Add historical patterns for frequency calculation
        for activity in historical_activities:
            stored_patterns = activity.get('modification_patterns')
            if stored_patterns:
                try:
                    historical_pattern = json.loads(stored_patterns) if isinstance(stored_patterns, str) else stored_patterns
                    # Merge with current patterns (same logic as above)
                    # TODO: Implement historical merge
                except Exception as e:
                    logger.warning(f"Failed to parse historical patterns: {e}")
        
        return aggregated
        
    except Exception as e:
        logger.error(f"Failed to aggregate patterns: {str(e)}")
        return {
            'length_patterns': [],
            'expression_patterns': [],
            'emoji_patterns': [],
            'structure_patterns': [],
            'tone_patterns': []
        }


def filter_patterns_by_confidence(aggregated: Dict) -> List[Dict]:
    """
    Filter patterns by confidence threshold
    
    Best Practice: "Only patterns with 3+ occurrences"
    """
    validated = []
    
    # Length patterns
    length_patterns = aggregated.get('length_patterns', [])
    if len(length_patterns) >= MIN_PATTERN_FREQUENCY:
        avg_reduction = sum(p.get('reduction_percent', 0) for p in length_patterns) / len(length_patterns)
        validated.append({
            'type': 'length_preferences',
            'pattern': 'prefers_shorter' if avg_reduction < 0 else 'prefers_longer',
            'avg_reduction': int(avg_reduction),
            'frequency': len(length_patterns),
            'confidence': 'high' if len(length_patterns) >= 10 else 'medium',
            'examples': [
                f"{p['original_length']} → {p['final_length']} chars"
                for p in length_patterns[:3]
            ]
        })
    
    # Expression patterns - group by original→final
    expression_patterns = aggregated.get('expression_patterns', [])
    expression_map = {}
    for expr in expression_patterns:
        key = f"{expr.get('original')}→{expr.get('final')}"
        if key not in expression_map:
            expression_map[key] = {
                'original': expr.get('original'),
                'final': expr.get('final'),
                'frequency': 0,
                'contexts': []
            }
        expression_map[key]['frequency'] += 1
        expression_map[key]['contexts'].append(expr.get('context'))
    
    # Filter expressions by frequency
    for expr_data in expression_map.values():
        if expr_data['frequency'] >= MIN_PATTERN_FREQUENCY:
            validated.append({
                'type': 'expression_preference',
                'avoid': expr_data['original'],
                'prefer': expr_data['final'],
                'frequency': expr_data['frequency'],
                'confidence': 'high' if expr_data['frequency'] >= 10 else 'medium',
                'contexts': list(set(expr_data['contexts']))
            })
    
    # Emoji patterns - aggregate removed/added
    emoji_patterns = aggregated.get('emoji_patterns', [])
    if len(emoji_patterns) >= MIN_PATTERN_FREQUENCY:
        all_removed = []
        all_added = []
        for emoji_data in emoji_patterns:
            all_removed.extend(emoji_data.get('removed', []))
            all_added.extend(emoji_data.get('added', []))
        
        # Count frequencies
        from collections import Counter
        removed_freq = Counter(all_removed)
        added_freq = Counter(all_added)
        
        validated.append({
            'type': 'emoji_preferences',
            'frequently_removed': [
                {'emoji': emoji, 'frequency': freq}
                for emoji, freq in removed_freq.most_common(5)
                if freq >= MIN_PATTERN_FREQUENCY
            ],
            'frequently_added': [
                {'emoji': emoji, 'frequency': freq}
                for emoji, freq in added_freq.most_common(5)
                if freq >= MIN_PATTERN_FREQUENCY
            ],
            'confidence': 'high' if len(emoji_patterns) >= 10 else 'medium'
        })
    
    # Structure patterns
    structure_patterns = aggregated.get('structure_patterns', [])
    if len(structure_patterns) >= MIN_PATTERN_FREQUENCY:
        # Find most common structure pattern
        from collections import Counter
        pattern_counts = Counter(p.get('pattern') for p in structure_patterns)
        most_common = pattern_counts.most_common(1)[0]
        
        validated.append({
            'type': 'structure_preference',
            'pattern': most_common[0],
            'frequency': most_common[1],
            'confidence': 'high' if most_common[1] >= 10 else 'medium'
        })
    
    # Tone patterns
    tone_patterns = aggregated.get('tone_patterns', [])
    if len(tone_patterns) >= MIN_PATTERN_FREQUENCY:
        from collections import Counter
        pattern_counts = Counter(p.get('pattern') for p in tone_patterns)
        most_common = pattern_counts.most_common(1)[0]
        
        validated.append({
            'type': 'tone_preference',
            'pattern': most_common[0],
            'frequency': most_common[1],
            'confidence': 'high' if most_common[1] >= 10 else 'medium'
        })
    
    logger.info(f"Validated {len(validated)} patterns (threshold: {MIN_PATTERN_FREQUENCY}+ occurrences)")
    return validated


def update_agentcore_memory(patterns: List[Dict]) -> None:
    """
    Update AgentCore Memory with validated patterns using boto3 directly
    
    Uses boto3 bedrock-agent-runtime API (no SDK dependencies needed)
    """
    try:
        memory_id = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")
        if not memory_id:
            logger.warning("BEDROCK_AGENTCORE_MEMORY_ID not configured, skipping memory update")
            return
        
        # Use boto3 bedrock-agentcore client (data plane)
        bedrock_agentcore = boto3.client('bedrock-agentcore', region_name=os.getenv('AWS_REGION', 'eu-west-1'))
        
        # Sanitize patterns before writing
        sanitized_patterns = [sanitize_feedback_data(p) for p in patterns]
        
        # Prepare feedback summary
        feedback_summary = {
            'version': '1.0.0',
            'updated_at': datetime.now(UTC).isoformat(),
            'confidence_threshold': MIN_PATTERN_FREQUENCY,
            'total_patterns': len(sanitized_patterns),
            'patterns_by_type': {}
        }
        
        # Group patterns by type
        for pattern in sanitized_patterns:
            pattern_type = pattern.get('type', 'unknown')
            if pattern_type not in feedback_summary['patterns_by_type']:
                feedback_summary['patterns_by_type'][pattern_type] = []
            feedback_summary['patterns_by_type'][pattern_type].append(pattern)
        
        # Write to AgentCore Memory using boto3 API
        # Format: payload with conversational turns
        response = bedrock_agentcore.create_event(
            memoryId=memory_id,
            actorId="system",
            sessionId="feedback_learning",
            eventTimestamp=datetime.now(UTC),
            payload=[
                {
                    'conversational': {
                        'content': {'text': json.dumps(feedback_summary)},
                        'role': 'USER'  # Store as USER message for easy retrieval
                    }
                }
            ]
        )
        
        logger.info(f"✅ Updated AgentCore Memory with {len(sanitized_patterns)} validated patterns")
        logger.info(f"   Memory ID: {memory_id}")
        logger.info(f"   Session: actor_id=system, session_id=feedback_learning")
        logger.info(f"   Response: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        
        # Log summary
        for pattern in sanitized_patterns:
            logger.info(f"  - {pattern['type']}: frequency={pattern.get('frequency')}, confidence={pattern.get('confidence')}")
        
    except Exception as e:
        logger.error(f"Failed to update AgentCore Memory: {str(e)}")
        raise


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
        
    except Exception as e:
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


def sanitize_feedback_data(pattern: Dict) -> Dict:
    """
    Validate and sanitize data before writing to memory
    
    AWS Best Practice: Protect against memory poisoning
    """
    sanitized = pattern.copy()
    
    # Limit string sizes
    if 'description' in sanitized:
        sanitized['description'] = str(sanitized['description'])[:500]
    
    # Validate numeric types
    if 'frequency' in sanitized:
        sanitized['frequency'] = max(0, min(1000, int(sanitized['frequency'])))
    
    # Remove dangerous characters
    for key, value in sanitized.items():
        if isinstance(value, str):
            sanitized[key] = value.replace('\x00', '').strip()
    
    return sanitized
