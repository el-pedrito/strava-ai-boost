# Implementation Plan

## Completed Infrastructure and Core Components

- [x] 1. Set up project structure and core infrastructure
  - Create Python CDK project structure with 5 stacks (core, webhook, content-generation, api-gateway, monitoring)
  - Set up core DynamoDB tables with encryption (activities, user-configuration, rate-limits, coaching-sessions)
  - Configure IAM roles and policies with least privilege principle
  - Create Secrets Manager secrets for OAuth tokens and Campus Coach credentials
  - Initialize AgentCore CLI deployment scripts (scripts/)
  - _Requirements: 6.1, 6.3, 7.1, 7.5_

- [x] 1.1 Write property test for infrastructure security
  - **Property 15: Data encryption at rest for all DynamoDB tables**
  - **Validates: Requirements 7.1**

- [x] 1.2 Write property test for IAM security
  - **Property 16: Secure communication using HTTPS for all API endpoints**
  - **Validates: Requirements 7.2**

- [x] 2. Implement Strava OAuth integration and rate limiting
  - [x] 2.1 Create OAuth handler with PKCE support and Secrets Manager integration
    - Implement OAuth authorization URL generation and callback handling
    - Store tokens securely in AWS Secrets Manager with automatic rotation
    - _Requirements: 1.2, 1.3, 7.3_
  
  - [x] 2.2 Build comprehensive rate limiting system with DynamoDB persistence
    - Create rate limiter with 100/15min and 1000/day limits tracking
    - Implement exponential backoff logic and cross-Lambda persistence
    - Add comprehensive status reporting and monitoring
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [x] 2.3 Create comprehensive Strava API client with retry logic
    - Build reusable Strava API client with OAuth token management
    - Implement retry logic with exponential backoff and rate limit integration
    - Add comprehensive API methods for activities and streams data
    - _Requirements: 8.1, 8.4, 10.1, 10.2_

- [x] 2.4 Write property test for OAuth token security
  - **Property 1: OAuth tokens securely stored in Secrets Manager**
  - **Validates: Requirements 1.3, 7.3**
  - **Status: PASSED** - All 5 test methods passed with 100 examples each

- [x] 2.5 Write property test for rate limit compliance
  - **Property 13: API calls respect both 15-minute and daily rate limits**
  - **Validates: Requirements 10.1, 10.2**
  - **Status: PASSED** - All 6 test methods passed with 100 examples each

- [x] 2.6 Write property test for rate limit persistence
  - **Property 14: Rate limit data persisted in DynamoDB across Lambda invocations**
  - **Validates: Requirements 10.5**
  - **Status: PASSED** - All 5 test methods passed with 100 examples each

- [x] 3. Complete webhook processing and Lambda functions
  - [x] 3.1 Create webhook handler with SQS integration
    - Implement webhook_handler.py for Strava webhook validation and queuing
    - Add enhancement pause/resume control checking
    - Integrate with SQS for reliable message processing
    - _Requirements: 2.2, 13.3, 13.7_
  
  - [x] 3.2 Create activity processor with Step Functions integration
    - Implement activity_processor.py to trigger Step Functions workflow
    - Add proper error handling and retry logic
    - Implement activity status tracking in DynamoDB
    - _Requirements: 2.2, 2.3, 8.3_
  
  - [x] 3.3 Create supporting Lambda functions for Step Functions workflow
    - Implement activity_fetcher.py for Strava API data retrieval
    - Implement strava_updater.py for activity content updates
    - Implement campus_coach_invoker.py for AgentCore Browser Tool invocation
    - Add comprehensive streams data fetching
    - _Requirements: 2.4, 2.5, 2.6, 2.7, 2.8, 2.12_

- [x] 3.4 Write property test for webhook reliability
  - **Property 2: Valid webhooks queued in SQS for reliable processing**
  - **Validates: Requirements 2.2**
  - **Status: COMPLETED** - Comprehensive test suite with 8 test methods covering all webhook scenarios

- [x] 3.5 Write property test for error recovery
  - **Property 9: Processing failures trigger SQS retry with exponential backoff**
  - **Validates: Requirements 2.13**
  - **Status: PASSED** ✅ - All 7 tests pass with 100% success rate
  - **Quality Improvements**: Fixed datetime deprecation warnings, improved test logic robustness

