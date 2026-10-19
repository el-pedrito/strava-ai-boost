"""
Step Functions Error Handler Lambda

Triggered by EventBridge when Step Functions executions fail.
Sends failed activity information to DLQ for manual review.
"""

import json
import os
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, UTC
from shared.logger import get_logger

logger = get_logger("stepfunctions-error-handler")

# Initialize AWS clients
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')

# Environment variables
DLQ_URL = os.environ['DLQ_URL']
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Step Functions failure events from EventBridge
    
    Event structure from EventBridge:
    {
        "detail-type": "Step Functions Execution Status Change",
        "detail": {
            "executionArn": "arn:aws:states:...",
            "stateMachineArn": "arn:aws:states:...",
            "name": "activity-123-1234567890",
            "status": "FAILED",
            "input": "{...}",
            "output": null,
            "cause": "Error message",
            "error": "States.TaskFailed"
        }
    }
    """
    try:
        detail = event.get('detail', {})
        execution_arn = detail.get('executionArn')
        status = detail.get('status')
        execution_name = detail.get('name', '')
        
        logger.info(f"Processing Step Functions failure: {execution_arn}, status: {status}")
        
        # Only process FAILED, TIMED_OUT, or ABORTED executions
        if status not in ['FAILED', 'TIMED_OUT', 'ABORTED']:
            logger.info(f"Ignoring execution with status: {status}")
            return {'statusCode': 200, 'message': 'Not a failure status'}
        
        # Extract activity_id from execution name (format: activity-{id}-{timestamp})
        activity_id = extract_activity_id(execution_name)
        
        if not activity_id:
            logger.error(f"Could not extract activity_id from execution name: {execution_name}")
            return {'statusCode': 400, 'error': 'Invalid execution name format'}
        
        # An execution stopped or failed during the athlete-input wait leaves an
        # open window and its task token on the row: close it, drop the token.
        close_athlete_input_window(activity_id)

        # Get execution details for more context
        execution_details = get_execution_details(execution_arn)
        
        # Update activity status in DynamoDB
        update_activity_failure_status(
            activity_id, 
            execution_arn, 
            detail.get('cause', 'Unknown error'),
            detail.get('error', 'Unknown')
        )
        
        # Send message to DLQ for manual review
        send_to_dlq(activity_id, execution_arn, detail, execution_details)
        
        logger.info(f"Successfully handled Step Functions failure for activity {activity_id}")
        
        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'execution_arn': execution_arn,
            'sent_to_dlq': True
        }
        
    except Exception as e:
        logger.error(f"Error handling Step Functions failure: {str(e)}")
        # Don't raise - we don't want EventBridge to retry this
        return {'statusCode': 500, 'error': str(e)}


def extract_activity_id(execution_name: str) -> str:
    """
    Extract activity ID from Step Functions execution name
    
    Expected format: activity-{activity_id}-{timestamp}
    Example: activity-12345678-1703001234
    """
    try:
        parts = execution_name.split('-')
        if len(parts) >= 2 and parts[0] == 'activity':
            # Return everything between 'activity-' and the last '-{timestamp}'
            return '-'.join(parts[1:-1])
        return None
    except Exception as e:
        logger.error(f"Error extracting activity_id: {str(e)}")
        return None


def get_execution_details(execution_arn: str) -> Dict[str, Any]:
    """Get detailed execution information from Step Functions"""
    try:
        response = stepfunctions.describe_execution(
            executionArn=execution_arn
        )
        
        return {
            'startDate': response.get('startDate', '').isoformat() if response.get('startDate') else None,
            'stopDate': response.get('stopDate', '').isoformat() if response.get('stopDate') else None,
            'input': response.get('input'),
            'output': response.get('output'),
            'cause': response.get('cause'),
            'error': response.get('error')
        }
    except Exception as e:
        logger.error(f"Failed to get execution details: {str(e)}")
        return {}


def close_athlete_input_window(activity_id: str) -> bool:
    """Close an open athlete-input window (docs/design/rpe-athlete-input.md).

    Conditional: only a row in ``awaiting`` or ``submitted`` is touched, so a row
    without a window (flag off) or already closed is left as is, without error.
    Never raises. Returns True when a window was closed.
    """
    try:
        dynamodb.Table(ACTIVITIES_TABLE).update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET athlete_input_state = :closed REMOVE input_task_token",
            ConditionExpression="athlete_input_state IN (:awaiting, :submitted)",
            ExpressionAttributeValues={
                ':closed': 'closed',
                ':awaiting': 'awaiting',
                ':submitted': 'submitted',
            },
        )
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            return False
        logger.warning(
            f"Could not close athlete-input window for {activity_id}: "
            f"{e.response.get('Error', {}).get('Code')}"
        )
        return False
    except Exception as e:  # noqa: BLE001 - never block the failure handling
        logger.warning(f"Could not close athlete-input window for {activity_id}: {type(e).__name__}")
        return False
    logger.info(f"Closed athlete-input window for activity {activity_id}")
    return True


def update_activity_failure_status(
    activity_id: str, 
    execution_arn: str, 
    cause: str,
    error: str
) -> None:
    """Update activity status in DynamoDB to reflect Step Functions failure"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="""
                SET processing_status = :status,
                    error_message = :error,
                    execution_arn = :arn,
                    failed_at = :timestamp,
                    failure_cause = :cause,
                    failure_error = :error_type
            """,
            ExpressionAttributeValues={
                ':status': 'failed',
                ':error': f"Step Functions failed: {cause}",
                ':arn': execution_arn,
                ':timestamp': datetime.now(UTC).isoformat(),
                ':cause': cause,
                ':error_type': error
            }
        )
        
        logger.info(f"Updated activity {activity_id} status to failed")
        
    except Exception as e:
        logger.error(f"Failed to update activity status: {str(e)}")


def send_to_dlq(
    activity_id: str, 
    execution_arn: str, 
    event_detail: Dict[str, Any],
    execution_details: Dict[str, Any]
) -> None:
    """Send failed activity information to DLQ for manual review"""
    try:
        # Construct DLQ message with all relevant information
        dlq_message = {
            'activity_id': activity_id,
            'execution_arn': execution_arn,
            'failure_type': 'step_functions_failure',
            'status': event_detail.get('status'),
            'cause': event_detail.get('cause'),
            'error': event_detail.get('error'),
            'execution_name': event_detail.get('name'),
            'state_machine_arn': event_detail.get('stateMachineArn'),
            'failed_at': datetime.now(UTC).isoformat(),
            'execution_details': execution_details,
            'original_input': event_detail.get('input')
        }
        
        # Send to DLQ
        response = sqs.send_message(
            QueueUrl=DLQ_URL,
            MessageBody=json.dumps(dlq_message),
            MessageAttributes={
                'FailureType': {
                    'StringValue': 'StepFunctionsFailure',
                    'DataType': 'String'
                },
                'ActivityId': {
                    'StringValue': activity_id,
                    'DataType': 'String'
                },
                'ExecutionArn': {
                    'StringValue': execution_arn,
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"Sent activity {activity_id} to DLQ: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Failed to send message to DLQ: {str(e)}")
        raise
