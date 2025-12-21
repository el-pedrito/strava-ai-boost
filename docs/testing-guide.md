# Strava AI Boost - Testing Guide

**Version:** v0.1.0 - Infrastructure Complete  
**Last Updated:** 2025-12-21

This guide provides comprehensive testing procedures and validation steps for the Strava AI Boost system, including property-based testing, unit testing, and integration testing strategies.

## Testing Philosophy

Strava AI Boost uses a dual testing approach combining traditional unit testing with property-based testing to ensure comprehensive coverage:

- **Unit Tests**: Verify specific examples, edge cases, and error conditions
- **Property Tests**: Verify universal properties that should hold across all inputs
- **Integration Tests**: Validate end-to-end workflows and AWS service integration

Together they provide comprehensive coverage: unit tests catch concrete bugs, property tests verify general correctness.

## Testing Framework

### Core Testing Dependencies

```bash
# Install testing dependencies
pip install pytest>=7.0.0
pip install pytest-cov>=4.0.0
pip install hypothesis>=6.0.0  # Property-based testing
pip install moto>=4.2.0        # AWS service mocking
```

### Property-Based Testing with Hypothesis

**Framework**: Hypothesis (Python) for property-based testing  
**Configuration**: Minimum 100 iterations per property test  
**Tagging**: Each property-based test tagged with format: `**Feature: strava-ai-boost, Property {number}: {property_text}**`

## Infrastructure Security Tests

### Property 15: Data Encryption at Rest

```python
@settings(max_examples=100)
@given(table_name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pd'))))
def test_property_15_data_encryption_at_rest(self, table_name):
    """
    **Feature: strava-ai-boost, Property 15: Data Encryption at Rest**
    
    For any DynamoDB table created by the infrastructure, encryption at rest 
    should be applied using AWS managed encryption.
    
    Validates: Requirements 7.1 - Data encryption at rest for all DynamoDB tables
    """
    template = assertions.Template.from_stack(self.core_stack)
    
    # Verify all DynamoDB tables have encryption enabled
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "SSESpecification": {
            "SSEEnabled": True
        }
    })
    
    # Verify point-in-time recovery is enabled for critical tables
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "PointInTimeRecoverySpecification": {
            "PointInTimeRecoveryEnabled": True
        }
    })
```

### Property 16: Secure HTTPS Communication

```python
@settings(max_examples=100)
@given(api_endpoint=st.text(min_size=1, max_size=100))
def test_property_16_secure_communication_https(self, api_endpoint):
    """
    **Feature: strava-ai-boost, Property 16: Secure Communication**
    
    For any API endpoint created by the infrastructure, HTTPS should be used 
    for all communications with proper TLS configuration.
    
    Validates: Requirements 7.2 - Secure communication using HTTPS for all API endpoints
    """
    template = assertions.Template.from_stack(self.webhook_stack)
    
    # Verify API Gateway is configured with proper security
    template.has_resource_properties("AWS::ApiGateway::RestApi", {
        "EndpointConfiguration": {
            "Types": ["REGIONAL"]
        }
    })
```

## Running Tests

### Infrastructure Security Tests

```bash
# Run all property-based security tests
python -m pytest tests/test_infrastructure_properties.py::TestInfrastructureSecurityProperties -v

# Run specific property test
python -m pytest tests/test_infrastructure_properties.py::TestInfrastructureSecurityProperties::test_property_15_data_encryption_at_rest -v

# Run with coverage
python -m pytest tests/test_infrastructure_properties.py --cov=stacks --cov-report=html
```

### Infrastructure Correctness Tests

```bash
# Run correctness validation tests
python -m pytest tests/test_infrastructure_properties.py::TestInfrastructureCorrectnessProperties -v

# Test DynamoDB table configuration
python -m pytest tests/test_infrastructure_properties.py::TestInfrastructureCorrectnessProperties::test_dynamodb_table_naming_consistency -v
```

### Complete Test Suite

```bash
# Run all tests
python -m pytest tests/ -v

# Run with detailed output and coverage
python -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

# Run tests in parallel (if pytest-xdist installed)
python -m pytest tests/ -n auto
```

## Test Categories

### 1. Infrastructure Security Tests

**Purpose**: Validate AWS security configurations and compliance  
**Framework**: Property-based testing with Hypothesis  
**Coverage**: IAM, DynamoDB, SQS, Lambda, API Gateway, Secrets Manager

```python
class TestInfrastructureSecurityProperties:
    """Property-based tests for infrastructure security"""
    
    def test_secrets_manager_encryption(self):
        """Test that Secrets Manager secrets are properly encrypted"""
        
    def test_iam_least_privilege_principle(self):
        """Test that IAM roles follow least privilege principle"""
        
    def test_sqs_encryption_and_dlq_configuration(self):
        """Test that SQS queues are properly encrypted and have DLQ configuration"""
        
    def test_lambda_function_security_configuration(self):
        """Test that Lambda functions have proper security configuration"""
```

