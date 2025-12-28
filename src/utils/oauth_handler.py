"""
Strava OAuth Handler with PKCE Support

Handles OAuth 2.0 authorization flow with PKCE for secure token exchange.
Implements Requirements 1.2, 1.3, 7.3 for secure Strava API authentication.
"""

import os
import secrets
import hashlib
import base64
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse
import boto3
from botocore.exceptions import ClientError
import requests
from requests_oauthlib import OAuth2Session
from datetime import datetime, timedelta, UTC
import json
import logging

logger = logging.getLogger(__name__)


class StravaOAuthHandler:
    """
    Handles Strava OAuth 2.0 flow with PKCE support.
    
    Implements secure token storage in AWS Secrets Manager and automatic refresh.
    """
    
    def __init__(self, 
                 client_id: str,
                 client_secret: str,
                 redirect_uri: str = "http://localhost:3000/oauth/callback",
                 secrets_manager_secret_name: str = "strava-ai-boost-oauth-tokens"):
        """
        Initialize OAuth handler.
        
        Args:
            client_id: Strava application client ID
            client_secret: Strava application client secret
            redirect_uri: OAuth callback URI
            secrets_manager_secret_name: AWS Secrets Manager secret name for token storage
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.secrets_manager_secret_name = secrets_manager_secret_name
        
        # Strava OAuth endpoints
        self.authorization_base_url = "https://www.strava.com/oauth/authorize"
        self.token_url = "https://www.strava.com/oauth/token"
        
        # AWS Secrets Manager client
        self.secrets_client = boto3.client('secretsmanager')
        
        # OAuth scopes for Strava API
        self.scopes = ["read,activity:write"]
    
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge (SHA256 hash of verifier)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Generate OAuth authorization URL with PKCE.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Tuple of (authorization_url, state, code_verifier)
        """
        if state is None:
            state = secrets.token_urlsafe(32)
        
        code_verifier, code_challenge = self.generate_pkce_pair()
        
        # Create OAuth2 session
        oauth = OAuth2Session(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope=self.scopes,
            state=state
        )
        
        # Generate authorization URL with PKCE parameters
        authorization_url, state = oauth.authorization_url(
            self.authorization_base_url,
            code_challenge=code_challenge,
            code_challenge_method='S256',
            approval_prompt='force'  # Force re-authorization for fresh tokens
        )
        
        logger.info(f"Generated authorization URL for client_id: {self.client_id}")
        
        return authorization_url, state, code_verifier
    
    def exchange_code_for_tokens(self, 
                                authorization_response: str, 
                                code_verifier: str,
                                state: str) -> Dict[str, any]:
        """
        Exchange authorization code for access tokens.
        
        Args:
            authorization_response: Full callback URL with authorization code
            code_verifier: PKCE code verifier from authorization step
            state: State parameter for CSRF validation
            
        Returns:
            Dictionary containing token information
            
        Raises:
            ValueError: If authorization fails or tokens are invalid
        """
        try:
            # Parse authorization response
            parsed_url = urlparse(authorization_response)
            query_params = parse_qs(parsed_url.query)
            
            # Validate state parameter
            response_state = query_params.get('state', [None])[0]
            if response_state != state:
                raise ValueError("State parameter mismatch - possible CSRF attack")
            
            # Check for authorization errors
            if 'error' in query_params:
                error = query_params['error'][0]
                error_description = query_params.get('error_description', ['Unknown error'])[0]
                raise ValueError(f"Authorization error: {error} - {error_description}")
            
            # Extract authorization code
            auth_code = query_params.get('code', [None])[0]
            if not auth_code:
                raise ValueError("No authorization code received")
            
            # Exchange code for tokens
            token_data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': auth_code,
                'grant_type': 'authorization_code',
                'code_verifier': code_verifier
            }
            
            response = requests.post(self.token_url, data=token_data)
            response.raise_for_status()
            
            tokens = response.json()
            
            # Validate token response
            required_fields = ['access_token', 'refresh_token', 'expires_at']
            for field in required_fields:
                if field not in tokens:
                    raise ValueError(f"Missing required field in token response: {field}")
            
            # Add metadata
            tokens['obtained_at'] = datetime.now(UTC).isoformat()
            tokens['client_id'] = self.client_id
            
            logger.info("Successfully exchanged authorization code for tokens")
            
            return tokens
            
        except requests.RequestException as e:
            logger.error(f"HTTP error during token exchange: {e}")
            raise ValueError(f"Failed to exchange authorization code: {e}")
        except Exception as e:
            logger.error(f"Error during token exchange: {e}")
            raise
    
    def store_tokens_securely(self, tokens: Dict[str, any], user_id: str = "default") -> bool:
        """
        Store OAuth tokens securely in AWS Secrets Manager.
        
        Args:
            tokens: Token dictionary from OAuth exchange
            user_id: User identifier for multi-user support
            
        Returns:
            True if storage successful, False otherwise
        """
        try:
            # Prepare secret value
            secret_value = {
                'user_id': user_id,
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'expires_at': tokens['expires_at'],
                'token_type': tokens.get('token_type', 'Bearer'),
                'scope': tokens.get('scope', 'read,activity:write'),
                'obtained_at': tokens.get('obtained_at', datetime.now(UTC).isoformat()),
                'client_id': tokens.get('client_id', self.client_id),
                'last_refreshed': None
            }
            
            # Store in Secrets Manager
            try:
                # Try to update existing secret
                self.secrets_client.update_secret(
                    SecretId=self.secrets_manager_secret_name,
                    SecretString=json.dumps(secret_value)
                )
                logger.info(f"Updated existing secret: {self.secrets_manager_secret_name}")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create new secret if it doesn't exist
                    self.secrets_client.create_secret(
                        Name=self.secrets_manager_secret_name,
                        Description=f"Strava OAuth tokens for Strava AI Boost - User: {user_id}",
                        SecretString=json.dumps(secret_value)
                    )
                    logger.info(f"Created new secret: {self.secrets_manager_secret_name}")
                else:
                    raise
            
            return True
            
        except ClientError as e:
            logger.error(f"AWS Secrets Manager error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error storing tokens: {e}")
            return False
    
    def get_stored_tokens(self, user_id: str = "default") -> Optional[Dict[str, any]]:
        """
        Retrieve stored OAuth tokens from AWS Secrets Manager.
        
        Args:
            user_id: User identifier
            
        Returns:
            Token dictionary if found, None otherwise
        """
        try:
            response = self.secrets_client.get_secret_value(
                SecretId=self.secrets_manager_secret_name
            )
            
            tokens = json.loads(response['SecretString'])
            
            # Handle missing or None user_id in stored tokens
            stored_user_id = tokens.get('user_id')
            if stored_user_id is None:
                logger.info(f"No user_id in stored tokens, setting to default: {user_id}")
                tokens['user_id'] = user_id
                # Update the stored tokens with the user_id
                self.store_tokens_securely(tokens, user_id)
            elif stored_user_id != user_id:
                logger.warning(f"User ID mismatch in stored tokens: expected {user_id}, got {stored_user_id}")
                # For single-user applications, allow fallback to default
                if user_id == "default" or stored_user_id == "default":
                    logger.info("Allowing fallback for single-user application")
                    tokens['user_id'] = user_id
                else:
                    return None
            
            return tokens
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info(f"No stored tokens found for secret: {self.secrets_manager_secret_name}")
                return None
            else:
                logger.error(f"Error retrieving tokens: {e}")
                return None
        except Exception as e:
            logger.error(f"Error parsing stored tokens: {e}")
            return None
    
    def is_token_expired(self, tokens: Dict[str, any]) -> bool:
        """
        Check if access token is expired or will expire soon.
        
        Args:
            tokens: Token dictionary
            
        Returns:
            True if token is expired or expires within 5 minutes
        """
        try:
            expires_at = tokens.get('expires_at')
            if not expires_at:
                return True
            
            # Convert to datetime (handle both timestamp and ISO format)
            if isinstance(expires_at, (int, float)):
                expiry_time = datetime.fromtimestamp(expires_at, tz=UTC)
            else:
                try:
                    # Try ISO format first
                    expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if expiry_time.tzinfo is None:
                        expiry_time = expiry_time.replace(tzinfo=UTC)
                except ValueError:
                    # Fallback to timestamp parsing
                    try:
                        expiry_time = datetime.fromtimestamp(float(expires_at), tz=UTC)
                    except (ValueError, TypeError):
                        logger.error(f"Unable to parse expires_at: {expires_at}")
                        return True
            
            # Check if expires within 5 minutes (buffer for safety)
            buffer_time = datetime.now(UTC) + timedelta(minutes=5)
            
            is_expired = expiry_time <= buffer_time
            
            if is_expired:
                logger.info(f"Token expires at {expiry_time}, current time + buffer: {buffer_time}")
            
            return is_expired
            
        except Exception as e:
            logger.error(f"Error checking token expiry: {e}")
            return True  # Assume expired on error
    
    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, any]]:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            New token dictionary if successful, None otherwise
        """
        try:
            token_data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }
            
            logger.info(f"Attempting to refresh token with client_id: {self.client_id}")
            
            response = requests.post(self.token_url, data=token_data)
            
            # Log response details for debugging
            logger.info(f"Token refresh response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
                return None
            
            new_tokens = response.json()
            
            # Validate response
            if 'access_token' not in new_tokens:
                logger.error(f"Invalid token refresh response: {new_tokens}")
                return None
            
            # Add metadata
            new_tokens['obtained_at'] = datetime.now(UTC).isoformat()
            new_tokens['last_refreshed'] = datetime.now(UTC).isoformat()
            new_tokens['client_id'] = self.client_id
            
            logger.info("Successfully refreshed access token")
            
            return new_tokens
            
        except requests.RequestException as e:
            logger.error(f"HTTP error during token refresh: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None
    
    def get_valid_access_token(self, user_id: str = "default") -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Args:
            user_id: User identifier
            
        Returns:
            Valid access token string if available, None otherwise
        """
        try:
            # Get stored tokens
            tokens = self.get_stored_tokens(user_id)
            if not tokens:
                logger.info("No stored tokens found")
                return None
            
            # Check if token needs refresh
            if self.is_token_expired(tokens):
                logger.info("Access token expired, attempting refresh")
                
                # Refresh token
                new_tokens = self.refresh_access_token(tokens['refresh_token'])
                if not new_tokens:
                    logger.error("Failed to refresh access token")
                    return None
                
                # Store refreshed tokens
                if not self.store_tokens_securely(new_tokens, user_id):
                    logger.error("Failed to store refreshed tokens")
                    return None
                
                return new_tokens['access_token']
            
            return tokens['access_token']
            
        except Exception as e:
            logger.error(f"Error getting valid access token: {e}")
            return None
    
    def revoke_tokens(self, user_id: str = "default") -> bool:
        """
        Revoke stored tokens and remove from Secrets Manager.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get stored tokens for revocation
            tokens = self.get_stored_tokens(user_id)
            
            if tokens and tokens.get('access_token'):
                # Revoke with Strava (best effort)
                try:
                    revoke_data = {
                        'access_token': tokens['access_token']
                    }
                    requests.post("https://www.strava.com/oauth/deauthorize", data=revoke_data)
                    logger.info("Revoked tokens with Strava")
                except Exception as e:
                    logger.warning(f"Failed to revoke with Strava (continuing): {e}")
            
            # Delete from Secrets Manager
            try:
                self.secrets_client.delete_secret(
                    SecretId=self.secrets_manager_secret_name,
                    ForceDeleteWithoutRecovery=True
                )
                logger.info(f"Deleted secret: {self.secrets_manager_secret_name}")
                return True
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.info("Secret already deleted or not found")
                    return True
                else:
                    logger.error(f"Error deleting secret: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error revoking tokens: {e}")
            return False
    
    def get_connection_status(self, user_id: str = "default") -> Dict[str, any]:
        """
        Get current OAuth connection status.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with connection status information
        """
        try:
            tokens = self.get_stored_tokens(user_id)
            
            if not tokens:
                return {
                    'connected': False,
                    'status': 'not_connected',
                    'message': 'No OAuth tokens found'
                }
            
            # Check token validity
            is_expired = self.is_token_expired(tokens)
            
            if is_expired:
                # Try to refresh
                valid_token = self.get_valid_access_token(user_id)
                if valid_token:
                    return {
                        'connected': True,
                        'status': 'connected',
                        'message': 'Connected (token refreshed)',
                        'obtained_at': tokens.get('obtained_at'),
                        'last_refreshed': datetime.now(UTC).isoformat()
                    }
                else:
                    return {
                        'connected': False,
                        'status': 'token_expired',
                        'message': 'Tokens expired and refresh failed',
                        'obtained_at': tokens.get('obtained_at')
                    }
            
            return {
                'connected': True,
                'status': 'connected',
                'message': 'Connected with valid tokens',
                'obtained_at': tokens.get('obtained_at'),
                'last_refreshed': tokens.get('last_refreshed')
            }
            
        except Exception as e:
            logger.error(f"Error checking connection status: {e}")
            return {
                'connected': False,
                'status': 'error',
                'message': f'Error checking status: {str(e)}'
            }


def create_oauth_handler_from_env() -> StravaOAuthHandler:
    """
    Create OAuth handler from environment variables.
    
    Expected environment variables:
    - STRAVA_CLIENT_ID: Strava application client ID
    - STRAVA_CLIENT_SECRET: Strava application client secret
    - STRAVA_REDIRECT_URI: OAuth callback URI (optional)
    - OAUTH_SECRETS_NAME: Secrets Manager secret name (optional)
    
    Returns:
        Configured StravaOAuthHandler instance
        
    Raises:
        ValueError: If required environment variables are missing
    """
    client_id = os.getenv('STRAVA_CLIENT_ID')
    client_secret = os.getenv('STRAVA_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError("STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET environment variables are required")
    
    redirect_uri = os.getenv('STRAVA_REDIRECT_URI', 'http://localhost:8080/auth/callback')
    secrets_name = os.getenv('OAUTH_SECRETS_NAME', 'strava-ai-boost-oauth-tokens')
    
    return StravaOAuthHandler(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        secrets_manager_secret_name=secrets_name
    )