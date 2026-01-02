"""
Rate Limiting Utility for API Lambda Functions

Provides rate limiting functionality using DynamoDB to track requests
"""

import json
import os
import logging
from typing import Dict, Any, Optional, Tuple
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Environment variables
RATE_LIMITS_TABLE = os.environ.get('RATE_LIMITS_TABLE', 'strava-ai-boost-rate-limits')

# Rate limit configurations (requests per minute)
RATE_LIMITS = {
    'dashboard': 60,      # 60 requests per minute for dashboard
    'status': 120,        # 120 requests per minute for status (more frequent polling)
    'configuration': 30,  # 30 requests per minute for configuration
    'default': 60         # Default rate limit
}


def check_rate_limit(client_ip: str, endpoint: str, user_agent: str = '') -> Tuple[bool, Dict[str, Any]]:
    """
    Check if request is within rate limits
    
    Args:
        client_ip: Client IP address
        endpoint: API endpoint being accessed
        user_agent: User agent string (optional)
    
    Returns:
        Tuple of (is_allowed, rate_limit_info)
    """
    try:
        # Create unique identifier for this client/endpoint combination
        client_key = create_client_key(client_ip, endpoint, user_agent)
        
        # Get rate limit for this endpoint
        limit = get_rate_limit_for_endpoint(endpoint)
        
        # Check current usage
        current_usage = get_current_usage(client_key)
        
        # Check if within limits
        is_allowed = current_usage < limit
        
        if is_allowed:
            # Increment usage counter
            increment_usage(client_key)
        
        # Prepare rate limit info
        rate_limit_info = {
            'limit': limit,
            'remaining': max(0, limit - current_usage - (1 if is_allowed else 0)),
            'reset_time': get_reset_time(),
            'endpoint': endpoint
        }
        
        return is_allowed, rate_limit_info
        
    except Exception as e:
        logger.error(f"Rate limit check error: {str(e)}")
        # On error, allow the request but log the issue
        return True, {
            'limit': RATE_LIMITS.get('default', 60),
            'remaining': 0,
            'reset_time': get_reset_time(),
            'error': 'Rate limit check failed'
        }


def create_client_key(client_ip: str, endpoint: str, user_agent: str = '') -> str:
    """Create unique key for client identification"""
    # Combine IP, endpoint, and optionally user agent for uniqueness
    key_data = f"{client_ip}:{endpoint}"
    
    # Add user agent hash if provided (to distinguish different clients from same IP)
    if user_agent:
        ua_hash = hashlib.md5(user_agent.encode()).hexdigest()[:8]
        key_data += f":{ua_hash}"
    
    # Create hash for consistent key length
    client_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    # Include current minute for time-based bucketing
    current_minute = datetime.utcnow().strftime('%Y%m%d%H%M')
    
    return f"rate_limit:{client_hash}:{current_minute}"


def get_rate_limit_for_endpoint(endpoint: str) -> int:
    """Get rate limit for specific endpoint"""
    # Extract endpoint type from path
    if 'dashboard' in endpoint:
        return RATE_LIMITS['dashboard']
    elif 'status' in endpoint:
        return RATE_LIMITS['status']
    elif 'configuration' in endpoint or 'config' in endpoint:
        return RATE_LIMITS['configuration']
    else:
        return RATE_LIMITS['default']


def get_current_usage(client_key: str) -> int:
    """Get current usage count for client key"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        response = table.get_item(Key={'limit_type': client_key})
        
        if 'Item' in response:
            return int(response['Item'].get('request_count', 0))
        else:
            return 0
            
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning(f"Rate limits table {RATE_LIMITS_TABLE} not found")
            return 0
        else:
            logger.error(f"Failed to get current usage: {str(e)}")
            return 0
    except Exception as e:
        logger.error(f"Failed to get current usage: {str(e)}")
        return 0


def increment_usage(client_key: str) -> None:
    """Increment usage counter for client key"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Use atomic counter increment
        table.update_item(
            Key={'limit_type': client_key},
            UpdateExpression='ADD request_count :inc SET updated_at = :timestamp, expires_at = :expires',
            ExpressionAttributeValues={
                ':inc': 1,
                ':timestamp': datetime.utcnow().isoformat(),
                ':expires': int((datetime.utcnow() + timedelta(minutes=2)).timestamp())  # Expire after 2 minutes
            }
        )
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning(f"Rate limits table {RATE_LIMITS_TABLE} not found, skipping rate limit tracking")
        else:
            logger.error(f"Failed to increment usage: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to increment usage: {str(e)}")


