"""
Content Generator Lambda Function

Generates enhanced content using AgentCore agents.
Delegates stream analysis and module processing to dedicated modules.
"""

import json
import os
import re
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from processing.streams_analysis import (
    classify_workout_from_streams,
    detect_workout_phases,
    extract_enduraw_report,
)
from processing.modules_processing import get_active_modules, apply_module_processing

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)

# Environment variables
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
USER_CONFIG_TABLE = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for content generation"""
    try:
        logger.info(f"Content generator received event: {json.dumps(event, default=str)}")

        activity_id = event.get('activity_id')
        user_id = event.get('user_id')

        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")

        # Retrieve activity data from DynamoDB
        activity_data_full = retrieve_activity_data_from_dynamodb(activity_id)
        if not activity_data_full:
            raise ValueError(f"Activity data not found in DynamoDB for activity {activity_id}")

        activity_data = activity_data_full.get('activity_data', {})
        streams_compressed = activity_data_full.get('streams_compressed')
        athlete_stats = activity_data_full.get('athlete_stats')
        athlete_profile = activity_data_full.get('athlete_profile')
        gear_details = activity_data_full.get('gear_details')
        intervals_icu_data = activity_data_full.get('intervals_icu_data')

        # Get user configuration and modules
        user_config = get_user_configuration(user_id)
        active_modules = get_active_modules(user_config)
        user_profile = build_user_profile_from_config(user_config)

        # Extract Enduraw Report if available
        enduraw_data = extract_enduraw_report(activity_data)

        # Apply module-specific processing
        enhanced_modules = apply_module_processing(activity_data, None, active_modules)

        # Generate enhanced content via AgentCore
        enhanced_content = generate_enhanced_content(
            activity_data, streams_compressed, user_id, enhanced_modules,
            user_profile, athlete_stats, athlete_profile, gear_details,
            enduraw_data, intervals_icu_data
        )

        # Store generated content
        store_generated_content(activity_id, enhanced_content)

        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'user_id': user_id,
            'enhanced_content': enhanced_content,
            'modules_applied': [m['name'] for m in enhanced_modules]
        }

    except Exception as e:
        logger.error(f"Content generation error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'activity_id': event.get('activity_id'),
            'user_id': event.get('user_id')
        }


# --- Data Retrieval ---

def retrieve_activity_data_from_dynamodb(activity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve complete activity data from DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={'activity_id': activity_id})

        if 'Item' not in response:
            logger.error(f"Activity {activity_id} not found in DynamoDB")
            return None

        item = response['Item']

        activity_data = json.loads(item.get('activity_data_json', '{}'))
        streams_compressed = json.loads(item.get('streams_compressed_json', 'null')) if item.get('streams_compressed_json') else None
        athlete_stats = json.loads(item.get('athlete_stats_json', 'null')) if item.get('athlete_stats_json') else None
        athlete_profile = json.loads(item.get('athlete_profile_json', 'null')) if item.get('athlete_profile_json') else None
        gear_details = json.loads(item.get('gear_details_json', 'null')) if item.get('gear_details_json') else None
        intervals_icu_data = json.loads(item.get('intervals_icu_json', 'null')) if item.get('intervals_icu_json') else None

        def convert_numeric_strings(obj: Any) -> Any:
            """Recursively convert numeric strings to float/int (DynamoDB Decimal issue)"""
            if isinstance(obj, dict):
                return {k: convert_numeric_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numeric_strings(item) for item in obj]
            elif isinstance(obj, str):
                try:
                    if '.' not in obj and 'e' not in obj.lower():
                        return int(obj)
                    else:
                        return float(obj)
                except (ValueError, AttributeError):
                    return obj
            return obj

        activity_data = convert_numeric_strings(activity_data)
        streams_compressed = convert_numeric_strings(streams_compressed) if streams_compressed else None
        athlete_stats = convert_numeric_strings(athlete_stats) if athlete_stats else None
        athlete_profile = convert_numeric_strings(athlete_profile) if athlete_profile else None
        gear_details = convert_numeric_strings(gear_details) if gear_details else None
        intervals_icu_data = convert_numeric_strings(intervals_icu_data) if intervals_icu_data else None

        return {
            'activity_data': activity_data,
            'streams_compressed': streams_compressed,
            'athlete_stats': athlete_stats,
            'athlete_profile': athlete_profile,
            'gear_details': gear_details,
            'intervals_icu_data': intervals_icu_data
        }

    except Exception as e:
        logger.error(f"Failed to retrieve activity data from DynamoDB: {str(e)}")
        return None


def get_user_configuration(user_id: str) -> Dict[str, Any]:
    """Get user configuration from DynamoDB"""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': user_id})
        user_config = response.get('Item', {
            'user_id': user_id,
            'modules_config': {},
            'enhancement_enabled': True
        })

        if 'modules_config' not in user_config:
            user_config['modules_config'] = {}

        return user_config

    except Exception as e:
        logger.error(f"Failed to get user configuration: {str(e)}")
        return {
            'user_id': user_id,
            'modules_config': {},
            'enhancement_enabled': True
        }


def build_user_profile_from_config(user_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build user_profile from user configuration for agent personalization"""
    try:
        preferences = user_config.get('user_preferences', {})
        if not preferences:
            return None

        user_profile = {
            'age_range': preferences.get('age_range', '26-35'),
            'interests': preferences.get('interests', []),
            'sport_approach': preferences.get('sport_approach', 'health & wellness'),
            'content_preferences': {
                'length': preferences.get('content_length', 'medium'),
                'tone': preferences.get('content_tone', 'motivational & energetic'),
                'emoji_usage': preferences.get('emoji_usage', 'moderate'),
                'technical_detail': preferences.get('technical_detail', 'intermediate'),
                'language': preferences.get('content_language', 'french')
            }
        }

        pace_zones = preferences.get('pace_zones')
        if pace_zones:
            user_profile['pace_zones'] = pace_zones

        return user_profile

    except Exception as e:
        logger.error(f"Failed to build user_profile: {str(e)}")
        return None


