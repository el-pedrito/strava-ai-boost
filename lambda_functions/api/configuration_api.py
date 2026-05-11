"""
Configuration API Lambda Function

Handles configuration requests from the local web interface:
- OAuth token management
- Module configuration
- System settings
"""

import json
import os
from typing import Dict, Any

import boto3
import requests
from botocore.exceptions import ClientError
from datetime import datetime, UTC, timedelta

from shared.responses import (
    CORS_HEADERS_WRITE as CORS_HEADERS,
    create_success_response,
    create_error_response,
)
from shared.logger import get_logger, inject_correlation_id

logger = get_logger("configuration_api")

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

# Environment variables
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
CAMPUS_COACH_SECRET = os.environ['CAMPUS_COACH_SECRET']
INTERVALS_ICU_SECRET = os.environ.get('INTERVALS_ICU_SECRET', 'strava-ai-boost-intervals-icu-credentials')


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

        # Extract athlete ID from tokens (athlete.id on first auth, user_id after refresh)
        athlete_id = None
        athlete = tokens.get('athlete', {})
        if isinstance(athlete, dict):
            athlete_id = athlete.get('id')
        if not athlete_id:
            athlete_id = tokens.get('user_id')

        if athlete_id:
            logger.info(f"Retrieved user_id from OAuth tokens: {athlete_id}")
            return str(athlete_id)
        else:
            logger.warning("No athlete ID in OAuth tokens, using default")
            return os.environ.get('DEFAULT_USER_ID', '')

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.warning("OAuth tokens not found, using default user_id")
        else:
            logger.error(f"Failed to retrieve OAuth tokens: {str(e)}")
        return os.environ.get('DEFAULT_USER_ID', '')
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Error parsing OAuth tokens: {str(e)}")
        return os.environ.get('DEFAULT_USER_ID', '')


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for configuration API"""
    inject_correlation_id(logger, event)
    try:
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')

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
            return create_error_response(400, validation_error, cors_headers=CORS_HEADERS)

        # Route requests
        if 'oauth' in path:
            if http_method == 'GET':
                return get_oauth_status()
            elif http_method == 'POST':
                return handle_oauth_callback(event)
            elif http_method == 'DELETE':
                return revoke_oauth_tokens()
        elif 'strava' in path and 'config' in path:
            if http_method == 'GET':
                return get_strava_app_config()
        elif 'test' in path and 'strava-connection' in path:
            if http_method == 'GET':
                return test_strava_connection()
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

        return create_error_response(404, 'Endpoint not found', cors_headers=CORS_HEADERS)

    except (ClientError, requests.RequestException) as e:
        logger.error(f"Configuration API error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Configuration API unexpected error: {str(e)}", exc_info=True)
        return create_error_response(500, 'Internal server error', cors_headers=CORS_HEADERS)


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

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Request validation error: {str(e)}")
        return 'Request validation failed'


def get_strava_app_config() -> Dict[str, Any]:
    """Get Strava app configuration status (without exposing secrets)"""
    try:
        response = secretsmanager.get_secret_value(SecretId='strava-ai-boost-app-config')
        config = json.loads(response['SecretString'])

        client_id = config.get('client_id')
        client_secret = config.get('client_secret')

        if client_id and client_secret:
            return create_success_response({
                'configured': True,
                'client_id': client_id,
                'has_client_secret': True,
                'redirect_uri': config.get('redirect_uri', '')
            }, cors_headers=CORS_HEADERS)
        else:
            return create_success_response({
                'configured': False,
                'message': 'Strava app configuration incomplete'
            }, cors_headers=CORS_HEADERS)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return create_success_response({
                'configured': False,
                'message': 'Strava app not configured'
            }, cors_headers=CORS_HEADERS)
        else:
            logger.error(f"Error checking Strava config: {e}")
            return create_error_response(500, 'Failed to check configuration', cors_headers=CORS_HEADERS)
    except json.JSONDecodeError:
        return create_success_response({
            'configured': False,
            'message': 'Invalid configuration format'
        }, cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Strava config check error: {str(e)}")
        return create_error_response(500, 'Configuration check failed', cors_headers=CORS_HEADERS)


def test_strava_connection() -> Dict[str, Any]:
    """Test Strava API connection with current OAuth tokens"""
    try:
        response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
        tokens = json.loads(response['SecretString'])

        access_token = tokens.get('access_token')
        if not access_token:
            return create_error_response(401, 'No access token available. Please connect to Strava first.', cors_headers=CORS_HEADERS)

        headers = {'Authorization': f'Bearer {access_token}'}
        strava_response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers, timeout=10)

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
            }, cors_headers=CORS_HEADERS)
        elif strava_response.status_code == 401:
            return create_error_response(401, 'Authentication failed. Please reconnect to Strava.', cors_headers=CORS_HEADERS)
        else:
            return create_error_response(500, f'Strava API returned {strava_response.status_code}', cors_headers=CORS_HEADERS)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return create_error_response(401, 'OAuth tokens not found. Please connect to Strava first.', cors_headers=CORS_HEADERS)
        else:
            logger.error(f"Secrets Manager error during connection test: {e}")
            return create_error_response(500, 'Connection test failed', cors_headers=CORS_HEADERS)
    except requests.RequestException as e:
        logger.error(f"Strava API request failed: {e}")
        return create_error_response(500, 'Connection test failed', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Connection test error: {str(e)}")
        return create_error_response(500, 'Connection test failed', cors_headers=CORS_HEADERS)


def revoke_oauth_tokens() -> Dict[str, Any]:
    """Revoke Strava OAuth tokens"""
    try:
        response = secretsmanager.get_secret_value(SecretId=STRAVA_OAUTH_SECRET)
        tokens = json.loads(response['SecretString'])

        access_token = tokens.get('access_token')
        if not access_token:
            return create_success_response({
                'status': 'already_disconnected',
                'message': 'No tokens to revoke'
            }, cors_headers=CORS_HEADERS)

        # Revoke token with Strava
        try:
            revoke_response = requests.post(
                'https://www.strava.com/oauth/deauthorize',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            )
            logger.info(f"Strava revoke response: {revoke_response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Failed to revoke with Strava API: {e}")

        # Clear tokens by putting empty object
        secretsmanager.put_secret_value(
            SecretId=STRAVA_OAUTH_SECRET,
            SecretString='{}'
        )

        return create_success_response({
            'status': 'revoked',
            'message': 'OAuth tokens revoked successfully'
        }, cors_headers=CORS_HEADERS)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return create_success_response({
                'status': 'already_disconnected',
                'message': 'No tokens found'
            }, cors_headers=CORS_HEADERS)
        else:
            logger.error(f"Secrets Manager error during revoke: {e}")
            return create_error_response(500, 'Failed to revoke tokens', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Revoke tokens error: {str(e)}")
        return create_error_response(500, 'Failed to revoke tokens', cors_headers=CORS_HEADERS)


def get_oauth_status() -> Dict[str, Any]:
    """Get Strava OAuth connection status with comprehensive validation"""
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
                }, cors_headers=CORS_HEADERS)

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

            except (ValueError, TypeError, OSError) as e:
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
        }, cors_headers=CORS_HEADERS)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return create_success_response({
                'connected': False,
                'status': 'not_connected',
                'message': 'No OAuth tokens found. Please connect to Strava first.'
            }, cors_headers=CORS_HEADERS)
        else:
            logger.error(f"Secrets Manager error: {e}")
            return create_error_response(500, 'Failed to check OAuth status', cors_headers=CORS_HEADERS)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in stored tokens: {e}")
        return create_success_response({
            'connected': False,
            'status': 'invalid_tokens',
            'message': 'Stored tokens are corrupted. Please reconnect to Strava.'
        }, cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"OAuth status error: {str(e)}")
        return create_error_response(500, 'Failed to get OAuth status', cors_headers=CORS_HEADERS)


def handle_oauth_callback(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle OAuth callback and exchange authorization code for tokens"""
    try:
        body = json.loads(event.get('body', '{}'))

        # Extract required parameters
        auth_code = body.get('code')
        code_verifier = body.get('code_verifier')
        client_id = body.get('client_id')

        # Validate required parameters
        if not auth_code:
            return create_error_response(400, 'Missing authorization code', cors_headers=CORS_HEADERS)
        if not code_verifier:
            return create_error_response(400, 'Missing PKCE code verifier', cors_headers=CORS_HEADERS)
        if not client_id:
            return create_error_response(400, 'Missing client ID', cors_headers=CORS_HEADERS)

        # Get client_secret from Secrets Manager
        try:
            secret_response = secretsmanager.get_secret_value(SecretId='strava-ai-boost-app-config')
            app_config = json.loads(secret_response['SecretString'])
            client_secret = app_config.get('client_secret')

            if not client_secret:
                return create_error_response(400, 'Client secret not configured in Secrets Manager', cors_headers=CORS_HEADERS)
        except ClientError as e:
            logger.error(f"Failed to get client_secret: {e}")
            return create_error_response(500, 'Failed to retrieve application credentials', cors_headers=CORS_HEADERS)

        # Exchange authorization code for tokens with Strava API
        try:
            token_data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'code': auth_code,
                'grant_type': 'authorization_code',
                'code_verifier': code_verifier
            }

            token_response = requests.post(
                'https://www.strava.com/oauth/token',
                data=token_data,
                timeout=30,
                headers={'Accept': 'application/json'}
            )

            if token_response.status_code != 200:
                logger.error(f"Strava token exchange failed: {token_response.status_code} - {token_response.text}")
                return create_error_response(400, 'Token exchange failed', cors_headers=CORS_HEADERS)

            tokens = token_response.json()

            # Validate token response
            required_fields = ['access_token', 'refresh_token', 'expires_at']
            for field in required_fields:
                if field not in tokens:
                    return create_error_response(400, f'Invalid token response: missing {field}', cors_headers=CORS_HEADERS)

            # Add metadata to tokens
            tokens['obtained_at'] = datetime.now(UTC).isoformat()
            tokens['client_id'] = client_id
            tokens['last_refreshed'] = None

            athlete = tokens.get('athlete', {})
            if athlete:
                logger.info(f"OAuth successful for athlete: {athlete.get('firstname', 'Unknown')} {athlete.get('lastname', '')}")

        except requests.RequestException as e:
            logger.error(f"HTTP error during token exchange: {e}")
            return create_error_response(500, 'Failed to connect to Strava', cors_headers=CORS_HEADERS)

        # Store tokens in Secrets Manager
        try:
            athlete_obj = tokens.get('athlete', {})
            secret_value = {
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'expires_at': tokens['expires_at'],
                'token_type': tokens.get('token_type', 'Bearer'),
                'scope': tokens.get('scope', 'read,activity:write'),
                'obtained_at': tokens['obtained_at'],
                'client_id': client_id,
                'last_refreshed': None,
                'athlete': athlete_obj,
                'user_id': str(athlete_obj.get('id', ''))
            }

            try:
                secretsmanager.put_secret_value(
                    SecretId=STRAVA_OAUTH_SECRET,
                    SecretString=json.dumps(secret_value)
                )
                logger.info("OAuth tokens updated in Secrets Manager")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
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
                athlete_id = str(tokens.get('athlete', {}).get('id', ''))
                if athlete_id:
                    # Fetch athlete zones (HR + power) using the new access token
                    athlete_zones = None
                    try:
                        zones_response = requests.get(
                            'https://www.strava.com/api/v3/athlete/zones',
                            headers={'Authorization': f"Bearer {tokens['access_token']}"},
                            timeout=10
                        )
                        if zones_response.status_code == 200:
                            athlete_zones = zones_response.json()
                            logger.info(f"Fetched athlete zones for {athlete_id}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch athlete zones: {e}")

                    update_expr = "SET strava_connected = :conn, connected_at = :cat, athlete_name = :name, scopes = :sc, updated_at = :upd"
                    expr_values = {
                        ':conn': True,
                        ':cat': datetime.now(UTC).isoformat(),
                        ':name': f"{tokens.get('athlete', {}).get('firstname', '')} {tokens.get('athlete', {}).get('lastname', '')}".strip(),
                        ':sc': tokens.get('scope', '').split(','),
                        ':upd': datetime.now(UTC).isoformat()
                    }
                    if athlete_zones:
                        update_expr += ", athlete_zones = :zones"
                        expr_values[':zones'] = athlete_zones

                    table = dynamodb.Table(USER_CONFIG_TABLE)
                    table.update_item(
                        Key={'user_id': athlete_id},
                        UpdateExpression=update_expr,
                        ExpressionAttributeValues=expr_values
                    )
                    logger.info(f"OAuth status updated for athlete {athlete_id}")

                    # Set strava_id on Cognito user for JWT-based user identification
                    try:
                        cognito_client = boto3.client('cognito-idp', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
                        user_pool_id = os.environ.get('COGNITO_USER_POOL_ID', '')
                        # Find user by email from the request context
                        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
                        username = claims.get('cognito:username', claims.get('sub', ''))
                        if user_pool_id and username:
                            cognito_client.admin_update_user_attributes(
                                UserPoolId=user_pool_id,
                                Username=username,
                                UserAttributes=[{'Name': 'custom:strava_id', 'Value': athlete_id}]
                            )
                            logger.info(f"Set custom:strava_id={athlete_id} on Cognito user {username}")
                    except Exception as e:
                        logger.warning(f"Failed to set strava_id on Cognito user: {e}")
            except ClientError as e:
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
            }, cors_headers=CORS_HEADERS)

        except ClientError as e:
            logger.error(f"AWS Secrets Manager error: {e}")
            return create_error_response(500, 'Failed to store tokens securely', cors_headers=CORS_HEADERS)

    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        return create_error_response(500, 'OAuth callback failed', cors_headers=CORS_HEADERS)