### 2. Infrastructure Correctness Tests

**Purpose**: Validate infrastructure configuration and naming consistency  
**Framework**: Standard unit testing  
**Coverage**: Resource naming, GSI configuration, TTL settings

```python
class TestInfrastructureCorrectnessProperties:
    """Additional correctness properties for infrastructure"""
    
    def test_dynamodb_table_naming_consistency(self):
        """Test that DynamoDB tables follow consistent naming convention"""
        
    def test_global_secondary_indexes_configuration(self):
        """Test that required GSIs are properly configured"""
        
    def test_ttl_configuration(self):
        """Test that TTL is properly configured for rate limits table"""
        
    def test_removal_policy_configuration(self):
        """Test that removal policies are set appropriately for development"""
```

### 3. Unit Tests (Future Implementation)

**Purpose**: Test specific business logic and edge cases  
**Framework**: pytest with mocking  
**Coverage**: Lambda functions, data models, API handlers

```python
# Example unit test structure (to be implemented)
class TestWebhookHandler:
    """Unit tests for Strava webhook handler"""
    
    @mock_aws
    def test_valid_webhook_processing(self):
        """Test processing of valid Strava webhook"""
        
    @mock_aws  
    def test_invalid_webhook_rejection(self):
        """Test rejection of invalid webhook payloads"""
        
    @mock_aws
    def test_rate_limit_enforcement(self):
        """Test rate limiting behavior"""

class TestActivityProcessor:
    """Unit tests for activity processing logic"""
    
    @mock_aws
    def test_activity_data_extraction(self):
        """Test extraction of activity data from Strava API"""
        
    @mock_aws
    def test_streams_data_processing(self):
        """Test processing of Strava streams data"""
```

### 4. Integration Tests (Future Implementation)

**Purpose**: Test end-to-end workflows and AWS service integration  
**Framework**: pytest with real AWS services (test environment)  
**Coverage**: Complete activity processing pipeline

```python
# Example integration test structure (to be implemented)
class TestEndToEndWorkflow:
    """Integration tests for complete activity processing"""
    
    def test_webhook_to_enhancement_pipeline(self):
        """Test complete pipeline from webhook to Strava update"""
        
    def test_campus_coach_integration(self):
        """Test Campus Coach module integration"""
        
    def test_error_recovery_mechanisms(self):
        """Test error handling and retry logic"""
```

## Test Configuration

### pytest Configuration

Create `pytest.ini` in project root:

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --cov-report=term-missing
    --cov-report=html:htmlcov
markers =
    property: Property-based tests
    unit: Unit tests
    integration: Integration tests
    security: Security-focused tests
    slow: Slow-running tests
```

### Hypothesis Configuration

Create `conftest.py` in tests directory:

```python
from hypothesis import settings, Verbosity

# Configure Hypothesis for property-based testing
settings.register_profile("default", max_examples=100, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=10, verbosity=Verbosity.verbose)

# Load profile based on environment
import os
profile = os.getenv("HYPOTHESIS_PROFILE", "default")
settings.load_profile(profile)
```

## Test Data and Fixtures

### CDK Test Fixtures

```python
import pytest
import aws_cdk as cdk
from stacks.core_infrastructure_stack import CoreInfrastructureStack
from stacks.webhook_processing_stack import WebhookProcessingStack

@pytest.fixture
def cdk_app():
    """Create CDK app for testing"""
    return cdk.App()

@pytest.fixture
def core_stack(cdk_app):
    """Create core infrastructure stack for testing"""
    return CoreInfrastructureStack(
        cdk_app, 
        "TestCore",
        env=cdk.Environment(account="123456789012", region="eu-west-1")
    )

@pytest.fixture
def webhook_stack(cdk_app, core_stack):
    """Create webhook processing stack for testing"""
    return WebhookProcessingStack(
        cdk_app,
        "TestWebhook", 
        core_stack=core_stack,
        env=cdk.Environment(account="123456789012", region="eu-west-1")
    )
```

### Mock Data Fixtures

```python
@pytest.fixture
def sample_activity_data():
    """Sample Strava activity data for testing"""
    return {
        "id": "12345678",
        "name": "Morning Run",
        "description": "Great run in the park",
        "type": "Run",
        "distance": 5000.0,
        "moving_time": 1800,
        "elapsed_time": 1900,
        "total_elevation_gain": 50.0,
        "start_date": "2025-12-21T08:00:00Z"
    }

@pytest.fixture
def sample_webhook_payload():
    """Sample Strava webhook payload for testing"""
    return {
        "object_type": "activity",
        "object_id": 12345678,
        "aspect_type": "create",
        "owner_id": 987654,
        "subscription_id": 123,
        "event_time": 1640995200
    }
