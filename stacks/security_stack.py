"""
Security Stack for Strava AI Boost

Creates Bedrock Guardrails for content safety and prompt injection protection.
"""

from aws_cdk import (
    Stack,
    aws_bedrock as bedrock,
    CfnOutput
)
from constructs import Construct


class SecurityStack(Stack):
    """Security stack with Bedrock Guardrails"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Bedrock Guardrail for content generation
        self.content_guardrail = bedrock.CfnGuardrail(
            self, "ContentGenerationGuardrail",
            name="strava-ai-boost-content-guardrail",
            description="Guardrail for Strava AI Boost content generation - protects against prompt injection and harmful content",
            blocked_input_messaging="Je ne peux pas traiter cette demande car elle contient du contenu inapproprié.",
            blocked_outputs_messaging="Je ne peux pas générer ce contenu car il viole notre politique de contenu.",
            
            # Content Policy: Block harmful content
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    # Prompt Attack Protection (HIGH priority)
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="PROMPT_ATTACK",
                        input_strength="HIGH",
                        output_strength="NONE"  # Only check inputs
                    ),
                    # Harmful content filters
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="SEXUAL",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="VIOLENCE",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="HATE",
                        input_strength="HIGH",
                        output_strength="HIGH"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="INSULTS",
                        input_strength="MEDIUM",
                        output_strength="MEDIUM"
                    ),
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type="MISCONDUCT",
                        input_strength="MEDIUM",
                        output_strength="MEDIUM"
                    )
                ]
            ),
            
            # Topic Policy: Keep content within sports/fitness domain
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="Politics",
                        definition="Political discussions, elections, government policies, political parties",
                        examples=[
                            "What do you think about the current president?",
                            "Tell me about political parties",
                            "Discuss government policies"
                        ],
                        type="DENY"
                    ),
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="FinancialAdvice",
                        definition="Investment advice, stock tips, financial planning, cryptocurrency",
                        examples=[
                            "Should I invest in this stock?",
                            "Give me financial advice",
                            "Tell me about cryptocurrency investments"
                        ],
                        type="DENY"
                    ),
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="MedicalAdvice",
                        definition="Medical diagnosis, treatment recommendations, prescription advice",
                        examples=[
                            "What medication should I take?",
                            "Diagnose my symptoms",
                            "Should I see a doctor?"
                        ],
                        type="DENY"
                    )
                ]
            ),
            
            # Sensitive Information Policy: Protect PII
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="EMAIL",
                        action="BLOCK"
                    ),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="PHONE",
                        action="BLOCK"
                    ),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="ADDRESS",
                        action="ANONYMIZE"
                    ),
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        type="CREDIT_DEBIT_CARD_NUMBER",
                        action="BLOCK"
                    )
                ]
            ),
            
            # Word Policy: Block prompt injection phrases
            word_policy_config=bedrock.CfnGuardrail.WordPolicyConfigProperty(
                words_config=[
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="ignore previous instructions"
                    ),
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="disregard all previous"
                    ),
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="you are now"
                    ),
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="forget everything"
                    ),
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="system prompt"
                    ),
                    bedrock.CfnGuardrail.WordConfigProperty(
                        text="override instructions"
                    )
                ]
            )
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
            value=self.guardrail_version.attr_version,
            description="Bedrock Guardrail Version",
            export_name="StravaAIBoost-GuardrailVersion"
        )
        
        # Store for use in other stacks
        self.guardrail_id = self.content_guardrail.attr_guardrail_id
        self.guardrail_version_number = self.guardrail_version.attr_version
