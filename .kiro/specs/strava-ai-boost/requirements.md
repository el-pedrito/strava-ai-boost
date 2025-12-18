# Requirements Document

## Introduction

**Strava AI Boost** is a simplified, modular web application that automatically enhances Strava activity titles and descriptions to make them more engaging for the community. This system is designed as a radical simplification of the existing Strava AI Coach project, focusing on core functionality while maintaining modularity for future integrations.

**Version 1 Approach:** The system uses a local web interface to avoid the complexity of user management, authentication systems (Cognito), and secure web hosting (CloudFront/S3). This approach prioritizes simplicity and rapid deployment for individual users. Future versions may include hosted solutions with multi-user support.

The system provides an easy-to-deploy AWS serverless solution that users can install in their own AWS environment with minimal effort, transforming basic Strava activities into expert-level content using Amazon Bedrock AI.

## Glossary

- **Strava**: Social fitness platform where athletes track running, cycling, and other activities
- **Amazon Bedrock**: AWS managed AI service providing access to foundation models like Claude
- **Campus Coach**: French running training platform providing structured weekly training programs
- **Strava AI Boost System**: The complete serverless application for automated content enhancement
- **OAuth Flow**: Secure authentication process for connecting user's Strava account
- **Webhook**: Real-time notification mechanism from Strava when activities are created/updated
- **Activity Enhancement**: Process of improving Strava activity titles and descriptions using AI
- **Module**: Independent, activatable/deactivatable integration component (e.g., Campus Coach module)
- **Local Web Interface**: Simple web application running locally to configure and monitor the system
- **API Gateway**: AWS service providing REST API endpoints for the local web interface
- **Enduraw**: Third-party Strava app providing enhanced analytics (pace without wind, weather impact, elevation cost)
- **SQS Queue**: AWS Simple Queue Service for reliable message processing and retry logic
- **Step Functions**: AWS service for orchestrating serverless workflows with visual monitoring
- **AWS Cloudscape**: Design system for building intuitive, accessible, and performant user interfaces

## Requirements

### Requirement 1

**User Story:** As a runner, I want to connect my Strava account to the system, so that I can authorize automatic enhancement of my activity descriptions.

#### Acceptance Criteria

1. WHEN a user starts the local web application THEN the Strava AI Boost System SHALL display a configuration interface built with AWS Cloudscape design system
2. WHEN a user clicks the "Connect with Strava" button THEN the Strava AI Boost System SHALL redirect to Strava OAuth authorization page
3. WHEN a user authorizes the application THEN the Strava AI Boost System SHALL securely store the OAuth tokens in AWS Secrets Manager
4. WHEN OAuth tokens are stored THEN the Strava AI Boost System SHALL display connection status in the local interface
5. WHEN OAuth tokens expire THEN the Strava AI Boost System SHALL automatically refresh them using the stored refresh token

### Requirement 2

**User Story:** As an athlete, I want my new Strava activities to be automatically enhanced with engaging descriptions, so that my community sees professional-quality content without manual effort.

#### Acceptance Criteria

1. WHEN a user uploads a new activity to Strava THEN the Strava AI Boost System SHALL receive a webhook notification within 30 seconds
2. WHEN a webhook is received THEN the Strava AI Boost System SHALL queue the activity processing request in SQS for reliable processing
3. WHEN an activity message is queued THEN the Strava AI Boost System SHALL trigger a Step Functions workflow to orchestrate the enhancement process
4. WHEN the Step Functions workflow starts THEN the Strava AI Boost System SHALL fetch the complete activity data from Strava API
5. WHEN activity data is retrieved THEN the Strava AI Boost System SHALL store the original description in DynamoDB for historical backup
6. WHEN activity data is analyzed THEN the Strava AI Boost System SHALL process any activity type (running, cycling, fitness, etc.) based on available Strava data
7. WHEN analyzing activity performance THEN the Strava AI Boost System SHALL utilize all available Strava activity data (67+ fields including performance metrics, environmental context, effort indicators, social engagement, and equipment details) for comprehensive analysis
8. WHEN detailed analysis is required THEN the Strava AI Boost System SHALL fetch complete Strava streams data (velocity_smooth, heartrate, time, distance, altitude) with second-by-second granularity for maximum precision
9. WHEN analyzing streams data THEN the Strava AI Boost System SHALL use Amazon Bedrock AI to intelligently detect effort patterns, intervals, heart rate zones, and workout classification inspired by the strava-ai-coach data-driven approach
10. WHEN generating content THEN the Strava AI Boost System SHALL analyze previous activities to understand personal style, avoid repetitive expressions, and vary response structure while maintaining authenticity
11. WHEN analysis is complete THEN the Strava AI Boost System SHALL generate an engaging title and description using sport-specific terminology while maintaining a fun, motivational, and personal tone combining strava-ai-coach technical precision with strata-activity-enhancer authenticity
12. WHEN content is generated THEN the Strava AI Boost System SHALL update the Strava activity with the enhanced content
13. WHEN processing fails at any step THEN the Strava AI Boost System SHALL use SQS retry logic with exponential backoff and dead letter queue for failed messages

