# AWS Profile Configuration

## Profile à Utiliser

Pour toutes les interactions avec l'environnement AWS, utiliser le profil:

```bash
--profile your-aws-profile
```

## Commandes AWS CLI

Toujours ajouter le flag `--profile` aux commandes AWS:

```bash
# Strava AI Boost specific commands

# DynamoDB tables
aws dynamodb scan --table-name strava-ai-boost-activities --profile your-aws-profile
aws dynamodb scan --table-name strava-ai-boost-user-configuration --profile your-aws-profile
aws dynamodb scan --table-name strava-ai-boost-rate-limits --profile your-aws-profile

# Secrets Manager
aws secretsmanager get-secret-value --secret-id strava-ai-boost-oauth-tokens --profile your-aws-profile
aws secretsmanager get-secret-value --secret-id strava-ai-boost-campus-coach-credentials --profile your-aws-profile

# CloudWatch Logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile

# Step Functions
aws stepfunctions list-executions --state-machine-arn <strava-ai-boost-workflow-arn> --profile your-aws-profile

# SQS Queues
aws sqs get-queue-attributes --queue-url <strava-ai-boost-queue-url> --profile your-aws-profile
```

## CDK Deployment

Le profil est configuré dans le contexte CDK, mais peut être spécifié explicitement:

```bash
# Déploiement avec profil
cdk deploy --profile your-aws-profile

# Bootstrap
cdk bootstrap --profile your-aws-profile

# Destroy
cdk destroy --profile your-aws-profile
```

## Variables d'Environnement

Alternative: définir le profil par défaut pour la session:

```bash
export AWS_PROFILE=your-aws-profile

# Puis utiliser les commandes normalement
aws dynamodb scan --table-name strava-activities
cdk deploy
```

## AgentCore Operations

Pour les opérations AgentCore Strava AI Boost, le profil AWS est utilisé automatiquement:

```bash
# Configuration AgentCore pour Strava AI Boost
agentcore configure --region eu-west-1 --profile your-aws-profile

# Déploiement des agents Strava AI Boost
agentcore agent deploy --name strava-ai-boost-content-generator --profile your-aws-profile
agentcore agent deploy --name strava-ai-boost-campus-coach-scraper --profile your-aws-profile

# Gestion de la mémoire AgentCore
agentcore memory create --name strava-ai-boost-memory --profile your-aws-profile
agentcore memory list --profile your-aws-profile

# Invocation des agents
agentcore invoke strava-ai-boost-content-generator --input '{"activity_data": {...}, "user_id": "user123"}'
```

## Vérification du Profile

Vérifier le profil actif:

```bash
aws sts get-caller-identity --profile your-aws-profile
```
