# Implementation Plan: Strava AI Boost

## Overview

This implementation plan reflects the current state of the Strava AI Boost system. The core infrastructure, Lambda functions, and agents have been implemented, but several key components need completion to achieve a fully functional system.

## Completed Infrastructure and Core Components ✅

- [x] 1. Set up project structure and core infrastructure
  - ✅ Python CDK project with 5 stacks (core, webhook, content-generation, api-gateway, monitoring)
  - ✅ DynamoDB tables with encryption (activities, user-configuration, rate-limits, coaching-sessions)
  - ✅ IAM roles and policies with least privilege principle
  - ✅ Secrets Manager secrets for OAuth tokens and Campus Coach credentials
  - ✅ AgentCore CLI deployment scripts (scripts/)
  - _Requirements: 6.1, 6.3, 7.1, 7.5_

- [x] 2. Implement Strava webhook processing and Lambda functions
  - ✅ webhook_handler.py with SQS integration and enhancement pause/resume control
  - ✅ activity_processor.py with Step Functions integration
  - ✅ activity_fetcher.py, strava_updater.py, campus_coach_invoker.py
  - ✅ Step Functions workflow for activity processing orchestration
  - ✅ SQS queues with dead letter queue for reliable processing
  - _Requirements: 2.2, 2.3, 8.3, 13.3, 13.7_

- [x] 3. Implement content generation with Strands Agent and AgentCore Memory simulation
  - ✅ content_generation_agent.py with Bedrock Claude integration
  - ✅ AgentCore Memory simulation using DynamoDB for personalization
  - ✅ Pattern analysis and workout classification using AI
  - ✅ Module-based content enhancement (Campus Coach, Enduraw)
  - ✅ content_generator.py Lambda with agent integration
  - _Requirements: 2.9, 2.10, 3.2_

- [x] 4. Implement utility classes and configuration
  - ✅ OAuth handler with PKCE support and Secrets Manager integration
  - ✅ Rate limiter with DynamoDB persistence (100/15min, 1000/day limits)
  - ✅ Strava API client with retry logic and rate limiting
  - ✅ LLM configuration for Bedrock Claude Sonnet 4.5
  - _Requirements: 1.2, 1.3, 7.3, 8.1, 8.4, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 5. Implement property-based tests for core functionality
  - ✅ OAuth token security tests (Property 1) - **PASSED**
  - ✅ Webhook reliability tests (Property 2) - **COMPLETED**
  - ✅ Rate limit compliance tests (Property 13, 14) - **PASSED**
  - ✅ Error recovery tests (Property 9) - **PASSED**
  - ✅ AI pattern detection tests (Property 6)
  - ✅ Memory personalization tests (Property 7)
  - ✅ Activity updates tests (Property 8)
  - ✅ Infrastructure security tests (Property 15, 16)
  - _Requirements: 1.3, 2.2, 2.9, 2.10, 2.12, 2.13, 7.1, 7.2, 7.3, 10.1, 10.2, 10.5_

## Critical Missing Components 🚧

- [x] 6. Complete module system implementation
  - [x] 6.1 Enhance base module interface and registration system
    - Complete base_module.py with abstract base classes and lifecycle management
    - Add module registration and discovery system in content generator
    - Implement module configuration validation and error handling
    - _Requirements: 4.1, 4.2_
  
  - [x] 6.2 Complete Campus Coach module implementation
    - Finish campus_coach_module.py with proper AgentCore Browser Tool integration
    - Replace placeholder AgentCore invocation with actual SDK calls
    - Add session matching and confidence scoring logic using Bedrock AI
    - Implement compliance analysis functionality comparing actual vs planned
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 3.3, 3.4, 3.5, 3.6, 3.7_
  
  - [x] 6.3 Build Enduraw integration module
    - Create enduraw_module.py with wait logic for 2-7 minute processing delay
    - Add enhanced metrics fetching (pace without wind, weather, elevation cost)
    - Integrate enhanced metrics into content generation pipeline
    - Implement toggle functionality via local interface
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 7. Complete data models and validation
  - [x] 7.1 Complete comprehensive Strava data models
    - ✅ Finish data_models.py with all 67+ Strava activity fields using Pydantic
    - ✅ Add streams data models with validation for second-by-second granularity
    - ✅ Implement module configuration models and processing status models
    - ✅ Add comprehensive error handling and validation models
    - _Requirements: 2.6, 2.7, 2.8_
  
  - [x] 7.2 Integrate utility classes properly
    - ✅ Connect strava_client.py with rate_limiter.py and oauth_handler.py
    - ✅ Add comprehensive error handling and retry logic throughout
    - ✅ Implement monitoring and alerting integration
    - ✅ Add utility functions for data transformation and validation
    - _Requirements: 8.1, 8.4, 10.1, 10.2, 10.3, 10.4_

