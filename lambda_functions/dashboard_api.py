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
from typing import Dict, Any, List, Optional
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']


def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


# Simple in-memory cache with TTL for performance optimization
_cache = {}
_cache_ttl = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache TTL

def get_cached_or_compute(cache_key: str, compute_func, *args, **kwargs):
    """Get data from cache or compute and cache it"""
    current_time = time.time()
    
    # Check if we have cached data that's still valid
    if cache_key in _cache and cache_key in _cache_ttl:
        if current_time < _cache_ttl[cache_key]:
            logger.info(f"Cache hit for {cache_key}")
            return _cache[cache_key]
    
    # Compute fresh data
    logger.info(f"Cache miss for {cache_key}, computing fresh data")
    result = compute_func(*args, **kwargs)
    
    # Cache the result
    _cache[cache_key] = result
    _cache_ttl[cache_key] = current_time + CACHE_TTL_SECONDS
    
    # Clean up old cache entries (simple cleanup)
    keys_to_remove = []
    for key, ttl in _cache_ttl.items():
        if current_time > ttl:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        _cache.pop(key, None)
        _cache_ttl.pop(key, None)
    
    return result


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
        elif '/dashboard/system' in path:
            response_data = get_system_stats()
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
    """Create standardized success response with Decimal conversion"""
    headers = CORS_HEADERS.copy()
    if rate_limit_info:
        headers = add_rate_limit_headers(headers, rate_limit_info)
    
    # Convert Decimal objects to float for JSON serialization
    data = decimal_to_float(data)
    
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps({
            **data,
            'timestamp': datetime.utcnow().isoformat()
        })
    }


