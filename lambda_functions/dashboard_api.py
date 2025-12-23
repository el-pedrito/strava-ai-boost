"""
Dashboard API Lambda Function

Provides dashboard data for the local web interface including:
- Activity processing statistics
- Engagement metrics
- Recent activity history
- System performance metrics
"""

import json
import os
import logging
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']


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
    Lambda handler for dashboard API endpoints
    
    Handles various dashboard data requests
    """
    try:
        # Extract client information for rate limiting
        client_ip, user_agent = extract_client_info(event)
        
        # Check rate limit
        is_allowed, rate_limit_info = check_rate_limit(client_ip, 'dashboard', user_agent)
        
        if not is_allowed:
            return create_rate_limit_response(rate_limit_info)
        
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
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
        if '/dashboard/stats' in path:
            response_data = get_dashboard_stats(query_params)
            return create_success_response(response_data, rate_limit_info=rate_limit_info)
        elif '/dashboard/activities' in path:
            response_data = get_activity_history(query_params)
            return create_success_response(response_data, rate_limit_info=rate_limit_info)
        else:
            return create_error_response(404, 'Endpoint not found', rate_limit_info)
        
    except Exception as e:
        logger.error(f"Dashboard API error: {str(e)}")
        return create_error_response(500, 'Internal server error')


def validate_request(event: Dict[str, Any]) -> str:
    """Validate incoming request"""
    try:
        # Check HTTP method
        http_method = event.get('httpMethod', '')
        if http_method not in ['GET', 'OPTIONS']:
            return f'Method {http_method} not allowed'
        
        # Validate query parameters for dashboard requests
        query_params = event.get('queryStringParameters') or {}
        
        # Validate 'days' parameter if present
        if 'days' in query_params:
            try:
                days = int(query_params['days'])
                if days < 1 or days > 365:
                    return 'Days parameter must be between 1 and 365'
            except ValueError:
                return 'Days parameter must be a valid integer'
        
        # Validate pagination parameters
        if 'limit' in query_params:
            try:
                limit = int(query_params['limit'])
                if limit < 1 or limit > 100:
                    return 'Limit parameter must be between 1 and 100'
            except ValueError:
                return 'Limit parameter must be a valid integer'
        
        if 'offset' in query_params:
            try:
                offset = int(query_params['offset'])
                if offset < 0:
                    return 'Offset parameter must be non-negative'
            except ValueError:
                return 'Offset parameter must be a valid integer'
        
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


def get_dashboard_stats(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Get dashboard statistics and metrics"""
    try:
        # Get time range from query params (default: last 30 days)
        days = int(query_params.get('days', '30'))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get activity processing statistics
        activity_stats = get_activity_processing_stats(start_date)
        
        # Get system performance metrics
        performance_metrics = get_performance_metrics()
        
        # Get module usage statistics
        module_stats = get_module_usage_stats(start_date)
        
        # Get engagement metrics (placeholder)
        engagement_metrics = get_engagement_metrics(start_date)
        
        return {
            'time_range': {
                'days': days,
                'start_date': start_date.isoformat(),
                'end_date': datetime.utcnow().isoformat()
            },
            'activity_stats': activity_stats,
            'performance_metrics': performance_metrics,
            'module_stats': module_stats,
            'engagement_metrics': engagement_metrics,
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {str(e)}")
        raise


def get_activity_processing_stats(start_date: datetime) -> Dict[str, Any]:
    """Get activity processing statistics from DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Scan activities table for recent activities
        # TODO: Use GSI with date range for better performance
        response = table.scan()
        
        activities = response.get('Items', [])
        
        # Filter activities by date range
        recent_activities = []
        for activity in activities:
            created_at = activity.get('created_at', '')
            if created_at:
                try:
                    activity_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if activity_date >= start_date:
                        recent_activities.append(activity)
                except ValueError:
                    # Skip activities with invalid dates
                    continue
        
        # Calculate statistics
        total_activities = len(recent_activities)
        completed_activities = len([a for a in recent_activities if a.get('processing_status') == 'completed'])
        failed_activities = len([a for a in recent_activities if a.get('processing_status') == 'failed'])
        processing_activities = len([a for a in recent_activities if a.get('processing_status') == 'processing'])
        
        success_rate = (completed_activities / total_activities * 100) if total_activities > 0 else 0
        
        return {
            'total_activities': total_activities,
            'completed_activities': completed_activities,
            'failed_activities': failed_activities,
            'processing_activities': processing_activities,
            'success_rate': round(success_rate, 1),
            'activity_types': get_activity_type_breakdown(recent_activities)
        }
        
    except Exception as e:
        logger.error(f"Failed to get activity processing stats: {str(e)}")
        return {
            'total_activities': 0,
            'completed_activities': 0,
            'failed_activities': 0,
            'processing_activities': 0,
            'success_rate': 0,
            'activity_types': {}
        }


def get_activity_type_breakdown(activities: List[Dict[str, Any]]) -> Dict[str, int]:
    """Get breakdown of activities by type"""
    type_counts = {}
    
    for activity in activities:
        activity_type = activity.get('activity_type', 'Unknown')
        type_counts[activity_type] = type_counts.get(activity_type, 0) + 1
    
    return type_counts


def get_performance_metrics() -> Dict[str, Any]:
    """Get system performance metrics from CloudWatch"""
    try:
        # Get Lambda function metrics for the last hour
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        # Get average duration for key Lambda functions
        lambda_functions = [
            'StravaAIBoost-WebhookHandler',
            'StravaAIBoost-ContentGenerator',
            'StravaAIBoost-ActivityFetcher'
        ]
        
        function_metrics = {}
        
        for function_name in lambda_functions:
            try:
                # Get average duration
                duration_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Duration',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour
                    Statistics=['Average']
                )
                
                avg_duration = 0
                if duration_response['Datapoints']:
                    avg_duration = duration_response['Datapoints'][0]['Average']
                
                # Get error count
                error_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[
                        {
                            'Name': 'FunctionName',
                            'Value': function_name
                        }
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                error_count = 0
                if error_response['Datapoints']:
                    error_count = error_response['Datapoints'][0]['Sum']
                
                function_metrics[function_name] = {
                    'avg_duration_ms': round(avg_duration, 2),
                    'error_count': int(error_count)
                }
                
            except Exception as e:
                logger.warning(f"Failed to get metrics for {function_name}: {str(e)}")
                function_metrics[function_name] = {
                    'avg_duration_ms': 0,
                    'error_count': 0
                }
        
        return {
            'lambda_functions': function_metrics,
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {str(e)}")
        return {
            'lambda_functions': {},
            'last_updated': datetime.utcnow().isoformat()
        }


def get_module_usage_stats(start_date: datetime) -> Dict[str, Any]:
    """Get module usage statistics"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get activities with module usage data
        response = table.scan()
        activities = response.get('Items', [])
        
        # Filter by date range
        recent_activities = []
        for activity in activities:
            created_at = activity.get('created_at', '')
            if created_at:
                try:
                    activity_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if activity_date >= start_date:
                        recent_activities.append(activity)
                except ValueError:
                    continue
        
        # Count module usage
        module_counts = {}
        total_with_modules = 0
        
        for activity in recent_activities:
            modules_used = activity.get('modules_used', [])
            if modules_used:
                total_with_modules += 1
                for module in modules_used:
                    module_counts[module] = module_counts.get(module, 0) + 1
        
        return {
            'total_activities_with_modules': total_with_modules,
            'module_usage': module_counts,
            'most_used_module': max(module_counts.items(), key=lambda x: x[1])[0] if module_counts else None
        }
        
    except Exception as e:
        logger.error(f"Failed to get module usage stats: {str(e)}")
        return {
            'total_activities_with_modules': 0,
            'module_usage': {},
            'most_used_module': None
        }


def get_engagement_metrics(start_date: datetime) -> Dict[str, Any]:
    """Get engagement metrics (placeholder implementation)"""
    try:
        # TODO: Implement actual engagement metrics from Strava API
        # This would require fetching activity data from Strava to get kudos, comments, etc.
        
        # Placeholder metrics
        return {
            'total_kudos': 0,
            'total_comments': 0,
            'avg_kudos_per_activity': 0,
            'engagement_improvement': 0,
            'note': 'Engagement metrics require Strava API integration'
        }
        
    except Exception as e:
        logger.error(f"Failed to get engagement metrics: {str(e)}")
        return {
            'total_kudos': 0,
            'total_comments': 0,
            'avg_kudos_per_activity': 0,
            'engagement_improvement': 0
        }


def get_activity_history(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Get recent activity history with processing details"""
    try:
        # Get pagination parameters
        limit = int(query_params.get('limit', '20'))
        offset = int(query_params.get('offset', '0'))
        
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Scan table for activities (TODO: use GSI for better performance)
        response = table.scan()
        activities = response.get('Items', [])
        
        # Sort by created_at descending
        activities.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Apply pagination
        paginated_activities = activities[offset:offset + limit]
        
        # Format activities for display
        formatted_activities = []
        for activity in paginated_activities:
            formatted_activity = {
                'activity_id': activity.get('activity_id'),
                'original_name': activity.get('original_name', ''),
                'enhanced_title': activity.get('enhanced_title', ''),
                'activity_type': activity.get('activity_type', ''),
                'distance': activity.get('distance', 0),
                'moving_time': activity.get('moving_time', 0),
                'processing_status': activity.get('processing_status', ''),
                'modules_used': activity.get('modules_used', []),
                'created_at': activity.get('created_at', ''),
                'updated_at': activity.get('updated_at', ''),
                'error_message': activity.get('error_message', '')
            }
            formatted_activities.append(formatted_activity)
        
        return {
            'activities': formatted_activities,
            'total_count': len(activities),
            'returned_count': len(formatted_activities),
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < len(activities)
        }
        
    except Exception as e:
        logger.error(f"Failed to get activity history: {str(e)}")
        return {
            'activities': [],
            'total_count': 0,
            'returned_count': 0,
            'offset': 0,
            'limit': 0,
            'has_more': False,
            'error': str(e)
        }