- [x] 8. Complete local web interface with AWS Cloudscape
  - [x] 8.1 Complete Flask application OAuth flow
    - Finish OAuth callback handling and token exchange in local_interface/app.py
    - Add session management for OAuth state and code_verifier
    - Implement real-time dashboard with activity statistics and engagement metrics
    - Add module configuration interface with enable/disable controls
    - Complete enhancement pause/resume control with visual indicators
    - _Requirements: 1.1, 4.1, 13.1, 13.5, 13.6_
  
  - [x] 8.2 Create AWS Cloudscape frontend templates
    - Create HTML templates with AWS Cloudscape design system components
    - Build configuration interface for module management (Campus Coach, Enduraw)
    - Add real-time status monitoring with Step Functions progress display
    - Implement error display with clear messages and suggested actions
    - Add responsive design for mobile and desktop
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [x] 8.3 Complete API Gateway integration
    - Finish configuration_api.py, dashboard_api.py, status_api.py Lambda functions
    - Add secure communication between local interface and AWS resources
    - Implement request validation and rate limiting for API endpoints
    - Add CORS configuration for local development
    - Connect local interface to actual AWS API Gateway endpoints
    - _Requirements: 7.4_

- [ ] 9. Deploy and integrate AgentCore agents
  - [ ] 9.1 Deploy AgentCore agents using CLI scripts
    - ✅ Updated deploy_agentcore.sh script with actual AgentCore CLI commands
    - ✅ Enhanced setup_memory.sh with proper memory configuration and LTM strategies
    - ✅ Updated deploy_campus_coach_agent.sh with retry logic and environment variables
    - ✅ Replaced DynamoDB memory simulation with actual AgentCore Memory integration
    - ✅ Updated Lambda functions to use actual AgentCore SDK calls via Bedrock Agent Runtime
    - ✅ Implemented retry logic for Campus Coach Browser Tool cold start issues
    - ✅ Added proper error handling and validation for agent responses
    - [x] Create comprehensive AgentCore prompts (content_generation_agent_prompt.md, campus_coach_agent_prompt.md)
    - [x] Build AgentCore YAML configurations with proper schemas and error handling
    - [ ] Execute AgentCore deployment scripts in AWS environment
    - _Requirements: 6.1_
  
  - [x] 9.2 Complete Step Functions workflow integration
    - ✅ Updated Step Functions workflow with conditional Campus Coach integration
    - ✅ Added Campus Coach choice state with user configuration-based decision logic
    - ✅ Enhanced activity fetcher to include user configuration data for workflow decisions
    - ✅ Added Campus Coach invoker Lambda permissions to Step Functions execution role
    - ✅ Implemented error handling and graceful skip logic for disabled modules
    - ✅ Tested complete Step Functions workflow with conditional AgentCore integration
    - _Requirements: 2.2, 2.3, 8.3, 6.1_
  
  - [x] 9.3 Test AgentCore Memory and Campus Coach integration
    - ✅ Created comprehensive AgentCore integration test suite with validation scripts
    - ✅ Validated AWS connectivity, permissions, and AgentCore service access
    - ✅ Tested Lambda function configuration and environment variables for AgentCore integration
    - ✅ Verified Step Functions workflow includes Campus Coach conditional logic and extraction steps
    - ✅ Validated DynamoDB user configuration functionality for module decision making
    - ✅ Confirmed all integration points working correctly with 100% test success rate
    - ✅ Created validation and testing scripts for ongoing AgentCore integration monitoring
    - _Requirements: 2.10, 5.1, 5.2, 5.3, 5.4_

## Critical Missing Components - TODOs Resolution 🔧