### Requirement 3

**User Story:** As an athlete with Campus Coach integration, I want the system to automatically match my Strava activities with planned training sessions, so that my descriptions include intelligent analysis of session execution.

#### Acceptance Criteria

1. WHEN Campus Coach module is active and a new activity is processed THEN the Strava AI Boost System SHALL fetch complete Strava streams data (velocity_smooth, heartrate, time, distance, altitude) with second-by-second granularity
2. WHEN streams data is analyzed THEN the Strava AI Boost System SHALL use Amazon Bedrock AI to intelligently detect effort patterns, intervals, heart rate zones, and workout structure from the detailed streams data
3. WHEN effort analysis is complete THEN the Strava AI Boost System SHALL use Amazon Bedrock to intelligently match the detected activity pattern against planned Campus Coach sessions with confidence scoring
4. WHEN a matching session is found THEN the Strava AI Boost System SHALL calculate a confidence score for the match based on effort patterns, intervals detected, and heart rate zone correspondence
5. WHEN the confidence score is above threshold THEN the Strava AI Boost System SHALL include detailed session compliance analysis comparing detected intervals with planned workout structure
6. WHEN session compliance is analyzed THEN the Strava AI Boost System SHALL compare actual performance (pace variability, heart rate zones, interval precision, effort distribution) with planned targets using streams-based analysis
7. WHEN no matching session is found THEN the Strava AI Boost System SHALL generate standalone technical activity analysis using the detected effort patterns and workout classification

### Requirement 4

**User Story:** As a runner, I want to configure which modules are active for my account, so that I can customize the type of analysis and content generation.

#### Acceptance Criteria

1. WHEN a user accesses the local configuration interface THEN the Strava AI Boost System SHALL display available modules (Campus Coach initially, with extensibility for Runna, imported training plans, etc.)
2. WHEN a user enables a module THEN the Strava AI Boost System SHALL activate that module's functionality for future activities
3. WHEN a user disables a module THEN the Strava AI Boost System SHALL deactivate that module while preserving its configuration
4. WHEN module settings are changed THEN the Strava AI Boost System SHALL save the configuration to DynamoDB
5. WHEN a module is active THEN the Strava AI Boost System SHALL include that module's analysis in content generation

### Requirement 5

**User Story:** As a Campus Coach subscriber, I want to enable the Campus Coach module, so that my activity descriptions include analysis comparing actual performance with planned training sessions.

#### Acceptance Criteria

1. WHEN a user enables Campus Coach module THEN the Strava AI Boost System SHALL prompt for Campus Coach login credentials
2. WHEN credentials are provided THEN the Strava AI Boost System SHALL securely store them in AWS Secrets Manager
3. WHEN Campus Coach module is active THEN the Strava AI Boost System SHALL deploy an AgentCore Browser Tool agent for automated web scraping
4. WHEN the Campus Coach agent runs THEN the Strava AI Boost System SHALL extract weekly training sessions automatically on a daily or weekly schedule
5. WHEN a new activity is processed THEN the Strava AI Boost System SHALL match it against planned Campus Coach sessions
6. WHEN a match is found THEN the Strava AI Boost System SHALL include comparative analysis in the generated content

### Requirement 6

**User Story:** As a developer, I want to deploy the system in my own AWS account, so that I have full control over my data and infrastructure.

#### Acceptance Criteria

1. WHEN a user runs the deployment script THEN the Strava AI Boost System SHALL create all required AWS serverless resources using CDK
2. WHEN deployment is complete THEN the Strava AI Boost System SHALL provide instructions to start the local web interface
3. WHEN AWS resources are created THEN the Strava AI Boost System SHALL use secure defaults with encryption at rest and in transit
4. WHEN the system is deployed THEN the Strava AI Boost System SHALL automatically configure webhook subscriptions with Strava
5. WHEN a user wants to remove the system THEN the Strava AI Boost System SHALL provide a clean uninstall process

### Requirement 7

**User Story:** As a user, I want my data to be stored securely in my own AWS environment, so that I maintain privacy and control over my personal information.

#### Acceptance Criteria

1. WHEN user data is stored THEN the Strava AI Boost System SHALL encrypt all data at rest using AWS managed encryption
2. WHEN data is transmitted THEN the Strava AI Boost System SHALL use HTTPS for all communications
3. WHEN storing OAuth tokens THEN the Strava AI Boost System SHALL use AWS Secrets Manager with automatic rotation
4. WHEN accessing the local web interface THEN the Strava AI Boost System SHALL fetch configuration and status from AWS resources securely
5. WHEN processing activities THEN the Strava AI Boost System SHALL store user configuration and activity data in DynamoDB tables