def get_dashboard_stats(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Get dashboard statistics and metrics with caching"""
    try:
        # Get time range from query params (default: last 30 days)
        days = int(query_params.get('days', '30'))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Create cache keys based on parameters
        cache_key_base = f"dashboard_stats_{days}d"
        
        # Get activity processing statistics (cached)
        activity_stats = get_cached_or_compute(
            f"{cache_key_base}_activity_stats",
            get_activity_processing_stats,
            start_date
        )
        
        # Get system performance metrics (cached with shorter TTL)
        performance_metrics = get_cached_or_compute(
            f"{cache_key_base}_performance",
            get_performance_metrics
        )
        
        # Get module usage statistics (cached)
        module_stats = get_cached_or_compute(
            f"{cache_key_base}_module_stats",
            get_module_usage_stats,
            start_date
        )
        
        # Get engagement metrics (cached)
        engagement_metrics = get_cached_or_compute(
            f"{cache_key_base}_engagement",
            get_engagement_metrics,
            start_date
        )
        
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
            'last_updated': datetime.utcnow().isoformat(),
            'cache_enabled': True
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {str(e)}")
        raise


def get_activity_processing_stats(start_date: datetime) -> Dict[str, Any]:
    """Get activity processing statistics from DynamoDB using GSI for better performance"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Use GSI to query by processing status for better performance
        # Query completed activities
        completed_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'completed',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        completed_activities = completed_response.get('Items', [])
        
        # Query failed activities
        failed_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'failed',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        failed_activities = failed_response.get('Items', [])
        
        # Query processing activities
        processing_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
            ExpressionAttributeValues={
                ':status': 'processing',
                ':start_date': start_date.isoformat()
            },
            FilterExpression='created_at >= :start_date'
        )
        processing_activities = processing_response.get('Items', [])
        
        # Combine all activities for total count and type breakdown
        all_activities = completed_activities + failed_activities + processing_activities
        
        # Calculate statistics
        total_activities = len(all_activities)
        completed_count = len(completed_activities)
        failed_count = len(failed_activities)
        processing_count = len(processing_activities)
        
        success_rate = (completed_count / total_activities * 100) if total_activities > 0 else 0
        
        return {
            'total_activities': total_activities,
            'completed_activities': completed_count,
            'failed_activities': failed_count,
            'processing_activities': processing_count,
            'success_rate': round(success_rate, 1),
            'activity_types': get_activity_type_breakdown(all_activities),
            'query_method': 'gsi_optimized'
        }
        
    except Exception as e:
        logger.error(f"Failed to get activity processing stats with GSI: {str(e)}")
        # Fallback to scan method
        logger.info("Falling back to table scan method")
        
        try:
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
                'activity_types': get_activity_type_breakdown(recent_activities),
                'query_method': 'scan_fallback'
            }
            
        except Exception as fallback_error:
            logger.error(f"Fallback scan method also failed: {str(fallback_error)}")
            return {
                'total_activities': 0,
                'completed_activities': 0,
                'failed_activities': 0,
                'processing_activities': 0,
                'success_rate': 0,
                'activity_types': {},
                'query_method': 'error',
                'error': str(fallback_error)
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
    """Get engagement metrics from Strava API and DynamoDB"""
    try:
        # Import Strava client here to avoid circular imports
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src', 'utils'))
        
        from strava_client import create_strava_client_from_env
        from oauth_handler import create_oauth_handler_from_env
        
        # Get activities from DynamoDB with enhanced data
        table = dynamodb.Table(ACTIVITIES_TABLE)
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
                    continue
        
        # Initialize metrics
        total_kudos = 0
        total_comments = 0
        total_activities = len(recent_activities)
        enhanced_activities = 0
        baseline_kudos = 0
        baseline_comments = 0
        
        # Try to get fresh engagement data from Strava API
        try:
            oauth_handler = create_oauth_handler_from_env()
            strava_client = create_strava_client_from_env()
            
            # Check if we have valid OAuth tokens
            if oauth_handler.get_valid_access_token("default"):
                # Get recent activities from Strava API for fresh engagement data
                strava_response = strava_client.get_activities(
                    after=start_date,
                    per_page=min(30, total_activities)  # Limit API calls
                )
                
                if strava_response.is_success:
                    strava_activities = strava_response.data
                    
                    # Create mapping of activity IDs to engagement data
                    engagement_map = {}
                    for strava_activity in strava_activities:
                        activity_id = str(strava_activity.get('id'))
                        engagement_map[activity_id] = {
                            'kudos_count': strava_activity.get('kudos_count', 0),
                            'comment_count': strava_activity.get('comment_count', 0)
                        }
                    
                    # Calculate metrics using fresh Strava data
                    for activity in recent_activities:
                        activity_id = activity.get('activity_id')
                        if activity_id in engagement_map:
                            # Use fresh data from Strava API
                            kudos = engagement_map[activity_id]['kudos_count']
                            comments = engagement_map[activity_id]['comment_count']
                        else:
                            # Fallback to stored data
                            kudos = activity.get('kudos_count', 0)
                            comments = activity.get('comment_count', 0)
                        
                        total_kudos += kudos
                        total_comments += comments
                        
                        # Track enhanced vs baseline activities
                        if activity.get('enhanced_title') or activity.get('enhanced_description'):
                            enhanced_activities += 1
                        else:
                            baseline_kudos += kudos
                            baseline_comments += comments
                
                else:
                    logger.warning("Failed to fetch activities from Strava API, using stored data")
                    # Fallback to stored data
                    for activity in recent_activities:
                        total_kudos += activity.get('kudos_count', 0)
                        total_comments += activity.get('comment_count', 0)
                        
                        if activity.get('enhanced_title') or activity.get('enhanced_description'):
                            enhanced_activities += 1
            else:
                logger.info("No valid Strava OAuth token, using stored engagement data")
                # Use stored data from DynamoDB
                for activity in recent_activities:
                    total_kudos += activity.get('kudos_count', 0)
                    total_comments += activity.get('comment_count', 0)
                    
                    if activity.get('enhanced_title') or activity.get('enhanced_description'):
                        enhanced_activities += 1
        
        except Exception as api_error:
            logger.warning(f"Strava API error, using stored data: {str(api_error)}")
            # Fallback to stored data
            for activity in recent_activities:
                total_kudos += activity.get('kudos_count', 0)
                total_comments += activity.get('comment_count', 0)
                
                if activity.get('enhanced_title') or activity.get('enhanced_description'):
                    enhanced_activities += 1
        
        # Calculate averages and improvements
        avg_kudos_per_activity = total_kudos / total_activities if total_activities > 0 else 0
        avg_comments_per_activity = total_comments / total_activities if total_activities > 0 else 0
        
        # Calculate engagement improvement (enhanced vs baseline)
        engagement_improvement = 0
        if enhanced_activities > 0 and (total_activities - enhanced_activities) > 0:
            enhanced_kudos = total_kudos - baseline_kudos
            enhanced_comments = total_comments - baseline_comments
            
            avg_enhanced_kudos = enhanced_kudos / enhanced_activities
            avg_baseline_kudos = baseline_kudos / (total_activities - enhanced_activities)
            
            if avg_baseline_kudos > 0:
                kudos_improvement = ((avg_enhanced_kudos - avg_baseline_kudos) / avg_baseline_kudos) * 100
                engagement_improvement = max(0, kudos_improvement)  # Only show positive improvements
        
        return {
            'total_kudos': total_kudos,
            'total_comments': total_comments,
            'avg_kudos_per_activity': round(avg_kudos_per_activity, 1),
            'avg_comments_per_activity': round(avg_comments_per_activity, 1),
            'engagement_improvement': round(engagement_improvement, 1),
            'enhanced_activities': enhanced_activities,
            'total_activities': total_activities,
            'data_source': 'strava_api_and_dynamodb'
        }
        
    except Exception as e:
        logger.error(f"Failed to get engagement metrics: {str(e)}")
        return {
            'total_kudos': 0,
            'total_comments': 0,
            'avg_kudos_per_activity': 0,
            'avg_comments_per_activity': 0,
            'engagement_improvement': 0,
            'enhanced_activities': 0,
            'total_activities': 0,
            'error': str(e)
        }


def get_activity_history(query_params: Dict[str, str]) -> Dict[str, Any]:
    """Get recent activity history with processing details using GSI for better performance"""
    try:
        # Get pagination parameters
        limit = int(query_params.get('limit', '20'))
        offset = int(query_params.get('offset', '0'))
        status_filter = query_params.get('status')  # Optional status filter
        
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        all_activities = []
        
        if status_filter:
            # Use GSI to query by specific status
            try:
                response = table.query(
                    IndexName='ProcessingStatusIndex',
                    KeyConditionExpression='processing_status = :status',
                    ExpressionAttributeValues={':status': status_filter},
                    ScanIndexForward=False  # Sort by created_at descending
                )
                all_activities = response.get('Items', [])
            except Exception as gsi_error:
                logger.warning(f"GSI query failed, falling back to scan: {str(gsi_error)}")
                # Fallback to scan with filter
                response = table.scan(
                    FilterExpression='processing_status = :status',
                    ExpressionAttributeValues={':status': status_filter}
                )
                all_activities = response.get('Items', [])
        else:
            # Get all activities - try GSI approach first
            try:
                # Query each status separately and combine
                statuses = ['completed', 'failed', 'processing', 'queued']
                for status in statuses:
                    try:
                        response = table.query(
                            IndexName='ProcessingStatusIndex',
                            KeyConditionExpression='processing_status = :status',
                            ExpressionAttributeValues={':status': status},
                            ScanIndexForward=False
                        )
                        all_activities.extend(response.get('Items', []))
                    except Exception:
                        # Skip this status if query fails
                        continue
                
                # If no activities found via GSI, fallback to scan
                if not all_activities:
                    response = table.scan()
                    all_activities = response.get('Items', [])
                    
            except Exception as gsi_error:
                logger.warning(f"GSI queries failed, falling back to scan: {str(gsi_error)}")
                # Fallback to scan
                response = table.scan()
                all_activities = response.get('Items', [])
        
        # Sort by created_at descending (in case GSI didn't sort properly)
        all_activities.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Apply pagination
        paginated_activities = all_activities[offset:offset + limit]
        
        # Format activities for display
        formatted_activities = []
        for activity in paginated_activities:
            formatted_activity = {
                'activity_id': activity.get('activity_id'),
                'original_name': activity.get('original_name', ''),
                'enhanced_title': activity.get('enhanced_title', ''),
                'enhanced_description': activity.get('enhanced_description', ''),
                'activity_type': activity.get('activity_type', ''),
                'distance': activity.get('distance', 0),
                'moving_time': activity.get('moving_time', 0),
                'processing_status': activity.get('processing_status', ''),
                'modules_used': activity.get('modules_used', []),
                'created_at': activity.get('created_at', ''),
                'updated_at': activity.get('updated_at', ''),
                'error_message': activity.get('error_message', ''),
                'kudos_count': activity.get('kudos_count', 0),
                'comment_count': activity.get('comment_count', 0)
            }
            formatted_activities.append(formatted_activity)
        
        return {
            'activities': formatted_activities,
            'total_count': len(all_activities),
            'returned_count': len(formatted_activities),
            'offset': offset,
            'limit': limit,
            'has_more': offset + limit < len(all_activities),
            'status_filter': status_filter,
            'query_method': 'gsi_optimized' if status_filter else 'gsi_combined'
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
            'error': str(e),
            'query_method': 'error'
        }



def get_system_stats() -> Dict[str, Any]:
    """Get system-wide statistics (total activities, success rate, queue depth)"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Get total activities count
        total_response = table.scan(Select='COUNT')
        total_activities = total_response.get('Count', 0)
        
        # Get activities from last 24 hours for success rate
        from datetime import datetime, timedelta
        cutoff_time = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        
        recent_response = table.scan(
            FilterExpression='created_at > :cutoff',
            ExpressionAttributeValues={':cutoff': cutoff_time}
        )
        
        recent_activities = recent_response.get('Items', [])
        total_recent = len(recent_activities)
        successful_recent = sum(1 for a in recent_activities if a.get('processing_status') == 'completed')
        
        success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0
        
        # Get processing activities count
        processing_response = table.scan(
            FilterExpression='processing_status = :status',
            ExpressionAttributeValues={':status': 'processing'},
            Select='COUNT'
        )
        processing_count = processing_response.get('Count', 0)
        
        # Get SQS queue depth if available
        queue_depth = 0
        dlq_depth = 0
        
        try:
            sqs = boto3.client('sqs')
            
            # Get processing queue URL from environment
            processing_queue_url = os.environ.get('PROCESSING_QUEUE_URL')
            dlq_url = os.environ.get('DLQ_URL')
            
            if processing_queue_url:
                queue_attrs = sqs.get_queue_attributes(
                    QueueUrl=processing_queue_url,
                    AttributeNames=['ApproximateNumberOfMessages']
                )
                queue_depth = int(queue_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
            
            if dlq_url:
                dlq_attrs = sqs.get_queue_attributes(
                    QueueUrl=dlq_url,
                    AttributeNames=['ApproximateNumberOfMessages']
                )
                dlq_depth = int(dlq_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
                
        except Exception as e:
            logger.warning(f"Failed to get SQS queue depth: {e}")
        
        return {
            'total_activities': total_activities,
            'success_rate': round(success_rate, 1),
            'recent_activities_24h': total_recent,
            'successful_24h': successful_recent,
            'processing_count': processing_count,
            'queue_depth': queue_depth,
            'dlq_depth': dlq_depth,
            'timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {str(e)}")
        return {
            'total_activities': 0,
            'success_rate': 0,
            'recent_activities_24h': 0,
            'successful_24h': 0,
            'processing_count': 0,
            'queue_depth': 0,
            'dlq_depth': 0,
            'error': str(e)
        }
