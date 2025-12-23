"""
Status API Lambda Function

Provides real-time processing status for activities including:
- Current processing status
- Step Functions workflow progress
- Error details and retry status
"""

import json
import os
import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')
sqs = boto3.client('sqs')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']


# CORS headers
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for status API endpoints
    
    Provides real-time processing status information
    """
    try:
        # Extract client information for rate limiting
        client_ip, user_agent = extract_client_info(event)
        
        # Check rate limit
        is_allowed, rate_limit_info = check_rate_limit(client_ip, 'status', user_agent)
        
        if not is_allowed:
            return create_rate_limit_response(rate_limit_info)
        
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        path_parameters = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}
        
        # Handle CORS preflight
        if http_method == 'OPTIONS':
            headers = add_rate_limit_headers(CORS_HEADERS.copy(), rate_limit_info)
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'status': 'ok'})
            }
        
        # Validate request
        validation_error = validate_request(event)
        if validation_error:
            return create_error_response(400, validation_error, rate_limit_info)
        
        # Route requests based on path
        if path_parameters.get('activity_id'):
            # Get status for specific activity
            activity_id = path_parameters['activity_id']
            response_data = get_activity_status(activity_id)
            return create_success_response(response_data, rate_limit_info=rate_limit_info)
        else:
            # Get overall system status
            response_data = get_system_status(query_params)
            return create_success_response(response_data, rate_limit_info=rate_limit_info)
        
    except Exception as e:
        logger.error(f"Status API error: {str(e)}")
        return create_error_response(500, 'Internal server error')


def validate_request(event: Dict[str, Any]) -> str:
    """Validate incoming request"""
    try:
        # Check HTTP method
        http_method = event.get('httpMethod', '')
        if http_method not in ['GET', 'OPTIONS']:
            return f'Method {http_method} not allowed'
        
        # Validate activity_id if present
        path_parameters = event.get('pathParameters') or {}
        activity_id = path_parameters.get('activity_id')
        
        if activity_id:
            # Basic activity ID validation (should be numeric string)
            if not activity_id.isdigit():
                return 'Activity ID must be numeric'
            
            # Check reasonable length (Strava activity IDs are typically 10 digits)
            if len(activity_id) < 8 or len(activity_id) > 15:
                return 'Activity ID format invalid'
        
        return None  # No validation errors
        
    except Exception as e:
        logger.error(f"Request validation error: {str(e)}")
        return f'Request validation failed: {str(e)}'


def create_error_response(status_code: int, message: str, rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create standardized error response"""
    headers = CORS_HEADERS.copy()
    if rate_limit_info:
        headers = add_rate_limit_headers(headers, rate_limit_info)
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.utcnow().isoformat()
        })
    }


