"""
Security Stack for Strava AI Boost

Creates Bedrock Guardrails for content safety and prompt injection protection.
Configures CloudWatch observability for AgentCore agents.
"""

from aws_cdk import (
    Stack,
    aws_bedrock as bedrock,
    aws_iam as iam,
    aws_logs as logs,
    CfnOutput,
    CustomResource,
    custom_resources as cr,
    Aws
)
from constructs import Construct
import json


class SecurityStack(Stack):
    """Security stack with Bedrock Guardrails and AgentCore Observability"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Bedrock Guardrail
        self._create_guardrail()

        # Create IAM role for AgentCore Memory built-in strategies
        self._create_memory_execution_role()

        # Enable AgentCore Observability
        self._enable_agentcore_observability()

    def _create_guardrail(self) -> None:
        """Create Bedrock Guardrail for content generation"""

        # Create Bedrock Guardrail for content generation
        self.content_guardrail = bedrock.CfnGuardrail(
            self, "ContentGenerationGuardrail",
            name="strava-ai-boost-content-guardrail",
            description="Guardrail for Strava AI Boost content generation - protects against prompt injection and harmful content",
            blocked_input_messaging="Je ne peux pas traiter cette demande car elle contient du contenu inapproprié.",
            blocked_outputs_messaging="Je ne peux pas générer ce contenu car il viole notre politique de contenu.",
            
            # Content Policy: Prompt Attack only (minimal configuration)
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    # Prompt Attack Protection (HIGH for maximum security)
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="PROMPT_ATTACK",
                        input_strength="HIGH",
                        output_strength="NONE"  # Only check inputs
                    )
                ]
            )
            
            # All other policies DISABLED to avoid rate limiting
            # Topic Policy: DISABLED (causes rate limiting with 230K+ char prompts)
            # PII Policy: DISABLED (optional protection)
            # Word Policy: DISABLED (covered by PROMPT_ATTACK)
            # Content Filters: DISABLED (sexual, violence, hate - optional)
        )
        
        # Create guardrail version
        self.guardrail_version = bedrock.CfnGuardrailVersion(
            self, "ContentGuardrailVersion",
            guardrail_identifier=self.content_guardrail.attr_guardrail_id,
            description="Production version for content generation"
        )
        
        # Export guardrail ID and version
        CfnOutput(
            self, "GuardrailId",
            value=self.content_guardrail.attr_guardrail_id,
            description="Bedrock Guardrail ID for content generation",
            export_name="StravaAIBoost-GuardrailId"
        )
        
        CfnOutput(
            self, "GuardrailVersion",
            value="DRAFT",  # Use DRAFT to always get latest changes
            description="Bedrock Guardrail Version (DRAFT = latest)",
            export_name="StravaAIBoost-GuardrailVersion"
        )
        
        # Store for use in other stacks
        self.guardrail_id = self.content_guardrail.attr_guardrail_id
        self.guardrail_version_number = self.guardrail_version.attr_version
    
    def _create_memory_execution_role(self) -> None:
        """
        Create IAM role for AgentCore Memory built-in strategies.

        This role is assumed by bedrock-agentcore.amazonaws.com to invoke
        Bedrock models for extraction and consolidation (UserPreferenceStrategy).
        """
        self.memory_execution_role = iam.Role(
            self, "AgentCoreMemoryExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "aws:SourceAccount": Aws.ACCOUNT_ID
                    },
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"
                    }
                }
            ),
            description="IAM role for AgentCore Memory strategy extraction/consolidation"
        )

        self.memory_execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{Aws.REGION}:{Aws.ACCOUNT_ID}:inference-profile/*"
                ]
            )
        )

        CfnOutput(
            self, "MemoryExecutionRoleArn",
            value=self.memory_execution_role.role_arn,
            description="IAM role ARN for AgentCore Memory strategy execution",
            export_name="StravaAIBoost-MemoryExecutionRoleArn"
        )

    def _enable_agentcore_observability(self) -> None:
        """Enable AgentCore Observability with Transaction Search"""
        
        # Create CloudWatch Logs resource policy for X-Ray
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "TransactionSearchXRayAccess",
                "Effect": "Allow",
                "Principal": {"Service": "xray.amazonaws.com"},
                "Action": "logs:PutLogEvents",
                "Resource": [
                    f"arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:aws/spans:*",
                    f"arn:aws:logs:{Aws.REGION}:{Aws.ACCOUNT_ID}:log-group:/aws/application-signals/data:*"
                ],
                "Condition": {
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:xray:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"
                    },
                    "StringEquals": {
                        "aws:SourceAccount": Aws.ACCOUNT_ID
                    }
                }
            }]
        }
        
        # Create custom resource to configure CloudWatch Logs policy
        logs_policy_provider = cr.Provider(
            self, "LogsPolicyProvider",
            on_event_handler=self._create_logs_policy_handler()
        )
        
        CustomResource(
            self, "CloudWatchLogsPolicy",
            service_token=logs_policy_provider.service_token,
            properties={
                "PolicyName": "AgentCoreTransactionSearch",
                "PolicyDocument": json.dumps(policy_document)
            }
        )
        
        # Create custom resource to configure X-Ray
        xray_config_provider = cr.Provider(
            self, "XRayConfigProvider",
            on_event_handler=self._create_xray_config_handler()
        )
        
        CustomResource(
            self, "XRayConfiguration",
            service_token=xray_config_provider.service_token,
            properties={
                "Destination": "CloudWatchLogs",
                "SamplingPercentage": 100  # 100% sampling - capture all traces
            }
        )
        
        CfnOutput(
            self, "ObservabilityDashboard",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={Aws.REGION}#gen-ai-observability/agent-core/agents",
            description="GenAI Observability Dashboard URL"
        )
    
    def _create_logs_policy_handler(self):
        """Create Lambda handler for CloudWatch Logs policy"""
        from aws_cdk import aws_lambda as lambda_
        
        return lambda_.Function(
            self, "LogsPolicyHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3
import json

logs = boto3.client('logs')

def handler(event, context):
    request_type = event['RequestType']
    props = event['ResourceProperties']
    
    try:
        if request_type in ['Create', 'Update']:
            logs.put_resource_policy(
                policyName=props['PolicyName'],
                policyDocument=props['PolicyDocument']
            )
            return {'PhysicalResourceId': props['PolicyName']}
        elif request_type == 'Delete':
            try:
                logs.delete_resource_policy(policyName=props['PolicyName'])
            except:
                pass  # Policy may not exist
            return {'PhysicalResourceId': props['PolicyName']}
    except Exception as e:
        print(f"Error: {e}")
        return {'PhysicalResourceId': props['PolicyName']}
"""),
            initial_policy=[
                iam.PolicyStatement(
                    actions=[
                        "logs:PutResourcePolicy",
                        "logs:DeleteResourcePolicy",
                        "logs:DescribeResourcePolicies"
                    ],
                    resources=["*"]
                )
            ]
        )
    
    def _create_xray_config_handler(self):
        """Create Lambda handler for X-Ray configuration"""
        from aws_cdk import aws_lambda as lambda_
        
        return lambda_.Function(
            self, "XRayConfigHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline("""
import boto3

xray = boto3.client('xray')

def handler(event, context):
    request_type = event['RequestType']
    props = event['ResourceProperties']
    
    try:
        if request_type in ['Create', 'Update']:
            # Update trace segment destination
            xray.update_trace_segment_destination(
                Destination=props['Destination']
            )
            
            # Update indexing rule (sampling)
            xray.update_indexing_rule(
                Name='Default',
                Rule={
                    'Probabilistic': {
                        'DesiredSamplingPercentage': int(props['SamplingPercentage'])
                    }
                }
            )
            
            return {'PhysicalResourceId': 'XRayConfig'}
        elif request_type == 'Delete':
            # Don't delete on stack deletion (keep observability)
            return {'PhysicalResourceId': 'XRayConfig'}
    except Exception as e:
        print(f"Error: {e}")
        return {'PhysicalResourceId': 'XRayConfig'}
"""),
            initial_policy=[
                iam.PolicyStatement(
                    actions=[
                        "xray:UpdateTraceSegmentDestination",
                        "xray:UpdateIndexingRule",
                        "xray:GetTraceSegmentDestination",
                        "xray:GetIndexingRules"
                    ],
                    resources=["*"]
                )
            ]
        )
