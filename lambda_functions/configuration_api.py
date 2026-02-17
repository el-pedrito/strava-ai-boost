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
from datetime import datetime, UTC, timedelta
import requests
from rate_limiter import check_rate_limit, create_rate_limit_response, add_rate_limit_headers, extract_client_info
from strava_rate_limit import record_usage as record_strava_usage

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


def get_authenticated_user_id() -> str:
    """
    Get authenticated user_id from Strava OAuth tokens
    
    Returns the athlete ID from stored OAuth tokens.
    Falls back to DEFAULT_USER_ID environment variable if tokens not found.
    """
    try:
        # Get OAuth tokens from Secrets Manager
        response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
        tokens = json.loads(response['SecretString'])
        
        # Extract athlete ID from tokens
        athlete = tokens.get('athlete', {})
        athlete_id = athlete.get('id')
        
        if athlete_id:
            logger.info(f"Retrieved user_id from OAuth tokens: {athlete_id}")
            return str(athlete_id)
        else:
            logger.warning("No athlete ID in OAuth tokens, using default")
            return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')
            
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning("OAuth tokens not found, using default user_id")
            return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')
        else:
            logger.error(f"Failed to retrieve OAuth tokens: {str(e)}")
            return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')
    except Exception as e:
        logger.error(f"Error getting authenticated user_id: {str(e)}")
        return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')


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
            elif http_method == 'DELETE':
                return revoke_oauth_tokens(rate_limit_info)
        elif 'strava' in path and 'config' in path:
            if http_method == 'GET':
                return get_strava_app_config(rate_limit_info)
        elif 'test' in path and 'strava-connection' in path:
            if http_method == 'GET':
                return test_strava_connection(rate_limit_info)
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


def get_strava_app_config(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get Strava app configuration status (without exposing secrets) - v2"""
    try:
        # Check if app config exists in Secrets Manager
        try:
            response = secretsmanager.get_secret_value(SecretId='strava-ai-boost-app-config')
            config = json.loads(response['SecretString'])
            
            # Validate config structure
            client_id = config.get('client_id')
            client_secret = config.get('client_secret')
            
            if client_id and client_secret:
                # Config exists and is valid
                return create_success_response({
                    'configured': True,
                    'client_id': client_id,  # Safe to expose (public)
                    'has_client_secret': True,  # Don't expose the secret itself
                    'redirect_uri': config.get('redirect_uri', 'http://localhost:3000/oauth/callback')
                }, rate_limit_info=rate_limit_info)
            else:
                return create_success_response({
                    'configured': False,
                    'message': 'Strava app configuration incomplete'
                }, rate_limit_info=rate_limit_info)
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_success_response({
                    'configured': False,
                    'message': 'Strava app not configured'
                }, rate_limit_info=rate_limit_info)
            else:
                logger.error(f"Error checking Strava config: {e}")
                return create_error_response(500, f'Failed to check configuration: {str(e)}', rate_limit_info)
                
    except json.JSONDecodeError:
        return create_success_response({
            'configured': False,
            'message': 'Invalid configuration format'
        }, rate_limit_info=rate_limit_info)
    except Exception as e:
        logger.error(f"Strava config check error: {str(e)}")
        return create_error_response(500, f'Configuration check failed: {str(e)}', rate_limit_info)


def test_strava_connection(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Test Strava API connection with current OAuth tokens"""
    try:
        # Get OAuth tokens
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            access_token = tokens.get('access_token')
            if not access_token:
                return create_error_response(401, 'No access token available. Please connect to Strava first.', rate_limit_info)
            
            # Test Strava API
            headers = {'Authorization': f'Bearer {access_token}'}
            strava_response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers, timeout=10)
            record_strava_usage(1)
            
            if strava_response.status_code == 200:
                athlete = strava_response.json()
                return create_success_response({
                    'success': True,
                    'message': 'Connection test successful',
                    'athlete': {
                        'id': athlete.get('id'),
                        'name': f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                        'city': athlete.get('city'),
                        'country': athlete.get('country')
                    }
                }, rate_limit_info=rate_limit_info)
            elif strava_response.status_code == 401:
                return create_error_response(401, 'Authentication failed. Please reconnect to Strava.', rate_limit_info)
            else:
                return create_error_response(500, f'Strava API returned {strava_response.status_code}', rate_limit_info)
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_error_response(401, 'OAuth tokens not found. Please connect to Strava first.', rate_limit_info)
            else:
                raise
                
    except Exception as e:
        logger.error(f"Connection test error: {str(e)}")
        return create_error_response(500, f'Connection test failed: {str(e)}', rate_limit_info)


