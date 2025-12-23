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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
stepfunctions = boto3.client('stepfunctions')
dynamodb = boto3.resource('dynamodb')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
RATE_LIMITS_TABLE = os.environ['RATE_LIMITS_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
STEP_FUNCTIONS_ARN = os.environ['STEP_FUNCTIONS_ARN']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for SQS-triggered activity processing
    
    Receives activity notifications from SQS and starts Step Functions workflow
    """
    try:
        # Process SQS records
        for record in event.get('Records', []):
            process_activity_record(record)
        
        return {'statusCode': 200, 'processed': len(event.get('Records', []))}
        
    except Exception as e:
        logger.error(f"Activity processor error: {str(e)}")
        # Let SQS handle retry logic
        raise


def process_activity_record(record: Dict[str, Any]) -> None:
    """Process a single activity record from SQS"""
    try:
        # Parse SQS message
        message_body = json.loads(record['body'])
        activity_id = message_body['activity_id']
        user_id = message_body['user_id']
        
        logger.info(f"Processing activity {activity_id} for user {user_id}")
        
        # Check rate limits before processing
        if not check_rate_limits():
            logger.warning("Rate limits exceeded, requeueing message")
            raise Exception("Rate limits exceeded")
        
        # Update activity status to processing
        update_activity_status(activity_id, 'processing', critical=True)
        
        # Start Step Functions workflow
        execution_arn = start_step_functions_workflow(activity_id, user_id, message_body)
        
        if execution_arn:
            logger.info(f"Started Step Functions workflow for activity {activity_id}: {execution_arn}")
            # Status will be updated by the workflow
        else:
            logger.error(f"Failed to start Step Functions workflow for activity {activity_id}")
            update_activity_status(activity_id, 'failed', 'Failed to start workflow', critical=False)
            # Raise exception to trigger SQS retry
            raise Exception("Failed to start Step Functions workflow")
        
    except Exception as e:
        logger.error(f"Failed to process activity record: {str(e)}")
        # Update status to failed
        if 'activity_id' in locals():
            update_activity_status(activity_id, 'failed', str(e), critical=False)
        # Re-raise to trigger SQS retry
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
    webhook_data: Dict[str, Any]
) -> str:
    """Start Step Functions workflow for activity processing"""
    try:
        # Prepare input for Step Functions
        workflow_input = {
            'activity_id': activity_id,
            'user_id': user_id,
            'webhook_data': webhook_data,
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