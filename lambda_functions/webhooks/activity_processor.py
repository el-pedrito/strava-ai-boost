"""
Activity Processor Lambda Function

Processes activities from SQS queue and triggers Step Functions workflow.
Handles error recovery.
"""

import json
import os
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, UTC
from shared.logger import get_logger, metrics, MetricUnit

logger = get_logger("activity_processor")

# Initialize AWS clients
stepfunctions = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
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
        
        # Publish business metrics
        processed = len(event.get('Records', [])) - len(batch_item_failures)
        if processed > 0:
            metrics.add_metric(name="ActivitiesProcessed", unit=MetricUnit.Count, value=processed)
        if batch_item_failures:
            metrics.add_metric(name="ActivitiesProcessFailed", unit=MetricUnit.Count, value=len(batch_item_failures))

        # Return batch item failures to SQS
        # Messages with failures will be retried, successful ones will be deleted
        return {
            'batchItemFailures': batch_item_failures
        }
        
    except (ClientError, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Activity processor critical error: {str(e)}", exc_info=True)
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
        
        # Skip if waiting for Enduraw (avoid concurrent processing during wait)
        # BUT allow processing if enduraw_waited flag is set (message after 2-min delay)
        if processing_status == 'waiting_enduraw':
            enduraw_waited = message_body.get('enduraw_waited', False)
            if not enduraw_waited:
                logger.info(f"Activity {activity_id} waiting for Enduraw, skipping")
                return True
            else:
                logger.info(f"Activity {activity_id} Enduraw wait completed, proceeding with processing")
                # Force processing - return False immediately to bypass other checks
                return False
        
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
        
    except (ClientError, ValueError, TypeError) as e:
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
        
    except ClientError as e:
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
        
    except ClientError as e:
        logger.error(f"Failed to update execution ARN: {str(e)}")

def fetch_user_configuration(user_id: str) -> Dict[str, Any]:
    """
    Fetch user configuration from DynamoDB
    
    Returns user configuration including module settings from user's own record
    """
    try:
        table = dynamodb.Table(os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration'))
        
        # Fetch user configuration directly
        user_config_response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in user_config_response:
            user_config = user_config_response['Item']
            logger.info(f"Retrieved configuration for user {user_id}")
            
            # Read modules_config from user's own record
            modules_config_data = user_config.get('modules_config', {})
            
            # Debug: log module structure
            enduraw_config = modules_config_data.get('enduraw', {})
            campus_coach_config = modules_config_data.get('campus_coach', {})
            
            logger.info(f"enduraw config: {enduraw_config}")
            logger.info(f"campus_coach config: {campus_coach_config}")
            
            # Return config in expected format
            return {
                'user_id': user_id,
                'modules_config': {
                    'enduraw': enduraw_config,
                    'campus_coach': campus_coach_config
                },
                'enhancement_enabled': user_config.get('enhancement_enabled', True)
            }
        else:
            # Return default configuration if user doesn't exist
            default_config = {
                'user_id': user_id,
                'modules_config': {
                    'campus_coach': {'enabled': False},
                    'enduraw': {'enabled': False}
                },
                'enhancement_enabled': True
            }
            logger.info(f"No configuration found for user {user_id}, using defaults")
            return default_config
            
    except ClientError as e:
        logger.error(f"Failed to fetch user configuration: {str(e)}")
        # Return minimal default config on error
        return {
            'user_id': user_id,
            'modules_config': {
                'campus_coach': {'enabled': False},
                'enduraw': {'enabled': False}
            },
            'enhancement_enabled': True
        }

