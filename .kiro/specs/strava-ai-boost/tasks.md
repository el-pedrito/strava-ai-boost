# Implementation Plan

## Completed Infrastructure

- [x] 1. Set up project structure and core infrastructure
  - Create Python CDK project structure following strava-ai-coach patterns
  - Set up core DynamoDB tables (strava-activities, user-configuration, strava-rate-limits, campus-coaching-sessions)
  - Configure AWS CDK stacks organization using Python (core, api-gateway, webhook, content-generation, monitoring)
  - Set up IAM roles and policies with least privilege principle
  - Initialize Strands Agents framework configuration
  - Create shell scripts directory for AgentCore CLI deployment (scripts/)
  - _Requirements: 6.1, 6.3, 7.1, 7.5_

- [x] 1.1 Write property test for infrastructure security
  - **Property 15: Data encryption at rest for all DynamoDB tables**
  - **Validates: Requirements 7.1**

- [x] 1.2 Write property test for IAM security
  - **Property 16: Secure communication using HTTPS for all API endpoints**
  - **Validates: Requirements 7.2**

- [x] 2. Implement Strava OAuth integration and rate limiting in Python
  - [x] 2.1 Create Python OAuth flow handler with PKCE support using requests-oauthlib
    - Implement OAuth authorization URL generation
    - Handle OAuth callback and token exchange
    - Store tokens securely in Secrets Manager
    - _Requirements: 1.2, 1.3, 7.3_
  
  - [x] 2.2 Implement secure token storage in AWS Secrets Manager with boto3 and automatic rotation
    - Create Secrets Manager helper functions
    - Implement token refresh logic
    - Add automatic rotation configuration
    - _Requirements: 1.3, 1.5, 7.3_
  
  - [x] 2.3 Build Python rate limiting system tracking 100/15min and 1000/day limits with DynamoDB
    - Create rate limiter Lambda function implementation
    - Implement DynamoDB-based rate tracking
    - Add exponential backoff logic
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  
  - [x] 2.4 Create Strava API client class with retry logic and exponential backoff using requests
    - Build reusable Strava API client
    - Implement retry logic with exponential backoff
    - Add rate limit checking before API calls
    - _Requirements: 8.1, 8.4, 10.1, 10.2_

- [x] 2.5 Write property test for OAuth token security
  - **Property 1: OAuth tokens securely stored in Secrets Manager**
  - **Validates: Requirements 1.3, 7.3**

- [x] 2.6 Write property test for rate limit compliance
  - **Property 13: API calls respect both 15-minute and daily rate limits**
  - **Validates: Requirements 10.1, 10.2**
  - **Status: PASSED** - All 6 test methods passed with 100 examples each

- [x] 2.7 Write property test for rate limit persistence
  - **Property 14: Rate limit data persisted in DynamoDB across Lambda invocations**
  - **Validates: Requirements 10.5**
  - **Status: PASSED** - All 5 test methods passed with 100 examples each

## Missing Lambda Functions and Step Functions Integration

- [ ] 3. Complete missing Lambda functions and Step Functions workflow
  - [ ] 3.1 Create missing Lambda functions for Step Functions workflow
    - Implement activity_fetcher.py for Strava API data retrieval
    - Implement strava_updater.py for activity content updates
    - Implement campus_coach_invoker.py for AgentCore Browser Tool invocation
    - Add comprehensive streams data fetching
    - _Requirements: 2.4, 2.5, 2.6, 2.7, 2.8, 2.12_
  
  - [ ] 3.2 Complete Step Functions workflow integration with activity processor
    - Update activity_processor.py to trigger Step Functions workflow
    - Add proper error handling and retry logic
    - Implement activity status tracking in DynamoDB
    - _Requirements: 2.2, 2.3, 8.3_
  
  - [ ] 3.3 Deploy remaining CDK stacks (content generation, API gateway, monitoring)
    - Deploy ContentGenerationStack with Step Functions workflow
    - Deploy ApiGatewayStack for local interface endpoints
    - Deploy MonitoringStack with CloudWatch alarms
    - _Requirements: 6.1, 11.2, 11.3_

- [ ]* 3.4 Write property test for webhook reliability
  - **Property 2: Valid webhooks queued in SQS for reliable processing**
  - **Validates: Requirements 2.2**

- [ ]* 3.5 Write property test for error recovery
  - **Property 9: Processing failures trigger SQS retry with exponential backoff**
  - **Validates: Requirements 2.13**

## AgentCore Agents Implementation