def get_modules() -> Dict[str, Any]:
    """Get available modules and their configurations"""
    try:
        user_id = get_authenticated_user_id()

        table = dynamodb.Table(USER_CONFIG_TABLE)

        try:
            response = table.get_item(Key={'user_id': user_id})
            stored_config = response.get('Item', {})
        except ClientError as e:
            logger.warning(f"Failed to get user config from DynamoDB: {e}")
            stored_config = {}

        modules_config = stored_config.get('modules_config', {})

        campus_coach_config = modules_config.get('campus_coach', {})
        campus_coach_enabled = campus_coach_config.get('enabled', False)
        campus_coach_configured = campus_coach_config.get('configured', False)

        enduraw_config = modules_config.get('enduraw', {})
        enduraw_enabled = enduraw_config.get('enabled', False)
        enduraw_wait_time = enduraw_config.get('wait_time', '2 minutes')

        intervals_icu_config = modules_config.get('intervals_icu', {})
        intervals_icu_enabled = intervals_icu_config.get('enabled', False)
        intervals_icu_configured = intervals_icu_config.get('configured', False)

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
                'configured': True,
                'requires_credentials': False,
                'wait_time': enduraw_wait_time,
                'status': 'active' if enduraw_enabled else 'disabled'
            },
            'intervals_icu': {
                'id': 'intervals_icu',
                'name': 'Intervals.icu',
                'description': 'Fitness metrics, training load, and recovery analysis',
                'enabled': intervals_icu_enabled,
                'configured': intervals_icu_configured,
                'requires_credentials': True,
                'status': 'active' if intervals_icu_enabled else 'disabled'
            }
        }

        return create_success_response({'modules': modules}, cors_headers=CORS_HEADERS)

    except Exception as e:
        logger.error(f"Get modules error: {str(e)}")
        return create_error_response(500, 'Failed to get modules', cors_headers=CORS_HEADERS)


