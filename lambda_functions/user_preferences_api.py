"""
User Preferences API Lambda Function

Handles user preferences for content personalization:
- GET: Retrieve user preferences
- POST: Update user preferences
"""

import json
import os
import logging
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, UTC

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for user preferences API"""
    try:
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        logger.info(f"User Preferences API: {http_method} {path}")
        
        if http_method == 'GET':
            return get_user_preferences(event)
        elif http_method == 'POST':
            return update_user_preferences(event)
        else:
            return create_error_response(405, 'Method not allowed')
            
    except Exception as e:
        logger.error(f"User preferences API error: {str(e)}")
        return create_error_response(500, f'Internal server error: {str(e)}')


def get_user_preferences(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get user preferences from DynamoDB"""
    try:
        # Get user_id from query parameters or use default
        query_params = event.get('queryStringParameters') or {}
        user_id = query_params.get('user_id', os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID'))
        
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
        
        return create_success_response(result)
        
    except Exception as e:
        logger.error(f"Get user preferences error: {str(e)}")
        return create_error_response(500, f'Failed to get user preferences: {str(e)}')


def update_user_preferences(event: Dict[str, Any]) -> Dict[str, Any]:
    """Update user preferences in DynamoDB"""
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        user_id = body.get('user_id', os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID'))
        
        preferences = {
            'age_range': body.get('age_range', '26-35'),
            'interests': body.get('interests', []),
            'sport_approach': body.get('sport_approach', 'health & wellness'),
            'content_length': body.get('content_length', 'medium'),
            'content_tone': body.get('content_tone', 'motivational & energetic'),
            'emoji_usage': body.get('emoji_usage', 'moderate'),
            'technical_detail': body.get('technical_detail', 'intermediate'),
            'content_language': body.get('content_language', 'french')
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
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return create_error_response(400, 'Invalid JSON in request body')
    except Exception as e:
        logger.error(f"Update user preferences error: {str(e)}")
        return create_error_response(500, f'Failed to update user preferences: {str(e)}')


def create_success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create successful API response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-API-Key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(data)
    }


def create_error_response(status_code: int, error_message: str) -> Dict[str, Any]:
    """Create error API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-API-Key',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({
            'error': error_message,
            'timestamp': datetime.now(UTC).isoformat()
        })
    }
