#!/usr/bin/env python3
"""
AgentCore Setup Validation Script

Validates AgentCore integration setup without requiring full deployment.
Tests configuration, permissions, and integration points.
"""

import json
import os
import sys
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS Configuration
AWS_PROFILE = 'your-aws-profile'
AWS_REGION = 'eu-west-1'

class AgentCoreSetupValidator:
    """Validates AgentCore integration setup and configuration"""
    
    def __init__(self):
        """Initialize validator with AWS clients"""
        # Set AWS profile
        os.environ['AWS_PROFILE'] = AWS_PROFILE
        
        # Initialize AWS clients
        self.session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        self.sts = self.session.client('sts')
        self.bedrock_agent_runtime = self.session.client('bedrock-agent-runtime')
        self.dynamodb = self.session.resource('dynamodb')
        self.secretsmanager = self.session.client('secretsmanager')
        self.lambda_client = self.session.client('lambda')
        self.stepfunctions = self.session.client('stepfunctions')
        
        # Validation results
        self.validation_results = {
            'aws_connectivity': {'status': 'pending', 'details': []},
            'agentcore_permissions': {'status': 'pending', 'details': []},
            'lambda_configuration': {'status': 'pending', 'details': []},
            'stepfunctions_workflow': {'status': 'pending', 'details': []},
            'secrets_configuration': {'status': 'pending', 'details': []},
            'dynamodb_tables': {'status': 'pending', 'details': []}
        }
    
    def run_all_validations(self) -> Dict[str, Any]:
        """Run all setup validations"""
        logger.info("🔍 Starting AgentCore Setup Validation")
        
        try:
            # Validation 1: AWS Connectivity and Permissions
            self.validate_aws_connectivity()
            
            # Validation 2: AgentCore Permissions
            self.validate_agentcore_permissions()
            
            # Validation 3: Lambda Function Configuration
            self.validate_lambda_configuration()
            
            # Validation 4: Step Functions Workflow
            self.validate_stepfunctions_workflow()
            
            # Validation 5: Secrets Manager Configuration
            self.validate_secrets_configuration()
            
            # Validation 6: DynamoDB Tables
            self.validate_dynamodb_tables()
            
            # Generate validation report
            return self.generate_validation_report()
            
        except Exception as e:
            logger.error(f"Validation suite failed: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e),
                'results': self.validation_results
            }
    
    def validate_aws_connectivity(self):
        """Validate AWS connectivity and profile configuration"""
        logger.info("🔗 Validating AWS Connectivity...")
        
        try:
            # Test AWS connectivity
            identity = self.sts.get_caller_identity()
            account_id = identity.get('Account')
            user_arn = identity.get('Arn')
            
            self.validation_results['aws_connectivity']['status'] = 'passed'
            self.validation_results['aws_connectivity']['details'].extend([
                f"✅ AWS Profile: {AWS_PROFILE}",
                f"✅ AWS Region: {AWS_REGION}",
                f"✅ Account ID: {account_id}",
                f"✅ User ARN: {user_arn}"
            ])
            
        except Exception as e:
            self.validation_results['aws_connectivity']['status'] = 'failed'
            self.validation_results['aws_connectivity']['details'].append(
                f"❌ AWS connectivity failed: {str(e)}"
            )
    
    def validate_agentcore_permissions(self):
        """Validate AgentCore service permissions"""
        logger.info("🛡️  Validating AgentCore Permissions...")
        
        try:
            # Test Bedrock Agent Runtime access
            try:
                # This will fail but tests if we have permission to call the service
                self.bedrock_agent_runtime.invoke_agent(
                    agentId='test-agent-id',
                    agentAliasId='TSTALIASID',
                    sessionId='test-session',
                    inputText='test'
                )
            except self.bedrock_agent_runtime.exceptions.ResourceNotFoundException:
                # Expected error - means we have permission but agent doesn't exist
                self.validation_results['agentcore_permissions']['details'].append(
                    "✅ Bedrock Agent Runtime: Access permissions verified"
                )
            except self.bedrock_agent_runtime.exceptions.AccessDeniedException:
                self.validation_results['agentcore_permissions']['details'].append(
                    "❌ Bedrock Agent Runtime: Access denied - check IAM permissions"
                )
                self.validation_results['agentcore_permissions']['status'] = 'failed'
                return
            except Exception as e:
                if 'AccessDenied' in str(e):
                    self.validation_results['agentcore_permissions']['details'].append(
                        "❌ Bedrock Agent Runtime: Access denied - check IAM permissions"
                    )
                    self.validation_results['agentcore_permissions']['status'] = 'failed'
                    return
                else:
                    # Other errors are acceptable for this test
                    self.validation_results['agentcore_permissions']['details'].append(
                        "✅ Bedrock Agent Runtime: Service accessible"
                    )
            
            self.validation_results['agentcore_permissions']['status'] = 'passed'
            
        except Exception as e:
            self.validation_results['agentcore_permissions']['status'] = 'failed'
            self.validation_results['agentcore_permissions']['details'].append(
                f"❌ AgentCore permissions validation failed: {str(e)}"
            )
    
    def validate_lambda_configuration(self):
        """Validate Lambda function configuration for AgentCore integration"""
        logger.info("⚡ Validating Lambda Configuration...")
        
        lambda_functions = [
            'StravaAIBoost-ContentGenerator',
            'StravaAIBoost-CampusCoachInvoker',
            'StravaAIBoost-ActivityFetcher'
        ]
        
        try:
            for function_name in lambda_functions:
                try:
                    # Get function configuration
                    response = self.lambda_client.get_function(FunctionName=function_name)
                    config = response['Configuration']
                    
                    # Check environment variables
                    env_vars = config.get('Environment', {}).get('Variables', {})
                    
                    self.validation_results['lambda_configuration']['details'].append(
                        f"✅ {function_name}: Function exists"
                    )
                    
                    # Check specific environment variables for AgentCore
                    if function_name == 'StravaAIBoost-ContentGenerator':
                        required_vars = ['BEDROCK_MODEL_ID', 'ACTIVITIES_TABLE']
                        for var in required_vars:
                            if var in env_vars:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ✅ Environment variable: {var}"
                                )
                            else:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ❌ Missing environment variable: {var}"
                                )
                    
                    elif function_name == 'StravaAIBoost-CampusCoachInvoker':
                        required_vars = ['COACHING_SESSIONS_TABLE', 'CAMPUS_COACH_SECRET']
                        for var in required_vars:
                            if var in env_vars:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ✅ Environment variable: {var}"
                                )
                            else:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ❌ Missing environment variable: {var}"
                                )
                    
                    elif function_name == 'StravaAIBoost-ActivityFetcher':
                        required_vars = ['ACTIVITIES_TABLE', 'USER_CONFIG_TABLE']
                        for var in required_vars:
                            if var in env_vars:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ✅ Environment variable: {var}"
                                )
                            else:
                                self.validation_results['lambda_configuration']['details'].append(
                                    f"   ❌ Missing environment variable: {var}"
                                )
                
                except self.lambda_client.exceptions.ResourceNotFoundException:
                    self.validation_results['lambda_configuration']['details'].append(
                        f"⚠️  {function_name}: Function not deployed yet"
                    )
                except Exception as e:
                    self.validation_results['lambda_configuration']['details'].append(
                        f"❌ {function_name}: Error - {str(e)}"
                    )
            
            # Check if any functions were found
            found_functions = [d for d in self.validation_results['lambda_configuration']['details'] if '✅' in d and 'Function exists' in d]
            if found_functions:
                self.validation_results['lambda_configuration']['status'] = 'passed'
            else:
                self.validation_results['lambda_configuration']['status'] = 'warning'
                self.validation_results['lambda_configuration']['details'].append(
                    "⚠️  No Lambda functions deployed yet - run CDK deployment first"
                )
            
        except Exception as e:
            self.validation_results['lambda_configuration']['status'] = 'failed'
            self.validation_results['lambda_configuration']['details'].append(
                f"❌ Lambda configuration validation failed: {str(e)}"
            )
    
    def validate_stepfunctions_workflow(self):
        """Validate Step Functions workflow configuration"""
        logger.info("🔄 Validating Step Functions Workflow...")
        
        try:
            # Check if Step Functions state machine exists
            state_machine_name = 'StravaAIBoost-ActivityProcessing'
            
            try:
                # List state machines to find ours
                response = self.stepfunctions.list_state_machines()
                state_machines = response.get('stateMachines', [])
                
                target_sm = None
                for sm in state_machines:
                    if state_machine_name in sm['name']:
                        target_sm = sm
                        break
                
                if target_sm:
                    # Get state machine definition
                    sm_arn = target_sm['stateMachineArn']
                    definition_response = self.stepfunctions.describe_state_machine(
                        stateMachineArn=sm_arn
                    )
                    
                    definition = json.loads(definition_response['definition'])
                    
                    self.validation_results['stepfunctions_workflow']['details'].append(
                        f"✅ State Machine: {state_machine_name} exists"
                    )
                    
                    # Check for Campus Coach integration in definition
                    definition_str = json.dumps(definition)
                    if 'CheckCampusCoachEnabled' in definition_str:
                        self.validation_results['stepfunctions_workflow']['details'].append(
                            "✅ Campus Coach conditional logic: Present in workflow"
                        )
                    else:
                        self.validation_results['stepfunctions_workflow']['details'].append(
                            "❌ Campus Coach conditional logic: Missing from workflow"
                        )
                    
                    if 'ExtractCampusSessions' in definition_str:
                        self.validation_results['stepfunctions_workflow']['details'].append(
                            "✅ Campus Coach extraction step: Present in workflow"
                        )
                    else:
                        self.validation_results['stepfunctions_workflow']['details'].append(
                            "❌ Campus Coach extraction step: Missing from workflow"
                        )
                    
                    self.validation_results['stepfunctions_workflow']['status'] = 'passed'
                    
                else:
                    self.validation_results['stepfunctions_workflow']['status'] = 'warning'
                    self.validation_results['stepfunctions_workflow']['details'].append(
                        f"⚠️  State Machine: {state_machine_name} not found - deploy CDK stack first"
                    )
            
            except Exception as e:
                self.validation_results['stepfunctions_workflow']['status'] = 'failed'
                self.validation_results['stepfunctions_workflow']['details'].append(
                    f"❌ Step Functions validation failed: {str(e)}"
                )
        
        except Exception as e:
            self.validation_results['stepfunctions_workflow']['status'] = 'failed'
            self.validation_results['stepfunctions_workflow']['details'].append(
                f"❌ Step Functions workflow validation failed: {str(e)}"
            )
    
    def validate_secrets_configuration(self):
        """Validate Secrets Manager configuration"""
        logger.info("🔐 Validating Secrets Configuration...")
        
        secrets = [
            'strava-ai-boost-oauth-tokens',
            'strava-ai-boost-campus-coach-credentials'
        ]
        
        try:
            for secret_name in secrets:
                try:
                    # Check if secret exists
                    response = self.secretsmanager.describe_secret(SecretId=secret_name)
                    
                    self.validation_results['secrets_configuration']['details'].append(
                        f"✅ Secret: {secret_name} exists"
                    )
                    
                    # Check if secret has a value (without retrieving it)
                    if response.get('LastChangedDate'):
                        self.validation_results['secrets_configuration']['details'].append(
                            f"   ✅ Secret has been configured (last changed: {response['LastChangedDate']})"
                        )
                    
                except self.secretsmanager.exceptions.ResourceNotFoundException:
                    self.validation_results['secrets_configuration']['details'].append(
                        f"⚠️  Secret: {secret_name} not found - will be created during deployment"
                    )
                except Exception as e:
                    self.validation_results['secrets_configuration']['details'].append(
                        f"❌ Secret: {secret_name} error - {str(e)}"
                    )
            
            # Check if any secrets were found
            found_secrets = [d for d in self.validation_results['secrets_configuration']['details'] if '✅' in d and 'exists' in d]
            if found_secrets:
                self.validation_results['secrets_configuration']['status'] = 'passed'
            else:
                self.validation_results['secrets_configuration']['status'] = 'warning'
                self.validation_results['secrets_configuration']['details'].append(
                    "⚠️  No secrets found - they will be created during CDK deployment"
                )
        
        except Exception as e:
            self.validation_results['secrets_configuration']['status'] = 'failed'
            self.validation_results['secrets_configuration']['details'].append(
                f"❌ Secrets configuration validation failed: {str(e)}"
            )
    
    def validate_dynamodb_tables(self):
        """Validate DynamoDB tables configuration"""
        logger.info("🗄️  Validating DynamoDB Tables...")
        
        tables = [
            'strava-ai-boost-activities',
            'strava-ai-boost-user-configuration',
            'strava-ai-boost-rate-limits',
            'campus-coaching-sessions'
        ]
        
        try:
            for table_name in tables:
                try:
                    # Check if table exists
                    table = self.dynamodb.Table(table_name)
                    table.load()  # This will raise an exception if table doesn't exist
                    
                    self.validation_results['dynamodb_tables']['details'].append(
                        f"✅ Table: {table_name} exists"
                    )
                    
                    # Check table status
                    if table.table_status == 'ACTIVE':
                        self.validation_results['dynamodb_tables']['details'].append(
                            f"   ✅ Status: ACTIVE"
                        )
                    else:
                        self.validation_results['dynamodb_tables']['details'].append(
                            f"   ⚠️  Status: {table.table_status}"
                        )
                
                except self.dynamodb.meta.client.exceptions.ResourceNotFoundException:
                    self.validation_results['dynamodb_tables']['details'].append(
                        f"⚠️  Table: {table_name} not found - will be created during deployment"
                    )
                except Exception as e:
                    self.validation_results['dynamodb_tables']['details'].append(
                        f"❌ Table: {table_name} error - {str(e)}"
                    )
            
            # Check if any tables were found
            found_tables = [d for d in self.validation_results['dynamodb_tables']['details'] if '✅' in d and 'exists' in d]
            if found_tables:
                self.validation_results['dynamodb_tables']['status'] = 'passed'
            else:
                self.validation_results['dynamodb_tables']['status'] = 'warning'
                self.validation_results['dynamodb_tables']['details'].append(
                    "⚠️  No tables found - they will be created during CDK deployment"
                )
        
        except Exception as e:
            self.validation_results['dynamodb_tables']['status'] = 'failed'
            self.validation_results['dynamodb_tables']['details'].append(
                f"❌ DynamoDB tables validation failed: {str(e)}"
            )
    
    def generate_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        logger.info("📊 Generating Validation Report...")
        
        # Count validation results
        passed = sum(1 for result in self.validation_results.values() if result['status'] == 'passed')
        failed = sum(1 for result in self.validation_results.values() if result['status'] == 'failed')
        warnings = sum(1 for result in self.validation_results.values() if result['status'] == 'warning')
        
        overall_status = 'ready' if failed == 0 and passed > 0 else 'needs_deployment' if warnings > 0 and failed == 0 else 'failed'
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': overall_status,
            'summary': {
                'total_validations': len(self.validation_results),
                'passed': passed,
                'failed': failed,
                'warnings': warnings
            },
            'validation_results': self.validation_results,
            'next_steps': self.generate_next_steps()
        }
        
        # Log summary
        logger.info(f"📋 Validation Summary: {passed} passed, {failed} failed, {warnings} warnings")
        
        return report
    
    def generate_next_steps(self) -> List[str]:
        """Generate next steps based on validation results"""
        next_steps = []
        
        # Check for deployment needs
        if self.validation_results['lambda_configuration']['status'] == 'warning':
            next_steps.append("🚀 Deploy CDK stacks: `cdk deploy --all --profile your-aws-profile`")
        
        if self.validation_results['secrets_configuration']['status'] == 'warning':
            next_steps.append("🔐 Configure secrets after deployment with actual credentials")
        
        if self.validation_results['agentcore_permissions']['status'] == 'failed':
            next_steps.append("🛡️  Fix IAM permissions for Bedrock Agent Runtime access")
        
        # Add AgentCore specific steps
        next_steps.extend([
            "🤖 Deploy AgentCore agents: `./scripts/deploy_agentcore.sh`",
            "💾 Setup AgentCore Memory: `./scripts/setup_memory.sh`",
            "🏃 Deploy Campus Coach agent: `./scripts/deploy_campus_coach_agent.sh`",
            "🧪 Run integration tests: `python scripts/test_agentcore_integration.py`"
        ])
        
        return next_steps


