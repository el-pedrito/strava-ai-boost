# Strava AI Boost

Strava AI Boost is a production-ready, modular serverless application that automatically enhances Strava activity titles and descriptions using Amazon Bedrock AI and AgentCore Memory. Built with a clean API Gateway + Lambda architecture, it provides secure, scalable functionality with zero direct AWS SDK dependencies in the frontend.

## Quick Start

### Prerequisites

- AWS Account with CLI configured (`your-aws-profile` profile)
- Python 3.12+, Node.js (for CDK)
- AgentCore CLI (for Phase 2 only)
- Strava Account with API application registered

### Phase 1: Infrastructure Deployment (Required)

```bash
# 1. Clone and setup
git clone <repository-url>
cd strava-ai-boost
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export AWS_PROFILE=your-aws-profile

# 2. Deploy CDK Infrastructure (~10-15 min)
./scripts/deploy.sh dev

# 3. Validate Deployment (~2 min)
./scripts/validate_deployment.sh dev

# 4. Setup Local Environment (~30 sec)
./scripts/setup_local_env.sh

# 5. Configure Strava Webhook (~1 min)
./scripts/configure_strava_webhook.sh dev --auto-configure
```

**What this deploys**: 7 CDK stacks, DynamoDB tables, 13 Lambda functions, Step Functions, Secrets Manager, Bedrock fallback mode (Claude Sonnet 4.5), structured logging with AWS Lambda Powertools. System is immediately functional.

### Phase 2: AgentCore Enhancement (Optional)

Add advanced personalization with Long-Term Memory:

```bash
# 1. Create AgentCore Memories (~3 min)
./scripts/create_agentcore_memories.sh

# 2. Deploy AgentCore Agents (~5-10 min)
./scripts/deploy_agentcore_agents.sh

# 3. Configure Integration (~2 min)
./scripts/configure_agentcore_integration.sh

# 4. Redeploy Agents with Guardrails (~5 min)
./scripts/deploy_agentcore_agents.sh

# 5. Final CDK Deployment (~5 min)
cdk deploy --all --profile your-aws-profile --require-approval never
```

### Start Using the System

```bash
cd frontend
cp .env.example .env.local  # Edit with your API Gateway URL, API key, and user ID
npm install && npm run dev
# Open http://localhost:3000
```

1. Click **"Connect with Strava"** and authorize the application
2. Configure your preferences (age, interests, style)
3. Enable modules (Campus Coach, Enduraw)
4. Upload or edit a Strava activity and watch it get enhanced!

**Deployment Modes**: Phase 1 only gives a fully functional system with Bedrock fallback. Phase 1 + 2 adds advanced personalization with AgentCore Memory.

---

## Configuration

### Strava OAuth Setup

