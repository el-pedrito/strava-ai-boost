"""
Pytest configuration and shared fixtures for Strava AI Boost tests
"""

import pytest
import os
import boto3
from moto import mock_aws
from .aws_config import get_aws_config


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring deployed AWS resources"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    """Setup environment variables for all tests with generic test values"""
    # AWS credentials (mocked for unit tests)
    os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"
    os.environ["AWS_SECURITY_TOKEN"] = "test-token"
    os.environ["AWS_SESSION_TOKEN"] = "test-session"
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    os.environ["AWS_REGION"] = "eu-west-1"
    
    # DynamoDB tables (generic test names)
    os.environ["ACTIVITIES_TABLE"] = "test-activities-table"
    os.environ["USER_CONFIG_TABLE"] = "test-user-config-table"
    os.environ["RATE_LIMITS_TABLE"] = "test-rate-limits-table"
    os.environ["COACHING_SESSIONS_TABLE"] = "test-coaching-sessions-table"
    
    # SQS (generic test URLs)
    os.environ["PROCESSING_QUEUE_URL"] = "https://sqs.eu-west-1.amazonaws.com/000000000000/test-queue"
    os.environ["DLQ_URL"] = "https://sqs.eu-west-1.amazonaws.com/000000000000/test-dlq"
    
    # Step Functions (generic test ARN)
    os.environ["STEP_FUNCTIONS_ARN"] = "arn:aws:states:eu-west-1:000000000000:stateMachine:test-state-machine"
    
    # Secrets Manager (generic test names)
    os.environ["STRAVA_OAUTH_SECRET"] = "test-oauth-secret"
    os.environ["STRAVA_APP_SECRET"] = "test-app-secret"
    os.environ["CAMPUS_COACH_SECRET"] = "test-campus-secret"
    
    # Bedrock (generic test model)
    os.environ["BEDROCK_MODEL_ID"] = "anthropic.claude-v2"
    
    # AgentCore (generic test ARNs)
    os.environ["CONTENT_GENERATION_AGENT_ARN"] = "arn:aws:bedrock-agentcore:eu-west-1:000000000000:runtime/test-agent"
    os.environ["CAMPUS_COACH_AGENT_ARN"] = "arn:aws:bedrock-agentcore:eu-west-1:000000000000:runtime/test-agent"
    os.environ["AGENTCORE_AGENTS_AVAILABLE"] = "false"
    
    # User (generic test ID)
    os.environ["DEFAULT_USER_ID"] = "test-user-123"


@pytest.fixture(scope="session")
def aws_credentials():
    """Mock AWS credentials for testing"""
    # Already set in setup_environment
    pass


@pytest.fixture(scope="function")
def aws_mock(aws_credentials):
    """Mock AWS services for testing"""
    with mock_aws():
        yield


@pytest.fixture(scope="session")
def aws_config():
    """Get dynamic AWS configuration for integration tests"""
    return get_aws_config()


@pytest.fixture(scope="session")
def aws_session():
    """Create AWS session with proper profile for integration tests"""
    profile = os.environ.get('AWS_PROFILE', 'your-aws-profile')
    return boto3.Session(profile_name=profile, region_name='eu-west-1')


@pytest.fixture
def api_gateway_url():
    """Mock API Gateway URL for testing"""
    return "https://test-api.execute-api.eu-west-1.amazonaws.com/prod"


@pytest.fixture
def api_gateway_key():
    """Mock API Gateway key for testing"""
    return "test-api-key-12345"


@pytest.fixture
def sample_activity_data():
    """Sample Strava activity data for testing"""
    return {
        "id": "12345678",
        "name": "Morning Run",
        "description": "Great run in the park",
        "type": "Run",
        "sport_type": "Run",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1900,
        "total_elevation_gain": 50.0,
        "start_date": "2025-01-03T08:00:00Z",
        "start_date_local": "2025-01-03T09:00:00+01:00",
        "timezone": "Europe/Paris",
        "athlete": {"id": YOUR_USER_ID}
    }


@pytest.fixture
def sample_webhook_event():
    """Sample Strava webhook event for testing"""
    return {
        "object_type": "activity",
        "object_id": 12345678,
        "aspect_type": "create",
        "owner_id": YOUR_USER_ID,
        "subscription_id": 123456,
        "event_time": 1704268800
    }


@pytest.fixture
def sample_user_config():
    """Sample user configuration for testing"""
    return {
        "user_id": "YOUR_USER_ID",
        "enhancement_enabled": True,
        "modules_config": {
            "campus_coach": {
                "enabled": True,
                "credentials": {
                    "username": "test@example.com"
                }
            },
            "enduraw": {
                "enabled": True
            }
        }
    }
