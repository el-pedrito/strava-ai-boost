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
from datetime import datetime, timedelta
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')
sqs = boto3.client('sqs')
cloudwatch = boto3.client('cloudwatch')

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
        queue_status = {}
        
        # Get processing queue status
        processing_queue_url = os.environ.get('PROCESSING_QUEUE_URL')
        if processing_queue_url:
            try:
                processing_attrs = sqs.get_queue_attributes(
                    QueueUrl=processing_queue_url,
                    AttributeNames=[
                        'ApproximateNumberOfMessages',
                        'ApproximateNumberOfMessagesNotVisible',
                        'ApproximateNumberOfMessagesDelayed'
                    ]
                )
                
                queue_status['processing_queue'] = {
                    'approximate_messages': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessages', 0)),
                    'approximate_messages_not_visible': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0)),
                    'approximate_messages_delayed': int(processing_attrs['Attributes'].get('ApproximateNumberOfMessagesDelayed', 0)),
                    'status': 'healthy',
                    'queue_url': processing_queue_url
                }
                
                # Determine queue health
                total_messages = queue_status['processing_queue']['approximate_messages']
                if total_messages > 50:
                    queue_status['processing_queue']['status'] = 'backlogged'
                elif total_messages > 100:
                    queue_status['processing_queue']['status'] = 'critical'
                    
            except Exception as e:
                logger.error(f"Failed to get processing queue status: {str(e)}")
                queue_status['processing_queue'] = {
                    'status': 'error',
                    'error': str(e)
                }
        else:
            queue_status['processing_queue'] = {
                'status': 'not_configured',
                'note': 'PROCESSING_QUEUE_URL not set'
            }
        
        # Get dead letter queue status
        dlq_url = os.environ.get('DLQ_URL')
        if dlq_url:
            try:
                dlq_attrs = sqs.get_queue_attributes(
                    QueueUrl=dlq_url,
                    AttributeNames=[
                        'ApproximateNumberOfMessages',
                        'ApproximateNumberOfMessagesNotVisible'
                    ]
                )
                
                dlq_messages = int(dlq_attrs['Attributes'].get('ApproximateNumberOfMessages', 0))
                
                queue_status['dead_letter_queue'] = {
                    'approximate_messages': dlq_messages,
                    'approximate_messages_not_visible': int(dlq_attrs['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0)),
                    'status': 'healthy' if dlq_messages < 10 else 'attention_needed',
                    'queue_url': dlq_url
                }
                
                if dlq_messages > 20:
                    queue_status['dead_letter_queue']['status'] = 'critical'
                    
            except Exception as e:
                logger.error(f"Failed to get DLQ status: {str(e)}")
                queue_status['dead_letter_queue'] = {
                    'status': 'error',
                    'error': str(e)
                }
        else:
            queue_status['dead_letter_queue'] = {
                'status': 'not_configured',
                'note': 'DLQ_URL not set'
            }
        
        # Add overall queue health assessment
        processing_healthy = queue_status.get('processing_queue', {}).get('status') in ['healthy', 'backlogged']
        dlq_healthy = queue_status.get('dead_letter_queue', {}).get('status') in ['healthy', 'not_configured']
        
        queue_status['overall_status'] = 'healthy' if processing_healthy and dlq_healthy else 'degraded'
        
        return queue_status
        
    except Exception as e:
        logger.error(f"Failed to get queue status: {str(e)}")
        return {
            'processing_queue': {'status': 'error'},
            'dead_letter_queue': {'status': 'error'},
            'overall_status': 'error',
            'error': str(e)
        }


def get_system_health() -> Dict[str, Any]:
    """Get system health indicators with comprehensive monitoring"""
    try:
        health_checks = {}
        
        # Check DynamoDB table accessibility
        health_checks['dynamodb_accessible'] = check_dynamodb_health()
        
        # Check recent error rates
        health_checks['recent_error_rate'] = calculate_recent_error_rate()
        
        # Check Step Functions health
        health_checks['step_functions_healthy'] = check_step_functions_health()
        
        # Check SQS queues health
        queue_status = get_queue_status()
        health_checks['sqs_healthy'] = queue_status.get('overall_status') == 'healthy'
        
        # Check Lambda functions health via CloudWatch metrics
        health_checks['lambda_functions_healthy'] = check_lambda_functions_health()
        
        # Check Secrets Manager accessibility
        health_checks['secrets_manager_healthy'] = check_secrets_manager_health()
        
        # Calculate overall health score
        healthy_components = sum(1 for check in health_checks.values() if isinstance(check, bool) and check)
        total_components = sum(1 for check in health_checks.values() if isinstance(check, bool))
        
        if total_components == 0:
            health_score = 0
        else:
            health_score = (healthy_components / total_components) * 100
        
        # Determine overall health status
        if health_score >= 90:
            overall_health = 'healthy'
        elif health_score >= 70:
            overall_health = 'degraded'
        else:
            overall_health = 'unhealthy'
        
        # Get specific component issues
        issues = []
        if not health_checks.get('dynamodb_accessible', True):
            issues.append('DynamoDB connectivity issues')
        if health_checks.get('recent_error_rate', 0) > 10:
            issues.append(f"High error rate: {health_checks['recent_error_rate']}%")
        if not health_checks.get('step_functions_healthy', True):
            issues.append('Step Functions execution issues')
        if not health_checks.get('sqs_healthy', True):
            issues.append('SQS queue issues')
        if not health_checks.get('lambda_functions_healthy', True):
            issues.append('Lambda function errors')
        if not health_checks.get('secrets_manager_healthy', True):
            issues.append('Secrets Manager access issues')
        
        return {
            'overall_health': overall_health,
            'health_score': round(health_score, 1),
            'component_health': health_checks,
            'issues': issues,
            'last_check': datetime.utcnow().isoformat(),
            'monitoring_enabled': True
        }
        
    except Exception as e:
        logger.error(f"Failed to get system health: {str(e)}")
        return {
            'overall_health': 'unknown',
            'health_score': 0,
            'component_health': {},
            'issues': [f'Health check failed: {str(e)}'],
            'error': str(e),
            'last_check': datetime.utcnow().isoformat()
        }


def check_step_functions_health() -> bool:
    """Check Step Functions health by looking at recent execution metrics"""
    try:
        step_functions_arn = os.environ.get('STEP_FUNCTIONS_ARN')
        if not step_functions_arn:
            return True  # Assume healthy if not configured
        
        # Check recent executions (last hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        response = stepfunctions.list_executions(
            stateMachineArn=step_functions_arn,
            maxResults=20
        )
        
        recent_executions = [
            exec for exec in response.get('executions', [])
            if exec['startDate'] >= one_hour_ago
        ]
        
        if not recent_executions:
            return True  # No recent executions, assume healthy
        
        # Calculate success rate
        failed_executions = [
            exec for exec in recent_executions
            if exec['status'] in ['FAILED', 'TIMED_OUT', 'ABORTED']
        ]
        
        failure_rate = len(failed_executions) / len(recent_executions) * 100
        return failure_rate < 20  # Healthy if less than 20% failure rate
        
    except Exception as e:
        logger.warning(f"Step Functions health check failed: {str(e)}")
        return False


def check_lambda_functions_health() -> bool:
    """Check Lambda functions health via CloudWatch metrics"""
    try:
        # Check error rates for key Lambda functions in the last hour
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        lambda_functions = [
            'StravaAIBoost-WebhookHandler',
            'StravaAIBoost-ActivityProcessor',
            'StravaAIBoost-ContentGenerator'
        ]
        
        total_errors = 0
        total_invocations = 0
        
        for function_name in lambda_functions:
            try:
                # Get error count
                error_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                # Get invocation count
                invocation_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                if error_response['Datapoints']:
                    total_errors += error_response['Datapoints'][0]['Sum']
                
                if invocation_response['Datapoints']:
                    total_invocations += invocation_response['Datapoints'][0]['Sum']
                    
            except Exception as e:
                logger.warning(f"Failed to get metrics for {function_name}: {str(e)}")
                continue
        
        if total_invocations == 0:
            return True  # No invocations, assume healthy
        
        error_rate = (total_errors / total_invocations) * 100
        return error_rate < 10  # Healthy if less than 10% error rate
        
    except Exception as e:
        logger.warning(f"Lambda health check failed: {str(e)}")
        return False


def check_secrets_manager_health() -> bool:
    """Check Secrets Manager accessibility"""
    try:
        # Try to list secrets to verify access
        secrets_client = boto3.client('secretsmanager')
        secrets_client.list_secrets(MaxResults=1)
        return True
    except Exception as e:
        logger.warning(f"Secrets Manager health check failed: {str(e)}")
        return False


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
        # Get Step Functions ARN from environment
        step_functions_arn = os.environ.get('STEP_FUNCTIONS_ARN')
        if not step_functions_arn:
            logger.warning("STEP_FUNCTIONS_ARN environment variable not set")
            return {
                'status': 'unknown',
                'current_step': 'unknown',
                'note': 'Step Functions ARN not configured'
            }
        
        # List recent executions for the state machine
        # We'll look for executions with the activity_id in the input
        try:
            response = stepfunctions.list_executions(
                stateMachineArn=step_functions_arn,
                statusFilter='RUNNING',
                maxResults=50
            )
            
            # Look for execution with matching activity_id
            matching_execution = None
            for execution in response.get('executions', []):
                execution_arn = execution['executionArn']
                
                # Get execution details to check input
                try:
                    execution_details = stepfunctions.describe_execution(
                        executionArn=execution_arn
                    )
                    
                    # Parse input to check for activity_id
                    input_data = json.loads(execution_details.get('input', '{}'))
                    if input_data.get('activity_id') == activity_id:
                        matching_execution = execution_details
                        break
                        
                except Exception as e:
                    logger.warning(f"Failed to get execution details for {execution_arn}: {str(e)}")
                    continue
            
            if matching_execution:
                # Get execution history to determine current step
                history_response = stepfunctions.get_execution_history(
                    executionArn=matching_execution['executionArn'],
                    reverseOrder=True,
                    maxResults=10
                )
                
                current_step = 'unknown'
                for event in history_response.get('events', []):
                    if event['type'] == 'TaskStateEntered':
                        current_step = event.get('stateEnteredEventDetails', {}).get('name', 'unknown')
                        break
                    elif event['type'] == 'LambdaFunctionScheduled':
                        # Extract step name from Lambda function name or resource
                        resource = event.get('lambdaFunctionScheduledEventDetails', {}).get('resource', '')
                        if 'ActivityFetcher' in resource:
                            current_step = 'Fetching Activity Data'
                        elif 'ContentGenerator' in resource:
                            current_step = 'Generating Content'
                        elif 'StravaUpdater' in resource:
                            current_step = 'Updating Strava'
                        elif 'CampusCoachInvoker' in resource:
                            current_step = 'Campus Coach Analysis'
                        break
                
                return {
                    'status': matching_execution['status'].lower(),
                    'current_step': current_step,
                    'execution_arn': matching_execution['executionArn'],
                    'start_date': matching_execution['startDate'].isoformat(),
                    'state_machine_arn': step_functions_arn
                }
            else:
                # Check for completed/failed executions in the last hour
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                
                for status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                    response = stepfunctions.list_executions(
                        stateMachineArn=step_functions_arn,
                        statusFilter=status,
                        maxResults=20
                    )
                    
                    for execution in response.get('executions', []):
                        # Only check recent executions
                        if execution['startDate'] < one_hour_ago:
                            continue
                            
                        execution_arn = execution['executionArn']
                        try:
                            execution_details = stepfunctions.describe_execution(
                                executionArn=execution_arn
                            )
                            
                            input_data = json.loads(execution_details.get('input', '{}'))
                            if input_data.get('activity_id') == activity_id:
                                return {
                                    'status': execution_details['status'].lower(),
                                    'current_step': 'completed' if status == 'SUCCEEDED' else 'failed',
                                    'execution_arn': execution_arn,
                                    'start_date': execution_details['startDate'].isoformat(),
                                    'end_date': execution_details.get('stopDate', '').isoformat() if execution_details.get('stopDate') else None,
                                    'state_machine_arn': step_functions_arn
                                }
                        except Exception as e:
                            logger.warning(f"Failed to get execution details for {execution_arn}: {str(e)}")
                            continue
                
                return {
                    'status': 'not_found',
                    'current_step': 'not_started',
                    'note': f'No Step Functions execution found for activity {activity_id}'
                }
        
        except Exception as sf_error:
            logger.error(f"Step Functions API error: {str(sf_error)}")
            return {
                'status': 'error',
                'current_step': 'unknown',
                'error': str(sf_error)
            }
        
    except Exception as e:
        logger.error(f"Failed to get Step Functions status: {str(e)}")
        return {
            'status': 'error',
            'current_step': 'unknown',
            'error': str(e)
        }


def get_retry_information(activity_id: str) -> Dict[str, Any]:
    """Get retry information for failed activities"""
    try:
        # Check SQS dead letter queue for retry information
        dlq_url = os.environ.get('DLQ_URL')
        if not dlq_url:
            logger.warning("DLQ_URL environment variable not set")
            return {
                'retry_count': 0,
                'max_retries': 3,
                'next_retry': None,
                'note': 'DLQ URL not configured'
            }
        
        try:
            # Get messages from DLQ to check for this activity
            response = sqs.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All'],
                AttributeNames=['All'],
                WaitTimeSeconds=1  # Short poll
            )
            
            messages = response.get('Messages', [])
            activity_messages = []
            
            for message in messages:
                try:
                    # Parse message body to check for activity_id
                    body = json.loads(message['Body'])
                    if body.get('activity_id') == activity_id:
                        activity_messages.append(message)
                except json.JSONDecodeError:
                    continue
            
            if activity_messages:
                # Get the most recent message for this activity
                latest_message = max(activity_messages, 
                                   key=lambda m: m.get('Attributes', {}).get('SentTimestamp', '0'))
                
                # Extract retry information from message attributes
                attributes = latest_message.get('Attributes', {})
                message_attributes = latest_message.get('MessageAttributes', {})
                
                retry_count = int(attributes.get('ApproximateReceiveCount', '1'))
                sent_timestamp = int(attributes.get('SentTimestamp', '0')) / 1000  # Convert to seconds
                sent_time = datetime.fromtimestamp(sent_timestamp) if sent_timestamp > 0 else None
                
                # Calculate next retry time (exponential backoff)
                if retry_count < 3:  # Max retries
                    backoff_seconds = min(300, 30 * (2 ** retry_count))  # Max 5 minutes
                    next_retry = sent_time + timedelta(seconds=backoff_seconds) if sent_time else None
                else:
                    next_retry = None
                
                return {
                    'retry_count': retry_count - 1,  # Subtract 1 because first receive isn't a retry
                    'max_retries': 3,
                    'next_retry': next_retry.isoformat() if next_retry else None,
                    'last_failure': sent_time.isoformat() if sent_time else None,
                    'dlq_message_id': latest_message.get('MessageId'),
                    'failure_reason': message_attributes.get('FailureReason', {}).get('StringValue', 'Unknown')
                }
            else:
                # Check processing queue for retry information
                processing_queue_url = os.environ.get('PROCESSING_QUEUE_URL')
                if processing_queue_url:
                    try:
                        # Check if activity is currently in processing queue
                        queue_response = sqs.receive_message(
                            QueueUrl=processing_queue_url,
                            MaxNumberOfMessages=10,
                            MessageAttributeNames=['All'],
                            WaitTimeSeconds=1
                        )
                        
                        queue_messages = queue_response.get('Messages', [])
                        for message in queue_messages:
                            try:
                                body = json.loads(message['Body'])
                                if body.get('activity_id') == activity_id:
                                    attributes = message.get('Attributes', {})
                                    retry_count = int(attributes.get('ApproximateReceiveCount', '1'))
                                    
                                    return {
                                        'retry_count': retry_count - 1,
                                        'max_retries': 3,
                                        'next_retry': None,
                                        'status': 'queued_for_retry',
                                        'queue_message_id': message.get('MessageId')
                                    }
                            except json.JSONDecodeError:
                                continue
                    except Exception as queue_error:
                        logger.warning(f"Failed to check processing queue: {str(queue_error)}")
                
                return {
                    'retry_count': 0,
                    'max_retries': 3,
                    'next_retry': None,
                    'note': f'No retry information found for activity {activity_id}'
                }
        
        except Exception as sqs_error:
            logger.error(f"SQS error while checking retry information: {str(sqs_error)}")
            return {
                'retry_count': 0,
                'max_retries': 3,
                'next_retry': None,
                'error': str(sqs_error)
            }
        
    except Exception as e:
        logger.error(f"Failed to get retry information: {str(e)}")
        return {
            'retry_count': 0,
            'max_retries': 0,
            'error': str(e)
        }