def revoke_oauth_tokens(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Revoke Strava OAuth tokens"""
    try:
        # Get current tokens
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            access_token = tokens.get('access_token')
            if not access_token:
                return create_success_response({
                    'status': 'already_disconnected',
                    'message': 'No tokens to revoke'
                }, rate_limit_info=rate_limit_info)
            
            # Revoke token with Strava
            try:
                revoke_response = requests.post(
                    'https://www.strava.com/oauth/deauthorize',  # tracked below
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )
                logger.info(f"Strava revoke response: {revoke_response.status_code}")
            except Exception as e:
                logger.warning(f"Failed to revoke with Strava API: {e}")
            
            # Clear tokens by putting empty object
            secretsmanager.put_secret_value(
                SecretId=STRAVA_OAUTH_SECRET,
                SecretString='{}'
            )
            
            return create_success_response({
                'status': 'revoked',
                'message': 'OAuth tokens revoked successfully'
            }, rate_limit_info=rate_limit_info)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_success_response({
                    'status': 'already_disconnected',
                    'message': 'No tokens found'
                }, rate_limit_info=rate_limit_info)
            else:
                raise
                
    except Exception as e:
        logger.error(f"Revoke tokens error: {str(e)}")
        return create_error_response(500, f'Failed to revoke tokens: {str(e)}', rate_limit_info)


def test_strava_connection(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Test Strava API connection with current OAuth tokens"""
    try:
        # Get OAuth tokens
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            access_token = tokens.get('access_token')
            if not access_token:
                return create_error_response(401, 'No access token available. Please connect to Strava first.', rate_limit_info)
            
            # Test Strava API
            headers = {'Authorization': f'Bearer {access_token}'}
            strava_response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers, timeout=10)
            record_strava_usage(1)
            
            if strava_response.status_code == 200:
                athlete = strava_response.json()
                return create_success_response({
                    'success': True,
                    'message': 'Connection test successful',
                    'athlete': {
                        'id': athlete.get('id'),
                        'name': f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                        'city': athlete.get('city'),
                        'country': athlete.get('country')
                    }
                }, rate_limit_info=rate_limit_info)
            elif strava_response.status_code == 401:
                return create_error_response(401, 'Authentication failed. Please reconnect to Strava.', rate_limit_info)
            else:
                return create_error_response(500, f'Strava API returned {strava_response.status_code}', rate_limit_info)
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_error_response(401, 'OAuth tokens not found. Please connect to Strava first.', rate_limit_info)
            else:
                raise
                
    except Exception as e:
        logger.error(f"Connection test error: {str(e)}")
        return create_error_response(500, f'Connection test failed: {str(e)}', rate_limit_info)