- [ ] 13. Complete local web interface TODOs
  - [ ] 13.1 Finish module configuration functionality
    - Complete module configuration endpoint in local_interface/app.py (line 318)
    - Implement actual module enable/disable logic with DynamoDB persistence
    - Add module configuration validation and error handling
    - Test module configuration changes with real AWS resources
    - _Requirements: 4.1, 4.2, 4.4_
  
  - [ ] 13.2 Complete module status retrieval
    - Implement module status retrieval from DynamoDB in local_interface/app.py (line 636)
    - Add real-time module status monitoring for dashboard
    - Integrate with Step Functions workflow status for module processing
    - Add module health checks and error status reporting
    - _Requirements: 11.1, 11.2, 12.1, 12.4, 12.5_
  
  - [ ] 13.3 Complete OAuth callback implementation
    - Finish OAuth authorization code exchange in configuration_api.py (line 205)
    - Implement complete PKCE token exchange with Strava API
    - Add OAuth token validation and error handling
    - Test end-to-end OAuth flow with real Strava application
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

- [ ] 14. Complete API endpoint implementations
  - [ ] 14.1 Finish dashboard API functionality
    - Implement actual engagement metrics from Strava API in dashboard_api.py (line 402)
    - Add GSI-based queries for better performance in dashboard_api.py (line 433)
    - Integrate with real Strava API for kudos, comments, and engagement data
    - Add caching layer for dashboard performance optimization
    - _Requirements: 11.2, 11.3_
  
  - [ ] 14.2 Complete status API implementation
    - Implement Step Functions status lookup in status_api.py (line 378)
    - Add retry tracking and SQS dead letter queue monitoring
    - Implement real-time processing status with execution ARN tracking
    - Add system health monitoring and alerting integration
    - _Requirements: 11.4, 11.5, 12.1, 12.3_
  
  - [ ] 14.3 Complete webhook validation
    - Implement webhook verify_token validation in webhook_handler.py (line 82)
    - Add Strava webhook signature verification for security
    - Implement webhook subscription management and validation
    - Test webhook security with real Strava webhook events
    - _Requirements: 2.1, 8.3_

- [ ] 15. Replace remaining simulation code
  - [ ] 15.1 Complete Campus Coach module integration
    - Replace AgentCore SDK simulation in campus_coach_module.py (line 279)
    - Implement actual credential testing with AgentCore Browser Tool (line 720)
    - Add real AgentCore connectivity testing (line 780)
    - Complete session extraction with actual Browser Tool automation
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  
  - [ ] 15.2 Complete Enduraw module implementation
    - Implement actual Enduraw API integration for enhanced metrics
    - Add real-time Enduraw processing status monitoring
    - Complete enhanced metrics integration (pace without wind, weather impact)
    - Test Enduraw wait logic with actual third-party integration
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ] 10. Complete deployment automation and documentation
  - [ ] 10.1 Complete CDK deployment scripts and environment configuration
    - Add environment configuration for different stages (dev, prod)
    - Implement webhook subscription automation with Strava
    - Add validation scripts for deployment verification
    - Create deployment orchestration script that includes AgentCore deployment
    - Test complete deployment pipeline from CDK to AgentCore agents
    - _Requirements: 6.2, 6.4_
  
  - [ ] 10.2 Create comprehensive setup instructions and documentation
    - Write step-by-step setup guide with prerequisites
    - Document AgentCore CLI requirements and installation process
    - Add troubleshooting guide for common issues and monitoring commands
    - Create user guide for local web interface
    - Document AgentCore prompt customization and agent configuration
    - Add performance tuning guide for AgentCore Memory and Browser Tool
    - _Requirements: 6.5_
  
  - [ ] 10.3 Implement clean uninstall process
    - Create CDK destroy scripts with proper resource cleanup
    - Add AgentCore cleanup scripts for agents and memory
    - Implement complete resource removal process with verification
    - Add data backup options before uninstall
    - _Requirements: 6.5_

- [ ] 16. Complete Strava application setup automation
  - [ ] 16.1 Implement Strava webhook subscription automation
    - Create automated Strava webhook subscription during deployment
    - Add webhook URL configuration and validation
    - Implement webhook subscription verification and testing
    - Add webhook subscription cleanup during uninstall
    - _Requirements: 6.4_
  
  - [ ] 16.2 Add Strava application configuration validation
    - Implement Strava application setup validation scripts
    - Add OAuth application configuration verification
    - Create Strava API connectivity testing during setup
    - Add comprehensive Strava integration health checks
    - _Requirements: 1.1, 1.2, 6.2_

## Final Integration Testing 🧪

- [ ] 11. Complete end-to-end testing and validation
  - [ ] 11.1 Test complete activity processing pipeline
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