1. Go to https://www.strava.com/settings/api and create an app
2. Set **Authorization Callback Domain** to `localhost` (no http://, no port)
3. Store credentials in Secrets Manager:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id strava-ai-boost-app-config \
     --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"YOUR_CLIENT_SECRET"}' \
     --profile your-aws-profile --region eu-west-1
   ```

### Module Configuration

#### Campus Coach (Optional)

Matches activities with planned training sessions from [campus.coach](https://campus.coach).

1. Go to Configuration > Modules, enable "Campus Coach"
2. Enter your Campus Coach username and password
3. Credentials are encrypted in AWS Secrets Manager

#### Enduraw Report (Optional)

Enhanced analytics with weather and wind impact analysis.

- **External setup required**: Configure at https://enduraw-report-strava.onrender.com first
- Then enable "Enduraw Integration" in modules
- System waits 2 minutes for Enduraw data via SQS delay (graceful fallback if unavailable)

### Personal Profile

Customize AI content generation in Configuration > Personal Profile:

| Setting | Options |
|---------|---------|
| **Sport Approach** | Health & Wellness, Performance & Competition, Social & Fun, Personal Challenge, Stress Relief, Weight Management |
| **Content Length** | Short (~300 chars), Medium (~800), Detailed (~1500), Adaptive |
| **Tone** | Technical & Analytical, Motivational & Energetic, Casual & Friendly, Humorous & Fun, Authentic & Personal |
| **Emoji Usage** | None, Minimal (1-2), Moderate (3-5), Enthusiastic (5+) |
| **Technical Detail** | Basic, Intermediate, Advanced |
| **Language** | French, English, Spanish, German, Italian |

### Enhancement Control

- **Pause/Resume**: Toggle automatic enhancement from the dashboard
- **2-minute window**: When Enduraw is enabled, you can add your own title/description during the wait - they will be preserved and incorporated

### Environment Variables

Configure in `frontend/.env.local` (copy from `.env.example`):
```bash
VITE_API_GATEWAY_URL=https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod
VITE_API_GATEWAY_KEY=your-api-key
VITE_DEFAULT_USER_ID=YOUR_USER_ID
```

---

## Architecture Overview

### Key Architecture Decisions

1. **React Frontend** - No cloud hosting complexity, runs on localhost
2. **Zero AWS SDK in Frontend** - All AWS operations via API Gateway + Lambda
3. **Modular Design** - Extensible module system (Campus Coach, Enduraw, future modules)
4. **Dual-Mode AI** - AgentCore (primary) + Bedrock fallback (always available)
5. **Serverless** - Pay-per-use, auto-scaling, no server management
6. **Security First** - Guardrails, encryption, least privilege IAM

### System Components

```mermaid
graph TB
    subgraph "User Layer"
        Browser[Web Browser<br/>localhost:3000]
    end

    subgraph "AWS Infrastructure - 7 CDK Stacks"
        subgraph "Core Stack"
            DDB[(DynamoDB<br/>3 Tables)]
            Secrets[Secrets Manager<br/>OAuth & Credentials]
        end

        subgraph "Security Stack"
            Guardrails[Bedrock Guardrails<br/>AI Safety]
        end

        subgraph "Webhook Stack"
            WebhookAPI[Webhook API<br/>Strava Events]
            SQS[SQS Queue<br/>+ DLQ]
        end

        subgraph "Content Stack"
            SF[Step Functions<br/>Workflow]
            Lambda13[13 Lambda Functions<br/>Processing Pipeline]
        end

        subgraph "API Stack"
            APIGW[API Gateway<br/>Frontend API]
        end

        subgraph "Monitoring Stack"
            CW[CloudWatch<br/>Logs & Metrics]
        end

        subgraph "Feedback Stack"
            FB[Feedback Analyzer<br/>EventBridge Schedule]
        end
    end

    subgraph "AI Services"
        AgentCore[AgentCore<br/>2 Agents + 2 Memories]
        Bedrock[Bedrock<br/>Claude Sonnet 4.5]
    end

    subgraph "External Services"
        Strava[Strava API]
        Campus[Campus Coach]
    end

    Browser --> APIGW
    APIGW --> Lambda13
    Lambda13 --> DDB
    Lambda13 --> Secrets

    Strava --> WebhookAPI
    WebhookAPI --> SQS
    SQS --> SF
    SF --> Lambda13

    Lambda13 --> Guardrails
    Guardrails --> Bedrock
    Lambda13 --> AgentCore
    Lambda13 --> Strava
    Lambda13 --> Campus

    Lambda13 --> CW
```

### Infrastructure Components

| Component | Details |
|-----------|---------|
| **7 CDK Stacks** | Core, Security, Webhook, Content, API, Monitoring, Feedback |
| **13 Lambda Functions** | 5 processing pipeline + 4 API endpoints + 3 utilities + 1 feedback |
| **3 DynamoDB Tables** | `activities` (GSI, TTL), `user_config`, `coaching_sessions` (GSI) |
| **2 AgentCore Agents** | `content_gen` (LTM memory), `campus_coach` (Browser Tool) |
| **External APIs** | Strava API, Campus Coach (optional) |
| **Shared Utilities** | `lambda_functions/shared/` - Structured logging, metrics, correlation IDs |

### Data Flow: Activity Enhancement

```mermaid
sequenceDiagram
    participant User
    participant Strava
    participant Webhook
    participant SQS
    participant StepFunctions
    participant Lambda
    participant AgentCore
    participant DynamoDB

    User->>Strava: Upload Activity
    Strava->>Webhook: Webhook Notification
    Webhook->>DynamoDB: Check Enhancement Status
    Webhook->>SQS: Queue Activity
    SQS->>StepFunctions: Trigger Workflow
    StepFunctions->>Lambda: Fetch + Enrich + Generate
    Lambda->>AgentCore: Invoke Content Agent (with Memory)
    Lambda->>Strava: Update Title & Description
    Lambda->>DynamoDB: Mark Completed
    User->>Strava: View Enhanced Activity