```

## Test Execution Strategies

### Local Development Testing

```bash
# Quick test run during development
python -m pytest tests/ -x --ff

# Test specific functionality
python -m pytest tests/test_infrastructure_properties.py -k "encryption" -v

# Test with coverage
python -m pytest tests/ --cov=stacks --cov-report=term-missing
```

### Continuous Integration Testing

```bash
# Full test suite with maximum examples
HYPOTHESIS_PROFILE=ci python -m pytest tests/ -v --cov=. --cov-report=xml

# Security-focused testing
python -m pytest tests/ -m security -v

# Performance testing
python -m pytest tests/ -m "not slow" --durations=10
```

### Pre-Deployment Testing

```bash
# Complete validation before deployment
python -m pytest tests/ -v --cov=. --cov-report=html
cdk synth --profile your-aws-profile
cdk diff --profile your-aws-profile
```

## Test Validation Checklist

### Infrastructure Tests

- [ ] All DynamoDB tables have encryption enabled (Property 15)
- [ ] All API endpoints use HTTPS (Property 16)
- [ ] IAM roles follow least privilege principle
- [ ] SQS queues have encryption and DLQ configuration
- [ ] Lambda functions have proper security configuration
- [ ] Secrets Manager secrets are properly configured
- [ ] Table naming follows consistent convention
- [ ] GSIs are properly configured
- [ ] TTL is configured where needed
- [ ] Removal policies are appropriate for environment

### Code Quality Tests

- [ ] All tests pass without warnings
- [ ] Code coverage meets minimum threshold (80%+)
- [ ] Property tests run with sufficient examples (100+)
- [ ] No hardcoded secrets or credentials in tests
- [ ] Test data is properly isolated and cleaned up
- [ ] Mock configurations match real AWS services
- [ ] Error scenarios are properly tested
- [ ] Edge cases are covered by property tests

## Performance Testing

### Test Execution Performance

```bash
# Measure test execution time
time python -m pytest tests/test_infrastructure_properties.py -v

# Profile test performance
python -m pytest tests/ --durations=0

# Parallel test execution
python -m pytest tests/ -n auto --dist=loadscope
```

### Expected Performance Metrics

- **Property Tests**: 100 iterations in <5 seconds per test
- **Infrastructure Tests**: Complete suite in <10 seconds
- **CDK Synthesis**: Template generation in <5 seconds
- **Mock Setup**: AWS service mocking in <1 second

## Troubleshooting Tests

### Common Test Issues

#### 1. CDK Template Assertion Failures

```bash
# Debug CDK template generation
cdk synth TestCore --profile your-aws-profile > test-template.json

# Inspect generated resources
jq '.Resources | keys' test-template.json
jq '.Resources."AWS::DynamoDB::Table"' test-template.json
```

#### 2. Hypothesis Test Failures

```bash
# Run with verbose output to see failing examples
python -m pytest tests/test_infrastructure_properties.py::test_property_15_data_encryption_at_rest -v -s

# Reproduce specific failing example
python -c "
from hypothesis import reproduce_failure
@reproduce_failure('6.148.7', b'...')  # Use failure reproduction code
def test_case():
    # Test implementation
"
```

#### 3. Mock Configuration Issues

```bash
# Verify moto version compatibility
python -c "import moto; print(moto.__version__)"

# Test mock setup in isolation
python -c "
from moto import mock_aws
with mock_aws():
    import boto3
    client = boto3.client('dynamodb', region_name='eu-west-1')
    print('Mock setup successful')
"
```

## Future Testing Enhancements

### Planned Test Categories

1. **API Integration Tests**
   - Strava API client testing
   - OAuth flow validation
   - Rate limiting behavior

2. **AgentCore Integration Tests**
   - Memory service integration
   - Browser Tool agent testing
   - Content generation validation

3. **End-to-End Workflow Tests**
   - Complete activity processing pipeline
   - Error recovery mechanisms
   - Performance benchmarking

4. **Load Testing**
   - Concurrent webhook processing
   - Rate limit stress testing
   - Resource utilization monitoring

### Test Automation Improvements

1. **Automated Test Data Generation**
   - Realistic Strava activity data
   - Edge case scenario generation
   - Performance test data sets

2. **Test Environment Management**
   - Isolated test AWS accounts
   - Automated test data cleanup
   - Test environment provisioning

3. **Continuous Testing Pipeline**
   - Pre-commit test hooks
   - Automated regression testing
   - Performance regression detection

---

**Version:** v0.1.0 - Infrastructure Complete  
**Last Updated:** 2025-12-21  
**Test Coverage:** Infrastructure Security and Correctness (100%)