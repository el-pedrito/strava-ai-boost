"""
Content Generator Lambda Function

Generates enhanced content using AgentCore agents.
Delegates module processing and content generation to dedicated modules.
"""

import json
import os
import re
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from processing.workout_analysis import (
    classify_workout_from_laps,
    extract_enduraw_report,
)
from processing.modules_processing import get_active_modules, apply_module_processing
from shared.logger import get_logger

logger = get_logger("content-generator")

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
        athlete_stats = activity_data_full.get('athlete_stats')
        athlete_profile = activity_data_full.get('athlete_profile')
        intervals_icu_data = activity_data_full.get('intervals_icu_data')
        laps_data = activity_data_full.get('laps_data')

        # Get user configuration and modules
        user_config = get_user_configuration(user_id)
        active_modules = get_active_modules(user_config)
        user_profile = build_user_profile_from_config(user_config)

        # Extract Enduraw Report if available
        enduraw_data = extract_enduraw_report(activity_data)

        # Inject laps into activity_data for module access (Campus Coach matching)
        if laps_data:
            activity_data['laps_data'] = laps_data

        # Apply module-specific processing
        enhanced_modules = apply_module_processing(activity_data, None, active_modules, laps_data)

        # Generate enhanced content via AgentCore
        enhanced_content = generate_enhanced_content(
            activity_data, user_id, enhanced_modules,
            user_profile, athlete_stats, athlete_profile,
            enduraw_data, intervals_icu_data, laps_data
        )

        # Store generated content
        store_generated_content(activity_id, enhanced_content)

        # P0.2: Mark Campus Coach session as done using pre-matched session from modules_processing
        matched_session = None
        for m in enhanced_modules:
            if m.get('name') == 'campus_coach' and m.get('matched_session'):
                matched_session = m['matched_session']
                break
        if matched_session:
            mark_campus_session_done(matched_session, activity_id)

        # Track strength history for WeightTraining activities
        sport_type = activity_data.get('sport_type', activity_data.get('type', ''))
        if sport_type == 'WeightTraining':
            _track_strength_history(user_id, activity_id, activity_data)

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
        athlete_stats = json.loads(item.get('athlete_stats_json', 'null')) if item.get('athlete_stats_json') else None
        athlete_profile = json.loads(item.get('athlete_profile_json', 'null')) if item.get('athlete_profile_json') else None
        intervals_icu_data = json.loads(item.get('intervals_icu_json', 'null')) if item.get('intervals_icu_json') else None
        laps_data = json.loads(item.get('laps_json', 'null')) if item.get('laps_json') else None

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
        athlete_stats = convert_numeric_strings(athlete_stats) if athlete_stats else None
        athlete_profile = convert_numeric_strings(athlete_profile) if athlete_profile else None
        intervals_icu_data = convert_numeric_strings(intervals_icu_data) if intervals_icu_data else None
        laps_data = convert_numeric_strings(laps_data) if laps_data else None

        return {
            'activity_data': activity_data,
            'athlete_stats': athlete_stats,
            'athlete_profile': athlete_profile,
            'intervals_icu_data': intervals_icu_data,
            'laps_data': laps_data
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

        athlete_profile_text = preferences.get('athlete_profile', '')
        if athlete_profile_text:
            user_profile['athlete_profile'] = athlete_profile_text

        personal_records = preferences.get('personal_records')
        if personal_records:
            user_profile['personal_records'] = personal_records

        max_hr = preferences.get('max_hr')
        if max_hr:
            user_profile['max_hr'] = max_hr

        strength_program = preferences.get('strength_program')
        if strength_program:
            user_profile['strength_program'] = strength_program

        return user_profile

    except Exception as e:
        logger.error(f"Failed to build user_profile: {str(e)}")
        return None


# --- AgentCore Content Generation ---

def generate_enhanced_content(
    activity_data: Dict[str, Any],
    user_id: str,
    modules: List[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None,
    athlete_stats: Optional[Dict[str, Any]] = None,
    athlete_profile: Optional[Dict[str, Any]] = None,
    enduraw_data: Optional[Dict[str, Any]] = None,
    intervals_icu_data: Optional[Dict[str, Any]] = None,
    laps_data: Optional[list] = None
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

    # Classify workout from laps
    user_pace_zones = user_profile.get('pace_zones') if user_profile else None
    workout_classification = classify_workout_from_laps(laps_data or [], pace_zones=user_pace_zones) if laps_data else None

    # Clean activity_data to remove previous AI content but KEEP original user description
    clean_activity_data = {k: v for k, v in activity_data.items()
                           if k not in ('enhanced_description', 'enhanced_title',
                                        'processing_status', 'processing_error', 'start_date')}
    # Ensure start_date_local is present (LLM must use local time, not UTC)
    if 'start_date_local' not in clean_activity_data and 'start_date' in activity_data:
        clean_activity_data['start_date_local'] = activity_data['start_date']
    # Remove AI-generated signature from description but keep user's original text
    desc = clean_activity_data.get('description', '')
    if desc and '@Generated by Strava AI Boost' in str(desc):
        desc = str(desc).split('@Generated by Strava AI Boost')[0].strip()
        clean_activity_data['description'] = desc if desc else ''
    if '@Generated by Strava AI Boost' in str(clean_activity_data.get('name', '')):
        clean_activity_data['name'] = 'Activity'

    # Build classification instruction
    classification_instruction = None
    if workout_classification and workout_classification.get('type') not in ('intervals', 'unknown', None):
        wc_label = workout_classification.get('label', workout_classification['type'])
        classification_instruction = (
            f"CRITICAL INSTRUCTION — Workout type detected from laps analysis: {wc_label}. "
            f"You MUST generate a title and description that matches this workout type. "
            f"Do NOT use 'fractionne', 'intervalles', or 'interval' unless the classification type is 'intervals'. "
            f"Do NOT copy or reproduce the existing activity title — generate a completely new one based on the classification."
        )

    # Extract activity date for correct week identification
    activity_start = activity_data.get('start_date_local') or activity_data.get('start_date', '')
    try:
        from datetime import datetime, timezone
        activity_dt = datetime.fromisoformat(activity_start.replace('Z', '+00:00'))
        activity_iso_week = activity_dt.isocalendar()[1]
        activity_date_str = activity_dt.strftime('%Y-%m-%d')
        activity_time_local = activity_dt.strftime('%Hh%M')
        activity_weekday = ['lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche'][activity_dt.weekday()]
    except (ValueError, AttributeError):
        from datetime import datetime, timezone
        activity_iso_week = datetime.now(timezone.utc).isocalendar()[1]
        activity_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        activity_time_local = ''
        activity_weekday = ''

    # Prepare agent input
    agent_input = {
        'action': 'generate_content',
        'activity_date': activity_date_str,
        'activity_iso_week': activity_iso_week,
        'activity_time_local': activity_time_local,
        'activity_weekday': activity_weekday,
        'classification_instruction': classification_instruction,
        'workout_classification': workout_classification,
        'activity_data': clean_activity_data,
        'laps_data': laps_data,
        'athlete_stats': athlete_stats,
        'athlete_profile': athlete_profile,
        'user_id': user_id,
        'user_profile': user_profile,
        'active_modules': modules,
        'campus_coach_session': campus_coach_sessions,
        'campus_coach_context': _get_campus_context(),
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
    payload = json.dumps(agent_input, default=str).encode('utf-8')
    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload
    )

    # Process response
    completion = _process_agent_response(response)

    # Parse agent response
    result = _parse_agent_response(completion, workout_classification, modules)

    # Remove incomplete fun facts (LLM sometimes cuts mid-sentence)
    result['description'] = _fix_truncated_fun_fact(result.get('description', ''))

    # Enforce user preferences on generated content
    result['title'], result['description'] = enforce_preferences(
        result['title'], result['description'], user_profile
    )

    # Strip em/en dashes (anti-AI writing rule)
    result['title'] = result['title'].replace('—', ',').replace('–', ',')
    result['description'] = result['description'].replace('—', ',').replace('–', ',')

    return result


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


def _get_campus_context() -> Optional[Dict[str, Any]]:
    """Fetch Campus Coach athlete context (goal, cycle, assiduity) for content enrichment."""
    try:
        table = dynamodb.Table(os.environ.get("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"))
        resp = table.scan(
            FilterExpression="session_date = :sd",
            ExpressionAttributeValues={":sd": "athlete-context"},
        )
        items = resp.get("Items", [])
        if not items:
            return None
        ctx = items[0]
        # Also get current week's cycle theme
        week_resp = table.scan(
            FilterExpression="is_current_week = :cw",
            ExpressionAttributeValues={":cw": True},
            Limit=1,
        )
        week_items = week_resp.get("Items", [])
        cycle_theme = week_items[0].get("cycle_theme", "") if week_items else ""
        cycle_desc = week_items[0].get("cycle_description", "") if week_items else ""

        return {
            "goal": ctx.get("goal", {}),
            "assiduity": ctx.get("assiduity", ""),
            "cycle_theme": cycle_theme,
            "cycle_description": cycle_desc,
        }
    except Exception:
        return None


def _fix_truncated_fun_fact(description: str) -> str:
    """Remove fun facts that were cut mid-sentence by the LLM."""
    idx = description.lower().rfind('fun fact')
    if idx < 0:
        return description

    # Find where the fun fact ends (next section marker or end of text)
    after = description[idx:]
    end_markers = ['\n\n📊', '\n\n@Generated']
    end_idx = len(after)
    for marker in end_markers:
        m = after.find(marker)
        if 0 < m < end_idx:
            end_idx = m

    fun_text = after[:end_idx].rstrip()
    if not fun_text:
        return description

    # Check if fun fact ends properly (punctuation or high unicode like emoji)
    last_char = fun_text[-1]
    if last_char in '.!?' or ord(last_char) > 127:
        return description  # Fun fact is complete

    # Truncated — remove it
    logger.warning(f"Removing truncated fun fact: '{fun_text[-50:]}'")
    return description[:idx].rstrip() + description[idx + end_idx:]


def enforce_preferences(title: str, description: str, user_profile: Optional[Dict[str, Any]]) -> tuple:
    """Post-process generated content to enforce user preferences."""
    if not user_profile:
        return title, description

    prefs = user_profile.get('content_preferences', {})

    # Enforce emoji limits
    emoji_usage = prefs.get('emoji_usage', 'moderate')
    emoji_limits = {'none': 0, 'minimal': 2, 'moderate': 5, 'enthusiastic': 10}
    max_emoji = emoji_limits.get(emoji_usage, 5)

    def _limit_emojis(text: str, max_count: int) -> str:
        """Keep only the first max_count emojis, strip the rest."""
        import re as _re
        emoji_pattern = _re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # supplemental
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # extended-A
            "]+",
            flags=_re.UNICODE,
        )
        found = 0
        result = []
        last_end = 0
        for match in emoji_pattern.finditer(text):
            result.append(text[last_end:match.start()])
            if found < max_count:
                result.append(match.group())
                found += 1
            last_end = match.end()
        result.append(text[last_end:])
        return ''.join(result)

    title = _limit_emojis(title, min(max_emoji, 2))  # Max 2 emojis in title regardless
    description = _limit_emojis(description, max_emoji)

    if max_emoji == 0:
        logger.info("enforce_preferences: stripped all emojis (emoji_usage=none)")

    # Enforce content_length as safety net
    # Note: 'adaptive' is resolved to short/medium/detailed in content_agent.py before generation,
    # but user_profile still has the original value. Use 1500 as safe upper bound for adaptive.
    length = prefs.get('length', 'medium')
    size_limits = {'short': 500, 'medium': 1200, 'detailed': 2500, 'adaptive': 2500}
    max_chars = size_limits.get(length, 800)
    signature = '\n\n@Generated by Strava AI Boost'

    if len(description) > max_chars:
        logger.warning(f"enforce_preferences: description too long ({len(description)} > {max_chars}), truncating")
        if signature in description:
            description = description.replace(signature, '')
        description = description[:max_chars - len(signature)].rstrip()
        # If truncation cut a fun fact mid-sentence, remove it entirely
        fun_idx = description.lower().rfind('fun fact')
        if fun_idx > 0:
            after_fun = description[fun_idx:]
            # Check if fun fact is complete (ends with punctuation or emoji)
            last_char = after_fun.rstrip()[-1:] if after_fun.rstrip() else ''
            if not last_char or (ord(last_char) < 128 and last_char not in '.!?'):
                description = description[:fun_idx].rstrip()
        description = description.rstrip() + signature

    return title, description


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
        'expressions_avoided': expressions_avoided,
        'matched_session_id': agent_response.get('matched_session_id')
    }


# --- Storage ---

def mark_campus_session_done(session: Dict[str, Any], activity_id: str) -> None:
    """P0.2: Mark a Campus Coach session as 'Fait' after deterministic matching."""
    try:
        coaching_table_name = os.environ.get('COACHING_SESSIONS_TABLE')
        if not coaching_table_name or not session:
            return
        # Use session_date (PK) and session_id (SK) directly from the session object
        session_date = session.get('session_date')
        session_id = session.get('session_id')
        if not session_date or not session_id:
            logger.warning(f"Cannot mark session done: missing session_date or session_id")
            return
        table = dynamodb.Table(coaching_table_name)
        table.update_item(
            Key={'session_date': session_date, 'session_id': session_id},
            UpdateExpression='SET #s = :done, completed_at = :ts, matched_activity_id = :aid',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':done': 'Fait',
                ':ts': datetime.now(timezone.utc).isoformat(),
                ':aid': activity_id
            }
        )
        logger.info(f"✅ Marked Campus Coach session '{session.get('title')}' ({session_id}) as Fait (activity {activity_id})")
    except Exception as e:
        logger.warning(f"Failed to mark session as Fait: {e}")


