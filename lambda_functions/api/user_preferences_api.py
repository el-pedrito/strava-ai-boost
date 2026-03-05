"""
User Preferences API Lambda Function

Handles user preferences for content personalization:
- GET: Retrieve user preferences
- POST: Update user preferences
"""

import json
import os
import re
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
            preferences = user_config.get('user_preferences', {})
        else:
            # Return default preferences
            preferences = {}

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
                'pace_zones': preferences.get('pace_zones', None)
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

        preferences = {
            'age_range': age_range,
            'interests': interests,
            'sport_approach': sport_approach,
            'content_length': content_length,
            'content_tone': content_tone,
            'emoji_usage': emoji_usage,
            'technical_detail': technical_detail,
            'content_language': content_language
        }

        # Add pace_zones if provided (validated format: {zone: {min: "mm:ss", max: "mm:ss"}})
        pace_zones = body.get('pace_zones')
        if pace_zones and isinstance(pace_zones, dict):
            valid_zones = {}
            for zone_key, zone_val in pace_zones.items():
                if isinstance(zone_val, dict) and 'min' in zone_val and 'max' in zone_val:
                    valid_zones[zone_key] = {
                        'min': str(zone_val['min']),
                        'max': str(zone_val['max'])
                    }
            if valid_zones:
                preferences['pace_zones'] = valid_zones
                logger.info(f"Pace zones configured: {list(valid_zones.keys())}")
        
        # Save to DynamoDB
        table = dynamodb.Table(USER_CONFIG_TABLE)
        table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET user_preferences = :prefs, updated_at = :timestamp',
            ExpressionAttributeValues={
                ':prefs': preferences,
                ':timestamp': datetime.now(UTC).isoformat()
            }
        )
        
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
