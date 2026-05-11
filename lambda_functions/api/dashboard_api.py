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
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone
from shared.responses import (
    CORS_HEADERS_READ as CORS_HEADERS,
    create_success_response,
    create_error_response,
)
from shared.logger import get_logger, inject_correlation_id, metrics, MetricUnit
import time

logger = get_logger("dashboard_api")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
_cloudwatch = None


def _get_cloudwatch():
    global _cloudwatch
    if _cloudwatch is None:
        _cloudwatch = boto3.client('cloudwatch')
    return _cloudwatch

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
DEFAULT_USER_ID = os.environ.get('DEFAULT_USER_ID', '')


def _get_user_id(event: Dict[str, Any]) -> str:
    """Extract user_id from Cognito JWT claims or fall back to DEFAULT_USER_ID."""
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        # custom:strava_id is set during OAuth callback
        strava_id = claims.get('custom:strava_id', '')
        if strava_id:
            return strava_id
        # Fall back to Cognito sub if no strava_id
        sub = claims.get('sub', '')
        if sub:
            return sub
    except (AttributeError, TypeError):
        pass
    return DEFAULT_USER_ID


_current_user_id = DEFAULT_USER_ID


def _query_user_activities(since: datetime = None, projection: str = None) -> List[Dict[str, Any]]:
    """Query activities for the default user using GSI. Falls back to scan if no user_id."""
    table = dynamodb.Table(ACTIVITIES_TABLE)

    if _current_user_id:
        kwargs: Dict[str, Any] = {
            "IndexName": "UserActivitiesIndex",
            "KeyConditionExpression": "user_id = :uid",
            "ExpressionAttributeValues": {":uid": _current_user_id},
            "ScanIndexForward": False,  # newest first
        }
        if since:
            kwargs["KeyConditionExpression"] += " AND created_at >= :since"
            kwargs["ExpressionAttributeValues"][":since"] = since.isoformat()
        if projection:
            kwargs["ProjectionExpression"] = projection
        response = table.query(**kwargs)
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.query(**kwargs)
            items.extend(response.get("Items", []))
        return items

    # Fallback: scan (no user_id configured)
    response = table.scan()
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    if since:
        items = [i for i in items if i.get("created_at", "") >= since.isoformat()]
    return items


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