## AgentCore Integration and Content Generation

- [ ] 4. Complete AgentCore agents and Strands framework integration
  - [ ] 4.1 Complete content generation agent with Strands framework and AgentCore Memory
    - Integrate Strands Agent framework in content_generation_agent.py
    - Add AgentCore Memory client for personal style learning and expression tracking
    - Implement memory-based content personalization to avoid repetition
    - Connect with Bedrock Claude for intelligent content generation
    - _Requirements: 2.10_
  
  - [ ] 4.2 Create Campus Coach Browser Tool agent
    - Implement AgentCore Browser Tool agent for automated session extraction
    - Add Campus Coach session extraction logic with retry for cold start issues
    - Implement secure credential management via Secrets Manager
    - Add session matching and confidence scoring using Bedrock AI
    - _Requirements: 5.1, 5.3, 5.4_
  
  - [ ] 4.3 Enhance content generator Lambda with agent integration
    - Update content_generator.py to use Strands Agent and AgentCore Memory
    - Integrate Bedrock Claude for pattern detection and workout classification
    - Add streams data analysis for effort patterns and heart rate zones
    - Implement module-based content enhancement
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

- [ ] 5. Complete modular system architecture
  - [ ] 5.1 Enhance base module interface and registration system
    - Complete base_module.py with abstract base classes and lifecycle management
    - Add module registration and discovery system
    - Implement module configuration validation
    - _Requirements: 4.1, 4.2_
  
  - [ ] 5.2 Implement module configuration persistence
    - Add module configuration storage and retrieval in DynamoDB
    - Implement configuration validation and activation/deactivation logic
    - Integrate with user configuration table
    - _Requirements: 4.3, 4.4_
  
  - [ ] 5.3 Complete Campus Coach module implementation
    - Finish campus_coach_module.py with AgentCore Browser Tool integration
    - Add session matching and confidence scoring logic using Bedrock AI
    - Implement compliance analysis functionality comparing actual vs planned
    - Add retry logic for AgentCore Browser Tool cold start issues
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 3.3, 3.4, 3.5, 3.6, 3.7_
  
  - [ ] 5.4 Build Enduraw integration module
    - Create enduraw_module.py with wait logic for 2-7 minute processing delay
    - Add enhanced metrics fetching (pace without wind, weather, elevation cost)
    - Integrate enhanced metrics into content generation pipeline
    - Implement toggle functionality via local interface
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

## Data Models and Utility Enhancement

- [ ] 6. Complete data models and utility classes
  - [ ] 6.1 Complete data models using Pydantic
    - Finish data_models.py with comprehensive Strava activity models (67+ fields)
    - Add streams data models with validation for second-by-second granularity
    - Implement module configuration models and processing status models
    - Add error handling and validation models
    - _Requirements: 2.6, 2.7, 2.8_
  
  - [ ] 6.2 Enhance utility classes integration
    - Integrate strava_client.py with rate_limiter.py and oauth_handler.py
    - Add comprehensive error handling and retry logic
    - Implement monitoring and alerting integration
    - Add utility functions for data transformation and validation
    - _Requirements: 8.1, 8.4, 10.1, 10.2, 10.3, 10.4_

- [ ]* 6.3 Write property test for data backup
  - **Property 3: Original activity descriptions backed up before modification**
  - **Validates: Requirements 2.5**

- [ ]* 6.4 Write property test for comprehensive analysis
  - **Property 4: All available Strava fields utilized in analysis**
  - **Validates: Requirements 2.7**

- [ ]* 6.5 Write property test for streams precision
  - **Property 5: Streams data fetched with second-by-second granularity**
  - **Validates: Requirements 2.8, 3.1**

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Local Web Interface Implementation

