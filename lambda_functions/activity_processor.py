"""
Activity Processor Lambda Function

Processes activities from SQS queue and triggers Step Functions workflow.
Handles rate limiting and error recovery.
"""

import json
import os
import logging
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, UTC
import time
import random

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
stepfunctions = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
RATE_LIMITS_TABLE = os.environ['RATE_LIMITS_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
STEP_FUNCTIONS_ARN = os.environ['STEP_FUNCTIONS_ARN']

# Get SQS queue URL from environment or construct it
PROCESSING_QUEUE_URL = os.environ.get('PROCESSING_QUEUE_URL', 
    f"https://sqs.{os.environ.get('AWS_REGION', 'eu-west-1')}.amazonaws.com/{os.environ.get('AWS_ACCOUNT_ID', '')}/strava-ai-boost-activity-processing")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for SQS-triggered activity processing
    
    Receives activity notifications from SQS and starts Step Functions workflow.
    Uses batch item failures to prevent deleting messages when Step Functions fails.
    """
    batch_item_failures = []
    
    try:
        # Process SQS records
        for record in event.get('Records', []):
            try:
                process_activity_record(record)
            except Exception as e:
                # Add failed record to batch item failures
                # This prevents SQS from deleting the message, allowing retry
                logger.error(f"Failed to process record {record.get('messageId')}: {str(e)}")
                batch_item_failures.append({
                    "itemIdentifier": record['messageId']
                })
        
        # Return batch item failures to SQS
        # Messages with failures will be retried, successful ones will be deleted
        return {
            'batchItemFailures': batch_item_failures
        }
        
    except Exception as e:
        logger.error(f"Activity processor critical error: {str(e)}")
        # Return all messages as failures to prevent deletion
        return {
            'batchItemFailures': [
                {"itemIdentifier": record['messageId']} 
                for record in event.get('Records', [])
            ]
        }


def process_activity_record(record: Dict[str, Any]) -> None:
    """
    Process a single activity record from SQS
    
    Raises exception on failure to signal batch item failure to SQS
    """
    activity_id = None
    
    try:
        # Parse SQS message
        message_body = json.loads(record['body'])
        activity_id = message_body['activity_id']
        user_id = message_body['user_id']
        
        logger.info(f"Processing activity {activity_id} for user {user_id}")
        
        # Check if activity is already processed or being processed (prevent webhook update loops)
        if should_skip_processing(activity_id, message_body):
            logger.info(f"Skipping activity {activity_id} - already processed or processing")
            return  # Exit successfully so SQS deletes the message
        
        # Fetch user configuration to check module settings
        user_config = fetch_user_configuration(user_id)
        
        # Check if Enduraw module is enabled and we haven't waited yet
        enduraw_config = user_config.get('modules_config', {}).get('enduraw', {})
        enduraw_enabled = enduraw_config.get('enabled', False)
        enduraw_waited = message_body.get('enduraw_waited', False)
        
        # Debug logs
        logger.info(f"Enduraw check - config: {enduraw_config}, enabled: {enduraw_enabled}, waited: {enduraw_waited}")
        
        if enduraw_enabled and not enduraw_waited:
            logger.info(f"Enduraw module enabled for activity {activity_id}, delaying by 2 minutes for Enduraw processing")
            
            # Update activity status to indicate Enduraw wait
            update_activity_status(activity_id, 'waiting_enduraw', 'Waiting 2 minutes for Enduraw Report processing', critical=False)
            
            # Mark that we've initiated Enduraw wait
            message_body['enduraw_waited'] = True
            message_body['enduraw_delay_started_at'] = datetime.now(UTC).isoformat()
            
            # Send back to SQS with 2-minute delay
            sqs.send_message(
                QueueUrl=PROCESSING_QUEUE_URL,
                MessageBody=json.dumps(message_body),
                DelaySeconds=120  # 2 minutes for Enduraw processing
            )
            
            logger.info(f"Activity {activity_id} requeued with 2-minute delay for Enduraw processing")
            # Exit successfully so original message is deleted
            return
        
        # Log if Enduraw wait was completed
        if enduraw_enabled and enduraw_waited:
            enduraw_delay_started = message_body.get('enduraw_delay_started_at', 'unknown')
            logger.info(f"Enduraw wait completed for activity {activity_id} (started at {enduraw_delay_started})")
        
        # Check rate limits BEFORE processing
        if not check_rate_limits():
            logger.warning(f"Rate limits exceeded for activity {activity_id}, delaying processing")
            # Update activity status to indicate rate limit delay
            update_activity_status(activity_id, 'rate_limited', 'Waiting for rate limits to reset', critical=False)
            
            # Use SQS delay to retry later instead of throwing exception
            delay_message_processing(record, activity_id, user_id, message_body)
            return  # Exit successfully so SQS deletes the original message
        
        # Update activity status to processing
        update_activity_status(activity_id, 'processing', critical=True)
        
        # Start Step Functions workflow with Enduraw metadata
        execution_arn = start_step_functions_workflow(activity_id, user_id, message_body, enduraw_enabled and enduraw_waited)
        
        if execution_arn:
            logger.info(f"Started Step Functions workflow for activity {activity_id}: {execution_arn}")
            # IMPORTANT: We return success here, but Step Functions might still fail
            # To handle Step Functions failures, we need to:
            # 1. Monitor Step Functions execution status (via CloudWatch Events)
            # 2. Or wait for execution to complete before returning (not recommended - too slow)
            # 3. Or use a separate error handler Lambda triggered by Step Functions failures
            
            # For now, we trust Step Functions to handle its own retries and error handling
            # The DLQ will only capture Lambda processing failures, not Step Functions failures
        else:
            logger.error(f"Failed to start Step Functions workflow for activity {activity_id}")
            update_activity_status(activity_id, 'failed', 'Failed to start workflow', critical=False)
            # Raise exception to trigger SQS retry via batch item failure
            raise Exception("Failed to start Step Functions workflow")
        
    except Exception as e:
        logger.error(f"Failed to process activity record: {str(e)}")
        # Update status to failed if we have activity_id
        if activity_id:
            update_activity_status(activity_id, 'failed', str(e), critical=False)
        # Re-raise to trigger batch item failure (message will be retried)
        raise


def check_rate_limits() -> bool:
    """Check if we're within Strava API rate limits"""
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Check short-term limit (100/15min)
        response = table.get_item(Key={'limit_type': 'short_term'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            if usage >= 90:  # Leave some buffer
                return False
        
        # Check daily limit (1000/day)
        response = table.get_item(Key={'limit_type': 'daily'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            if usage >= 950:  # Leave some buffer
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Rate limit check error: {str(e)}")
        # Assume we're at limit if we can't check
        return False


def should_skip_processing(activity_id: str, message_body: Dict[str, Any]) -> bool:
    """
    Check if activity should be skipped to prevent webhook update loops
    
    Returns True if:
    - Activity is already completed
    - Activity is currently processing 
    - Activity failed recently (within 1 hour) to avoid rapid retries
    - Webhook is an 'update' event and activity was already processed
    """
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Check if activity exists in DynamoDB
        response = table.get_item(Key={'activity_id': activity_id})
        
        if 'Item' not in response:
            # New activity, should process
            logger.info(f"New activity {activity_id}, proceeding with processing")
            return False
        
        activity = response['Item']
        processing_status = activity.get('processing_status', 'unknown')
        webhook_data = message_body.get('webhook_data', {})
        aspect_type = webhook_data.get('aspect_type', 'unknown')
        
        # Skip if already completed
        if processing_status == 'completed':
            logger.info(f"Activity {activity_id} already completed, skipping")
            return True
        
        # Skip if currently processing (avoid concurrent processing)
        if processing_status == 'processing':
            logger.info(f"Activity {activity_id} currently processing, skipping")
            return True
        
        # For update webhooks, be more restrictive
        if aspect_type == 'update':
            # Skip if we've ever processed this activity successfully
            if processing_status in ['completed', 'processing']:
                logger.info(f"Activity {activity_id} update webhook but already processed, skipping")
                return True
            
            # Skip if failed recently (within 1 hour) to avoid rapid retries from updates
            updated_at = activity.get('updated_at')
            if processing_status == 'failed' and updated_at:
                try:
                    from datetime import datetime, timedelta
                    last_update = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    if datetime.utcnow().replace(tzinfo=last_update.tzinfo) - last_update < timedelta(hours=1):
                        logger.info(f"Activity {activity_id} failed recently, skipping update webhook")
                        return True
                except Exception as e:
                    logger.warning(f"Error parsing updated_at timestamp: {e}")
        
        # For create webhooks or failed activities (older than 1 hour), allow processing
        logger.info(f"Activity {activity_id} status: {processing_status}, aspect: {aspect_type}, proceeding")
        return False
        
    except Exception as e:
        logger.error(f"Error checking processing status for activity {activity_id}: {str(e)}")
        # On error, allow processing to avoid blocking legitimate requests
        return False


def update_activity_status(
    activity_id: str, 
    status: str, 
    error_message: str = None,
    critical: bool = False
) -> None:
    """Update activity processing status in DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        update_expression = "SET processing_status = :status, updated_at = :timestamp"
        expression_values = {
            ':status': status,
            ':timestamp': datetime.now(UTC).isoformat()  # Use current timestamp
        }
        
        if error_message:
            update_expression += ", error_message = :error"
            expression_values[':error'] = error_message
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"Updated activity {activity_id} status to {status}")
        
    except Exception as e:
        logger.error(f"Failed to update activity status: {str(e)}")
        # For critical status updates (like initial processing), raise to trigger retry
        if critical:
            raise
        # For non-critical updates (like final status), don't raise


def start_step_functions_workflow(
    activity_id: str, 
    user_id: str, 
    webhook_data: Dict[str, Any],
    enduraw_waited: bool = False
) -> str:
    """Start Step Functions workflow for activity processing"""
    try:
        # Prepare input for Step Functions
        workflow_input = {
            'activity_id': activity_id,
            'user_id': user_id,
            'webhook_data': webhook_data,
            'enduraw_waited': enduraw_waited,
            'processing_started_at': datetime.now(UTC).isoformat()
        }
        
        # Start execution
        response = stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTIONS_ARN,
            name=f"activity-{activity_id}-{int(datetime.now(UTC).timestamp())}",
            input=json.dumps(workflow_input)
        )
        
        execution_arn = response['executionArn']
        
        # Update activity with execution ARN for tracking
        update_activity_execution_arn(activity_id, execution_arn)
        
        return execution_arn
        
    except Exception as e:
        logger.error(f"Failed to start Step Functions workflow: {str(e)}")
        # Re-raise to trigger SQS retry
        raise


def update_activity_execution_arn(activity_id: str, execution_arn: str) -> None:
    """Update activity record with Step Functions execution ARN"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET execution_arn = :arn, processing_status = :status",
            ExpressionAttributeValues={
                ':arn': execution_arn,
                ':status': 'processing'
            }
        )
        
        logger.info(f"Updated activity {activity_id} with execution ARN")
        
    except Exception as e:
        logger.error(f"Failed to update execution ARN: {str(e)}")


def delay_message_processing(
    record: Dict[str, Any], 
    activity_id: str, 
    user_id: str, 
    message_body: Dict[str, Any]
) -> None:
    """
    Delay message processing by sending it back to SQS with a delay
    
    This allows rate-limited messages to be processed later without losing them
    """
    try:
        # Calculate intelligent delay based on rate limit type
        delay_seconds = calculate_rate_limit_delay()
        
        # Add retry count to prevent infinite loops
        retry_count = message_body.get('rate_limit_retry_count', 0)
        max_retries = 5  # Maximum retries for rate limiting
        
        if retry_count >= max_retries:
            logger.error(f"Activity {activity_id} exceeded max rate limit retries ({max_retries})")
            update_activity_status(activity_id, 'failed', f'Exceeded max rate limit retries ({max_retries})', critical=False)
            return  # Don't requeue, let it be processed normally (will likely fail but won't loop)
        
        # Increment retry count
        message_body['rate_limit_retry_count'] = retry_count + 1
        message_body['rate_limit_delayed_at'] = datetime.now(UTC).isoformat()
        
        # Send delayed message back to SQS
        sqs.send_message(
            QueueUrl=PROCESSING_QUEUE_URL,
            MessageBody=json.dumps(message_body),
            DelaySeconds=min(delay_seconds, 900)  # SQS max delay is 15 minutes
        )
        
        logger.info(f"Delayed activity {activity_id} processing by {delay_seconds} seconds (retry {retry_count + 1}/{max_retries})")
        
    except Exception as e:
        logger.error(f"Failed to delay message processing for activity {activity_id}: {str(e)}")
        # If we can't delay, let the original processing continue (will likely hit rate limits but won't loop)


def fetch_user_configuration(user_id: str) -> Dict[str, Any]:
    """
    Fetch user configuration from DynamoDB
    
    Returns user configuration including module settings from MODULE_CONFIG item
    """
    try:
        table = dynamodb.Table(os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration'))
        
        # Fetch MODULE_CONFIG for module settings
        module_config_response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
        
        if 'Item' in module_config_response:
            module_config = module_config_response['Item']
            logger.info(f"Retrieved MODULE_CONFIG")
            
            # Debug: log module structure
            enduraw_config = module_config.get('enduraw', {})
            campus_coach_config = module_config.get('campus_coach', {})
            logger.info(f"enduraw config: {enduraw_config}")
            logger.info(f"campus_coach config: {campus_coach_config}")
            
            # Return config in expected format
            return {
                'user_id': user_id,
                'modules_config': {
                    'enduraw': enduraw_config,
                    'campus_coach': campus_coach_config
                }
            }
        else:
            # Return default configuration if MODULE_CONFIG doesn't exist
            default_config = {
                'user_id': user_id,
                'modules_config': {
                    'campus_coach': {'enabled': False},
                    'enduraw': {'enabled': False}
                }
            }
            logger.info(f"No MODULE_CONFIG found, using defaults")
            return default_config
            
    except Exception as e:
        logger.error(f"Failed to fetch MODULE_CONFIG: {str(e)}")
        # Return minimal default config on error
        return {
            'user_id': user_id,
            'modules_config': {
                'campus_coach': {'enabled': False},
                'enduraw': {'enabled': False}
            }
        }


def calculate_rate_limit_delay() -> int:
    """
    Calculate intelligent delay based on current rate limit status
    
    Returns delay in seconds
    """
    try:
        table = dynamodb.Table(RATE_LIMITS_TABLE)
        
        # Check which limit is exceeded
        short_term_exceeded = False
        daily_exceeded = False
        
        # Check short-term limit
        response = table.get_item(Key={'limit_type': 'short_term'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            if usage >= 90:
                short_term_exceeded = True
        
        # Check daily limit  
        response = table.get_item(Key={'limit_type': 'daily'})
        if 'Item' in response:
            usage = response['Item'].get('current_usage', 0)
            if usage >= 950:
                daily_exceeded = True
        
        # Calculate delay based on which limit is exceeded
        if daily_exceeded:
            # Daily limit exceeded - wait longer (1-2 hours with jitter)
            base_delay = 3600  # 1 hour
            jitter = random.randint(0, 3600)  # Up to 1 hour additional
            return base_delay + jitter
        elif short_term_exceeded:
            # Short-term limit exceeded - wait for 15-minute window to reset
            base_delay = 900  # 15 minutes
            jitter = random.randint(0, 300)  # Up to 5 minutes additional
            return base_delay + jitter
        else:
            # Default delay if we can't determine the specific limit
            return 600 + random.randint(0, 300)  # 10-15 minutes
            
    except Exception as e:
        logger.error(f"Failed to calculate rate limit delay: {str(e)}")
        # Default delay with jitter
        return 900 + random.randint(0, 300)  # 15-20 minutes