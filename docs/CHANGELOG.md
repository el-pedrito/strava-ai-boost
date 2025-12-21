# Changelog

All notable changes to the Strava AI Boost project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-12-21 - Generic AWS Profile Configuration

### Changed
- **AWS Profile Configuration**: Removed hardcoded AWS profile from all project files
  - Replaced specific profile references with generic placeholders in documentation
  - Updated deployment scripts to use environment variable `AWS_PROFILE` with fallback to `your-aws-profile`
  - Enhanced script portability for different AWS environments
  - Maintained profile configuration in steering files for development use

### Security
- **Profile Privacy**: Eliminated hardcoded AWS profile names from version control
  - Prevents accidental exposure of specific AWS account information
  - Improves project portability across different AWS environments
  - Maintains security best practices for infrastructure code

### Files Modified
- `docs/SETUP.md`: All AWS CLI commands use generic profile placeholder
- `scripts/deploy_agentcore.sh`: Uses `${AWS_PROFILE:-your-aws-profile}` variable
- `scripts/deploy_campus_coach_agent.sh`: Uses environment variable for profile
- `scripts/setup_memory.sh`: Uses environment variable for profile  
- `scripts/validate_setup.sh`: Uses environment variable for profile validation

## [0.1.0] - 2025-12-21 - Initial Infrastructure and Property Tests

### Added
- **Core Infrastructure Stack**: Complete AWS CDK infrastructure with security best practices
  - 4 DynamoDB tables with AWS managed encryption and point-in-time recovery
  - IAM roles following least privilege principle with AWS managed policies
  - Secrets Manager integration for secure credential storage
  - All resources configured for development with proper removal policies

### Added
- **Webhook Processing Stack**: Reliable message processing infrastructure
  - SQS queues with KMS encryption and dead letter queue configuration
  - Lambda functions with Python 3.12 runtime and proper security configuration
  - API Gateway with HTTPS endpoints for webhook processing
  - Retry logic with exponential backoff (maxReceiveCount: 3)

### Added
- **Property-Based Testing Framework**: Comprehensive security and correctness validation
  - **Property 15**: Data encryption at rest validation for all DynamoDB tables
  - **Property 16**: Secure HTTPS communication validation for all API endpoints
  - Hypothesis framework integration with 100 iterations per property test
  - Infrastructure security tests covering IAM, SQS, Lambda, and Secrets Manager

### Added
- **CDK Project Structure**: Complete Python CDK application with modular design
  - 5 stack architecture (core, webhook, content, api, monitoring)
  - Proper dependency management with separate requirements.txt files
  - CDK synthesis working correctly with AWS profile integration
  - Environment configuration for eu-west-1 region

### Performance
- **CDK Synthesis**: ~4-5 seconds for complete infrastructure synthesis
- **Property Tests**: 100 iterations per test completing in <5 seconds
- **Infrastructure Validation**: 10 comprehensive tests validating security and correctness
- **Development Ready**: All tests passing, infrastructure deployable

### Technical Details
- **AWS CDK**: v2.219.0 with Python constructs
- **Testing Framework**: pytest + hypothesis for property-based testing
- **Security**: AWS managed encryption, least privilege IAM, HTTPS endpoints
- **Reliability**: SQS with DLQ, retry logic, point-in-time recovery
- **Compliance**: All tests validate requirements 7.1 (encryption) and 7.2 (HTTPS)

### Files Modified
- `stacks/core_infrastructure_stack.py`: Core DynamoDB and IAM infrastructure
- `stacks/webhook_processing_stack.py`: SQS and Lambda webhook processing
- `tests/test_infrastructure_properties.py`: Property-based security tests
- `requirements.txt`: Added hypothesis and moto testing dependencies
- `app.py`: CDK application entry point with proper synthesis