- [ ] 8. Complete local web interface with AWS Cloudscape
  - [ ] 8.1 Enhance Flask application with complete OAuth flow
    - Complete OAuth flow implementation with Strava in local_interface/app.py
    - Add real-time dashboard with activity statistics and engagement metrics
    - Implement module configuration interface with enable/disable controls
    - Add enhancement pause/resume control with visual indicators and persistence
    - _Requirements: 1.1, 4.1, 13.1, 13.5, 13.6_
  
  - [ ] 8.2 Implement AWS Cloudscape frontend components
    - Create HTML templates with AWS Cloudscape design system components
    - Build configuration interface for module management (Campus Coach, Enduraw)
    - Add real-time status monitoring with Step Functions progress display
    - Implement error display with clear messages and suggested actions
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [ ] 8.3 Complete API Gateway integration for local interface
    - Complete configuration_api.py, dashboard_api.py, status_api.py Lambda functions
    - Add secure communication between local interface and AWS resources
    - Implement request validation and rate limiting for API endpoints
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

## AgentCore Deployment and Step Functions Integration

- [ ] 9. Deploy AgentCore agents and complete Step Functions workflow
  - [ ] 9.1 Deploy AgentCore agents using CLI scripts
    - Run deploy_agentcore.sh script for AgentCore infrastructure setup
    - Deploy content generation agent with AgentCore Memory integration
    - Deploy Campus Coach Browser Tool agent with retry logic
    - Verify agent deployments and connectivity
    - _Requirements: 6.1_
  
  - [ ] 9.2 Complete Step Functions workflow with all Lambda functions
    - Deploy ContentGenerationStack with complete Step Functions workflow
    - Integrate all Lambda functions (fetcher, generator, updater, campus_coach_invoker)
    - Add proper error handling and retry logic throughout workflow
    - Test end-to-end activity processing pipeline
    - _Requirements: 2.2, 2.3, 8.3, 6.1_
  
  - [ ] 9.3 Test AgentCore Memory and Campus Coach integration
    - Test personal style storage and retrieval via AgentCore Memory
    - Verify Campus Coach session extraction with retry logic for cold starts
    - Test session matching and confidence scoring
    - Validate memory persistence across invocations
    - _Requirements: 2.10, 5.1, 5.2, 5.3, 5.4_

## System Integration and Deployment

- [ ] 10. Complete deployment automation and documentation
  - [ ] 10.1 Complete CDK deployment scripts and environment configuration
    - Add environment configuration for different stages (dev, prod)
    - Implement webhook subscription automation with Strava
    - Add validation scripts for deployment verification
    - Create deployment orchestration script
    - _Requirements: 6.2, 6.4_
  
  - [ ] 10.2 Create comprehensive setup instructions and documentation
    - Write step-by-step setup guide with prerequisites
    - Document AgentCore CLI requirements and installation process
    - Add troubleshooting guide for common issues and monitoring commands
    - Create user guide for local web interface
    - _Requirements: 6.5_
  
  - [ ] 10.3 Implement clean uninstall process
    - Create CDK destroy scripts with proper resource cleanup
    - Add AgentCore cleanup scripts for agents and memory
    - Implement complete resource removal process with verification
    - Add data backup options before uninstall
    - _Requirements: 6.5_

- [ ] 11. Final integration testing and validation
  - [ ] 11.1 Test complete activity processing pipeline end-to-end
    - Test webhook → SQS → Step Functions → Bedrock → Strava update flow
    - Validate all module integrations (Campus Coach, Enduraw) work correctly
    - Test error scenarios and recovery mechanisms with SQS retry
    - Verify enhancement pause/resume functionality
    - _Requirements: All requirements validation_
  
  - [ ] 11.2 Verify security configurations and compliance
    - Test all security configurations and encryption at rest/in transit
    - Validate IAM permissions follow least privilege principle
    - Test OAuth token security and automatic refresh
    - Verify Secrets Manager integration for all credentials
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [ ] 11.3 Test local web interface functionality completely
    - Test OAuth flow end-to-end with Strava
    - Verify dashboard real-time updates and activity statistics
    - Test module configuration and management (enable/disable)
    - Validate enhancement pause/resume with persistence
    - Test error handling and user feedback
    - _Requirements: 1.1, 11.1, 12.1, 13.1_

- [ ]* 11.4 Write integration tests for complete pipeline
  - Test webhook → SQS → Step Functions → Bedrock → Strava update flow
  - Test module activation/deactivation scenarios
  - Test error recovery and retry mechanisms

- [ ] 12. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.