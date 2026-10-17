"""
User Preferences API Lambda Function

Handles user preferences for content personalization:
- GET: Retrieve user preferences
- POST: Update user preferences
"""

import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, UTC
from shared.responses import (
    CORS_HEADERS_WRITE as CORS_HEADERS,
    create_success_response,
    create_error_response,
)
from shared.logger import get_logger, inject_correlation_id
from shared.pace_zones import effective_pace_zones

logger = get_logger("user_preferences_api")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']

# Allowed preference values for validation
ALLOWED_AGE_RANGES = ['18-25', '26-35', '36-45', '46-55', '56-65', '65+']
ALLOWED_SPORT_APPROACHES = ['health & wellness', 'performance & competition', 'social & fun', 'personal challenge', 'stress relief', 'weight management']
ALLOWED_CONTENT_LENGTHS = ['short', 'medium', 'detailed', 'adaptive']
ALLOWED_CONTENT_TONES = ['technical & analytical', 'motivational & energetic', 'casual & friendly', 'humorous & fun', 'authentic & personal']
ALLOWED_EMOJI_USAGES = ['none', 'minimal', 'moderate', 'enthusiastic']
ALLOWED_TECHNICAL_DETAILS = ['basic', 'intermediate', 'advanced']
ALLOWED_CONTENT_LANGUAGES = ['french', 'english', 'spanish', 'german', 'italian']

# Body metrics bounds (structured fields, same flat convention as max_hr)
BODY_WEIGHT_MIN_KG = 30
BODY_WEIGHT_MAX_KG = 250
HEIGHT_MIN_CM = 100
HEIGHT_MAX_CM = 250


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for user preferences API"""
    inject_correlation_id(logger, event)
    try:
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        logger.info(f"User Preferences API: {http_method} {path}")
        
        if http_method == 'GET':
            return get_user_preferences(event)
        elif http_method == 'POST':
            return update_user_preferences(event)
        else:
            return create_error_response(405, 'Method not allowed', cors_headers=CORS_HEADERS)

    except (ClientError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"User preferences API error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error', cors_headers=CORS_HEADERS)


def get_user_preferences(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get user preferences from DynamoDB"""
    try:
        # Get user_id from query parameters or use default
        query_params = event.get('queryStringParameters') or {}
        user_id = query_params.get('user_id', os.environ.get('DEFAULT_USER_ID', ''))
        if not user_id or not re.match(r'^[a-zA-Z0-9_-]{1,64}$', user_id):
            return create_error_response(400, 'Invalid or missing user_id', cors_headers=CORS_HEADERS)

        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': user_id})

        if 'Item' in response:
            user_config = response['Item']
            stored_config = user_config
            preferences = user_config.get('user_preferences', {})
        else:
            # Return default preferences
            stored_config = {}
            preferences = {}

        # Include auto-accumulated PRs if available
        best_efforts_prs = stored_config.get('best_efforts_prs', {})

        # Campus is the only source of pace zones; the page shows them read-only.
        # The source comes from the same rule every reader uses.
        _, pace_zones_source = effective_pace_zones(stored_config)
        campus_pace_zones = stored_config.get('campus_pace_zones')
        if not isinstance(campus_pace_zones, dict) or not campus_pace_zones:
            campus_pace_zones = None

        # Return with defaults
        result = {
            'success': True,
            'preferences': {
                'age_range': preferences.get('age_range', '26-35'),
                'interests': preferences.get('interests', []),
                'sport_approach': preferences.get('sport_approach', 'health & wellness'),
                'content_length': preferences.get('content_length', 'medium'),
                'content_tone': preferences.get('content_tone', 'motivational & energetic'),
                'emoji_usage': preferences.get('emoji_usage', 'moderate'),
                'technical_detail': preferences.get('technical_detail', 'intermediate'),
                'content_language': preferences.get('content_language', 'french'),
                'pace_zones': preferences.get('pace_zones', None),
                'athlete_profile': preferences.get('athlete_profile', ''),
                'personal_records': preferences.get('personal_records', []),
                'max_hr': preferences.get('max_hr', None),
                'body_weight_kg': preferences.get('body_weight_kg', None),
                'height_cm': preferences.get('height_cm', None),
                'best_efforts_prs': best_efforts_prs,
                'strength_program': preferences.get('strength_program', None),
                'campus_pace_zones': campus_pace_zones,
                'campus_pace_zones_week': stored_config.get('campus_pace_zones_week'),
                'campus_pace_zones_synced_at': stored_config.get('campus_pace_zones_synced_at'),
                'pace_zones_source': pace_zones_source,
            }
        }

        return create_success_response(result, cors_headers=CORS_HEADERS)

    except ClientError as e:
        logger.error(f"Get user preferences error: {str(e)}")
        return create_error_response(500, 'Failed to get user preferences', cors_headers=CORS_HEADERS)