# --- AgentCore Content Generation ---

def generate_enhanced_content(
    activity_data: Dict[str, Any],
    streams_compressed: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None,
    athlete_stats: Optional[Dict[str, Any]] = None,
    athlete_profile: Optional[Dict[str, Any]] = None,
    gear_details: Optional[Dict[str, Any]] = None,
    enduraw_data: Optional[Dict[str, Any]] = None,
    intervals_icu_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate enhanced content using AgentCore agent. Raises on failure."""

    # Initialize AgentCore client
    try:
        agentcore_client = boto3.client('bedrock-agentcore', region_name=REGION)
    except Exception:
        agentcore_client = boto3.client('bedrock-agent-runtime', region_name=REGION)

    session_id = f"content-gen-{uuid.uuid4().hex}"

    # Extract Campus Coach sessions
    campus_coach_sessions = None
    for module in modules:
        if module.get('name') == 'campus_coach' and module.get('sessions_available'):
            campus_coach_sessions = module.get('campus_coach_sessions', [])
            break

    # Pre-compute workout analysis
    workout_phases = detect_workout_phases(streams_compressed) if streams_compressed else []
    route_landmarks = streams_compressed.get('route_landmarks', []) if streams_compressed else []
    blocks = streams_compressed.get('blocks', []) if streams_compressed else []
    user_pace_zones = user_profile.get('pace_zones') if user_profile else None
    workout_classification = classify_workout_from_streams(blocks, pace_zones=user_pace_zones) if blocks else None

    # Clean activity_data to remove previous AI content
    clean_activity_data = {k: v for k, v in activity_data.items()
                           if k not in ('enhanced_description', 'enhanced_title', 'description',
                                        'processing_status', 'processing_error')}
    if '@Generated by Strava AI Boost' in str(clean_activity_data.get('name', '')):
        clean_activity_data['name'] = 'Activity'

    # Build classification instruction
    classification_instruction = None
    if workout_classification and workout_classification.get('type') not in ('intervals', 'unknown', None):
        wc_label = workout_classification.get('label', workout_classification['type'])
        classification_instruction = (
            f"CRITICAL INSTRUCTION — Workout type detected from GPS/HR stream analysis: {wc_label}. "
            f"You MUST generate a title and description that matches this workout type. "
            f"Do NOT use 'fractionne', 'intervalles', or 'interval' unless the classification type is 'intervals'. "
            f"Do NOT copy or reproduce the existing activity title — generate a completely new one based on the classification."
        )

    # Prepare agent input
    agent_input = {
        'action': 'generate_content',
        'classification_instruction': classification_instruction,
        'workout_classification': workout_classification,
        'activity_data': clean_activity_data,
        'workout_phases': workout_phases,
        'compressed_blocks': blocks,
        'route_landmarks': route_landmarks,
        'athlete_stats': athlete_stats,
        'athlete_profile': athlete_profile,
        'gear_details': gear_details,
        'user_id': user_id,
        'user_profile': user_profile,
        'active_modules': modules,
        'campus_coach_session': campus_coach_sessions,
        'enduraw_data': enduraw_data,
        'intervals_icu_data': intervals_icu_data,
        'workout_type': activity_data.get('workout_type'),
        'use_memory': True,
        'personalization': True
    }

    # Get agent ARN
    agent_arn = os.environ.get('CONTENT_GENERATION_AGENT_ARN', '')
    if not agent_arn:
        raise ValueError("CONTENT_GENERATION_AGENT_ARN not configured")

    # Invoke agent
    payload = json.dumps(agent_input).encode('utf-8')
    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload
    )

    # Process response
    completion = _process_agent_response(response)

    # Parse agent response
    return _parse_agent_response(completion, workout_classification, modules)


def _process_agent_response(response: Dict[str, Any]) -> str:
    """Process streaming or JSON response from AgentCore. Raises on failure."""
    completion = ""
    if "text/event-stream" in response.get("contentType", ""):
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                try:
                    line = line.decode("utf-8", errors='replace')
                except Exception:
                    continue
                if line.startswith("data: "):
                    completion += line[6:]
    elif response.get("contentType") == "application/json":
        content = []
        for chunk in response.get("response", []):
            try:
                content.append(chunk.decode('utf-8', errors='replace'))
            except Exception:
                continue
        completion = ''.join(content)
    else:
        completion = str(response.get("response", ""))

    if not completion:
        raise ValueError("Empty response from AgentCore agent")

    logger.info(f"AgentCore response length: {len(completion)}")
    return completion


def _parse_agent_response(
    completion: str,
    workout_classification: Optional[Dict[str, Any]],
    modules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parse and validate AgentCore agent response. Raises on parse failure."""
    outer_response = json.loads(completion)

    response_text = outer_response.get('response', completion) if isinstance(outer_response, dict) else completion

    # Remove markdown code blocks
    response_text = re.sub(r'```json\s*', '', response_text)
    response_text = re.sub(r'```\s*$', '', response_text)
    response_text = response_text.strip()

    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not json_match:
        raise ValueError(f"No JSON found in AgentCore response: {response_text[:200]}")

    agent_response = json.loads(json_match.group())

    # Extract title/description
    title, description, confidence = None, None, 0.8

    if 'generated_content' in agent_response:
        gc = agent_response['generated_content']
        title = gc.get('title', 'Enhanced Activity')
        description = gc.get('description', 'AI-enhanced description')
        if 'content_metadata' in agent_response:
            confidence = agent_response['content_metadata'].get('confidence', 0.8)
    elif 'title' in agent_response and 'description' in agent_response:
        title = agent_response.get('title', 'Enhanced Activity')
        description = agent_response.get('description', 'AI-enhanced description')
        confidence = agent_response.get('confidence', 0.8)

    if not title or not description:
        raise ValueError(f"Missing title/description in agent response: {list(agent_response.keys())}")

    # Validate title matches workout classification
    if workout_classification and workout_classification.get('type') not in ('intervals', 'unknown', None):
        interval_keywords = re.compile(r'fractionn|interval|split|repetition', re.IGNORECASE)
        if interval_keywords.search(title):
            wc_label = workout_classification.get('label', 'Activite')
            emojis = ''.join(c for c in title if ord(c) > 0x1F000)
            title = f"{emojis or chr(0x1F3C3)} {wc_label}"

    # Add signature
    if not description.endswith('@Generated by Strava AI Boost'):
        description += '\n\n@Generated by Strava AI Boost'

    # Extract metadata
    style_elements = ['ai_generated']
    patterns_detected = []
    memory_used = False
    expressions_avoided = []

    if 'content_metadata' in agent_response:
        metadata = agent_response['content_metadata']
        style_elements = [metadata.get('tone_used', 'ai_generated')]
        patterns_detected = metadata.get('fun_elements_included', [])

    if 'memory_operations' in agent_response:
        memory_ops = agent_response['memory_operations']
        memory_used = memory_ops.get('retrieved', False) or memory_ops.get('stored', False)
        expressions_avoided = memory_ops.get('expressions_avoided', [])

    return {
        'title': title[:50],
        'description': description,
        'style_elements': style_elements,
        'confidence': confidence,
        'modules_used': [m['name'] for m in modules],
        'patterns_detected': patterns_detected,
        'analysis_type': 'agentcore_memory',
        'memory_used': memory_used,
        'expressions_avoided': expressions_avoided
    }


# --- Storage ---

def store_generated_content(activity_id: str, content: Dict[str, Any]) -> None:
    """Store generated content in DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)

        def convert_floats_to_decimal(obj: Any) -> Any:
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats_to_decimal(item) for item in obj]
            return obj

        metadata = {
            'style_elements': content.get('style_elements', []),
            'confidence': convert_floats_to_decimal(content.get('confidence', 0.0)),
            'modules_used': content.get('modules_used', []),
            'patterns_detected': content.get('patterns_detected', []),
            'analysis_type': content.get('analysis_type', 'unknown'),
            'generated_at': datetime.now(timezone.utc).isoformat()
        }

        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET enhanced_title = :title, enhanced_description = :desc, generation_metadata = :meta",
            ExpressionAttributeValues={
                ':title': content['title'],
                ':desc': content['description'],
                ':meta': metadata
            }
        )

        logger.info(f"Stored generated content for activity {activity_id}")

    except Exception as e:
        logger.error(f"Failed to store generated content: {str(e)}")
