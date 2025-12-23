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
from datetime import datetime, UTC
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

# Environment variables
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
CAMPUS_COACH_SECRET = os.environ['CAMPUS_COACH_SECRET']

# CORS headers
CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration API"""
    try:
        # Extract client information for rate limiting
        client_ip, user_agent = extract_client_info(event)
        
        # Check rate limit
        is_allowed, rate_limit_info = check_rate_limit(client_ip, 'configuration', user_agent)
        
        if not is_allowed:
            return create_rate_limit_response(rate_limit_info)
        
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        
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
        
        # Route requests
        if 'oauth' in path:
            if http_method == 'GET':
                return get_oauth_status(rate_limit_info)
            elif http_method == 'POST':
                return handle_oauth_callback(event, rate_limit_info)
        elif 'modules' in path:
            if http_method == 'GET':
                return get_modules(rate_limit_info)
            elif http_method == 'POST':
                return configure_module(event, rate_limit_info)
        elif 'enhancement' in path:
            if http_method == 'GET':
                return get_enhancement_status(rate_limit_info)
            elif http_method == 'POST':
                return toggle_enhancement_status(event, rate_limit_info)
        
        return create_error_response(404, 'Endpoint not found', rate_limit_info)
        
    except Exception as e:
        logger.error(f"Configuration API error: {str(e)}")
        return create_error_response(500, 'Internal server error')


def validate_request(event: Dict[str, Any]) -> str:
    """Validate incoming request"""
    try:
        # Check for required headers
        headers = event.get('headers', {})
        
        # For POST requests, validate Content-Type
        if event.get('httpMethod') == 'POST':
            content_type = headers.get('Content-Type', headers.get('content-type', ''))
            if 'application/json' not in content_type:
                return 'Content-Type must be application/json for POST requests'
            
            # Validate JSON body
            body = event.get('body', '')
            if body:
                try:
                    json.loads(body)
                except json.JSONDecodeError:
                    return 'Invalid JSON in request body'
        
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
            'timestamp': datetime.now(UTC).isoformat()
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
            'timestamp': datetime.now(UTC).isoformat()
        })
    }


def get_oauth_status(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get Strava OAuth connection status"""
    try:
        # Check if OAuth tokens exist in Secrets Manager
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            # Check token expiry
            expires_at = tokens.get('expires_at')
            is_expired = False
            
            if expires_at:
                if isinstance(expires_at, (int, float)):
                    expiry_time = datetime.fromtimestamp(expires_at, UTC)
                else:
                    expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                
                is_expired = expiry_time <= datetime.now(UTC)
            
            return create_success_response({
                'connected': not is_expired,
                'expires_at': expires_at,
                'scopes': tokens.get('scope', '').split(','),
                'obtained_at': tokens.get('obtained_at'),
                'last_refreshed': tokens.get('last_refreshed'),
                'status': 'expired' if is_expired else 'active'
            }, rate_limit_info=rate_limit_info)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_success_response({
                    'connected': False,
                    'status': 'not_connected',
                    'message': 'No OAuth tokens found'
                }, rate_limit_info=rate_limit_info)
            raise
            
    except Exception as e:
        logger.error(f"OAuth status error: {str(e)}")
        return create_error_response(500, f'Failed to get OAuth status: {str(e)}', rate_limit_info)