- [ ] 4. Implement AgentCore agents and Strands framework integration
  - [ ] 4.1 Complete content generation agent with Strands framework
    - Implement Strands Agent initialization and configuration in content_generation_agent.py
    - Add AgentCore Memory client integration
    - Implement personal style learning and storage
    - Add expression tracking to avoid repetition
    - _Requirements: 2.10_
  
  - [ ] 4.2 Create Campus Coach Browser Tool agent
    - Implement AgentCore Browser Tool agent for web scraping in campus_coach_agent.py
    - Add Campus Coach session extraction logic
    - Implement retry logic for cold start issues
    - Add secure credential management
    - _Requirements: 5.1, 5.3, 5.4_
  
  - [ ] 4.3 Integrate Bedrock Claude for intelligent analysis
    - Add Claude Sonnet 4.5 integration for pattern detection
    - Implement effort analysis, intervals, heart rate zones detection
    - Add workout classification logic
    - Integrate with streams data analysis
    - _Requirements: 2.9, 3.2_

- [ ]* 4.4 Write property test for AI pattern detection
  - **Property 6: Bedrock AI detects effort patterns and workout classification**
  - **Validates: Requirements 2.9, 3.2**

- [ ]* 4.5 Write property test for memory-based personalization
  - **Property 7: Content generation uses AgentCore Memory for style consistency and expression variety**
  - **Validates: Requirements 2.10**

- [ ]* 4.6 Write property test for activity updates
  - **Property 8: Generated content successfully updates Strava activities**
  - **Validates: Requirements 2.12**

## Module System Implementation

- [ ] 5. Implement modular system architecture in Python
  - [ ] 5.1 Complete Python base module interface and registration system
    - Implement abstract base classes for modules in base_module.py
    - Add module registration and discovery system
    - Create module lifecycle management
    - _Requirements: 4.1, 4.2_
  
  - [ ] 5.2 Implement module configuration persistence in DynamoDB
    - Add module configuration storage and retrieval
    - Implement configuration validation
    - Add module activation/deactivation logic
    - _Requirements: 4.3, 4.4_
  
  - [ ] 5.3 Complete Campus Coach module implementation
    - Finish Campus Coach module class in campus_coach_module.py
    - Integrate with AgentCore Browser Tool agent
    - Add session matching and confidence scoring logic
    - Implement compliance analysis functionality
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 3.3, 3.4, 3.5, 3.6, 3.7_
  
  - [ ] 5.4 Build Enduraw integration module
    - Create Enduraw module class in enduraw_module.py
    - Implement wait logic for 2-7 minute processing delay
    - Add enhanced metrics fetching (pace without wind, weather, elevation cost)
    - Integrate enhanced metrics into content generation pipeline
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ]* 5.5 Write property test for module configuration
  - **Property 11: Module settings persisted in DynamoDB**
  - **Validates: Requirements 4.4**

- [ ]* 5.6 Write property test for credential security
  - **Property 12: Campus Coach credentials securely stored in Secrets Manager**
  - **Validates: Requirements 5.2**

- [ ]* 5.7 Write property test for session matching
  - **Property 10: Activity patterns matched against planned sessions with confidence scoring**
  - **Validates: Requirements 3.3, 3.4**

- [ ]* 5.8 Write property test for Enduraw wait logic
  - **Property 17: System waits 2-7 minutes for Enduraw when active**
  - **Validates: Requirements 9.3**

- [ ]* 5.9 Write property test for enhanced metrics integration
  - **Property 18: Enduraw data included in content generation**
  - **Validates: Requirements 9.5**

## Utility Classes and Data Models

- [ ] 6. Implement utility classes and data models
  - [ ] 6.1 Create Strava API client utility class
    - Implement strava_client.py with OAuth token management
    - Add rate limiting integration
    - Implement comprehensive API methods for activities and streams
    - Add error handling and retry logic
    - _Requirements: 8.1, 8.4, 10.1, 10.2_
  
  - [ ] 6.2 Complete data models using Pydantic
    - Finish data_models.py with comprehensive Strava activity models
    - Add streams data models with validation
    - Implement module configuration models
    - Add processing status and error models
    - _Requirements: 2.6, 2.7, 2.8_
  
  - [ ] 6.3 Implement rate limiter utility class
    - Create rate_limiter.py with DynamoDB integration
    - Add exponential backoff logic
    - Implement rate limit checking and queuing
    - Add monitoring and alerting integration
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ]* 6.4 Write property test for data backup
  - **Property 3: Original activity descriptions backed up before modification**
  - **Validates: Requirements 2.5**

