# Project Documentation References

This steering file ensures Kiro has access to all project documentation when working on the codebase.

## Core Project Documentation

### Essential Reading (Always Include)
- **README.md**: Project overview, prerequisites, getting started guide
- **docs/HIGH-LEVEL-DESIGN.md**: Complete system architecture, visual diagrams, technical decisions
- **docs/ARCHITECTURE.md**: Detailed technical implementation, AWS services, performance metrics

### Context-Specific Documentation (Include When Relevant)

#### For Infrastructure/Deployment Work
- **docs/SETUP.md**: Deployment procedures, environment configuration
- **docs/SECURITY.md**: Security practices, IAM policies, encryption

#### For Development/Debugging Work  
- **docs/CHANGELOG.md**: Recent changes, version history, known issues
- **docs/testing-guide.md**: Testing procedures, validation steps
- **docs/KNOWN-ISSUES.md**: Current active issues, troubleshooting, monitoring commands

## Documentation File References

Use these references to include specific documentation:

```
#[[file:README.md]]
#[[file:docs/HIGH-LEVEL-DESIGN.md]]
#[[file:docs/ARCHITECTURE.md]]
#[[file:docs/SETUP.md]]
#[[file:docs/SECURITY.md]]
#[[file:docs/CHANGELOG.md]]
#[[file:docs/testing-guide.md]]
#[[file:docs/KNOWN-ISSUES.md]]
```

## Project Context Summary

**Strava AI Boost** - Simplified Modular Strava Activity Enhancement
- **Purpose**: Automatically enhance Strava activity titles and descriptions using AI with local web interface
- **Architecture**: AWS serverless (Python CDK, Lambda, DynamoDB, Step Functions, Bedrock) + AgentCore CLI
- **AI Framework**: Strands Agents with AgentCore Memory for personalization
- **Modules**: Campus Coach integration (AgentCore Browser Tool), Enduraw integration
- **Performance Target**: ~$0.02/activity, <30s processing, 98% success rate
- **Status**: In development - simplified version of strava-ai-coach

## Technology Stack & Structure References

All technology stack details, project structure, and architecture decisions are documented in:

### Technology Stack
- **Language**: Python 3.12 (CDK, Lambda, local interface)
- **Infrastructure**: AWS CDK (Python) + AgentCore CLI scripts
- **AI Framework**: Strands Agents + AgentCore Memory + AgentCore Browser Tool
- **Local Interface**: Python Flask/FastAPI with AWS Cloudscape components
- **Dependencies**: Root `requirements.txt` and `lambda_functions/requirements.txt`

### Project Structure  
- **Specs**: `.kiro/specs/strava-ai-boost/` (requirements, design, tasks)
- **CDK Stacks**: `stacks/` (Python CDK infrastructure)
- **Lambda Functions**: `lambda_functions/` (Python 3.12)
- **Agents**: `src/agents/` (Strands + AgentCore agents)
- **Scripts**: `scripts/` (AgentCore CLI deployment)
- **Local Interface**: `local_interface/` (Python web app)

### Architecture Decisions
- **Simplification**: Local web interface vs hosted solution (no Cognito/CloudFront)
- **Modularity**: Extensible module system (Campus Coach, Enduraw, future modules)
- **AgentCore CLI**: Shell scripts instead of experimental CDK L2 constructs
- **Memory Integration**: AgentCore Memory for personalized content generation

## When to Include Documentation

### Always Include (Core Context)
- README.md - Project overview and prerequisites
- HIGH-LEVEL-DESIGN.md - System architecture and decisions

### Include for Code Changes
- ARCHITECTURE.md - Technical implementation details
- CHANGELOG.md - Recent changes and version history

### Include for Infrastructure Work
- SETUP.md - Deployment and configuration
- SECURITY.md - Security practices and policies

### Include for Testing/Debugging
- testing-guide.md - Testing procedures
- CHANGELOG.md - Known issues and recent fixes
- KNOWN-ISSUES.md - Current active issues and troubleshooting

This approach ensures Kiro always has access to up-to-date documentation without duplicating content in steering files. All technical details are maintained in the authoritative `/docs` directory.