def handle_oauth_callback(event: Dict[str, Any], rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Handle OAuth callback and store tokens"""
    try:
        body = json.loads(event.get('body', '{}'))
        auth_code = body.get('code')
        
        if not auth_code:
            return create_error_response(400, 'Missing authorization code', rate_limit_info)
        
        # TODO: Exchange authorization code for tokens
        # This would involve calling Strava's token endpoint
        # For now, store placeholder tokens for testing
        
        tokens = {
            'access_token': f'test_access_token_{auth_code[:10]}',
            'refresh_token': f'test_refresh_token_{auth_code[:10]}',
            'expires_at': int((datetime.now(UTC).timestamp() + 21600)),  # 6 hours from now
            'scope': 'read,activity:read_all,activity:write',
            'obtained_at': datetime.now(UTC).isoformat(),
            'token_type': 'Bearer'
        }
        
        # Store tokens in Secrets Manager
        try:
            secretsmanager.put_secret_value(
                SecretId=STRAVA_OAUTH_SECRET,
                SecretString=json.dumps(tokens)
            )
            
            logger.info("OAuth tokens stored successfully")
            
            return create_success_response({
                'status': 'tokens_stored',
                'message': 'OAuth tokens stored successfully',
                'expires_at': tokens['expires_at']
            }, rate_limit_info=rate_limit_info)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Create secret if it doesn't exist
                secretsmanager.create_secret(
                    Name=STRAVA_OAUTH_SECRET,
                    Description='Strava OAuth tokens for AI Boost',
                    SecretString=json.dumps(tokens)
                )
                
                logger.info("OAuth secret created and tokens stored")
                
                return create_success_response({
                    'status': 'tokens_stored',
                    'message': 'OAuth tokens stored successfully',
                    'expires_at': tokens['expires_at']
                }, rate_limit_info=rate_limit_info)
            raise
        
    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', rate_limit_info)
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return create_error_response(500, f'OAuth callback failed: {str(e)}', rate_limit_info)


def get_modules(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get available modules and their configurations"""
    try:
        # Get module configurations from DynamoDB
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        try:
            response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
            stored_config = response.get('Item', {})
        except Exception as e:
            logger.warning(f"Failed to get module config from DynamoDB: {e}")
            stored_config = {}
        
        # Default module configurations
        modules = {
            'campus_coach': {
                'id': 'campus_coach',
                'name': 'Campus Coach',
                'description': 'Training session matching and performance analysis',
                'enabled': stored_config.get('campus_coach_enabled', False),
                'configured': stored_config.get('campus_coach_configured', False),
                'requires_credentials': True,
                'last_extraction': stored_config.get('campus_coach_last_extraction'),
                'status': 'active' if stored_config.get('campus_coach_enabled') else 'disabled'
            },
            'enduraw': {
                'id': 'enduraw',
                'name': 'Enduraw Integration',
                'description': 'Enhanced analytics with weather and wind impact',
                'enabled': stored_config.get('enduraw_enabled', False),
                'configured': True,  # No credentials required
                'requires_credentials': False,
                'wait_time': '2-7 minutes',
                'status': 'active' if stored_config.get('enduraw_enabled') else 'disabled'
            }
        }
        
        return create_success_response({'modules': modules}, rate_limit_info=rate_limit_info)
        
    except Exception as e:
        logger.error(f"Get modules error: {str(e)}")
        return create_error_response(500, f'Failed to get modules: {str(e)}', rate_limit_info)


def configure_module(event: Dict[str, Any], rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Configure a module"""
    try:
        body = json.loads(event.get('body', '{}'))
        module_id = body.get('module_id')
        enabled = body.get('enabled', False)
        config = body.get('config', {})
        
        if not module_id or module_id not in ['campus_coach', 'enduraw']:
            return create_error_response(400, 'Invalid or missing module_id', rate_limit_info)
        
        # Handle Campus Coach configuration
        if module_id == 'campus_coach' and enabled:
            credentials = config.get('credentials', {})
            if not credentials.get('username') or not credentials.get('password'):
                return create_error_response(400, 'Campus Coach credentials required when enabling', rate_limit_info)
            
            # Store credentials in Secrets Manager
            try:
                credential_data = {
                    'username': credentials['username'],
                    'password': credentials['password'],
                    'configured_at': datetime.now(UTC).isoformat()
                }
                
                secretsmanager.put_secret_value(
                    SecretId=CAMPUS_COACH_SECRET,
                    SecretString=json.dumps(credential_data)
                )
                
                logger.info("Campus Coach credentials stored")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create secret if it doesn't exist
                    secretsmanager.create_secret(
                        Name=CAMPUS_COACH_SECRET,
                        Description='Campus Coach credentials for AI Boost',
                        SecretString=json.dumps(credential_data)
                    )
                    logger.info("Campus Coach secret created")
                else:
                    raise
        
        # Store module configuration in DynamoDB
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        # Get existing config
        try:
            response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
            module_config = response.get('Item', {'user_id': 'MODULE_CONFIG'})
        except Exception:
            module_config = {'user_id': 'MODULE_CONFIG'}
        
        # Update module configuration
        module_config[f'{module_id}_enabled'] = enabled
        module_config[f'{module_id}_configured'] = True
        module_config[f'{module_id}_updated_at'] = datetime.now(UTC).isoformat()
        
        if module_id == 'campus_coach' and enabled:
            module_config['campus_coach_configured'] = True
        
        # Store updated configuration
        table.put_item(Item=module_config)
        
        logger.info(f"Module {module_id} configured: enabled={enabled}")
        
        return create_success_response({
            'status': 'configured',
            'module_id': module_id,
            'enabled': enabled,
            'message': f'{module_id.replace("_", " ").title()} {"enabled" if enabled else "disabled"} successfully'
        }, rate_limit_info=rate_limit_info)
        
    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', rate_limit_info)
    except Exception as e:
        logger.error(f"Configure module error: {str(e)}")
        return create_error_response(500, f'Module configuration failed: {str(e)}', rate_limit_info)


def get_enhancement_status(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get current enhancement status (enabled/paused)"""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        try:
            response = table.get_item(Key={'user_id': 'SYSTEM_CONFIG'})
            
            if 'Item' in response:
                config = response['Item']
                enhancement_enabled = config.get('enhancement_enabled', True)
                paused_at = config.get('enhancement_paused_at')
                resumed_at = config.get('enhancement_resumed_at')
                
                return create_success_response({
                    'enhancement_enabled': enhancement_enabled,
                    'enhancement_paused_at': paused_at,
                    'enhancement_resumed_at': resumed_at,
                    'status': 'active' if enhancement_enabled else 'paused'
                }, rate_limit_info=rate_limit_info)
            else:
                # Default configuration
                return create_success_response({
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'enhancement_resumed_at': None,
                    'status': 'active'
                }, rate_limit_info=rate_limit_info)
                
        except Exception as e:
            logger.warning(f"Failed to get enhancement status from DynamoDB: {e}")
            # Return default status
            return create_success_response({
                'enhancement_enabled': True,
                'enhancement_paused_at': None,
                'status': 'active'
            }, rate_limit_info=rate_limit_info)
            
    except Exception as e:
        logger.error(f"Get enhancement status error: {str(e)}")
        return create_error_response(500, f'Failed to get enhancement status: {str(e)}', rate_limit_info)


def toggle_enhancement_status(event: Dict[str, Any], rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Toggle enhancement status (pause/resume)"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')  # 'pause' or 'resume'
        
        if action not in ['pause', 'resume']:
            return create_error_response(400, 'Invalid action. Use "pause" or "resume"', rate_limit_info)
        
        table = dynamodb.Table(USER_CONFIG_TABLE)
        current_time = datetime.now(UTC).isoformat()
        
        if action == 'pause':
            # Pause enhancement
            config_item = {
                'user_id': 'SYSTEM_CONFIG',
                'enhancement_enabled': False,
                'enhancement_paused_at': current_time,
                'updated_at': current_time
            }
            
            table.put_item(Item=config_item)
            
            logger.info("Enhancement paused")
            
            return create_success_response({
                'status': 'paused',
                'paused_at': current_time,
                'message': 'Enhancement has been paused. New activities will not be processed.'
            }, rate_limit_info=rate_limit_info)
            
        else:  # resume
            # Resume enhancement
            config_item = {
                'user_id': 'SYSTEM_CONFIG',
                'enhancement_enabled': True,
                'enhancement_paused_at': None,
                'enhancement_resumed_at': current_time,
                'updated_at': current_time
            }
            
            table.put_item(Item=config_item)
            
            logger.info("Enhancement resumed")
            
            return create_success_response({
                'status': 'active',
                'resumed_at': current_time,
                'message': 'Enhancement has been resumed. New activities will be processed automatically.'
            }, rate_limit_info=rate_limit_info)
            
    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', rate_limit_info)
    except Exception as e:
        logger.error(f"Toggle enhancement status error: {str(e)}")
        return create_error_response(500, f'Failed to toggle enhancement status: {str(e)}', rate_limit_info)