### Requirement 8

**User Story:** As a system administrator, I want the system to handle errors gracefully, so that temporary failures don't prevent activity processing.

#### Acceptance Criteria

1. WHEN Strava API rate limits are exceeded THEN the Strava AI Boost System SHALL queue requests and retry with exponential backoff
2. WHEN Amazon Bedrock is temporarily unavailable THEN the Strava AI Boost System SHALL retry the request up to 3 times
3. WHEN webhook processing fails THEN the Strava AI Boost System SHALL log the error and attempt reprocessing
4. WHEN OAuth tokens are invalid THEN the Strava AI Boost System SHALL attempt automatic refresh before failing
5. WHEN a module fails to process THEN the Strava AI Boost System SHALL continue with basic content generation

### Requirement 9

**User Story:** As an Enduraw user, I want to configure Enduraw integration in my system, so that my activity descriptions include enhanced analytics like pace without wind and weather impact.

#### Acceptance Criteria

1. WHEN a user accesses the local configuration interface THEN the Strava AI Boost System SHALL display an Enduraw integration toggle option
2. WHEN a user enables Enduraw integration THEN the Strava AI Boost System SHALL modify the webhook processing workflow to wait for Enduraw analysis
3. WHEN Enduraw integration is active and a new activity webhook is received THEN the Strava AI Boost System SHALL wait 2-7 minutes for Enduraw to process the activity
4. WHEN Enduraw analysis is available THEN the Strava AI Boost System SHALL fetch the enhanced metrics (pace without wind, weather conditions, elevation cost)
5. WHEN Enduraw data is retrieved THEN the Strava AI Boost System SHALL include these enhanced metrics in the content generation process
6. WHEN Enduraw integration is disabled THEN the Strava AI Boost System SHALL process activities immediately without waiting for enhanced analytics

### Requirement 10

**User Story:** As a system administrator, I want the system to respect Strava API rate limits (100 requests per 15 minutes, 1000 requests per day), so that the service doesn't get temporarily banned for 15 minutes or blocked for an entire day, which would prevent all users from having their activities enhanced and make the system completely unusable during peak usage periods.

#### Acceptance Criteria

1. WHEN making Strava API calls THEN the Strava AI Boost System SHALL track and respect the 100 requests per 15 minutes limit to prevent temporary 15-minute bans
2. WHEN making Strava API calls THEN the Strava AI Boost System SHALL track and respect the 1000 requests per day limit to prevent daily service blockage
3. WHEN rate limits are approached THEN the Strava AI Boost System SHALL queue pending requests and process them with appropriate delays to maintain service availability
4. WHEN rate limits are exceeded THEN the Strava AI Boost System SHALL implement exponential backoff retry strategy to avoid cascading failures
5. WHEN rate limit status changes THEN the Strava AI Boost System SHALL store rate limit tracking data in DynamoDB for persistence across Lambda invocations

### Requirement 11

**User Story:** As a user, I want to see a dashboard with statistics and activity processing status, so that I can monitor system performance and engagement metrics.

#### Acceptance Criteria

1. WHEN a user accesses the local web interface THEN the Strava AI Boost System SHALL display a dashboard with system statistics using AWS Cloudscape components
2. WHEN viewing the dashboard THEN the Strava AI Boost System SHALL show total activities processed, success rate, and recent activity history
3. WHEN viewing engagement metrics THEN the Strava AI Boost System SHALL display kudos received, comments, and engagement improvements on enhanced activities
4. WHEN an activity is being processed THEN the Strava AI Boost System SHALL show real-time processing status with Step Functions workflow progress
5. WHEN processing fails THEN the Strava AI Boost System SHALL display error details and retry status from SQS dead letter queue
6. WHEN viewing activity history THEN the Strava AI Boost System SHALL show which activities were enhanced, when, and with which modules active

### Requirement 12

**User Story:** As a user, I want to see the status of my activity processing, so that I can understand what the system is doing with my data.

#### Acceptance Criteria

1. WHEN an activity is being processed THEN the Strava AI Boost System SHALL display processing status in the local web interface
2. WHEN processing is complete THEN the Strava AI Boost System SHALL show a success notification with generated content preview
3. WHEN an error occurs THEN the Strava AI Boost System SHALL display a clear error message with suggested actions
4. WHEN viewing activity history THEN the Strava AI Boost System SHALL show which activities were enhanced and when
5. WHEN modules are processing THEN the Strava AI Boost System SHALL indicate which modules are active for each activity