def configure_module(event: Dict[str, Any]) -> Dict[str, Any]:
    """Configure a module"""
    try:
        body = json.loads(event.get('body', '{}'))
        module_id = body.get('module_id')
        enabled = body.get('enabled', False)
        config = body.get('config', {})

        if not module_id or module_id not in ['campus_coach', 'enduraw', 'intervals_icu']:
            return create_error_response(400, 'Invalid or missing module_id', cors_headers=CORS_HEADERS)

        user_id = get_authenticated_user_id()

        # Handle Campus Coach configuration
        if module_id == 'campus_coach' and enabled:
            credentials = config.get('credentials', {})

            if credentials.get('username') and credentials.get('password'):
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
                        secretsmanager.create_secret(
                            Name=CAMPUS_COACH_SECRET,
                            Description='Campus Coach credentials for AI Boost',
                            SecretString=json.dumps(credential_data)
                        )
                        logger.info("Campus Coach secret created")
                    else:
                        raise
            else:
                try:
                    response = secretsmanager.get_secret_value(SecretId=CAMPUS_COACH_SECRET)
                    secret_data = json.loads(response['SecretString'])

                    if not secret_data.get('username') or not secret_data.get('password'):
                        return create_error_response(400, 'Campus Coach credentials in Secrets Manager are incomplete. Please reconfigure.', cors_headers=CORS_HEADERS)

                    logger.info("Campus Coach credentials already exist in Secrets Manager")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        return create_error_response(400, 'Campus Coach credentials required when enabling for the first time', cors_headers=CORS_HEADERS)
                    else:
                        raise

        # Handle Intervals.icu configuration
        if module_id == 'intervals_icu' and enabled:
            api_key = config.get('api_key', '')

            if api_key:
                try:
                    credential_data = {
                        'api_key': api_key,
                        'configured_at': datetime.now(UTC).isoformat()
                    }
                    secretsmanager.put_secret_value(
                        SecretId=INTERVALS_ICU_SECRET,
                        SecretString=json.dumps(credential_data)
                    )
                    logger.info("Intervals.icu API key stored")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        secretsmanager.create_secret(
                            Name=INTERVALS_ICU_SECRET,
                            Description='Intervals.icu API key for AI Boost',
                            SecretString=json.dumps(credential_data)
                        )
                        logger.info("Intervals.icu secret created")
                    else:
                        raise
            else:
                try:
                    response = secretsmanager.get_secret_value(SecretId=INTERVALS_ICU_SECRET)
                    secret_data = json.loads(response['SecretString'])
                    if not secret_data.get('api_key'):
                        return create_error_response(400, 'Intervals.icu API key in Secrets Manager is empty. Please reconfigure.', cors_headers=CORS_HEADERS)
                    logger.info("Intervals.icu API key already exists in Secrets Manager")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        return create_error_response(400, 'Intervals.icu API key required when enabling for the first time', cors_headers=CORS_HEADERS)
                    else:
                        raise

        # Store module configuration in DynamoDB (user-specific)
        table = dynamodb.Table(USER_CONFIG_TABLE)

        try:
            response = table.get_item(Key={'user_id': user_id})
            user_config = response.get('Item', {'user_id': user_id})
        except ClientError:
            user_config = {'user_id': user_id}

        if 'modules_config' not in user_config:
            user_config['modules_config'] = {}

        if module_id not in user_config['modules_config']:
            user_config['modules_config'][module_id] = {}

        user_config['modules_config'][module_id]['enabled'] = enabled
        user_config['modules_config'][module_id]['configured'] = True
        user_config['modules_config'][module_id]['updated_at'] = datetime.now(UTC).isoformat()

        if module_id == 'enduraw':
            user_config['modules_config'][module_id]['wait_time'] = config.get('wait_time', '2 minutes')

        table.put_item(Item=user_config)

        # Enable/Disable EventBridge Scheduler for Campus Coach if applicable
        if module_id == 'campus_coach':
            try:
                events_client = boto3.client('events')
                rule_name = 'StravaAIBoost-CampusCoach-DailyExtraction'

                if enabled:
                    events_client.enable_rule(Name=rule_name)
                    logger.info("Enabled EventBridge scheduler for Campus Coach")
                else:
                    events_client.disable_rule(Name=rule_name)
                    logger.info("Disabled EventBridge scheduler for Campus Coach")
            except ClientError as e:
                logger.warning(f"Failed to update EventBridge scheduler: {str(e)}")

        status_label = "configured" if enabled else "unconfigured"
        logger.info(f"Module {module_id} {status_label} for user {user_id}: enabled={enabled}")

        return create_success_response({
            'status': status_label,
            'module_id': module_id,
            'enabled': enabled,
            'message': f'{module_id.replace("_", " ").title()} {"enabled" if enabled else "disabled"} successfully'
        }, cors_headers=CORS_HEADERS)

    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', cors_headers=CORS_HEADERS)
    except ClientError as e:
        logger.error(f"AWS error during module configuration: {str(e)}")
        return create_error_response(500, 'Module configuration failed', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Configure module error: {str(e)}")
        return create_error_response(500, 'Module configuration failed', cors_headers=CORS_HEADERS)


def get_enhancement_status() -> Dict[str, Any]:
    """Get current enhancement status (enabled/paused) for user"""
    try:
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
                }, cors_headers=CORS_HEADERS)
            else:
                return create_success_response({
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'enhancement_resumed_at': None,
                    'status': 'active'
                }, cors_headers=CORS_HEADERS)

        except ClientError as e:
            logger.warning(f"Failed to get enhancement status from DynamoDB: {e}")
            return create_success_response({
                'enhancement_enabled': True,
                'enhancement_paused_at': None,
                'status': 'active'
            }, cors_headers=CORS_HEADERS)

    except Exception as e:
        logger.error(f"Get enhancement status error: {str(e)}")
        return create_error_response(500, 'Failed to get enhancement status', cors_headers=CORS_HEADERS)