def get_strava_app_config(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get Strava app configuration status (without exposing secrets) - v2"""
    try:
        # Check if app config exists in Secrets Manager
        try:
            response = secretsmanager.get_secret_value(SecretId='strava-ai-boost-app-config')
            config = json.loads(response['SecretString'])
            
            # Validate config structure
            client_id = config.get('client_id')
            client_secret = config.get('client_secret')
            
            if client_id and client_secret:
                # Config exists and is valid
                return create_success_response({
                    'configured': True,
                    'client_id': client_id,  # Safe to expose (public)
                    'has_client_secret': True,  # Don't expose the secret itself
                    'redirect_uri': config.get('redirect_uri', 'http://localhost:3000/oauth/callback')
                }, rate_limit_info=rate_limit_info)
            else:
                return create_success_response({
                    'configured': False,
                    'message': 'Strava app configuration incomplete'
                }, rate_limit_info=rate_limit_info)
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_success_response({
                    'configured': False,
                    'message': 'Strava app not configured'
                }, rate_limit_info=rate_limit_info)
            else:
                logger.error(f"Error checking Strava config: {e}")
                return create_error_response(500, f'Failed to check configuration: {str(e)}', rate_limit_info)
                
    except json.JSONDecodeError:
        return create_success_response({
            'configured': False,
            'message': 'Invalid configuration format'
        }, rate_limit_info=rate_limit_info)
    except Exception as e:
        logger.error(f"Strava config check error: {str(e)}")
        return create_error_response(500, f'Configuration check failed: {str(e)}', rate_limit_info)


def get_oauth_status(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get Strava OAuth connection status with comprehensive validation"""
    try:
        # Check if OAuth tokens exist in Secrets Manager
        try:
            response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
            tokens = json.loads(response['SecretString'])
            
            # Validate token structure
            required_fields = ['access_token', 'refresh_token', 'expires_at']
            for field in required_fields:
                if field not in tokens:
                    return create_success_response({
                        'connected': False,
                        'status': 'invalid_tokens',
                        'message': f'Invalid token structure: missing {field}'
                    }, rate_limit_info=rate_limit_info)
            
            # Check token expiry
            expires_at = tokens.get('expires_at')
            is_expired = False
            expires_soon = False
            
            if expires_at:
                try:
                    if isinstance(expires_at, (int, float)):
                        expiry_time = datetime.fromtimestamp(expires_at, UTC)
                    else:
                        expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    
                    current_time = datetime.now(UTC)
                    is_expired = expiry_time <= current_time
                    expires_soon = expiry_time <= (current_time + timedelta(minutes=30))
                    
                except Exception as e:
                    logger.warning(f"Error parsing expiry time: {e}")
                    is_expired = True
            else:
                is_expired = True
            
            # Get athlete information
            athlete = tokens.get('athlete', {})
            athlete_info = None
            if athlete:
                athlete_info = {
                    'id': athlete.get('id'),
                    'name': f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
                    'profile': athlete.get('profile'),
                    'city': athlete.get('city'),
                    'state': athlete.get('state'),
                    'country': athlete.get('country')
                }
            
            # Determine connection status
            if is_expired:
                status = 'expired'
                connected = False
                message = 'OAuth tokens have expired. Please reconnect to Strava.'
            elif expires_soon:
                status = 'expires_soon'
                connected = True
                message = 'OAuth tokens expire soon but are still valid.'
            else:
                status = 'active'
                connected = True
                message = 'Successfully connected to Strava with valid tokens.'
            
            return create_success_response({
                'connected': connected,
                'status': status,
                'message': message,
                'expires_at': expires_at,
                'expires_soon': expires_soon,
                'scopes': tokens.get('scope', '').split(',') if tokens.get('scope') else [],
                'obtained_at': tokens.get('obtained_at'),
                'last_refreshed': tokens.get('last_refreshed'),
                'athlete': athlete_info,
                'token_type': tokens.get('token_type', 'Bearer')
            }, rate_limit_info=rate_limit_info)
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                return create_success_response({
                    'connected': False,
                    'status': 'not_connected',
                    'message': 'No OAuth tokens found. Please connect to Strava first.'
                }, rate_limit_info=rate_limit_info)
            else:
                logger.error(f"Secrets Manager error: {e}")
                return create_error_response(
                    500,
                    f'Failed to check OAuth status: {str(e)}',
                    rate_limit_info
                )
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in stored tokens: {e}")
        return create_success_response({
            'connected': False,
            'status': 'invalid_tokens',
            'message': 'Stored tokens are corrupted. Please reconnect to Strava.'
        }, rate_limit_info=rate_limit_info)
    except Exception as e:
        logger.error(f"OAuth status error: {str(e)}")
        return create_error_response(500, f'Failed to get OAuth status: {str(e)}', rate_limit_info)


def handle_oauth_callback(event: Dict[str, Any], rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Handle OAuth callback and exchange authorization code for tokens"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        # Extract required parameters
        auth_code = body.get('code')
        state = body.get('state')
        code_verifier = body.get('code_verifier')
        client_id = body.get('client_id')
        
        # Validate required parameters
        if not auth_code:
            return create_error_response(400, 'Missing authorization code', rate_limit_info)
        
        if not code_verifier:
            return create_error_response(400, 'Missing PKCE code verifier', rate_limit_info)
        
        if not client_id:
            return create_error_response(400, 'Missing client ID', rate_limit_info)
        
        # Get client_secret from Secrets Manager
        try:
            secret_response = secretsmanager.get_secret_value(SecretId='strava-ai-boost-app-config')
            app_config = json.loads(secret_response['SecretString'])
            client_secret = app_config.get('client_secret')
            
            if not client_secret:
                return create_error_response(400, 'Client secret not configured in Secrets Manager', rate_limit_info)
        except Exception as e:
            logger.error(f"Failed to get client_secret: {e}")
            return create_error_response(500, 'Failed to retrieve application credentials', rate_limit_info)
        
        # Exchange authorization code for tokens with Strava API
        try:
            token_data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'code': auth_code,
                'grant_type': 'authorization_code',
                'code_verifier': code_verifier
            }
            
            # Call Strava token endpoint
            token_response = requests.post(
                'https://www.strava.com/oauth/token',  # tracked below
                data=token_data,
                timeout=30,
                headers={'Accept': 'application/json'}
            )
            
            if token_response.status_code != 200:
                logger.error(f"Strava token exchange failed: {token_response.status_code} - {token_response.text}")
                return create_error_response(
                    400, 
                    f'Token exchange failed: {token_response.json().get("message", "Unknown error")}',
                    rate_limit_info
                )
            
            # Parse token response
            tokens = token_response.json()
            
            # Validate token response
            required_fields = ['access_token', 'refresh_token', 'expires_at']
            for field in required_fields:
                if field not in tokens:
                    return create_error_response(
                        400,
                        f'Invalid token response: missing {field}',
                        rate_limit_info
                    )
            
            # Add metadata to tokens
            tokens['obtained_at'] = datetime.now(UTC).isoformat()
            tokens['client_id'] = client_id
            tokens['last_refreshed'] = None
            
            # Validate athlete information if present
            athlete = tokens.get('athlete', {})
            if athlete:
                logger.info(f"OAuth successful for athlete: {athlete.get('firstname', 'Unknown')} {athlete.get('lastname', '')}")
            
        except requests.RequestException as e:
            logger.error(f"HTTP error during token exchange: {e}")
            return create_error_response(
                500,
                f'Failed to connect to Strava: {str(e)}',
                rate_limit_info
            )
        except Exception as e:
            logger.error(f"Error during token exchange: {e}")
            return create_error_response(
                500,
                f'Token exchange error: {str(e)}',
                rate_limit_info
            )
        
        # Store tokens in Secrets Manager
        try:
            # Prepare secret value with validation
            secret_value = {
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'expires_at': tokens['expires_at'],
                'token_type': tokens.get('token_type', 'Bearer'),
                'scope': tokens.get('scope', 'read,activity:write'),
                'obtained_at': tokens['obtained_at'],
                'client_id': client_id,
                'last_refreshed': None,
                'athlete': tokens.get('athlete', {})
            }
            
            # Store in Secrets Manager
            try:
                secretsmanager.put_secret_value(
                    SecretId=STRAVA_OAUTH_SECRET,
                    SecretString=json.dumps(secret_value)
                )
                logger.info("OAuth tokens updated in Secrets Manager")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create secret if it doesn't exist
                    secretsmanager.create_secret(
                        Name=STRAVA_OAUTH_SECRET,
                        Description='Strava OAuth tokens for AI Boost',
                        SecretString=json.dumps(secret_value)
                    )
                    logger.info("OAuth secret created and tokens stored")
                else:
                    raise
            
            # Update user configuration to mark OAuth as connected
            try:
                table = dynamodb.Table(USER_CONFIG_TABLE)
                table.put_item(
                    Item={
                        'user_id': 'OAUTH_STATUS',
                        'strava_connected': True,
                        'connected_at': datetime.now(UTC).isoformat(),
                        'athlete_id': tokens.get('athlete', {}).get('id'),
                        'athlete_name': f"{tokens.get('athlete', {}).get('firstname', '')} {tokens.get('athlete', {}).get('lastname', '')}".strip(),
                        'scopes': tokens.get('scope', '').split(','),
                        'updated_at': datetime.now(UTC).isoformat()
                    }
                )
                logger.info("OAuth status updated in DynamoDB")
            except Exception as e:
                logger.warning(f"Failed to update OAuth status in DynamoDB: {e}")
            
            return create_success_response({
                'status': 'tokens_stored',
                'message': 'Successfully connected to Strava! Your account is now linked.',
                'expires_at': tokens['expires_at'],
                'athlete': {
                    'id': tokens.get('athlete', {}).get('id'),
                    'name': f"{tokens.get('athlete', {}).get('firstname', '')} {tokens.get('athlete', {}).get('lastname', '')}".strip(),
                    'profile': tokens.get('athlete', {}).get('profile')
                },
                'scopes': tokens.get('scope', '').split(',')
            }, rate_limit_info=rate_limit_info)
            
        except ClientError as e:
            logger.error(f"AWS Secrets Manager error: {e}")
            return create_error_response(
                500,
                f'Failed to store tokens securely: {str(e)}',
                rate_limit_info
            )
        except Exception as e:
            logger.error(f"Error storing tokens: {e}")
            return create_error_response(
                500,
                f'Failed to store tokens: {str(e)}',
                rate_limit_info
            )
        
    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', rate_limit_info)
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return create_error_response(500, f'OAuth callback failed: {str(e)}', rate_limit_info)


def get_modules(rate_limit_info: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get available modules and their configurations"""
    try:
        # Get authenticated user_id from OAuth tokens
        user_id = get_authenticated_user_id()
        
        # Get module configurations from DynamoDB
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        try:
            response = table.get_item(Key={'user_id': user_id})
            stored_config = response.get('Item', {})
        except Exception as e:
            logger.warning(f"Failed to get user config from DynamoDB: {e}")
            stored_config = {}
        
        # Get modules_config (nested format)
        modules_config = stored_config.get('modules_config', {})
        
        # Campus Coach configuration
        campus_coach_config = modules_config.get('campus_coach', {})
        campus_coach_enabled = campus_coach_config.get('enabled', False)
        campus_coach_configured = campus_coach_config.get('configured', False)
        
        # Enduraw configuration
        enduraw_config = modules_config.get('enduraw', {})
        enduraw_enabled = enduraw_config.get('enabled', False)
        enduraw_wait_time = enduraw_config.get('wait_time', '2 minutes')
        
        # Default module configurations
        modules = {
            'campus_coach': {
                'id': 'campus_coach',
                'name': 'Campus Coach',
                'description': 'Training session matching and performance analysis',
                'enabled': campus_coach_enabled,
                'configured': campus_coach_configured,
                'requires_credentials': True,
                'last_extraction': stored_config.get('campus_coach_last_extraction'),
                'status': 'active' if campus_coach_enabled else 'disabled'
            },
            'enduraw': {
                'id': 'enduraw',
                'name': 'Enduraw Integration',
                'description': 'Enhanced analytics with weather and wind impact',
                'enabled': enduraw_enabled,
                'configured': True,  # No credentials required
                'requires_credentials': False,
                'wait_time': enduraw_wait_time,
                'status': 'active' if enduraw_enabled else 'disabled'
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
        
        # Get authenticated user_id from OAuth tokens
        user_id = get_authenticated_user_id()
        
        # Handle Campus Coach configuration
        if module_id == 'campus_coach' and enabled:
            credentials = config.get('credentials', {})
            
            # Only require credentials if they don't exist in Secrets Manager
            if credentials.get('username') and credentials.get('password'):
                # Store/update credentials in Secrets Manager
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
            else:
                # No credentials provided, check if they exist in Secrets Manager
                try:
                    response = secretsmanager.get_secret_value(SecretId=CAMPUS_COACH_SECRET)
                    secret_data = json.loads(response['SecretString'])
                    
                    # Verify that username and password exist in the secret
                    if not secret_data.get('username') or not secret_data.get('password'):
                        return create_error_response(400, 'Campus Coach credentials in Secrets Manager are incomplete. Please reconfigure.', rate_limit_info)
                    
                    logger.info("Campus Coach credentials already exist in Secrets Manager")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        return create_error_response(400, 'Campus Coach credentials required when enabling for the first time', rate_limit_info)
                    else:
                        raise
        
        # Store module configuration in DynamoDB (user-specific)
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        # Get existing user config
        try:
            response = table.get_item(Key={'user_id': user_id})
            user_config = response.get('Item', {'user_id': user_id})
        except Exception:
            user_config = {'user_id': user_id}
        
        # Update module configuration in nested structure (single source of truth)
        if 'modules_config' not in user_config:
            user_config['modules_config'] = {}
        
        if module_id not in user_config['modules_config']:
            user_config['modules_config'][module_id] = {}
        
        user_config['modules_config'][module_id]['enabled'] = enabled
        user_config['modules_config'][module_id]['configured'] = True
        user_config['modules_config'][module_id]['updated_at'] = datetime.now(UTC).isoformat()
        
        # Add module-specific configuration
        if module_id == 'enduraw':
            user_config['modules_config'][module_id]['wait_time'] = config.get('wait_time', '2 minutes')
        
        # Store updated configuration
        table.put_item(Item=user_config)
        
        # Enable/Disable EventBridge Scheduler for Campus Coach if applicable
        if module_id == 'campus_coach':
            try:
                events_client = boto3.client('events')
                rule_name = 'StravaAIBoost-CampusCoach-DailyExtraction'
                
                if enabled:
                    # Enable the EventBridge rule
                    events_client.enable_rule(Name=rule_name)
                    logger.info(f"✅ Enabled EventBridge scheduler for Campus Coach")
                else:
                    # Disable the EventBridge rule
                    events_client.disable_rule(Name=rule_name)
                    logger.info(f"⏸️ Disabled EventBridge scheduler for Campus Coach")
            except Exception as e:
                logger.warning(f"Failed to update EventBridge scheduler: {str(e)}")
                # Don't fail the whole operation if EventBridge update fails
        
        # Log with clear status
        status_label = "configured" if enabled else "unconfigured"
        logger.info(f"Module {module_id} {status_label} for user {user_id}: enabled={enabled}")
        
        return create_success_response({
            'status': status_label,
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
    """Get current enhancement status (enabled/paused) for user"""
    try:
        # Get authenticated user_id from OAuth tokens
        user_id = get_authenticated_user_id()
        
        table = dynamodb.Table(USER_CONFIG_TABLE)
        
        try:
            response = table.get_item(Key={'user_id': user_id})
            
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
    """Toggle enhancement status (pause/resume) for user"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')  # 'pause' or 'resume'
        
        if action not in ['pause', 'resume']:
            return create_error_response(400, 'Invalid action. Use "pause" or "resume"', rate_limit_info)
        
        # Get authenticated user_id from OAuth tokens
        user_id = get_authenticated_user_id()
        
        table = dynamodb.Table(USER_CONFIG_TABLE)
        current_time = datetime.now(UTC).isoformat()
        
        # Get existing user config
        try:
            response = table.get_item(Key={'user_id': user_id})
            user_config = response.get('Item', {'user_id': user_id})
        except Exception:
            user_config = {'user_id': user_id}
        
        if action == 'pause':
            # Pause enhancement
            user_config['enhancement_enabled'] = False
            user_config['enhancement_paused_at'] = current_time
            user_config['updated_at'] = current_time
            
            table.put_item(Item=user_config)
            
            logger.info(f"Enhancement paused for user {user_id}")
            
            return create_success_response({
                'status': 'paused',
                'paused_at': current_time,
                'message': 'Enhancement has been paused. New activities will not be processed.'
            }, rate_limit_info=rate_limit_info)
            
        else:  # resume
            # Resume enhancement
            user_config['enhancement_enabled'] = True
            user_config['enhancement_paused_at'] = None
            user_config['enhancement_resumed_at'] = current_time
            user_config['updated_at'] = current_time
            
            table.put_item(Item=user_config)
            
            logger.info(f"Enhancement resumed for user {user_id}")
            
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