def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for dashboard API endpoints
    
    Handles various dashboard data requests
    """
    global _current_user_id
    _current_user_id = _get_user_id(event)
    inject_correlation_id(logger, event)
    try:
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}

        # Handle CORS preflight
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS.copy(),
                'body': json.dumps({'status': 'ok'})
            }

        # Validate request
        validation_error = validate_request(event)
        if validation_error:
            return create_error_response(400, validation_error)

        # Route requests based on path
        if '/dashboard/stats' in path:
            response_data = get_dashboard_stats(query_params)
            return create_success_response(response_data)
        elif '/dashboard/activities' in path:
            response_data = get_activity_history(query_params)
            return create_success_response(response_data)
        elif '/dashboard/system' in path:
            response_data = get_system_stats()
            return create_success_response(response_data)
        elif '/coach/summary' in path:
            response_data = get_coach_summary()
            return create_success_response(response_data)
        else:
            return create_error_response(404, 'Endpoint not found')
        
    except ClientError as e:
        logger.error(f"Dashboard API AWS error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error')
    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Dashboard API data error: {str(e)}", exc_info=True)
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

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Request validation error: {str(e)}")
        return f'Request validation failed: {str(e)}'


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
        
    except (ClientError, ValueError, TypeError) as e:
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
        
    except ClientError as e:
        logger.error(f"Failed to get activity processing stats with GSI: {str(e)}")
        # Fallback to query helper
        logger.info("Falling back to UserActivitiesIndex query")

        try:
            recent_activities = _query_user_activities(since=start_date)
            
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
            
        except ClientError as fallback_error:
            logger.error(f"Fallback scan method also failed: {str(fallback_error)}")
            return {
                'total_activities': 0,
                'completed_activities': 0,
                'failed_activities': 0,
                'processing_activities': 0,
                'success_rate': 0,
                'activity_types': {},
                'query_method': 'error',
                'error': 'Query failed'
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
                duration_response = _get_cloudwatch().get_metric_statistics(
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
                error_response = _get_cloudwatch().get_metric_statistics(
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
                
            except ClientError as e:
                logger.warning(f"Failed to get metrics for {function_name}: {str(e)}")
                function_metrics[function_name] = {
                    'avg_duration_ms': 0,
                    'error_count': 0
                }
        
        return {
            'lambda_functions': function_metrics,
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except ClientError as e:
        logger.error(f"Failed to get performance metrics: {str(e)}")
        return {
            'lambda_functions': {},
            'last_updated': datetime.utcnow().isoformat()
        }


def get_module_usage_stats(start_date: datetime) -> Dict[str, Any]:
    """Get module usage statistics"""
    try:
        recent_activities = _query_user_activities(since=start_date)

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

    except ClientError as e:
        logger.error(f"Failed to get module usage stats: {str(e)}")
        return {
            'total_activities_with_modules': 0,
            'module_usage': {},
            'most_used_module': None
        }


def get_engagement_metrics(start_date: datetime) -> Dict[str, Any]:
    """Get engagement metrics from DynamoDB stored activity data"""
    try:
        recent_activities = _query_user_activities(since=start_date)

        total_kudos = 0
        total_comments = 0
        total_activities = len(recent_activities)
        enhanced_activities = 0
        baseline_kudos = 0
        baseline_comments = 0

        for activity in recent_activities:
            kudos = activity.get('kudos_count', 0)
            comments = activity.get('comment_count', 0)
            total_kudos += kudos
            total_comments += comments

            if activity.get('enhanced_title') or activity.get('enhanced_description'):
                enhanced_activities += 1
            else:
                baseline_kudos += kudos
                baseline_comments += comments

        avg_kudos_per_activity = total_kudos / total_activities if total_activities > 0 else 0
        avg_comments_per_activity = total_comments / total_activities if total_activities > 0 else 0

        # Calculate engagement improvement (enhanced vs baseline)
        engagement_improvement = 0
        if enhanced_activities > 0 and (total_activities - enhanced_activities) > 0:
            enhanced_kudos = total_kudos - baseline_kudos
            avg_enhanced_kudos = enhanced_kudos / enhanced_activities
            avg_baseline_kudos = baseline_kudos / (total_activities - enhanced_activities)

            if avg_baseline_kudos > 0:
                kudos_improvement = ((avg_enhanced_kudos - avg_baseline_kudos) / avg_baseline_kudos) * 100
                engagement_improvement = max(0, kudos_improvement)

        return {
            'total_kudos': total_kudos,
            'total_comments': total_comments,
            'avg_kudos_per_activity': round(avg_kudos_per_activity, 1),
            'avg_comments_per_activity': round(avg_comments_per_activity, 1),
            'engagement_improvement': round(engagement_improvement, 1),
            'enhanced_activities': enhanced_activities,
            'total_activities': total_activities,
            'data_source': 'dynamodb'
        }

    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get engagement metrics: {str(e)}")
        return {
            'total_kudos': 0,
            'total_comments': 0,
            'avg_kudos_per_activity': 0,
            'avg_comments_per_activity': 0,
            'engagement_improvement': 0,
            'enhanced_activities': 0,
            'total_activities': 0,
            'error': 'Failed to load engagement metrics'
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
                logger.warning(f"GSI query failed, falling back to query: {str(gsi_error)}")
                all_activities = _query_user_activities()
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
                
                # If no activities found via GSI, fallback to query helper
                if not all_activities:
                    all_activities = _query_user_activities()
                    
            except Exception as gsi_error:
                logger.warning(f"GSI queries failed, falling back to query: {str(gsi_error)}")
                all_activities = _query_user_activities()
        
        # Sort by created_at descending (in case GSI didn't sort properly)
        all_activities.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Apply pagination
        paginated_activities = all_activities[offset:offset + limit]
        
        # Format activities for display
        formatted_activities = []
        for activity in paginated_activities:
            gen_metadata = activity.get('generation_metadata') or {}
            confidence = gen_metadata.get('confidence', 0)
            if hasattr(confidence, '__float__'):
                confidence = float(confidence)

            similarity = activity.get('similarity_score', '')
            if similarity and hasattr(similarity, '__float__'):
                similarity = float(similarity)
            elif similarity:
                try:
                    similarity = float(similarity)
                except (ValueError, TypeError):
                    similarity = 0

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
                'comment_count': activity.get('comment_count', 0),
                'confidence': confidence,
                'description_modified': activity.get('description_modified', None),
                'similarity_score': similarity,
                'feedback_analyzed': activity.get('feedback_analyzed', False),
                'generated_at': gen_metadata.get('generated_at', ''),
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
        
    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get activity history: {str(e)}")
        return {
            'activities': [],
            'total_count': 0,
            'returned_count': 0,
            'offset': 0,
            'limit': 0,
            'has_more': False,
            'error': 'Failed to load activities',
            'query_method': 'error'
        }



def get_system_stats() -> Dict[str, Any]:
    """Get system-wide statistics (total activities, success rate, queue depth)"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)

        # Get total activities count via query (or scan count as fallback)
        if DEFAULT_USER_ID:
            total_response = table.query(
                IndexName="UserActivitiesIndex",
                KeyConditionExpression="user_id = :uid",
                ExpressionAttributeValues={":uid": DEFAULT_USER_ID},
                Select='COUNT'
            )
            total_activities = total_response.get('Count', 0)
        else:
            total_response = table.scan(Select='COUNT')
            total_activities = total_response.get('Count', 0)

        # Get activities from last 24 hours for success rate
        cutoff_time = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).isoformat()
        recent_activities = _query_user_activities(since=datetime.now(tz=timezone.utc) - timedelta(hours=24))

        total_recent = len(recent_activities)
        successful_recent = sum(1 for a in recent_activities if a.get('processing_status') == 'completed')

        success_rate = (successful_recent / total_recent * 100) if total_recent > 0 else 0

        # Get processing activities count via ProcessingStatusIndex
        processing_response = table.query(
            IndexName='ProcessingStatusIndex',
            KeyConditionExpression='processing_status = :status',
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
                
        except ClientError as e:
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
        
    except (ClientError, ValueError) as e:
        logger.error(f"Failed to get system stats: {str(e)}")
        return {
            'total_activities': 0,
            'success_rate': 0,
            'recent_activities_24h': 0,
            'successful_24h': 0,
            'processing_count': 0,
            'queue_depth': 0,
            'dlq_depth': 0,
            'error': 'Failed to load system stats'
        }


def get_coach_summary() -> Dict[str, Any]:
    """Get coach summary: recent feedback, training trends, and athlete profile."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        config_table = dynamodb.Table(USER_CONFIG_TABLE)

        # Get athlete profile from user preferences
        athlete_profile = ''
        try:
            user_id = os.environ.get('DEFAULT_USER_ID', '')
            if user_id:
                config_response = config_table.get_item(Key={'user_id': user_id})
                prefs = config_response.get('Item', {}).get('user_preferences', {})
                athlete_profile = prefs.get('athlete_profile', '')
        except ClientError:
            pass

        # Get recent activities (last 30 days) sorted by date
        now = datetime.now(tz=timezone.utc)
        start_date = now - timedelta(days=30)

        recent = _query_user_activities(since=start_date)
        recent.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Recent feedback: last 5 activities with coach_feedback
        recent_feedback = []
        for a in recent:
            fb = a.get('coach_feedback')
            if fb:
                if isinstance(fb, str):
                    try:
                        fb = json.loads(fb)
                    except (json.JSONDecodeError, TypeError):
                        fb = None
                if fb:
                    recent_feedback.append({
                        'activity_id': a.get('activity_id', ''),
                        'date': a.get('created_at', '')[:10],
                        'title': a.get('enhanced_title') or a.get('original_name', 'Activité'),
                        'coach_feedback': fb,
                    })
            if len(recent_feedback) >= 5:
                break

        # Compute weekly trends (last 4 weeks)
        weekly_volume = [0.0] * 4
        sessions_per_week = [0] * 4
        weekly_moving_time = [0.0] * 4
        weekly_distance_for_pace = [0.0] * 4

        for a in recent:
            created_at = a.get('created_at', '')
            if not created_at:
                continue
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days_ago = (now - dt).days
                week_idx = days_ago // 7
                if week_idx >= 4:
                    continue
                distance_m = float(a.get('distance', 0) or 0)
                moving_time_s = float(a.get('moving_time', 0) or 0)
                weekly_volume[week_idx] += distance_m / 1000
                sessions_per_week[week_idx] += 1
                if distance_m > 0 and moving_time_s > 0:
                    weekly_moving_time[week_idx] += moving_time_s
                    weekly_distance_for_pace[week_idx] += distance_m
            except (ValueError, TypeError):
                continue

        # Compute avg pace per week (min/km)
        avg_pace_per_week = []
        for i in range(4):
            if weekly_distance_for_pace[i] > 0:
                pace_s_per_km = weekly_moving_time[i] / (weekly_distance_for_pace[i] / 1000)
                mins = int(pace_s_per_km // 60)
                secs = int(pace_s_per_km % 60)
                avg_pace_per_week.append(f"{mins}:{secs:02d}")
            else:
                avg_pace_per_week.append("-")

        # Reverse so oldest week is first (chronological order)
        weekly_volume.reverse()
        sessions_per_week.reverse()
        avg_pace_per_week.reverse()

        # Compute ramp rate (week-over-week volume change percentage)
        ramp_rate = None
        if len(weekly_volume) >= 2:
            prev_week = weekly_volume[-2]  # second to last (previous week)
            curr_week = weekly_volume[-1]  # last (current week)
            if prev_week > 0:
                ramp_rate = round((curr_week - prev_week) / prev_week * 100, 1)

        # Compute detailed pace metrics from laps
        interval_paces = []  # [{date, pace_sec, hr}] - work intervals only
        ef_paces = []  # [{date, pace_sec, hr}] - easy runs only

        for a in recent:
            created = a.get('created_at', '')[:10]
            laps_raw = a.get('laps_json')
            if not laps_raw:
                continue
            try:
                laps = json.loads(laps_raw) if isinstance(laps_raw, str) else laps_raw
            except (json.JSONDecodeError, TypeError):
                continue

            if not laps or len(laps) < 2:
                continue

            # Classify laps: compute median pace, fast laps = work intervals
            speeds = [float(l.get('average_speed', 0)) for l in laps if float(l.get('average_speed', 0)) > 0]
            if not speeds:
                continue
            median_speed = sorted(speeds)[len(speeds) // 2]

            fast_laps = [l for l in laps if float(l.get('average_speed', 0)) > median_speed * 1.15 and float(l.get('distance', 0)) > 200]
            slow_laps = [l for l in laps if float(l.get('average_speed', 0)) <= median_speed * 1.05 and float(l.get('distance', 0)) > 500]

            # If has fast laps (>15% faster than median) = interval session
            if len(fast_laps) >= 2:
                for fl in fast_laps:
                    sp = float(fl.get('average_speed', 0))
                    if sp > 0:
                        interval_paces.append({
                            'date': created,
                            'pace_sec': round(1000 / sp),
                            'hr': fl.get('average_heartrate'),
                        })
            # If mostly slow laps and low pace variance = EF session
            elif len(slow_laps) >= len(laps) * 0.7:
                total_dist = sum(float(l.get('distance', 0)) for l in laps)
                total_time = sum(float(l.get('moving_time', 0)) for l in laps)
                avg_hr = float(a.get('average_heartrate', 0) or 0)
                if total_dist > 0 and total_time > 0:
                    ef_paces.append({
                        'date': created,
                        'pace_sec': round(total_time / (total_dist / 1000)),
                        'hr': round(avg_hr) if avg_hr else None,
                    })

        # Format for frontend
        def _fmt_pace(sec):
            return f"{int(sec // 60)}:{int(sec % 60):02d}"

        interval_trend = [{'date': p['date'], 'pace': _fmt_pace(p['pace_sec']), 'pace_sec': p['pace_sec'], 'hr': p.get('hr')} for p in sorted(interval_paces, key=lambda x: x['date'])]
        ef_trend = [{'date': p['date'], 'pace': _fmt_pace(p['pace_sec']), 'pace_sec': p['pace_sec'], 'hr': p.get('hr')} for p in sorted(ef_paces, key=lambda x: x['date'])]

        # Compliance scoring: compare activities done vs Campus Coach plan
        compliance = None
        try:
            sessions_table = dynamodb.Table(COACHING_SESSIONS_TABLE)
            sessions_resp = sessions_table.scan(Limit=10)
            sessions = sessions_resp.get('Items', [])
            if sessions:
                sessions.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
                current_week = sessions[0].get('week_number', '')
                week_sessions = [s for s in sessions if s.get('week_number') == current_week]
                total_planned = len(week_sessions)
                # Count running sessions in current week from activities
                completed_this_week = sessions_per_week[-1] if sessions_per_week else 0
                if total_planned > 0:
                    compliance = {
                        'planned': total_planned,
                        'completed': min(completed_this_week, total_planned),
                        'percentage': min(round(completed_this_week / total_planned * 100), 100)
                    }
        except Exception as e:
            logger.warning(f'Failed to compute compliance: {e}')

        return {
            'athlete_profile': athlete_profile,
            'recent_feedback': recent_feedback,
            'trends': {
                'weekly_volume_km': [round(v, 1) for v in weekly_volume],
                'sessions_per_week': sessions_per_week,
                'avg_pace_per_week': avg_pace_per_week,
                'interval_paces': interval_trend[-20:],
                'ef_paces': ef_trend[-20:],
                'ramp_rate': ramp_rate,
                'compliance': compliance,
            }
        }

    except (ClientError, ValueError, TypeError) as e:
        logger.error(f"Failed to get coach summary: {str(e)}")
        return {
            'athlete_profile': '',
            'recent_feedback': [],
            'trends': {
                'weekly_volume_km': [0, 0, 0, 0],
                'sessions_per_week': [0, 0, 0, 0],
                'avg_pace_per_week': ['-', '-', '-', '-'],
            }
        }