def get_reset_time() -> str:
    """Get the time when rate limits reset (next minute)"""
    next_minute = datetime.utcnow().replace(second=0, microsecond=0) + timedelta(minutes=1)
    return next_minute.isoformat()


def create_rate_limit_response(rate_limit_info: Dict[str, Any]) -> Dict[str, Any]:
    """Create rate limit exceeded response"""
    return {
        'statusCode': 429,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'X-RateLimit-Limit': str(rate_limit_info['limit']),
            'X-RateLimit-Remaining': str(rate_limit_info['remaining']),
            'X-RateLimit-Reset': rate_limit_info['reset_time'],
            'Retry-After': '60'  # Retry after 60 seconds
        },
        'body': json.dumps({
            'error': 'Rate limit exceeded',
            'message': f'Too many requests. Limit: {rate_limit_info["limit"]} requests per minute',
            'rate_limit': rate_limit_info,
            'timestamp': datetime.utcnow().isoformat()
        })
    }


def add_rate_limit_headers(headers: Dict[str, str], rate_limit_info: Dict[str, Any]) -> Dict[str, str]:
    """Add rate limit headers to response"""
    headers.update({
        'X-RateLimit-Limit': str(rate_limit_info['limit']),
        'X-RateLimit-Remaining': str(rate_limit_info['remaining']),
        'X-RateLimit-Reset': rate_limit_info['reset_time']
    })
    return headers


def extract_client_info(event: Dict[str, Any]) -> Tuple[str, str]:
    """Extract client IP and user agent from Lambda event"""
    # Get client IP from various possible sources
    client_ip = 'unknown'
    
    # Check for IP in request context (API Gateway)
    request_context = event.get('requestContext', {})
    identity = request_context.get('identity', {})
    
    if identity.get('sourceIp'):
        client_ip = identity['sourceIp']
    elif event.get('headers', {}).get('X-Forwarded-For'):
        # Get first IP from X-Forwarded-For header
        forwarded_ips = event['headers']['X-Forwarded-For'].split(',')
        client_ip = forwarded_ips[0].strip()
    elif event.get('headers', {}).get('X-Real-IP'):
        client_ip = event['headers']['X-Real-IP']
    
    # Get user agent
    headers = event.get('headers', {})
    user_agent = headers.get('User-Agent', headers.get('user-agent', ''))
    
    return client_ip, user_agent


# Decorator for easy rate limiting
def rate_limited(endpoint_name: str):
    """Decorator to add rate limiting to Lambda handlers"""
    def decorator(handler_func):
        def wrapper(event, context):
            try:
                # Extract client information
                client_ip, user_agent = extract_client_info(event)
                
                # Check rate limit
                is_allowed, rate_limit_info = check_rate_limit(client_ip, endpoint_name, user_agent)
                
                if not is_allowed:
                    return create_rate_limit_response(rate_limit_info)
                
                # Call original handler
                response = handler_func(event, context)
                
                # Add rate limit headers to successful responses
                if isinstance(response, dict) and 'headers' in response:
                    response['headers'] = add_rate_limit_headers(response['headers'], rate_limit_info)
                
                return response
                
            except Exception as e:
                logger.error(f"Rate limiting decorator error: {str(e)}")
                # On error, call original handler without rate limiting
                return handler_func(event, context)
        
        return wrapper
    return decorator