def toggle_enhancement_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """Toggle enhancement status (pause/resume) for user"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')  # 'pause' or 'resume'

        if action not in ['pause', 'resume']:
            return create_error_response(400, 'Invalid action. Use "pause" or "resume"', cors_headers=CORS_HEADERS)

        user_id = get_authenticated_user_id()

        table = dynamodb.Table(USER_CONFIG_TABLE)
        current_time = datetime.now(UTC).isoformat()

        try:
            response = table.get_item(Key={'user_id': user_id})
            user_config = response.get('Item', {'user_id': user_id})
        except ClientError:
            user_config = {'user_id': user_id}

        if action == 'pause':
            user_config['enhancement_enabled'] = False
            user_config['enhancement_paused_at'] = current_time
            user_config['updated_at'] = current_time

            table.put_item(Item=user_config)

            logger.info(f"Enhancement paused for user {user_id}")

            return create_success_response({
                'status': 'paused',
                'paused_at': current_time,
                'message': 'Enhancement has been paused. New activities will not be processed.'
            }, cors_headers=CORS_HEADERS)

        else:  # resume
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
            }, cors_headers=CORS_HEADERS)

    except json.JSONDecodeError:
        return create_error_response(400, 'Invalid JSON in request body', cors_headers=CORS_HEADERS)
    except ClientError as e:
        logger.error(f"DynamoDB error toggling enhancement: {str(e)}")
        return create_error_response(500, 'Failed to toggle enhancement status', cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Toggle enhancement status error: {str(e)}")
        return create_error_response(500, 'Failed to toggle enhancement status', cors_headers=CORS_HEADERS)
