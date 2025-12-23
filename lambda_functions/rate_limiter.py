"""
Rate Limiter Lambda Function

Manages Strava API rate limits (100/15min, 1000/day) with DynamoDB persistence.
Provides rate limit checking and reset functionality.
"""

import json
import os
import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
RATE_LIMITS_TABLE = os.environ['RATE_LIMITS_TABLE']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for rate limit management
    
    Handles rate limit checking, updating, and reset operations
    """
    try:
        action = event.get('action', 'check')
        
        if action == 'check':
            return check_rate_limits()
        elif action == 'update':
            api_calls = event.get('api_calls', 1)
            return update_rate_limits(api_calls)
        elif action == 'reset':
            limit_type = event.get('limit_type', 'both')
            return reset_rate_limits(limit_type)
        elif action == 'status':
            return get_rate_limit_status()
        else:
            raise ValueError(f"Unknown action: {action}")
        
    except Exception as e:
        logger.error(f"Rate limiter error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'action': event.get('action')
        }


def check_rate_limits() -> Dict[str, Any]:
    """Check current rate limit status"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        current_time = datetime.utcnow()
        
        # Check short-term limit (100/15min)
        short_term_status = check_limit_type('short_term', 100, 15, current_time)
        
        # Check daily limit (1000/day)
        daily_status = check_limit_type('daily', 1000, 1440, current_time)  # 1440 minutes = 24 hours
        
        # Determine overall status
        within_limits = short_term_status['within_limit'] and daily_status['within_limit']
        
        return {
            'statusCode': 200,
            'within_limits': within_limits,
            'short_term': short_term_status,
            'daily': daily_status,
            'checked_at': current_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to check rate limits: {str(e)}")
        return {
            'statusCode': 500,
            'within_limits': False,
            'error': str(e)
        }


def check_limit_type(
    limit_type: str, 
    max_requests: int, 
    window_minutes: int, 
    current_time: datetime
) -> Dict[str, Any]:
    """Check a specific rate limit type"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        response = table.get_item(Key={'limit_type': limit_type})
        
        if 'Item' not in response:
            # Initialize rate limit record
            reset_time = current_time + timedelta(minutes=window_minutes)
            table.put_item(
                Item={
                    'limit_type': limit_type,
                    'current_usage': 0,
                    'max_requests': max_requests,
                    'window_minutes': window_minutes,
                    'reset_time': reset_time.isoformat(),
                    'last_request': current_time.isoformat()
                }
            )
            
            return {
                'within_limit': True,
                'current_usage': 0,
                'max_requests': max_requests,
                'remaining': max_requests,
                'reset_time': reset_time.isoformat(),
                'window_minutes': window_minutes
            }
        
        item = response['Item']
        current_usage = item.get('current_usage', 0)
        reset_time_str = item.get('reset_time', '')
        
        # Check if reset time has passed
        if reset_time_str:
            reset_time = datetime.fromisoformat(reset_time_str)
            if current_time >= reset_time:
                # Reset the counter
                new_reset_time = current_time + timedelta(minutes=window_minutes)
                table.update_item(
                    Key={'limit_type': limit_type},
                    UpdateExpression="SET current_usage = :zero, reset_time = :reset, last_request = :time",
                    ExpressionAttributeValues={
                        ':zero': 0,
                        ':reset': new_reset_time.isoformat(),
                        ':time': current_time.isoformat()
                    }
                )
                current_usage = 0
                reset_time = new_reset_time
        else:
            reset_time = current_time + timedelta(minutes=window_minutes)
        
        within_limit = current_usage < max_requests
        remaining = max(0, max_requests - current_usage)
        
        return {
            'within_limit': within_limit,
            'current_usage': current_usage,
            'max_requests': max_requests,
            'remaining': remaining,
            'reset_time': reset_time.isoformat() if isinstance(reset_time, datetime) else reset_time,
            'window_minutes': window_minutes
        }
        
    except Exception as e:
        logger.error(f"Failed to check {limit_type} limit: {str(e)}")
        return {
            'within_limit': False,
            'current_usage': 0,
            'max_requests': max_requests,
            'remaining': 0,
            'error': str(e)
        }


def update_rate_limits(api_calls: int) -> Dict[str, Any]:
    """Update rate limit counters after API calls"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        current_time = datetime.utcnow()
        
        # Update short-term limit
        short_term_result = update_limit_type('short_term', api_calls, current_time)
        
        # Update daily limit
        daily_result = update_limit_type('daily', api_calls, current_time)
        
        return {
            'statusCode': 200,
            'api_calls_added': api_calls,
            'short_term': short_term_result,
            'daily': daily_result,
            'updated_at': current_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to update rate limits: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'api_calls_added': api_calls
        }


def update_limit_type(limit_type: str, api_calls: int, current_time: datetime) -> Dict[str, Any]:
    """Update a specific rate limit type"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Use atomic update to increment usage
        response = table.update_item(
            Key={'limit_type': limit_type},
            UpdateExpression="ADD current_usage :calls SET last_request = :time",
            ExpressionAttributeValues={
                ':calls': api_calls,
                ':time': current_time.isoformat()
            },
            ReturnValues="ALL_NEW"
        )
        
        item = response['Attributes']
        
        return {
            'current_usage': item.get('current_usage', 0),
            'max_requests': item.get('max_requests', 0),
            'remaining': max(0, item.get('max_requests', 0) - item.get('current_usage', 0)),
            'reset_time': item.get('reset_time', ''),
            'last_request': item.get('last_request', '')
        }
        
    except Exception as e:
        logger.error(f"Failed to update {limit_type} limit: {str(e)}")
        return {
            'error': str(e),
            'current_usage': 0,
            'max_requests': 0,
            'remaining': 0
        }


def reset_rate_limits(limit_type: str = 'both') -> Dict[str, Any]:
    """Reset rate limit counters"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        current_time = datetime.utcnow()
        
        results = {}
        
        if limit_type in ['both', 'short_term']:
            # Reset short-term limit
            reset_time = current_time + timedelta(minutes=15)
            table.update_item(
                Key={'limit_type': 'short_term'},
                UpdateExpression="SET current_usage = :zero, reset_time = :reset, last_request = :time",
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':reset': reset_time.isoformat(),
                    ':time': current_time.isoformat()
                }
            )
            results['short_term'] = 'reset'
        
        if limit_type in ['both', 'daily']:
            # Reset daily limit
            reset_time = current_time + timedelta(days=1)
            table.update_item(
                Key={'limit_type': 'daily'},
                UpdateExpression="SET current_usage = :zero, reset_time = :reset, last_request = :time",
                ExpressionAttributeValues={
                    ':zero': 0,
                    ':reset': reset_time.isoformat(),
                    ':time': current_time.isoformat()
                }
            )
            results['daily'] = 'reset'
        
        return {
            'statusCode': 200,
            'reset_results': results,
            'reset_at': current_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to reset rate limits: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'limit_type': limit_type
        }


def get_rate_limit_status() -> Dict[str, Any]:
    """Get detailed rate limit status information"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Get all rate limit records
        response = table.scan()
        items = response.get('Items', [])
        
        status = {}
        for item in items:
            limit_type = item.get('limit_type')
            status[limit_type] = {
                'current_usage': item.get('current_usage', 0),
                'max_requests': item.get('max_requests', 0),
                'remaining': max(0, item.get('max_requests', 0) - item.get('current_usage', 0)),
                'reset_time': item.get('reset_time', ''),
                'last_request': item.get('last_request', ''),
                'window_minutes': item.get('window_minutes', 0)
            }
        
        return {
            'statusCode': 200,
            'rate_limits': status,
            'retrieved_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get rate limit status: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'rate_limits': {}
        }