def update_user_preferences(event: Dict[str, Any]) -> Dict[str, Any]:
    """Update user preferences in DynamoDB"""
    try:
        # Parse and validate request body
        body_str = event.get('body', '{}')
        if len(body_str) > 10000:
            return create_error_response(413, 'Request body too large', cors_headers=CORS_HEADERS)
        body = json.loads(body_str)
        user_id = body.get('user_id', os.environ.get('DEFAULT_USER_ID', ''))
        if not user_id or not re.match(r'^[a-zA-Z0-9_-]{1,64}$', user_id):
            return create_error_response(400, 'Invalid or missing user_id', cors_headers=CORS_HEADERS)

        # Validate preference values against allowed lists
        age_range = body.get('age_range', '26-35')
        if age_range not in ALLOWED_AGE_RANGES:
            return create_error_response(400, f'Invalid age_range. Allowed: {ALLOWED_AGE_RANGES}', cors_headers=CORS_HEADERS)
        sport_approach = body.get('sport_approach', 'health & wellness')
        if sport_approach not in ALLOWED_SPORT_APPROACHES:
            return create_error_response(400, f'Invalid sport_approach. Allowed: {ALLOWED_SPORT_APPROACHES}', cors_headers=CORS_HEADERS)
        content_length = body.get('content_length', 'medium')
        if content_length not in ALLOWED_CONTENT_LENGTHS:
            return create_error_response(400, f'Invalid content_length. Allowed: {ALLOWED_CONTENT_LENGTHS}', cors_headers=CORS_HEADERS)
        content_tone = body.get('content_tone', 'motivational & energetic')
        if content_tone not in ALLOWED_CONTENT_TONES:
            return create_error_response(400, f'Invalid content_tone. Allowed: {ALLOWED_CONTENT_TONES}', cors_headers=CORS_HEADERS)
        emoji_usage = body.get('emoji_usage', 'moderate')
        if emoji_usage not in ALLOWED_EMOJI_USAGES:
            return create_error_response(400, f'Invalid emoji_usage. Allowed: {ALLOWED_EMOJI_USAGES}', cors_headers=CORS_HEADERS)
        technical_detail = body.get('technical_detail', 'intermediate')
        if technical_detail not in ALLOWED_TECHNICAL_DETAILS:
            return create_error_response(400, f'Invalid technical_detail. Allowed: {ALLOWED_TECHNICAL_DETAILS}', cors_headers=CORS_HEADERS)
        content_language = body.get('content_language', 'french')
        if content_language not in ALLOWED_CONTENT_LANGUAGES:
            return create_error_response(400, f'Invalid content_language. Allowed: {ALLOWED_CONTENT_LANGUAGES}', cors_headers=CORS_HEADERS)

        interests = body.get('interests', [])
        if not isinstance(interests, list) or len(interests) > 20:
            return create_error_response(400, 'interests must be a list with at most 20 items', cors_headers=CORS_HEADERS)

        # Validate athlete_profile (free-text, max 2000 chars). Deliberately NOT in
        # OPTIONAL_REMOVABLE_KEYS: an omitted athlete_profile is stored as '' (always
        # SET), exactly as before the child-path save. Readers treat '' and absent the
        # same, so keeping today's behaviour avoids a semantic change in this branch.
        athlete_profile = body.get('athlete_profile', '')
        if not isinstance(athlete_profile, str) or len(athlete_profile) > 2000:
            return create_error_response(400, 'athlete_profile must be a string with at most 2000 characters', cors_headers=CORS_HEADERS)

        preferences = {
            'age_range': age_range,
            'interests': interests,
            'sport_approach': sport_approach,
            'content_length': content_length,
            'content_tone': content_tone,
            'emoji_usage': emoji_usage,
            'technical_detail': technical_detail,
            'content_language': content_language,
            'athlete_profile': athlete_profile
        }

        # pace_zones from the request is ignored: Campus is the only source of pace
        # zones (docs/design/campus-paces.md), and a save must never overwrite the
        # legacy manual zones still stored under user_preferences.pace_zones.
        if 'pace_zones' in body:
            logger.info("Ignoring pace_zones in preferences POST (Campus is the only source)")

        # Add personal_records if provided (manual PRs: [{distance, time, date, event}])
        personal_records = body.get('personal_records')
        if personal_records is not None:
            if not isinstance(personal_records, list) or len(personal_records) > 30:
                return create_error_response(400, 'personal_records must be a list with at most 30 items', cors_headers=CORS_HEADERS)
            valid_records = []
            for rec in personal_records:
                if isinstance(rec, dict) and rec.get('distance') and rec.get('time'):
                    valid_records.append({
                        'distance': str(rec['distance']),
                        'time': str(rec['time']),
                        'date': str(rec.get('date', '')),
                        'event': str(rec.get('event', ''))
                    })
            preferences['personal_records'] = valid_records
            logger.info(f"Personal records configured: {len(valid_records)} entries")

        # Add max_hr if provided (integer, 120-230 bpm)
        max_hr = body.get('max_hr')
        if max_hr is not None:
            try:
                max_hr = int(max_hr)
                if 120 <= max_hr <= 230:
                    preferences['max_hr'] = max_hr
                else:
                    return create_error_response(400, 'max_hr must be between 120 and 230', cors_headers=CORS_HEADERS)
            except (ValueError, TypeError):
                return create_error_response(400, 'max_hr must be an integer', cors_headers=CORS_HEADERS)

        # Add body_weight_kg if provided (number, 30-250 kg)
        body_weight_kg = body.get('body_weight_kg')
        if body_weight_kg is not None:
            try:
                weight_value = Decimal(str(body_weight_kg))
            except (InvalidOperation, ValueError, TypeError):
                return create_error_response(400, 'body_weight_kg must be a number', cors_headers=CORS_HEADERS)
            if BODY_WEIGHT_MIN_KG <= weight_value <= BODY_WEIGHT_MAX_KG:
                preferences['body_weight_kg'] = weight_value
            else:
                return create_error_response(
                    400,
                    f'body_weight_kg must be between {BODY_WEIGHT_MIN_KG} and {BODY_WEIGHT_MAX_KG}',
                    cors_headers=CORS_HEADERS,
                )

        # Add height_cm if provided (number, 100-250 cm)
        height_cm = body.get('height_cm')
        if height_cm is not None:
            try:
                height_value = Decimal(str(height_cm))
            except (InvalidOperation, ValueError, TypeError):
                return create_error_response(400, 'height_cm must be a number', cors_headers=CORS_HEADERS)
            if HEIGHT_MIN_CM <= height_value <= HEIGHT_MAX_CM:
                preferences['height_cm'] = height_value
            else:
                return create_error_response(
                    400,
                    f'height_cm must be between {HEIGHT_MIN_CM} and {HEIGHT_MAX_CM}',
                    cors_headers=CORS_HEADERS,
                )

        # Add strength_program if provided
        strength_program = body.get('strength_program')
        if strength_program is not None:
            preferences['strength_program'] = strength_program

        # Save to DynamoDB without replacing the whole map (see _save_preferences)
        _save_preferences(user_id, preferences)
        
        logger.info(f"User preferences updated for user {user_id}")
        
        return create_success_response({
            'success': True,
            'message': 'Preferences saved successfully',
            'preferences': preferences
        }, cors_headers=CORS_HEADERS)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_error_response(400, 'Invalid JSON in request body', cors_headers=CORS_HEADERS)
    except ClientError as e:
        logger.error(f"Update user preferences DynamoDB error: {str(e)}")
        return create_error_response(500, 'Failed to update user preferences', cors_headers=CORS_HEADERS)