def create_success_response(data: Dict[str, Any], status_code: int = 200, rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create standardized success response"""
    headers = CORS_HEADERS.copy()
    if rate_limit_info:
        headers = add_rate_limit_headers(headers, rate_limit_info)
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps({
            **data,
            'timestamp': datetime.utcnow().isoformat()
        })
    }


def get_activity_status(activity_id: str) -> Dict[str, Any]:
    """Get detailed status for a specific activity"""
    try:
        # Get activity from DynamoDB
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={'activity_id': activity_id})
        
        if 'Item' not in response:
            return {
                'activity_id': activity_id,
                'status': 'not_found',
                'message': 'Activity not found in processing records'
            }
        
        activity = response['Item']
        
        # Get basic status information
        status_info = {
            'activity_id': activity_id,
            'status': activity.get('processing_status', 'unknown'),
            'original_name': activity.get('original_name', ''),
            'enhanced_title': activity.get('enhanced_title', ''),
            'activity_type': activity.get('activity_type', ''),
            'created_at': activity.get('created_at', ''),
            'updated_at': activity.get('updated_at', ''),
            'modules_used': activity.get('modules_used', []),
            'error_message': activity.get('error_message', '')
        }
        
        # Get Step Functions execution status if processing
        if status_info['status'] == 'processing':
            step_functions_status = get_step_functions_status(activity_id)
            status_info['workflow_status'] = step_functions_status
        
        # Get retry information if failed
        if status_info['status'] == 'failed':
            retry_info = get_retry_information(activity_id)
            status_info['retry_info'] = retry_info
        
        return status_info
        
    except Exception as e:
        logger.error(f"Failed to get activity status for {activity_id}: {str(e)}")
        return {
            'activity_id': activity_id,
            'status': 'error',
            'error': str(e)
        }


def get_system_status(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Get overall system processing status"""
    try:
        # Get recent activities status
        recent_activities = get_recent_activities_status()
        
        # Get queue status
        queue_status = get_queue_status()
        
        # Get system health indicators
        health_status = get_system_health()
        
        return {
            'system_status': 'operational',  # TODO: Determine based on metrics
            'recent_activities': recent_activities,
            'queue_status': queue_status,
            'health_status': health_status,
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system status: {str(e)}")
        return {
            'system_status': 'error',
            'error': str(e),
            'last_updated': datetime.utcnow().isoformat()
        }


def get_recent_activities_status() -> Dict[str, Any]:
    """Get status of recent activities"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get recent activities (last 50)
        response = table.scan(Limit=50)
        activities = response.get('Items', [])
        
        # Sort by updated_at descending
        activities.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
        
        # Take only the most recent 10 for status display
        recent_activities = activities[:10]
        
        # Count by status
        status_counts = {}
        for activity in activities:
            status = activity.get('processing_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Format recent activities for display
        formatted_activities = []
        for activity in recent_activities:
            formatted_activity = {
                'activity_id': activity.get('activity_id'),
                'status': activity.get('processing_status', 'unknown'),
                'original_name': activity.get('original_name', ''),
                'activity_type': activity.get('activity_type', ''),
                'updated_at': activity.get('updated_at', ''),
                'modules_used': activity.get('modules_used', [])
            }
            formatted_activities.append(formatted_activity)
        
        return {
            'recent_activities': formatted_activities,
            'status_summary': status_counts,
            'total_recent': len(activities)
        }
        
    except Exception as e:
        logger.error(f"Failed to get recent activities status: {str(e)}")
        return {
            'recent_activities': [],
            'status_summary': {},
            'total_recent': 0,
            'error': str(e)
        }


def get_queue_status() -> Dict[str, Any]:
    """Get SQS queue status information"""
    try:
        # TODO: Get actual queue URLs from environment or configuration
        # For now, return placeholder data
        
        return {
            'processing_queue': {
                'approximate_messages': 0,
                'approximate_messages_not_visible': 0,
                'status': 'healthy'
            },
            'dead_letter_queue': {
                'approximate_messages': 0,
                'status': 'healthy'
            },
            'note': 'Queue status requires SQS queue URL configuration'
        }
        
    except Exception as e:
        logger.error(f"Failed to get queue status: {str(e)}")
        return {
            'processing_queue': {'status': 'error'},
            'dead_letter_queue': {'status': 'error'},
            'error': str(e)
        }


def get_system_health() -> Dict[str, Any]:
    """Get system health indicators"""
    try:
        # Check DynamoDB table accessibility
        table_health = check_dynamodb_health()
        
        # Check recent error rates
        error_rate = calculate_recent_error_rate()
        
        # Determine overall health
        overall_health = 'healthy'
        if not table_health or error_rate > 10:  # More than 10% error rate
            overall_health = 'degraded'
        if error_rate > 50:  # More than 50% error rate
            overall_health = 'unhealthy'
        
        return {
            'overall_health': overall_health,
            'dynamodb_accessible': table_health,
            'recent_error_rate': error_rate,
            'last_check': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system health: {str(e)}")
        return {
            'overall_health': 'unknown',
            'error': str(e),
            'last_check': datetime.utcnow().isoformat()
        }


def check_dynamodb_health() -> bool:
    """Check if DynamoDB table is accessible"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        # Simple describe table operation to check accessibility
        table.load()
        return True
    except Exception as e:
        logger.error(f"DynamoDB health check failed: {str(e)}")
        return False


def calculate_recent_error_rate() -> float:
    """Calculate error rate from recent activities"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get recent activities (last 100)
        response = table.scan(Limit=100)
        activities = response.get('Items', [])
        
        if not activities:
            return 0.0
        
        failed_count = len([a for a in activities if a.get('processing_status') == 'failed'])
        error_rate = (failed_count / len(activities)) * 100
        
        return round(error_rate, 2)
        
    except Exception as e:
        logger.error(f"Failed to calculate error rate: {str(e)}")
        return 0.0


def get_step_functions_status(activity_id: str) -> Optional[Dict[str, Any]]:
    """Get Step Functions workflow status for an activity"""
    try:
        # TODO: Implement Step Functions status lookup
        # This requires tracking execution ARNs or using tags to find executions
        
        # Placeholder implementation
        return {
            'status': 'unknown',
            'current_step': 'unknown',
            'note': 'Step Functions status tracking requires execution ARN mapping'
        }
        
    except Exception as e:
        logger.error(f"Failed to get Step Functions status: {str(e)}")
        return None


def get_retry_information(activity_id: str) -> Dict[str, Any]:
    """Get retry information for failed activities"""
    try:
        # TODO: Implement retry tracking
        # This could involve checking SQS DLQ or maintaining retry counters
        
        # Placeholder implementation
        return {
            'retry_count': 0,
            'max_retries': 3,
            'next_retry': None,
            'note': 'Retry information requires SQS DLQ integration'
        }
        
    except Exception as e:
        logger.error(f"Failed to get retry information: {str(e)}")
        return {
            'retry_count': 0,
            'max_retries': 0,
            'error': str(e)
        }