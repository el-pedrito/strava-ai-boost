# Strava AI Boost

**Version:** v0.1.0  
**Status:** In Development - Infrastructure Complete

Strava AI Boost is a simplified, modular serverless application that automatically enhances Strava activity titles and descriptions using Amazon Bedrock AI. Built as a streamlined version of the existing Strava AI Coach project, it focuses on core functionality while maintaining modularity for future integrations.

## Overview

The system uses a local web interface approach to avoid complexity of user management, authentication systems, and secure web hosting. This prioritizes simplicity and rapid deployment for individual users who can install the system in their own AWS environment.

### Key Features

- **Local Web Interface**: Python Flask application with AWS Cloudscape components
- **Modular Architecture**: Extensible module system starting with Campus Coach integration  
- **AI-Powered Enhancement**: Amazon Bedrock Claude Sonnet 4.5 for intelligent content generation
- **AgentCore Memory**: Persistent personalization avoiding repetitive expressions
- **Campus Coach Integration**: AgentCore Browser Tool for automated session extraction
- **Serverless Architecture**: Full AWS serverless stack for cost efficiency and scalability

## Prerequisites

### Required Services

1. **Strava Account** (social fitness platform)
   - API Limits: 100 req/15min, 1000 req/day
   - OAuth application registration required

2. **Campus Coach Account** (French training platform) - Optional Module
   - Subscription required for module activation
   - Website: https://campus.coach

3. **Enduraw Integration** (third-party Strava app) - Optional Module
   - Enhanced analytics (pace without wind, weather impact)
   - Processing delay: 2-7 minutes when enabled

4. **AWS Account**
   - Cost: ~$0.02 per activity (estimated)
   - Region: eu-west-1 recommended
   - AgentCore CLI access required

### Development Environment

- Python 3.12+
- AWS CDK CLI
- AgentCore CLI
- Node.js (for CDK)

## Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Local Web     │    │   AWS Serverless │    │     Strava      │
│   Interface     │◄──►│    Backend       │◄──►│      API        │
│ (Cloudscape UI) │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   Third-Party    │
                       │   Integrations   │
                       │ (Campus Coach,   │
                       │   Enduraw)       │
                       └──────────────────┘
```

### Technology Stack

**Infrastructure:**
- AWS CDK: Python constructs
- Python Runtime: 3.12
- Region: eu-west-1 (Ireland)
- AgentCore CLI: Shell script deployment

**AWS Services:**
- Lambda: Python 3.12 runtime
- DynamoDB: Core tables (activities, config, rate-limits, sessions)
- Step Functions: Activity processing workflow
- SQS: Message queuing with DLQ
- Bedrock: Claude Sonnet 4.5
- Secrets Manager: OAuth tokens and credentials
- API Gateway: Local interface REST API

**AI/ML Framework:**
- Strands Agents: Agent orchestration framework
- AgentCore Memory: Persistent personalization
- AgentCore Browser Tool: Campus Coach scraping
- Claude Sonnet 4.5: Content generation and analysis

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure AWS Profile

```bash
export AWS_PROFILE=your-aws-profile
aws sts get-caller-identity --profile your-aws-profile
```

### 3. Deploy Infrastructure

```bash
# Bootstrap CDK (first time only)
cdk bootstrap --profile your-aws-profile

# Deploy infrastructure
cdk deploy --profile your-aws-profile
```

### 4. Run Tests

```bash
# Run property-based security tests
python -m pytest tests/test_infrastructure_properties.py -v

# Run all tests
python -m pytest -v
```

## Project Structure

```
strava-ai-boost/
├── app.py                              # CDK app entry point
├── stacks/
│   ├── core_infrastructure_stack.py    # DynamoDB, IAM roles
│   ├── api_gateway_stack.py           # Local interface API
│   ├── webhook_processing_stack.py    # Strava webhooks, SQS
│   ├── content_generation_stack.py    # Step Functions, Bedrock
│   └── monitoring_stack.py            # CloudWatch, alarms
├── scripts/
│   ├── deploy_agentcore.sh            # AgentCore CLI deployment
│   ├── setup_memory.sh                # AgentCore Memory configuration
│   └── deploy_campus_coach_agent.sh   # Campus Coach agent deployment
├── lambda_functions/
│   ├── webhook_handler.py             # Strava webhook processing
│   ├── activity_processor.py          # Activity data processing
│   ├── content_generator.py           # Bedrock content generation
│   └── campus_coach_invoker.py        # AgentCore invocation
├── src/
│   ├── agents/
│   │   ├── content_generation_agent.py # Strands Agent with AgentCore Memory
│   │   ├── campus_coach_agent.py       # AgentCore Browser Tool agent
│   │   └── session_matching_agent.py   # Strands Agent for matching
│   ├── modules/
│   │   ├── base_module.py             # Base module interface
│   │   ├── campus_coach_module.py     # Campus Coach integration
│   │   └── enduraw_module.py          # Enduraw integration
│   └── utils/
│       ├── strava_client.py           # Strava API client
│       ├── rate_limiter.py            # Rate limiting logic
│       └── data_models.py             # Pydantic models
├── local_interface/
│   ├── app.py                         # Flask/FastAPI application
│   └── static/                        # Cloudscape UI components
├── tests/
│   └── test_infrastructure_properties.py # Property-based security tests
└── docs/
    ├── README.md                      # This file
    ├── ARCHITECTURE.md                # Technical architecture
    ├── HIGH-LEVEL-DESIGN.md           # System design and decisions
    ├── SETUP.md                       # Deployment procedures
    ├── SECURITY.md                    # Security practices
    ├── CHANGELOG.md                   # Version history
    ├── testing-guide.md               # Testing procedures
    └── KNOWN-ISSUES.md                # Current issues and troubleshooting
```

## Performance Targets

- **Webhook Processing**: <5 seconds to queue
- **Content Generation**: <30 seconds end-to-end
- **Dashboard Loading**: <2 seconds
- **Configuration Changes**: <1 second
- **Cost per Activity**: ~$0.02 (target)

## Security

- **Data Encryption**: AWS managed encryption for all DynamoDB tables
- **Secure Communication**: HTTPS for all API endpoints
- **Credential Management**: AWS Secrets Manager with automatic rotation
- **IAM**: Least privilege principle with AWS managed policies
- **Local Interface**: Local-only access (127.0.0.1)

## Documentation

For detailed information, see:

- [Architecture Documentation](docs/ARCHITECTURE.md) - Technical implementation details
- [High-Level Design](docs/HIGH-LEVEL-DESIGN.md) - System architecture and decisions
- [Setup Guide](docs/SETUP.md) - Deployment and configuration
- [Security Guide](docs/SECURITY.md) - Security practices and policies
- [Testing Guide](docs/testing-guide.md) - Testing procedures and validation
- [Known Issues](docs/KNOWN-ISSUES.md) - Current issues and troubleshooting
- [Changelog](docs/CHANGELOG.md) - Version history and changes

## Contributing

1. Follow the property-based testing approach for all infrastructure changes
2. Update CHANGELOG.md for all significant changes
3. Ensure all tests pass before committing
4. Use AWS profile `your-aws-profile` for all AWS operations

## License

This project is licensed under the MIT License.

---

**Current Version:** v0.1.0  
**Last Updated:** 2025-12-21  
**Status:** Infrastructure Complete - Ready for OAuth Integration