# Optional keys this API owns: absent from a POST means "cleared", so they are
# REMOVEd from the stored map (the old full-map replace dropped them the same way).
# personal_records is owned too but only written when sent: an absent list keeps
# the stored one. Every other key of user_preferences (pace_zones,
# strength_history, anything another writer adds) is never touched by a save.
OPTIONAL_REMOVABLE_KEYS = ('max_hr', 'body_weight_kg', 'height_cm', 'strength_program')


def _child_path_update(table: Any, user_id: str, preferences: Dict[str, Any], timestamp: str) -> None:
    """SET each sent key and REMOVE each absent optional key, by child path.

    Conditional on the map existing: a child path on a missing map is invalid,
    and the condition turns that case into ConditionalCheckFailedException.
    """
    names: Dict[str, str] = {'#prefs': 'user_preferences', '#updated': 'updated_at'}
    values: Dict[str, Any] = {':timestamp': timestamp}
    set_parts = ['#updated = :timestamp']
    for index, (key, value) in enumerate(sorted(preferences.items())):
        names[f'#k{index}'] = key
        values[f':v{index}'] = value
        set_parts.append(f'#prefs.#k{index} = :v{index}')
    remove_parts = []
    for index, key in enumerate(k for k in OPTIONAL_REMOVABLE_KEYS if k not in preferences):
        names[f'#r{index}'] = key
        remove_parts.append(f'#prefs.#r{index}')
    expression = 'SET ' + ', '.join(set_parts)
    if remove_parts:
        expression += ' REMOVE ' + ', '.join(remove_parts)
    table.update_item(
        Key={'user_id': user_id},
        UpdateExpression=expression,
        ConditionExpression='attribute_exists(#prefs)',
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _is_conditional_failure(error: ClientError) -> bool:
    return error.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException'


def _save_preferences(user_id: str, preferences: Dict[str, Any]) -> None:
    """Persist the API-owned preference keys without replacing the whole map.

    1. Map present: child-path update (keys not owned by this API survive).
    2. Map absent: create it with the API keys, only if still absent.
    3. Another writer created it in between: child-path update once more.
    """
    table = dynamodb.Table(USER_CONFIG_TABLE)
    timestamp = datetime.now(UTC).isoformat()
    try:
        _child_path_update(table, user_id, preferences, timestamp)
        return
    except ClientError as e:
        if not _is_conditional_failure(e):
            raise
    try:
        table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET #prefs = :prefs, #updated = :timestamp',
            ConditionExpression='attribute_not_exists(#prefs)',
            ExpressionAttributeNames={'#prefs': 'user_preferences', '#updated': 'updated_at'},
            ExpressionAttributeValues={':prefs': preferences, ':timestamp': timestamp},
        )
        return
    except ClientError as e:
        if not _is_conditional_failure(e):
            raise
    logger.info("user_preferences created concurrently, retrying child-path update")
    _child_path_update(table, user_id, preferences, timestamp)
