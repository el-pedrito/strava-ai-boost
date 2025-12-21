"""
Configuration API Lambda Function

Handles configuration requests from the local web interface:
- OAuth token management
- Module configuration
- System settings
"""

import json
import os
import logging
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

# Environment variables
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
CAMPUS_COACH_SECRET = os.environ['CAMPUS_COACH_SECRET']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration API"""
    try:
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
        # Route requests
        if 'oauth' in path:
            if http_method == 'GET':
                return get_oauth_status()
            elif http_method == 'POST':
                return handle_oauth_callback(event)
        elif 'modules' in path:
            if http_method == 'GET':
                return get_modules()
            elif http_method == 'POST':
                return configure_module(event)
        elif 'enhancement' in path:
            if http_method == 'GET':
                return get_enhancement_status()
            elif http_method == 'POST':
                return toggle_enhancement_status(event)
        
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not found'})
        }
        
    except Exception as e:
        logger.error(f"Configuration API error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


def get_oauth_status() -> Dict[str, Any]:
    """Get Strava OAuth connection status"""
    try:
        # Check if OAuth tokens exist in Secrets Manager
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'connected': True,
                    'expires_at': tokens.get('expires_at'),
                    'scopes': tokens.get('scope', '').split(',')
                })
            }
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return {
                    'statusCode': 200,
                    'body': json.dumps({'connected': False})
                }
            raise
            
    except Exception as e:
        logger.error(f"OAuth status error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def handle_oauth_callback(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle OAuth callback and store tokens"""
    try:
        body = json.loads(event.get('body', '{}'))
        auth_code = body.get('code')
        
        if not auth_code:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing authorization code'})
            }
        
        # TODO: Exchange authorization code for tokens
        # This would involve calling Strava's token endpoint
        
        # Placeholder - store dummy tokens
        tokens = {
            'access_token': 'dummy_access_token',
            'refresh_token': 'dummy_refresh_token',
            'expires_at': 1735689600,  # Example timestamp
            'scope': 'read,activity:read_all,activity:write'
        }
        
        # Store tokens in Secrets Manager
        secretsmanager.put_secret_value(
            SecretId=STRAVA_OAUTH_SECRET,
            SecretString=json.dumps(tokens)
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'tokens_stored'})
        }
        
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_modules() -> Dict[str, Any]:
    """Get available modules and their configurations"""
    try:
        # TODO: Get module configurations from DynamoDB
        
        modules = {
            'campus_coach': {
                'id': 'campus_coach',
                'name': 'Campus Coach',
                'description': 'Training session matching and performance analysis',
                'enabled': False,
                'configured': False,
                'requires_credentials': True
            },
            'enduraw': {
                'id': 'enduraw',
                'name': 'Enduraw Integration',
                'description': 'Enhanced analytics with weather and wind impact',
                'enabled': False,
                'configured': True,
                'requires_credentials': False
            }
        }
        
        return {
            'statusCode': 200,
            'body': json.dumps(modules)
        }
        
    except Exception as e:
        logger.error(f"Get modules error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def configure_module(event: Dict[str, Any]) -> Dict[str, Any]:
    """Configure a module"""
    try:
        body = json.loads(event.get('body', '{}'))
        module_id = body.get('module_id')
        config = body.get('config', {})
        
        if not module_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing module_id'})
            }
        
        # Handle Campus Coach configuration
        if module_id == 'campus_coach':
            credentials = config.get('credentials', {})
            if not credentials.get('username') or not credentials.get('password'):
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Missing Campus Coach credentials'})
                }
            
            # Store credentials in Secrets Manager
            secretsmanager.put_secret_value(
                SecretId=CAMPUS_COACH_SECRET,
                SecretString=json.dumps(credentials)
            )
        
        # TODO: Store module configuration in DynamoDB
        
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'configured'})
        }
        
    except Exception as e:
        logger.error(f"Configure module error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }



def get_enhancement_status() -> Dict[str, Any]:
    """Get current enhancement status (enabled/paused)"""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': 'SYSTEM_CONFIG'})
        
        if 'Item' in response:
            config = response['Item']
            enhancement_enabled = config.get('enhancement_enabled', True)
            paused_at = config.get('enhancement_paused_at')
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'enhancement_enabled': enhancement_enabled,
                    'enhancement_paused_at': paused_at,
                    'status': 'active' if enhancement_enabled else 'paused'
                })
            }
        else:
            # Default configuration
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'status': 'active'
                })
            }
            
    except Exception as e:
        logger.error(f"Get enhancement status error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def toggle_enhancement_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle enhancement status (pause/resume)"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')  # 'pause' or 'resume'
        
        if action not in ['pause', 'resume']:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid action. Use "pause" or "resume"'})
            }
        
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        if action == 'pause':
            # Pause enhancement
            from datetime import datetime
            paused_at = datetime.utcnow().isoformat()
            
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': False,
                    'enhancement_paused_at': paused_at,
                    'updated_at': paused_at
                }
            )
            
            logger.info("Enhancement paused")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'paused',
                    'paused_at': paused_at,
                    'message': 'Enhancement has been paused. New activities will not be processed.'
                })
            }
            
        else:  # resume
            # Resume enhancement
            from datetime import datetime
            resumed_at = datetime.utcnow().isoformat()
            
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'enhancement_resumed_at': resumed_at,
                    'updated_at': resumed_at
                }
            )
            
            logger.info("Enhancement resumed")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'active',
                    'resumed_at': resumed_at,
                    'message': 'Enhancement has been resumed. New activities will be processed automatically.'
                })
            }
            
    except Exception as e:
        logger.error(f"Toggle enhancement status error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }