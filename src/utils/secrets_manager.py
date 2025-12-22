"""
AWS Secrets Manager Helper for Secure Token Storage

Implements secure token storage with automatic rotation capabilities.
Handles Requirements 1.3, 1.5, 7.3 for secure credential management.
"""

import json
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta, UTC
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SecretMetadata:
    """Metadata for a secret in Secrets Manager"""
    name: str
    arn: str
    description: Optional[str]
    created_date: datetime
    last_accessed_date: Optional[datetime]
    last_changed_date: Optional[datetime]
    last_rotated_date: Optional[datetime]
    rotation_enabled: bool
    rotation_lambda_arn: Optional[str]
    rotation_rules: Optional[Dict[str, Any]]


class SecretsManagerHelper:
    """
    Helper class for AWS Secrets Manager operations.
    
    Provides secure storage, retrieval, and rotation management for OAuth tokens
    and other sensitive credentials.
    """
    
    def __init__(self, region_name: str = 'eu-west-1'):
        """
        Initialize Secrets Manager helper.
        
        Args:
            region_name: AWS region for Secrets Manager
        """
        self.region_name = region_name
        self.client = boto3.client('secretsmanager', region_name=region_name)
    
    def create_secret(self, 
                     name: str, 
                     secret_value: Dict[str, Any], 
                     description: str = "",
                     kms_key_id: Optional[str] = None,
                     enable_rotation: bool = False,
                     rotation_lambda_arn: Optional[str] = None,
                     rotation_interval_days: int = 30) -> bool:
        """
        Create a new secret in AWS Secrets Manager.
        
        Args:
            name: Secret name
            secret_value: Dictionary containing secret data
            description: Secret description
            kms_key_id: KMS key ID for encryption (optional)
            enable_rotation: Whether to enable automatic rotation
            rotation_lambda_arn: Lambda function ARN for rotation
            rotation_interval_days: Rotation interval in days
            
        Returns:
            True if successful, False otherwise
        """
        try:
            create_params = {
                'Name': name,
                'Description': description,
                'SecretString': json.dumps(secret_value)
            }
            
            # Add KMS key if specified
            if kms_key_id:
                create_params['KmsKeyId'] = kms_key_id
            
            # Create the secret
            response = self.client.create_secret(**create_params)
            secret_arn = response['ARN']
            
            logger.info(f"Created secret: {name} (ARN: {secret_arn})")
            
            # Enable rotation if requested
            if enable_rotation and rotation_lambda_arn:
                self.enable_rotation(
                    secret_name=name,
                    lambda_arn=rotation_lambda_arn,
                    rotation_interval_days=rotation_interval_days
                )
            
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceExistsException':
                logger.warning(f"Secret {name} already exists")
                return False
            else:
                logger.error(f"Error creating secret {name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error creating secret {name}: {e}")
            return False
    
    def update_secret(self, 
                     name: str, 
                     secret_value: Dict[str, Any],
                     description: Optional[str] = None) -> bool:
        """
        Update an existing secret's value.
        
        Args:
            name: Secret name
            secret_value: New secret data
            description: Updated description (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            update_params = {
                'SecretId': name,
                'SecretString': json.dumps(secret_value)
            }
            
            if description:
                update_params['Description'] = description
            
            self.client.update_secret(**update_params)
            logger.info(f"Updated secret: {name}")
            return True
            
        except ClientError as e:
            logger.error(f"Error updating secret {name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating secret {name}: {e}")
            return False
    
    def get_secret(self, name: str, version_stage: str = 'AWSCURRENT') -> Optional[Dict[str, Any]]:
        """
        Retrieve secret value from Secrets Manager.
        
        Args:
            name: Secret name or ARN
            version_stage: Version stage to retrieve (AWSCURRENT, AWSPENDING)
            
        Returns:
            Secret data as dictionary, None if not found
        """
        try:
            response = self.client.get_secret_value(
                SecretId=name,
                VersionStage=version_stage
            )
            
            secret_data = json.loads(response['SecretString'])
            logger.debug(f"Retrieved secret: {name}")
            return secret_data
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.info(f"Secret not found: {name}")
                return None
            elif error_code == 'DecryptionFailureException':
                logger.error(f"Failed to decrypt secret: {name}")
                return None
            else:
                logger.error(f"Error retrieving secret {name}: {e}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing secret JSON for {name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving secret {name}: {e}")
            return None
    
    def delete_secret(self, 
                     name: str, 
                     force_delete: bool = False,
                     recovery_window_days: int = 30) -> bool:
        """
        Delete a secret from Secrets Manager.
        
        Args:
            name: Secret name or ARN
            force_delete: If True, delete immediately without recovery window
            recovery_window_days: Days to wait before permanent deletion (7-30)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            delete_params = {'SecretId': name}
            
            if force_delete:
                delete_params['ForceDeleteWithoutRecovery'] = True
            else:
                delete_params['RecoveryWindowInDays'] = recovery_window_days
            
            self.client.delete_secret(**delete_params)
            
            action = "immediately" if force_delete else f"in {recovery_window_days} days"
            logger.info(f"Scheduled secret deletion {action}: {name}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.info(f"Secret not found for deletion: {name}")
                return True  # Consider success if already deleted
            else:
                logger.error(f"Error deleting secret {name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting secret {name}: {e}")
            return False
    
    def enable_rotation(self, 
                       secret_name: str,
                       lambda_arn: str,
                       rotation_interval_days: int = 30) -> bool:
        """
        Enable automatic rotation for a secret.
        
        Args:
            secret_name: Secret name or ARN
            lambda_arn: Lambda function ARN for rotation
            rotation_interval_days: Rotation interval (1-365 days)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.rotate_secret(
                SecretId=secret_name,
                RotationLambdaArn=lambda_arn,
                RotationRules={
                    'AutomaticallyAfterDays': rotation_interval_days
                }
            )
            
            logger.info(f"Enabled rotation for secret {secret_name} every {rotation_interval_days} days")
            return True
            
        except ClientError as e:
            logger.error(f"Error enabling rotation for secret {secret_name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error enabling rotation for secret {secret_name}: {e}")
            return False
    
    def disable_rotation(self, secret_name: str) -> bool:
        """
        Disable automatic rotation for a secret.
        
        Args:
            secret_name: Secret name or ARN
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.cancel_rotate_secret(SecretId=secret_name)
            logger.info(f"Disabled rotation for secret: {secret_name}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.info(f"Secret not found: {secret_name}")
                return True
            elif error_code == 'InvalidRequestException':
                logger.info(f"Rotation not enabled for secret: {secret_name}")
                return True
            else:
                logger.error(f"Error disabling rotation for secret {secret_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error disabling rotation for secret {secret_name}: {e}")
            return False
    
    def get_secret_metadata(self, name: str) -> Optional[SecretMetadata]:
        """
        Get metadata for a secret.
        
        Args:
            name: Secret name or ARN
            
        Returns:
            SecretMetadata object if found, None otherwise
        """
        try:
            response = self.client.describe_secret(SecretId=name)
            
            metadata = SecretMetadata(
                name=response['Name'],
                arn=response['ARN'],
                description=response.get('Description'),
                created_date=response['CreatedDate'],
                last_accessed_date=response.get('LastAccessedDate'),
                last_changed_date=response.get('LastChangedDate'),
                last_rotated_date=response.get('LastRotatedDate'),
                rotation_enabled=response.get('RotationEnabled', False),
                rotation_lambda_arn=response.get('RotationLambdaArn'),
                rotation_rules=response.get('RotationRules')
            )
            
            return metadata
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.info(f"Secret not found: {name}")
                return None
            else:
                logger.error(f"Error getting metadata for secret {name}: {e}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error getting metadata for secret {name}: {e}")
            return None
    
    def list_secrets(self, 
                    name_filter: Optional[str] = None,
                    max_results: int = 100) -> List[SecretMetadata]:
        """
        List secrets in the account.
        
        Args:
            name_filter: Filter secrets by name pattern
            max_results: Maximum number of results to return
            
        Returns:
            List of SecretMetadata objects
        """
        try:
            list_params = {'MaxResults': max_results}
            
            if name_filter:
                list_params['Filters'] = [
                    {
                        'Key': 'name',
                        'Values': [name_filter]
                    }
                ]
            
            response = self.client.list_secrets(**list_params)
            
            secrets = []
            for secret_info in response.get('SecretList', []):
                metadata = SecretMetadata(
                    name=secret_info['Name'],
                    arn=secret_info['ARN'],
                    description=secret_info.get('Description'),
                    created_date=secret_info['CreatedDate'],
                    last_accessed_date=secret_info.get('LastAccessedDate'),
                    last_changed_date=secret_info.get('LastChangedDate'),
                    last_rotated_date=secret_info.get('LastRotatedDate'),
                    rotation_enabled=secret_info.get('RotationEnabled', False),
                    rotation_lambda_arn=secret_info.get('RotationLambdaArn'),
                    rotation_rules=secret_info.get('RotationRules')
                )
                secrets.append(metadata)
            
            logger.info(f"Listed {len(secrets)} secrets")
            return secrets
            
        except ClientError as e:
            logger.error(f"Error listing secrets: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing secrets: {e}")
            return []
    
    def create_or_update_secret(self, 
                               name: str, 
                               secret_value: Dict[str, Any],
                               description: str = "",
                               **kwargs) -> bool:
        """
        Create a new secret or update existing one.
        
        Args:
            name: Secret name
            secret_value: Secret data
            description: Secret description
            **kwargs: Additional arguments for create_secret
            
        Returns:
            True if successful, False otherwise
        """
        # Try to get existing secret
        existing_secret = self.get_secret(name)
        
        if existing_secret is not None:
            # Update existing secret
            return self.update_secret(name, secret_value, description)
        else:
            # Create new secret
            return self.create_secret(name, secret_value, description, **kwargs)


class StravaTokenManager:
    """
    Specialized manager for Strava OAuth tokens with automatic rotation.
    
    Handles secure storage and automatic refresh of Strava API tokens.
    """
    
    def __init__(self, 
                 secrets_helper: Optional[SecretsManagerHelper] = None,
                 secret_name: str = "strava-ai-boost-oauth-tokens"):
        """
        Initialize token manager.
        
        Args:
            secrets_helper: SecretsManagerHelper instance (creates new if None)
            secret_name: Name for the OAuth tokens secret
        """
        self.secrets_helper = secrets_helper or SecretsManagerHelper()
        self.secret_name = secret_name
    
    def store_oauth_tokens(self, 
                          tokens: Dict[str, Any], 
                          user_id: str = "default") -> bool:
        """
        Store OAuth tokens securely with metadata.
        
        Args:
            tokens: OAuth token dictionary
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare token data with metadata
            token_data = {
                'user_id': user_id,
                'access_token': tokens['access_token'],
                'refresh_token': tokens['refresh_token'],
                'expires_at': tokens['expires_at'],
                'token_type': tokens.get('token_type', 'Bearer'),
                'scope': tokens.get('scope', 'read,activity:write'),
                'obtained_at': tokens.get('obtained_at', datetime.now(UTC).isoformat()),
                'client_id': tokens.get('client_id'),
                'last_refreshed': tokens.get('last_refreshed'),
                'refresh_count': tokens.get('refresh_count', 0),
                'created_at': datetime.now(UTC).isoformat()
            }
            
            description = f"Strava OAuth tokens for user: {user_id}"
            
            return self.secrets_helper.create_or_update_secret(
                name=self.secret_name,
                secret_value=token_data,
                description=description
            )
            
        except Exception as e:
            logger.error(f"Error storing OAuth tokens: {e}")
            return False
    
    def get_oauth_tokens(self, user_id: str = "default") -> Optional[Dict[str, Any]]:
        """
        Retrieve OAuth tokens for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Token dictionary if found and valid, None otherwise
        """
        try:
            token_data = self.secrets_helper.get_secret(self.secret_name)
            
            if not token_data:
                return None
            
            # Validate user_id
            if token_data.get('user_id') != user_id:
                logger.warning(f"User ID mismatch: expected {user_id}, got {token_data.get('user_id')}")
                return None
            
            return token_data
            
        except Exception as e:
            logger.error(f"Error retrieving OAuth tokens: {e}")
            return None
    
    def update_refreshed_tokens(self, 
                               new_tokens: Dict[str, Any], 
                               user_id: str = "default") -> bool:
        """
        Update tokens after refresh operation.
        
        Args:
            new_tokens: Refreshed token data
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing token data to preserve metadata
            existing_data = self.get_oauth_tokens(user_id)
            if not existing_data:
                logger.error("No existing tokens found for refresh update")
                return False
            
            # Update with new token data
            updated_data = existing_data.copy()
            updated_data.update({
                'access_token': new_tokens['access_token'],
                'refresh_token': new_tokens.get('refresh_token', existing_data['refresh_token']),
                'expires_at': new_tokens['expires_at'],
                'last_refreshed': datetime.now(UTC).isoformat(),
                'refresh_count': existing_data.get('refresh_count', 0) + 1
            })
            
            return self.secrets_helper.update_secret(
                name=self.secret_name,
                secret_value=updated_data
            )
            
        except Exception as e:
            logger.error(f"Error updating refreshed tokens: {e}")
            return False
    
    def delete_oauth_tokens(self, user_id: str = "default") -> bool:
        """
        Delete OAuth tokens for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Verify user_id matches before deletion
            token_data = self.get_oauth_tokens(user_id)
            if token_data and token_data.get('user_id') == user_id:
                return self.secrets_helper.delete_secret(
                    name=self.secret_name,
                    force_delete=True
                )
            else:
                logger.warning(f"Token deletion skipped: user_id mismatch or no tokens found")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting OAuth tokens: {e}")
            return False
    
    def get_token_status(self, user_id: str = "default") -> Dict[str, Any]:
        """
        Get comprehensive token status information.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with token status details
        """
        try:
            tokens = self.get_oauth_tokens(user_id)
            
            if not tokens:
                return {
                    'exists': False,
                    'valid': False,
                    'message': 'No tokens found'
                }
            
            # Check expiry
            expires_at = tokens.get('expires_at')
            is_expired = True
            expires_in_seconds = 0
            
            if expires_at:
                try:
                    if isinstance(expires_at, (int, float)):
                        expiry_time = datetime.fromtimestamp(expires_at)
                    else:
                        expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    
                    now = datetime.now(UTC)
                    expires_in_seconds = (expiry_time - now).total_seconds()
                    is_expired = expires_in_seconds <= 0
                    
                except Exception as e:
                    logger.error(f"Error parsing expiry time: {e}")
            
            return {
                'exists': True,
                'valid': not is_expired,
                'expires_in_seconds': max(0, expires_in_seconds),
                'expires_in_minutes': max(0, expires_in_seconds / 60),
                'obtained_at': tokens.get('obtained_at'),
                'last_refreshed': tokens.get('last_refreshed'),
                'refresh_count': tokens.get('refresh_count', 0),
                'scope': tokens.get('scope'),
                'message': 'Valid tokens' if not is_expired else 'Tokens expired'
            }
            
        except Exception as e:
            logger.error(f"Error getting token status: {e}")
            return {
                'exists': False,
                'valid': False,
                'message': f'Error checking status: {str(e)}'
            }


def create_token_manager_from_env() -> StravaTokenManager:
    """
    Create token manager from environment variables.
    
    Expected environment variables:
    - AWS_REGION: AWS region (optional, defaults to eu-west-1)
    - OAUTH_SECRETS_NAME: Secret name (optional, defaults to strava-ai-boost-oauth-tokens)
    
    Returns:
        Configured StravaTokenManager instance
    """
    import os
    
    region = os.getenv('AWS_REGION', 'eu-west-1')
    secret_name = os.getenv('OAUTH_SECRETS_NAME', 'strava-ai-boost-oauth-tokens')
    
    secrets_helper = SecretsManagerHelper(region_name=region)
    return StravaTokenManager(secrets_helper=secrets_helper, secret_name=secret_name)