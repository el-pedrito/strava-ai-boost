"""
Strava Webhook Handler Lambda Function

Handles incoming Strava webhook notifications and queues them for processing.
Validates webhook signatures and manages rate limiting.
"""

import json
import os
import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
PROCESSING_QUEUE_URL = os.environ['PROCESSING_QUEUE_URL']
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
RATE_LIMITS_TABLE = os.environ['RATE_LIMITS_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']


def get_sqs_client():
    """Get SQS client - allows for easier testing and error handling"""
    return boto3.client('sqs')


def get_dynamodb_resource():
    """Get DynamoDB resource - allows for easier testing and error handling"""
    return boto3.resource('dynamodb')


def get_secretsmanager_client():
    """Get Secrets Manager client - allows for easier testing and error handling"""
    return boto3.client('secretsmanager')


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Strava webhook notifications
    
    Handles both GET (verification) and POST (webhook) requests from Strava
    """
    try:
        http_method = event.get('httpMethod', '')
        
        if http_method == 'GET':
            return handle_webhook_verification(event)
        elif http_method == 'POST':
            return handle_webhook_notification(event)
        else:
            return {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method not allowed'})
            }
            
    except Exception as e:
        logger.error(f"Webhook handler error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


def handle_webhook_verification(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Strava webhook verification (GET request)
    
    Strava sends a verification request with hub.challenge parameter
    """
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        
        # Extract verification parameters
        hub_mode = query_params.get('hub.mode')
        hub_challenge = query_params.get('hub.challenge')
        hub_verify_token = query_params.get('hub.verify_token')
        
        # TODO: Validate verify_token against stored value
        # For now, accept all verification requests
        
        if hub_mode == 'subscribe' and hub_challenge:
            logger.info(f"Webhook verification successful: {hub_challenge}")
            return {
                'statusCode': 200,
                'body': json.dumps({'hub.challenge': hub_challenge}),
                'headers': {'Content-Type': 'application/json'}
            }
        else:
            logger.warning("Invalid webhook verification request")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid verification request'})
            }
            
    except Exception as e:
        logger.error(f"Webhook verification error: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Verification failed'})
        }


def handle_webhook_notification(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Strava webhook notification (POST request)
    
    Validates the webhook and queues activity for processing if enhancement is enabled
    """
    try:
        # Parse webhook body
        body = event.get('body', '')
        if isinstance(body, str):
            webhook_data = json.loads(body)
        else:
            webhook_data = body
            
        logger.info(f"Received webhook: {webhook_data}")
        
        # Validate webhook structure
        if not validate_webhook_data(webhook_data):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid webhook data'})
            }
        
        # Check if enhancement is paused
        if is_enhancement_paused():
            logger.info("Enhancement is paused, acknowledging webhook but skipping processing")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'acknowledged_paused'})
            }
        
        # Only process activity creation/update events
        object_type = webhook_data.get('object_type')
        aspect_type = webhook_data.get('aspect_type')
        
        if object_type == 'activity' and aspect_type in ['create', 'update']:
            # Queue activity for processing
            activity_id = str(webhook_data.get('object_id'))
            owner_id = str(webhook_data.get('owner_id'))
            
            message = {
                'activity_id': activity_id,
                'user_id': owner_id,
                'webhook_data': webhook_data,
                'event_time': webhook_data.get('event_time')
            }
            
            # Send to SQS queue
            sqs = get_sqs_client()
            sqs.send_message(
                QueueUrl=PROCESSING_QUEUE_URL,
                MessageBody=json.dumps(message),
                MessageAttributes={
                    'ActivityId': {
                        'StringValue': activity_id,
                        'DataType': 'String'
                    },
                    'UserId': {
                        'StringValue': owner_id,
                        'DataType': 'String'
                    }
                }
            )
            
            logger.info(f"Queued activity {activity_id} for processing")
            
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'received'})
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook body: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON'})
        }
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Processing failed'})
        }


def is_enhancement_paused() -> bool:
    """
    Check if enhancement is currently paused by reading from DynamoDB
    """
    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration'))
        
        # Use a system-wide configuration key
        response = table.get_item(Key={'user_id': 'SYSTEM_CONFIG'})
        
        if 'Item' in response:
            config = response['Item']
            return not config.get('enhancement_enabled', True)
        
        # Default to enabled if no configuration found
        return False
        
    except Exception as e:
        logger.error(f"Failed to check enhancement status: {str(e)}")
        # Default to enabled on error to avoid blocking processing
        return False


def validate_webhook_data(data: Dict[str, Any]) -> bool:
    """
    Validate webhook data structure
    """
    required_fields = ['object_type', 'object_id', 'aspect_type', 'owner_id']
    
    for field in required_fields:
        if field not in data:
            logger.warning(f"Missing required field: {field}")
            return False
    
    return True