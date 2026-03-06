"""Unit test configuration — set env vars before Lambda module imports"""

import os

# Must be set before any Lambda module is imported (module-level os.environ[] calls)
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("ACTIVITIES_TABLE", "test-activities")
os.environ.setdefault("USER_CONFIG_TABLE", "test-user-config")
os.environ.setdefault("COACHING_SESSIONS_TABLE", "test-coaching-sessions")
os.environ.setdefault("PROCESSING_QUEUE_URL", "https://sqs.eu-west-1.amazonaws.com/000000000000/test-queue")
os.environ.setdefault("DLQ_URL", "https://sqs.eu-west-1.amazonaws.com/000000000000/test-dlq")
os.environ.setdefault("STRAVA_OAUTH_SECRET", "test-oauth-secret")
os.environ.setdefault("BEDROCK_MODEL_ID", "anthropic.claude-v2")
os.environ.setdefault("CONTENT_GENERATION_AGENT_ARN", "arn:aws:bedrock-agentcore:eu-west-1:000000000000:runtime/test")
