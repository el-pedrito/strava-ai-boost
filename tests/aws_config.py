"""
Dynamic AWS Configuration for Tests

Automatically discovers deployed AWS resources for testing.
Uses CloudFormation outputs and AWS API to find resources.
"""

import boto3
import os
import json
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AWSTestConfig:
    """Dynamic AWS configuration for tests"""
    
    def __init__(self, profile: str = None, region: str = 'eu-west-1'):
        """Initialize AWS config with profile"""
        self.profile = profile or os.environ.get('AWS_PROFILE', 'your-aws-profile')
        self.region = region
        self.session = boto3.Session(profile_name=self.profile, region_name=self.region)
        self._cache = {}
    
    def get_stack_outputs(self, stack_name: str) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        if stack_name in self._cache:
            return self._cache[stack_name]
        
        try:
            cfn = self.session.client('cloudformation')
            response = cfn.describe_stacks(StackName=stack_name)
            
            if response['Stacks']:
                outputs = {}
                for output in response['Stacks'][0].get('Outputs', []):
                    outputs[output['OutputKey']] = output['OutputValue']
                
                self._cache[stack_name] = outputs
                return outputs
        except Exception as e:
            logger.warning(f"Failed to get stack outputs for {stack_name}: {e}")
            return {}
    
    def get_dynamodb_tables(self) -> list:
        """Get all Strava AI Boost DynamoDB tables"""
        try:
            dynamodb = self.session.client('dynamodb')
            response = dynamodb.list_tables()
            
            boost_tables = [t for t in response['TableNames'] 
                          if 'strava-ai-boost' in t.lower()]
            return boost_tables
        except Exception as e:
            logger.warning(f"Failed to list DynamoDB tables: {e}")
            return []
    
    def get_lambda_functions(self) -> list:
        """Get all Strava AI Boost Lambda functions"""
        try:
            lambda_client = self.session.client('lambda')
            response = lambda_client.list_functions()
            
            boost_functions = [f['FunctionName'] for f in response['Functions'] 
                             if 'StravaAIBoost' in f['FunctionName']]
            return boost_functions
        except Exception as e:
            logger.warning(f"Failed to list Lambda functions: {e}")
            return []
    
    def get_sqs_queues(self) -> list:
        """Get all Strava AI Boost SQS queues"""
        try:
            sqs = self.session.client('sqs')
            response = sqs.list_queues(QueueNamePrefix='strava-ai-boost')
            
            return response.get('QueueUrls', [])
        except Exception as e:
            logger.warning(f"Failed to list SQS queues: {e}")
            return []
    
    def get_step_functions(self) -> list:
        """Get all Strava AI Boost Step Functions"""
        try:
            sfn = self.session.client('stepfunctions')
            response = sfn.list_state_machines()
            
            boost_machines = [sm for sm in response['stateMachines'] 
                            if 'StravaAIBoost' in sm['name']]
            return boost_machines
        except Exception as e:
            logger.warning(f"Failed to list Step Functions: {e}")
            return []
    
    def get_secrets(self) -> list:
        """Get all Strava AI Boost secrets"""
        try:
            secrets = self.session.client('secretsmanager')
            response = secrets.list_secrets()
            
            boost_secrets = [s for s in response['SecretList'] 
                           if 'strava-ai-boost' in s['Name'].lower()]
            return boost_secrets
        except Exception as e:
            logger.warning(f"Failed to list secrets: {e}")
            return []
    
    def get_api_gateway_url(self) -> Optional[str]:
        """Get API Gateway URL from CloudFormation or API Gateway"""
        # Try CloudFormation first
        api_stack_outputs = self.get_stack_outputs('StravaAIBoost-API')
        if api_stack_outputs and 'APIGatewayURL' in api_stack_outputs:
            return api_stack_outputs['APIGatewayURL']
        
        # Try to find Local Interface API Gateway directly
        try:
            apigw = self.session.client('apigateway')
            apis = apigw.get_rest_apis()
            
            for api in apis['items']:
                # Look for Local Interface API (not Webhook API)
                if 'Local Interface' in api['name']:
                    api_id = api['id']
                    return f"https://{api_id}.execute-api.{self.region}.amazonaws.com/prod"
        except Exception as e:
            logger.warning(f"Failed to get API Gateway URL: {e}")
        
        return None
    
    def get_api_gateway_key(self) -> Optional[str]:
        """Get API Gateway key value from API Gateway"""
        try:
            apigw = self.session.client('apigateway')
            
            # Find API keys with values
            keys = apigw.get_api_keys(includeValues=True)
            
            for key in keys['items']:
                if 'strava-ai-boost' in key['name'].lower():
                    # Return the actual key value, not the ID
                    return key.get('value', key.get('id'))
            
            # If no named key found, try to get any key
            if keys['items']:
                return keys['items'][0].get('value', keys['items'][0].get('id'))
                
        except Exception as e:
            logger.warning(f"Failed to get API Gateway key: {e}")
        
        return None
    
    def get_all_resources(self) -> Dict[str, Any]:
        """Get all AWS resources for testing"""
        return {
            'tables': self.get_dynamodb_tables(),
            'lambdas': self.get_lambda_functions(),
            'queues': self.get_sqs_queues(),
            'step_functions': self.get_step_functions(),
            'secrets': self.get_secrets(),
            'api_url': self.get_api_gateway_url(),
            'api_key': self.get_api_gateway_key()
        }
    
    def print_summary(self):
        """Print summary of discovered resources"""
        resources = self.get_all_resources()
        
        print("\n" + "="*60)
        print("AWS Resources Discovered for Testing")
        print("="*60)
        print(f"Profile: {self.profile}")
        print(f"Region: {self.region}")
        print(f"\nDynamoDB Tables: {len(resources['tables'])}")
        for table in resources['tables']:
            print(f"  - {table}")
        
        print(f"\nLambda Functions: {len(resources['lambdas'])}")
        for func in resources['lambdas']:
            print(f"  - {func}")
        
        print(f"\nSQS Queues: {len(resources['queues'])}")
        for queue in resources['queues']:
            print(f"  - {queue.split('/')[-1]}")
        
        print(f"\nStep Functions: {len(resources['step_functions'])}")
        for sm in resources['step_functions']:
            print(f"  - {sm['name']}")
        
        print(f"\nSecrets: {len(resources['secrets'])}")
        for secret in resources['secrets']:
            print(f"  - {secret['Name']}")
        
        if resources['api_url']:
            print(f"\nAPI Gateway URL: {resources['api_url']}")
        if resources['api_key']:
            print(f"API Gateway Key: {resources['api_key'][:10]}...")
        
        print("="*60 + "\n")


# Global instance
_config = None


def get_aws_config() -> AWSTestConfig:
    """Get or create AWS config instance"""
    global _config
    if _config is None:
        _config = AWSTestConfig()
    return _config


if __name__ == '__main__':
    # Test the configuration
    config = AWSTestConfig()
    config.print_summary()