def _track_strength_history(user_id: str, activity_id: str, activity_data: Dict[str, Any]) -> None:
    """Parse WeightTraining description and append to strength_history for progression tracking."""
    try:
        description = activity_data.get('description', '')
        if not description or len(description) < 10:
            return

        # Check if already tracked (avoid duplicates on reprocess)
        table = dynamodb.Table(USER_CONFIG_TABLE)
        existing = table.get_item(
            Key={'user_id': user_id},
            ProjectionExpression='user_preferences.strength_history.entries'
        )
        entries = existing.get('Item', {}).get('user_preferences', {}).get('strength_history', {}).get('entries', [])
        if any(e.get('activity_id') == activity_id for e in entries):
            logger.info(f"Strength history already tracked for activity {activity_id}, skipping")
            return

        activity_date = activity_data.get('start_date_local', activity_data.get('start_date', ''))
        duration_min = activity_data.get('moving_time', 0) / 60

        # Store raw description as a history entry — the coach LLM will interpret it
        # against the strength_program to track progressions
        entry = {
            'date': activity_date[:10] if activity_date else datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'activity_id': activity_id,
            'duration_min': int(duration_min),
            'description': description[:500],
        }

        table = dynamodb.Table(USER_CONFIG_TABLE)
        table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET user_preferences.strength_history.entries = list_append(if_not_exists(user_preferences.strength_history.entries, :empty), :entry), user_preferences.strength_history.last_updated = :ts',
            ExpressionAttributeValues={
                ':entry': [entry],
                ':empty': [],
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"📝 Tracked strength history for activity {activity_id} ({activity_date[:10]})")
    except Exception as e:
        logger.warning(f"Failed to track strength history: {e}")


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
