#!/usr/bin/env python3
"""
Apply cost-allocation tags to AgentCore runtimes, memories, and their IAM roles.
Also apply CloudWatch Data Protection Policy on runtime log groups (P1.3).

Environment variables (optional):
    AWS_REGION, TAGS_PROJECT, TAGS_ENVIRONMENT, TAGS_OWNER,
    TAGS_COST_CENTER, TAGS_MANAGED_BY
"""

import json
import os
import boto3


def main() -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    base_tags = {
        "Project": os.environ.get("TAGS_PROJECT", "StravaAIBoost"),
        "Environment": os.environ.get("TAGS_ENVIRONMENT", "dev"),
        "Owner": os.environ.get("TAGS_OWNER", "admin"),
        "CostCenter": os.environ.get("TAGS_COST_CENTER", "strava-ai-boost"),
        "ManagedBy": os.environ.get("TAGS_MANAGED_BY", "AgentCore-CLI"),
    }

    agentcore = boto3.client("bedrock-agentcore-control", region_name=region)
    iam = boto3.client("iam")
    logs = boto3.client("logs", region_name=region)

    # 1. Runtimes + their IAM execution roles
    for rt in agentcore.list_agent_runtimes().get("agentRuntimes", []):
        arn = rt.get("agentRuntimeArn", "")
        name = rt.get("agentRuntimeName", "unknown")
        try:
            agentcore.tag_resource(resourceArn=arn, tags=base_tags)
            print(f"  ✅ Runtime tagged: {name}")
        except Exception as e:
            print(f"  ❌ Runtime {name}: {e}")
        try:
            details = agentcore.get_agent_runtime(agentRuntimeId=rt.get("agentRuntimeId", ""))
            role_arn = details.get("roleArn", "")
            role_name = role_arn.split("/")[-1] if role_arn else ""
            if role_name:
                role_tags = [{"Key": "agent", "Value": name}] + [
                    {"Key": k, "Value": v} for k, v in base_tags.items()
                ]
                iam.tag_role(RoleName=role_name, Tags=role_tags)
                print(f"  ✅ IAM role tagged: {role_name} (agent={name})")
        except Exception as e:
            print(f"  ❌ IAM role for {name}: {e}")

    # 2. Memories
    for mem in agentcore.list_memories().get("memories", []):
        arn = mem.get("memoryArn", mem.get("arn", ""))
        name = arn.split("/")[-1] if arn else "unknown"
        try:
            agentcore.tag_resource(resourceArn=arn, tags=base_tags)
            print(f"  ✅ Memory tagged: {name}")
        except Exception as e:
            print(f"  ❌ Memory {name}: {e}")

    # 3. P1.3: CloudWatch Data Protection Policy on AgentCore runtime log groups
    policy = {
        "Name": "StravaAIBoostDataProtection",
        "Description": "Mask credentials and PII in AgentCore runtime logs",
        "Version": "2021-06-01",
        "Configuration": {
            "CustomDataIdentifier": [
                {
                    "Name": "CampusCoachPassword",
                    "Regex": r"(?i)(?:password|mot\s*de\s*passe|pwd)\s*[:=]\s*[^\s'\"`]{6,}",
                },
                {
                    "Name": "BasicAuthHeader",
                    "Regex": r"(?i)authorization\s*:\s*(?:bearer|basic)\s+[A-Za-z0-9._\-+/=]+",
                },
            ]
        },
        "Statement": [
            {
                "Sid": "audit",
                "DataIdentifier": [
                    "arn:aws:dataprotection::aws:data-identifier/EmailAddress",
                    "arn:aws:dataprotection::aws:data-identifier/AwsSecretKey",
                    "CampusCoachPassword",
                    "BasicAuthHeader",
                ],
                "Operation": {"Audit": {"FindingsDestination": {}}},
            },
            {
                "Sid": "redact",
                "DataIdentifier": [
                    "arn:aws:dataprotection::aws:data-identifier/EmailAddress",
                    "arn:aws:dataprotection::aws:data-identifier/AwsSecretKey",
                    "CampusCoachPassword",
                    "BasicAuthHeader",
                ],
                "Operation": {"Deidentify": {"MaskConfig": {}}},
            },
        ],
    }
    for lg in logs.describe_log_groups(logGroupNamePrefix="/aws/bedrock-agentcore/runtimes/").get(
        "logGroups", []
    ):
        lg_name = lg["logGroupName"]
        try:
            logs.put_data_protection_policy(
                logGroupIdentifier=lg_name,
                policyDocument=json.dumps(policy),
            )
            print(f"  ✅ Data Protection Policy applied: {lg_name}")
        except Exception as e:
            print(f"  ❌ Data Protection on {lg_name}: {e}")


if __name__ == "__main__":
    main()
