"""
Strava Application Configuration for Strava AI Boost

Centralized configuration for Strava OAuth application settings.
Handles client ID, secret, and redirect URI configuration.
"""

import os
import json
import boto3
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


class StravaAppConfig:
    """Centralized Strava application configuration"""
    
    def __init__(self, region: str = 'eu-west-1'):
        """
        Initialize Strava app configuration
        
        Args:
            region: AWS region for Secrets Manager
        """
        self.region = region
        self.secretsmanager = boto3.client('secretsmanager', region_name=region)
        
        # Configuration sources (in order of precedence)
        # 1. Environment variables (for development)
        # 2. AWS Secrets Manager (for production)
        # 3. Local configuration file (fallback)
        
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None
        
        # Load configuration
        self._load_configuration()
    
    def _load_configuration(self):
        """Load Strava app configuration from various sources"""
        
        # Try environment variables first (development)
        self.client_id = os.getenv('STRAVA_CLIENT_ID')
        self.client_secret = os.getenv('STRAVA_CLIENT_SECRET')
        self.redirect_uri = os.getenv('STRAVA_REDIRECT_URI', 'http://localhost:3000/oauth/callback')
        
        if self.client_id and self.client_secret:
            logger.info("Loaded Strava configuration from environment variables")
            return
        
        # Try AWS Secrets Manager (production)
        try:
            secret_name = "strava-ai-boost-app-config"
            response = self.secretsmanager.get_secret_value(SecretId=secret_name)
            config = json.loads(response['SecretString'])
            
            self.client_id = config.get('client_id')
            self.client_secret = config.get('client_secret')
            self.redirect_uri = config.get('redirect_uri', 'http://localhost:3000/oauth/callback')
            
            if self.client_id and self.client_secret:
                logger.info("Loaded Strava configuration from AWS Secrets Manager")
                return
                
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                logger.error(f"Error loading Strava config from Secrets Manager: {e}")
        
        # Fallback to placeholder values for initial setup
        logger.warning("No Strava configuration found - using placeholder values")
        self.client_id = "YOUR_STRAVA_CLIENT_ID"
        self.client_secret = "YOUR_STRAVA_CLIENT_SECRET"
        self.redirect_uri = "http://localhost:3000/oauth/callback"
    
    def is_configured(self) -> bool:
        """Check if Strava app is properly configured"""
        return (
            self.client_id and 
            self.client_secret and 
            self.client_id != "YOUR_STRAVA_CLIENT_ID" and
            self.client_secret != "YOUR_STRAVA_CLIENT_SECRET"
        )
    
    def store_configuration(
        self, 
        client_id: str, 
        client_secret: str, 
        redirect_uri: Optional[str] = None
    ) -> bool:
        """
        Store Strava app configuration in AWS Secrets Manager
        
        Args:
            client_id: Strava application client ID
            client_secret: Strava application client secret
            redirect_uri: OAuth redirect URI (optional)
            
        Returns:
            True if storage successful, False otherwise
        """
        try:
            if not redirect_uri:
                redirect_uri = self.redirect_uri
            
            config = {
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'configured_at': '2024-12-23T00:00:00Z'  # Current timestamp
            }
            
            secret_name = "strava-ai-boost-app-config"
            
            try:
                # Try to update existing secret
                self.secretsmanager.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(config)
                )
                logger.info("Updated Strava app configuration in Secrets Manager")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create new secret if it doesn't exist
                    self.secretsmanager.create_secret(
                        Name=secret_name,
                        Description="Strava application configuration for OAuth",
                        SecretString=json.dumps(config)
                    )
                    logger.info("Created new Strava app configuration in Secrets Manager")
                else:
                    raise
            
            # Update instance variables
            self.client_id = client_id
            self.client_secret = client_secret
            self.redirect_uri = redirect_uri
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store Strava configuration: {e}")
            return False
    
    def get_oauth_config(self) -> Dict[str, str]:
        """Get OAuth configuration for use with OAuth handler"""
        return {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri
        }
    
    def get_setup_instructions(self) -> Dict[str, Any]:
        """Get setup instructions for Strava app registration"""
        return {
            'steps': [
                {
                    'step': 1,
                    'title': 'Create Strava Application',
                    'description': 'Go to https://www.strava.com/settings/api and create a new application',
                    'details': [
                        'Application Name: "Strava AI Boost"',
                        'Category: "Training"',
                        'Club: Leave blank',
                        'Website: Your website or localhost for development',
                        f'Authorization Callback Domain: "{self._get_callback_domain()}"'
                    ]
                },
                {
                    'step': 2,
                    'title': 'Copy Application Credentials',
                    'description': 'After creating the app, copy the Client ID and Client Secret',
                    'details': [
                        'Client ID: A numeric value (e.g., 12345)',
                        'Client Secret: A long alphanumeric string',
                        'Keep these credentials secure and never share them publicly'
                    ]
                },
                {
                    'step': 3,
                    'title': 'Configure in Strava AI Boost',
                    'description': 'Enter the credentials in the configuration interface',
                    'details': [
                        'Use the configuration form below',
                        'Credentials will be stored securely in AWS Secrets Manager',
                        'Test the connection after configuration'
                    ]
                }
            ],
            'callback_url': self.redirect_uri,
            'scopes_required': [
                'read: Access to read basic profile information',
                'activity:read_all: Access to read all activity data',
                'activity:write: Permission to update activity titles and descriptions'
            ]
        }
    
    def _get_callback_domain(self) -> str:
        """Extract domain from redirect URI for Strava app configuration"""
        if self.redirect_uri.startswith('http://localhost'):
            return 'localhost'
        elif self.redirect_uri.startswith('https://'):
            # Extract domain from HTTPS URL
            return self.redirect_uri.split('//')[1].split('/')[0]
        else:
            return 'localhost'
    
    def validate_configuration(self, client_id: str, client_secret: str) -> Dict[str, Any]:
        """
        Validate Strava app configuration
        
        Args:
            client_id: Client ID to validate
            client_secret: Client secret to validate
            
        Returns:
            Validation result with status and messages
        """
        errors = []
        warnings = []
        
        # Validate client ID format
        if not client_id or client_id == "YOUR_STRAVA_CLIENT_ID":
            errors.append("Client ID is required")
        elif not client_id.isdigit():
            warnings.append("Client ID should be numeric (from Strava)")
        
        # Validate client secret format
        if not client_secret or client_secret == "YOUR_STRAVA_CLIENT_SECRET":
            errors.append("Client Secret is required")
        elif len(client_secret) < 20:
            warnings.append("Client Secret seems too short (should be 40+ characters)")
        
        # Validate redirect URI
        if not self.redirect_uri.startswith(('http://', 'https://')):
            errors.append("Redirect URI must be a valid HTTP/HTTPS URL")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'redirect_uri': self.redirect_uri
        }


# Global configuration instance
strava_config = StravaAppConfig()

# Convenience functions
def get_strava_config() -> StravaAppConfig:
    """Get the global Strava configuration instance"""
    return strava_config

def is_strava_configured() -> bool:
    """Check if Strava app is configured"""
    return strava_config.is_configured()

def get_oauth_config() -> Dict[str, str]:
    """Get OAuth configuration dictionary"""
    return strava_config.get_oauth_config()