```

### Technology Stack

**Infrastructure**: AWS CDK (Python), Python 3.12, eu-west-1

**AWS Services**: Lambda (13 functions, Powertools), DynamoDB (3 tables, GSI, TTL), Step Functions, SQS + DLQ, Bedrock (Claude Sonnet 4.5), Secrets Manager, API Gateway

**AI/ML**: Strands Agents, AgentCore Memory (2 LTM memories), AgentCore Browser Tool, Claude Sonnet 4.5

### Performance Targets

- Webhook Processing: <5s to queue
- Content Generation: <30s end-to-end
- Dashboard Loading: <2s
- Cost per Activity: ~$0.02

---

## Troubleshooting

### Quick Diagnostics

```bash
# Check AWS connectivity
aws sts get-caller-identity --profile your-aws-profile

# Check Lambda logs (structured JSON with correlation IDs)
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile

# Filter by error level
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-ConfigurationAPI \
  --filter-pattern '{ $.level = "ERROR" }' \
  --profile your-aws-profile

# Validate deployment
./scripts/validate_deployment.sh dev
```

### Common Issues

**OAuth: "Failed to connect to Strava"**
- Verify callback domain is exactly `localhost` (no http://, no port)
- Check Client ID/Secret match your Strava app
- Try incognito mode to clear cached state

**Activities not being enhanced**
- Check enhancement is not paused (Dashboard > Resume Enhancement)
- Verify webhook: `./scripts/configure_strava_webhook.sh dev --validate-only`
- Check SQS queue and DLQ for stuck messages

**Modules showing disabled after OAuth refresh**
- Fixed in v2.4.0: `user_id` is now persisted at top level during OAuth callback
- If still occurring, disconnect and reconnect Strava OAuth

**Frontend won't load**
- Verify `frontend/.env.local` is configured (copy from `.env.example`)
- Check port 3000 is available: `lsof -i :3000`
- Restart: `cd frontend && npm install && npm run dev`

**Processing takes too long**
- Basic enhancement: 30-60s | With Campus Coach: 2-3min | With Enduraw: +2min wait
- Check CloudWatch for Lambda timeouts or Bedrock throttling

**Enhanced content is repetitive**
- Update personal profile with more specific preferences
- Verify AgentCore Memory service is working
- Check feedback loop is running (EventBridge schedule)

### DLQ Reprocessing

```bash
# Check DLQ message count
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --attribute-names ApproximateNumberOfMessages \
  --profile your-aws-profile

# Reprocess all DLQ messages
./scripts/reprocess_dlq.sh
```

### Webhook Infinite Loop Prevention

Strava sends `update` webhooks when activities are modified. The system prevents infinite loops by:
- Skipping activities with `completed` or `processing` status
- Skipping `update` webhooks for already-processed activities
- 1-hour cooldown for failed activities on update webhooks

---

## Known Issues

### 1. AgentCore Browser Tool - Cold Start (~30% first-call failure)

AgentCore Browser Tool experiences cold start delays. Exponential backoff retry (3 attempts) is implemented. Success rate: ~90% after retries.

### 2. Lambda Layer Cross-Stack Export Constraint

The Lambda Layer cannot be replaced via CDK due to CloudFormation cross-stack export limitations. New dependencies are installed directly into `lambda_functions/` via `pip install -t` and bundled with `Code.from_asset`. The Layer still provides original dependencies.

### 3. CDK Feature Flags Warning (Cosmetic)

58 unconfigured feature flags generate warnings during CDK operations. No functional impact. Run `cdk flags` to review.

---

## Testing

```bash
# Full test suite (73 tests)
export AWS_PROFILE=your-aws-profile
pytest tests/ -v

# Specific categories
pytest tests/test_api_gateway.py -v      # API Gateway endpoints
pytest tests/test_cdk_infrastructure.py -v  # CDK infrastructure
pytest tests/test_end_to_end.py -v       # Integration tests

# Frontend tests
cd frontend && npm test
```

## Security

- **Bedrock Guardrails**: AI safety and prompt injection protection
- **Data Encryption**: AWS managed encryption for all DynamoDB tables
- **HTTPS**: All API endpoints use secure communication
- **Secrets Manager**: OAuth tokens and credentials with automatic rotation
- **IAM**: Least privilege with scoped resource ARNs
- **Frontend**: Local-only access (localhost:3000), ErrorBoundary for graceful recovery
- **User Isolation**: Per-user configuration keyed by Strava athlete ID

## Documentation

- **[AGENTS.md](AGENTS.md)** - Complete development guide for AI assistants
- **[Scripts](scripts/README.md)** - Deployment and maintenance scripts
- **[Tests](tests/README.md)** - Test suite documentation

## Contributing

1. Follow property-based testing for infrastructure changes
2. Ensure all tests pass before committing
3. Use `your-aws-profile` for all AWS operations

## License

This project is licensed under the MIT License.
