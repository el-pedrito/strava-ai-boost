# Scripts - Strava AI Boost

## Phase 1: Infrastructure (Required)

```bash
export AWS_PROFILE=your-aws-profile

./scripts/deploy.sh dev                                     # Deploy all CDK stacks (~10-15 min)
./scripts/validate_deployment.sh dev                         # Validate deployment
./scripts/setup_local_env.sh                                 # Get API Gateway URL + key for frontend
./scripts/configure_strava_webhook.sh dev --auto-configure   # Setup Strava webhook
```

## Phase 2: AgentCore (Optional)

```bash
./scripts/create_agentcore_memories.sh                       # Create LTM memories (~3 min)
./scripts/deploy_agentcore_agents.sh                         # Deploy content_gen + coach + coach_chat agents
./scripts/configure_agentcore_integration.sh                 # IAM permissions + Lambda env vars
python scripts/configure_memory_strategy.py                  # UserPreferenceStrategy setup
./scripts/deploy_agentcore_agents.sh                         # Redeploy with guardrails
cdk deploy --all --profile your-aws-profile --require-approval never  # Final CDK update
```

## Maintenance

```bash
./scripts/reprocess_dlq.sh dev --dry-run                     # View DLQ messages
./scripts/reprocess_dlq.sh dev --max-messages 10             # Reprocess failed messages
./scripts/validate_deployment.sh dev                          # Health check
```

## Webhook Management

```bash
./scripts/configure_strava_webhook.sh dev --validate-only    # Check webhook status
./scripts/configure_strava_webhook.sh dev --auto-configure   # Reconfigure webhook
./scripts/configure_strava_webhook.sh dev --cleanup           # Remove via flag
./scripts/cleanup_strava_webhook.sh dev                       # Remove via dedicated script
```

## Uninstall

```bash
./scripts/uninstall.sh dev --backup                          # Full removal with backup (~10-15 min)
./scripts/uninstall.sh dev --force --keep-data               # Remove infra, keep DynamoDB + Secrets
./scripts/verify_uninstall.sh dev                             # Verify clean removal
```

Uninstall order: Webhook > AgentCore agents > AgentCore memories > CDK stacks (Monitoring > API > Webhook > Content > Core) > orphan resources > data.

---

## Script Reference

| Script | Description | Options |
|--------|-------------|---------|
| `deploy.sh` | CDK infrastructure (7 stacks) | `[dev\|prod]` |
| `setup_local_env.sh` | Generate frontend `.env.local` from CloudFormation | |
| `configure_strava_webhook.sh` | Strava webhook subscription | `--auto-configure`, `--validate-only`, `--cleanup` |
| `validate_deployment.sh` | Post-deploy validation | `[dev\|prod]` |
| `create_agentcore_memories.sh` | AgentCore LTM memories (semantic search, 365d) | |
| `deploy_agentcore_agents.sh` | Deploy agents (content_gen, strava_ai_boost_coach, coach_chat) — injects `BEDROCK_MODEL_ID` from the central registry | |
| `run_prompt_regression.py` | V1 deterministic prompt regression against the deployed content_gen runtime (~$0.20/run) | `--fixtures`, `--update-baseline`, `--agent-arn` |
| `run_managed_evals.py` | V2 managed AgentCore Evaluations (built-ins + custom LLM-as-a-Judge, ~$1.2/run) | `--scenarios`, `--update-baseline` |
| `build_eval_dataset.py` | Convert regression fixtures → AgentCore Evaluations dataset | `--output` |
| `create_managed_evaluators.py` | Create/update custom judge evaluators (idempotent, registry-substituted model IDs) | `--region` |
| `tag_agentcore_resources.sh` | Tag runtimes + memories + IAM execution roles for cost allocation | |
| `configure_agentcore_integration.sh` | IAM policies + Lambda env vars for AgentCore | |
| `configure_memory_strategy.py` | UserPreferenceStrategy on content_gen memory | |
| `reprocess_dlq.sh` | Reprocess DLQ messages | `--dry-run`, `--max-messages N`, `--delete-after` |
| `cleanup_strava_webhook.sh` | Remove Strava webhooks | `[dev\|prod]` |
| `uninstall.sh` | Complete system removal | `--force`, `--backup`, `--keep-data` |
| `verify_uninstall.sh` | Verify all AWS resources deleted | `[dev\|prod]` |

### Key environment variables set by `configure_agentcore_integration.sh`

```bash
CONTENT_GENERATION_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:xxx:runtime/content_gen-xxx
COACH_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:xxx:runtime/strava_ai_boost_coach-xxx
AGENTCORE_AGENTS_AVAILABLE=true
AGENTCORE_MEMORY_ENABLED=true
```

---

## Workflows

### Update Infrastructure

```bash
./scripts/deploy.sh dev
./scripts/validate_deployment.sh dev
./scripts/configure_agentcore_integration.sh   # If AgentCore deployed
```

### Troubleshooting

```bash
# AWS connectivity
aws sts get-caller-identity --profile your-aws-profile

# Lambda logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile

# AgentCore logs
aws logs tail /aws/bedrock-agentcore/runtimes/content_gen-* --follow --profile your-aws-profile

# CloudFormation events (on deploy failure)
aws cloudformation describe-stack-events --stack-name StravaAIBoost-Core --profile your-aws-profile --max-items 20

# AgentCore status
agentcore agent list --region eu-west-1
agentcore memory list --region eu-west-1

# DLQ diagnosis
./scripts/reprocess_dlq.sh dev --dry-run
```