- [ ]* 6.5 Write property test for comprehensive analysis
  - **Property 4: All available Strava fields utilized in analysis**
  - **Validates: Requirements 2.7**

- [ ]* 6.6 Write property test for streams precision
  - **Property 5: Streams data fetched with second-by-second granularity**
  - **Validates: Requirements 2.8, 3.1**

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Local Web Interface Implementation

- [ ] 8. Complete local web interface implementation
  - [ ] 8.1 Enhance Python Flask/FastAPI application
    - Complete OAuth flow implementation with Strava in local_interface/app.py
    - Add real-time dashboard with WebSocket or polling
    - Implement module configuration interface
    - Add enhancement pause/resume control with visual indicators
    - _Requirements: 1.1, 4.1, 13.1, 13.5, 13.6_
  
  - [ ] 8.2 Implement AWS Cloudscape frontend components
    - Create dashboard with activity statistics and engagement metrics
    - Build configuration interface for module management
    - Add real-time status monitoring with Step Functions progress
    - Implement error display with clear messages and suggested actions
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [ ] 8.3 Complete API Gateway integration
    - Implement missing Lambda functions (configuration_api.py, dashboard_api.py, status_api.py)
    - Add secure communication between local interface and AWS
    - Implement request validation and rate limiting
    - Add CORS configuration for local development
    - _Requirements: 7.4_

- [ ]* 8.4 Write property test for real-time status
  - **Property 19: Processing status displayed in real-time**
  - **Validates: Requirements 11.4, 12.1**

- [ ]* 8.5 Write property test for error messaging
  - **Property 20: Clear error messages with suggested actions displayed**
  - **Validates: Requirements 12.3**

- [ ]* 8.6 Write property test for enhancement pause control
  - **Property 21: Enhancement pause control persists and prevents processing**
  - **Validates: Requirements 13.3, 13.7**

## AgentCore Deployment and Testing

- [ ] 9. Deploy and test AgentCore integration
  - [ ] 9.1 Deploy AgentCore agents using CLI scripts
    - Run deploy_agentcore.sh script for infrastructure setup
    - Deploy content generation agent with AgentCore Memory
    - Deploy Campus Coach Browser Tool agent
    - Verify agent deployments and connectivity
    - _Requirements: 6.1_
  
  - [ ] 9.2 Test AgentCore Memory integration
    - Test personal style storage and retrieval
    - Verify expression tracking functionality
    - Test memory-based content personalization
    - Validate memory persistence across invocations
    - _Requirements: 2.10_
  
  - [ ] 9.3 Test Campus Coach Browser Tool agent
    - Test session extraction functionality
    - Verify retry logic for cold start issues
    - Test credential security and storage
    - Validate session matching and confidence scoring
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

## System Integration and Deployment

- [ ] 10. Complete deployment and setup automation
  - [ ] 10.1 Complete CDK deployment scripts
    - Add environment configuration for different stages
    - Implement webhook subscription automation with Strava
    - Add validation scripts for deployment verification
    - _Requirements: 6.2, 6.4_
  
  - [ ] 10.2 Create setup instructions and documentation
    - Write comprehensive setup guide
    - Document AgentCore CLI requirements and installation
    - Add troubleshooting guide for common issues
    - _Requirements: 6.5_
  
  - [ ] 10.3 Implement clean uninstall process
    - Create CDK destroy scripts
    - Add AgentCore cleanup scripts
    - Implement complete resource removal process
    - _Requirements: 6.5_

- [ ] 11. Final integration and end-to-end testing
  - [ ] 11.1 Test complete activity processing pipeline
    - Test webhook → SQS → Step Functions → Bedrock → Strava update flow
    - Validate all module integrations work correctly
    - Test error scenarios and recovery mechanisms
    - _Requirements: All requirements validation_
  
  - [ ] 11.2 Verify security configurations and encryption
    - Test all security configurations
    - Verify encryption at rest and in transit
    - Validate IAM permissions and least privilege
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [ ] 11.3 Test local web interface functionality
    - Test OAuth flow end-to-end
    - Verify dashboard real-time updates
    - Test module configuration and management
    - Validate enhancement pause/resume functionality
    - _Requirements: 1.1, 11.1, 12.1, 13.1_

- [ ]* 11.4 Write integration tests for complete pipeline
  - Test webhook → SQS → Step Functions → Bedrock → Strava update flow
  - Test module activation/deactivation scenarios
  - Test error recovery and retry mechanisms

- [ ] 12. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.