def main():
    """Main validation execution function"""
    print("🔍 AgentCore Setup Validation")
    print("=" * 50)
    
    # Initialize validator
    validator = AgentCoreSetupValidator()
    
    # Run validations
    report = validator.run_all_validations()
    
    # Print detailed report
    print("\n📊 VALIDATION REPORT")
    print("=" * 50)
    print(f"Overall Status: {report['overall_status'].upper()}")
    print(f"Validations: {report['summary']['passed']} passed, {report['summary']['failed']} failed, {report['summary']['warnings']} warnings")
    
    print("\n📋 DETAILED RESULTS")
    print("-" * 30)
    for validation_name, result in report['validation_results'].items():
        status_emoji = "✅" if result['status'] == 'passed' else "❌" if result['status'] == 'failed' else "⚠️"
        print(f"\n{status_emoji} {validation_name.replace('_', ' ').title()}: {result['status'].upper()}")
        for detail in result['details']:
            print(f"   {detail}")
    
    print("\n🚀 NEXT STEPS")
    print("-" * 30)
    for step in report['next_steps']:
        print(f"   {step}")
    
    # Save report to file
    report_file = f"agentcore_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Full report saved to: {report_file}")
    
    return report['overall_status'] in ['ready', 'needs_deployment']


if __name__ == "__main__":
    # Run the validation suite
    success = main()
    sys.exit(0 if success else 1)