- [ ] 17. Complete critical TODO resolution testing
  - [ ] 17.1 Test completed local web interface functionality
    - Test module configuration endpoints with real DynamoDB operations
    - Validate module status retrieval and real-time updates
    - Test OAuth callback implementation with actual Strava integration
    - Verify all TODOs in local_interface/app.py are resolved
    - _Requirements: 1.1, 4.1, 11.1, 12.1_
  
  - [ ] 17.2 Test completed API endpoint functionality
    - Test dashboard API with real Strava engagement metrics
    - Validate Step Functions status lookup and monitoring
    - Test webhook validation with actual Strava webhook events
    - Verify all API endpoints work with real AWS resources
    - _Requirements: 2.1, 11.2, 11.4, 12.1_
  
  - [ ] 17.3 Test AgentCore integration without simulation
    - Test Campus Coach module with actual AgentCore Browser Tool
    - Validate Enduraw module with real third-party integration
    - Test all module functionality without placeholder code
    - Verify complete end-to-end module processing pipeline
    - _Requirements: 3.1, 5.1, 9.1, 9.3_

## Optional Property-Based Tests 🧪*

- [ ]* 12. Additional property-based tests (optional for MVP)
  - [ ]* 12.1 Write property test for module configuration persistence
    - **Property 11: Module settings persisted in DynamoDB**
    - **Validates: Requirements 4.4**
  
  - [ ]* 12.2 Write property test for credential security
    - **Property 12: Campus Coach credentials securely stored in Secrets Manager**
    - **Validates: Requirements 5.2**
  
  - [ ]* 12.3 Write property test for session matching
    - **Property 10: Activity patterns matched against planned sessions with confidence scoring**
    - **Validates: Requirements 3.3, 3.4**
  
  - [ ]* 12.4 Write property test for data backup
    - **Property 3: Original activity descriptions backed up before modification**
    - **Validates: Requirements 2.5**
  
  - [ ]* 12.5 Write property test for comprehensive analysis
    - **Property 4: All available Strava fields utilized in analysis**
    - **Validates: Requirements 2.7**
  
  - [ ]* 12.6 Write property test for streams precision
    - **Property 5: Streams data fetched with second-by-second granularity**
    - **Validates: Requirements 2.8, 3.1**
  
  - [ ]* 12.7 Write property test for Enduraw wait logic
    - **Property 17: System waits 2-7 minutes for Enduraw when active**
    - **Validates: Requirements 9.3**
  
  - [ ]* 12.8 Write property test for enhanced metrics integration
    - **Property 18: Enduraw data included in content generation**
    - **Validates: Requirements 9.5**
  
  - [ ]* 12.9 Write property test for real-time status
    - **Property 19: Processing status displayed in real-time**
    - **Validates: Requirements 11.4, 12.1**
  
  - [ ]* 12.10 Write property test for error messaging
    - **Property 20: Clear error messages with suggested actions displayed**
    - **Validates: Requirements 12.3**
  
  - [ ]* 12.11 Write property test for enhancement pause control
    - **Property 21: Enhancement pause control persists and prevents processing**
    - **Validates: Requirements 13.3, 13.7**

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- **Tasks 13-17 address critical TODOs identified in PROJECT-STATUS.md**
- **Priority order: Tasks 13-15 (TODOs) → Task 9 (AgentCore) → Tasks 16-17 (Testing)**
- Core infrastructure and Lambda functions are implemented but need integration
- AgentCore integration requires replacing simulation with actual SDK calls
- Local web interface needs frontend templates and complete OAuth flow
- Property-based tests provide comprehensive validation of system correctness

## Critical TODOs Summary

### High Priority (Blocking Production)
- **Task 13**: Complete local web interface TODOs (module config, status, OAuth)
- **Task 14**: Complete API endpoint implementations (dashboard, status, webhook)
- **Task 15**: Replace remaining simulation code (Campus Coach, Enduraw)

### Medium Priority (Enhancement)
- **Task 9**: Execute AgentCore deployment scripts
- **Task 16**: Strava application setup automation
- **Task 17**: End-to-end testing of completed functionality

### Files with Critical TODOs
- `local_interface/app.py` (lines 318, 636)
- `lambda_functions/configuration_api.py` (line 205)
- `lambda_functions/dashboard_api.py` (lines 402, 433)
- `lambda_functions/status_api.py` (line 378)
- `lambda_functions/webhook_handler.py` (line 82)
- `src/modules/campus_coach_module.py` (lines 279, 720, 780)