"""
LLM Configuration for Strava AI Boost

Centralized configuration for all LLM models used across the application.
"""

import os
from typing import Dict, Any

# Default LLM Model Configuration
DEFAULT_BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
DEFAULT_ANTHROPIC_VERSION = "bedrock-2023-05-31"
DEFAULT_MAX_TOKENS = 1200
DEFAULT_TEMPERATURE = 0.7

class LLMConfig:
    """Centralized LLM configuration for consistent model usage across the application"""
    
    def __init__(self):
        """Initialize LLM configuration from environment variables"""
        
        # Primary model configuration
        self.bedrock_model_id = os.getenv('BEDROCK_MODEL_ID', DEFAULT_BEDROCK_MODEL_ID)
        self.anthropic_version = os.getenv('ANTHROPIC_VERSION', DEFAULT_ANTHROPIC_VERSION)
        
        # Model parameters
        self.max_tokens = int(os.getenv('LLM_MAX_TOKENS', str(DEFAULT_MAX_TOKENS)))
        self.temperature = float(os.getenv('LLM_TEMPERATURE', str(DEFAULT_TEMPERATURE)))
        
        # AWS region for Bedrock
        self.aws_region = os.getenv('AWS_REGION', 'eu-west-1')
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate LLM configuration parameters"""
        if not self.bedrock_model_id:
            raise ValueError("BEDROCK_MODEL_ID cannot be empty")
        
        if self.max_tokens <= 0 or self.max_tokens > 4096:
            raise ValueError("LLM_MAX_TOKENS must be between 1 and 4096")
        
        if self.temperature < 0 or self.temperature > 1:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 1")
    
    def get_bedrock_params(self) -> Dict[str, Any]:
        """Get standardized Bedrock invocation parameters"""
        return {
            'modelId': self.bedrock_model_id,
            'body': {
                'anthropic_version': self.anthropic_version,
                'max_tokens': self.max_tokens,
                'temperature': self.temperature
            }
        }
    
    def get_iam_model_arn(self, region: str = None) -> str:
        """Get IAM ARN for the configured model"""
        region = region or self.aws_region
        return f"arn:aws:bedrock:{region}::foundation-model/{self.bedrock_model_id}"
    
    def __str__(self) -> str:
        """String representation of configuration"""
        return f"LLMConfig(model={self.bedrock_model_id}, region={self.aws_region})"


# Global configuration instance
llm_config = LLMConfig()

# Convenience functions for backward compatibility
def get_bedrock_model_id() -> str:
    """Get the configured Bedrock model ID"""
    return llm_config.bedrock_model_id

def get_bedrock_params() -> Dict[str, Any]:
    """Get standardized Bedrock invocation parameters"""
    return llm_config.get_bedrock_params()

def get_model_arn(region: str = None) -> str:
    """Get IAM ARN for the configured model"""
    return llm_config.get_iam_model_arn(region)