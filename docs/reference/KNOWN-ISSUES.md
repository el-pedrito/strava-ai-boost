# ⚠️ Known Issues and Troubleshooting

**Version:** v1.3.7 - Complete End-to-End Testing Suite  
**Last Updated:** 2025-12-23

This document tracks current known issues, their workarounds, and troubleshooting procedures for the Strava AI Boost system.

## Current Active Issues

### 1. AgentCore Browser Tool - Cold Start Problem (INHERITED ISSUE)

**Status**: 🔴 Known issue inherited from strava-ai-coach project  
**Severity**: Medium - Affects Campus Coach module reliability  
**Impact**: ~30% success rate on first invocation, 90% success after retries

#### Symptoms
- First invocation of AgentCore Browser Tool often fails
- Error messages related to browser initialization timeout
- Subsequent invocations (2-3 retries) typically succeed
- More pronounced during periods of low activity (cold starts)

#### Root Cause
- AgentCore Browser Tool runtime experiences cold start delays
- Browser initialization takes longer than expected timeout
- Resource allocation delays in serverless environment

#### Current Workaround
```python
# Exponential backoff retry logic implemented
class CampusCoachInvoker:
    async def invoke_with_retry(self, credentials: Dict[str, str], max_retries: int = 3) -> Dict:
        for attempt in range(max_retries):
            try:
                response = await self.agentcore_client.invoke_agent(
                    agent_name='campus-coach-scraper',
                    input_data={'credentials': credentials}
                )
                return response
            except AgentCoreError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(wait_time)
                    logger.warning(f"Campus Coach invocation failed, retrying in {wait_time}s (attempt {attempt + 1})")
                else:
                    logger.error(f"Campus Coach invocation failed after {max_retries} attempts")
                    raise
```

#### Monitoring Commands
```bash
# Monitor AgentCore Browser Tool logs
aws logs tail /aws/bedrock-agentcore/runtimes/strava-ai-boost-campus-coach-* --follow --profile your-aws-profile --region eu-west-1

# Check agent invocation success rate
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-CampusCoachInvoker \
  --filter-pattern "ERROR" \
  --profile your-aws-profile

# Monitor retry patterns
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-CampusCoachInvoker \
  --filter-pattern "retrying" \
  --profile your-aws-profile
```

#### Planned Mitigation
- Implement agent warming strategy for predictable invocations
- Increase timeout values for initial invocations
- Consider provisioned concurrency for Campus Coach invoker Lambda
- Monitor AgentCore service improvements and updates

### 2. CDK Feature Flags Warning (LOW PRIORITY)

**Status**: 🟡 Informational - Does not affect functionality  
**Severity**: Low - Cosmetic warning during CDK operations  
**Impact**: No functional impact, generates warning messages

#### Symptoms
```bash
You currently have 58 unconfigured feature flags that may require attention to keep your application up-to-date. Run 'cdk flags' to learn more.
```

#### Root Cause
- CDK v2.219.0 includes new feature flags not explicitly configured
- Default behavior is maintained for unconfigured flags
- Warning is informational to encourage explicit configuration

#### Workaround
```bash
# View available feature flags
cdk flags --profile your-aws-profile

# Configure specific flags in cdk.json if needed
{
  "context": {
    "@aws-cdk/aws-lambda:recognizeLayerVersion": true,
    "@aws-cdk/aws-cloudfront:defaultSecurityPolicyTLSv1.2_2021": true
  }
}
```

#### Resolution Plan
- Review feature flags during next CDK version upgrade
- Configure relevant flags based on project requirements
- Low priority - does not affect current functionality

## Potential Future Issues

### 1. Strava API Rate Limits

**Risk Level**: 🟡 Medium - Predictable based on usage patterns  
**Limits**: 100 requests per 15 minutes, 1000 requests per day  
**Mitigation**: Implemented rate limiting with DynamoDB tracking

#### Prevention Strategy
```python
class StravaRateLimiter:
    def __init__(self):
        self.short_term_limit = 100  # per 15 minutes
        self.daily_limit = 1000      # per day
        
    async def check_and_wait(self) -> bool:
        # Check current usage in DynamoDB
        # Queue requests if limits approached
        # Exponential backoff for exceeded limits
```

#### Monitoring
```bash
# Check rate limit utilization
aws dynamodb scan --table-name strava-ai-boost-rate-limits --profile your-aws-profile

# Monitor API call patterns
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-ActivityProcessor \
  --filter-pattern "rate_limit" \
  --profile your-aws-profile
```

### 2. AgentCore Memory Service Connectivity

**Risk Level**: 🟡 Medium - Dependent on external service  
**Potential Issues**: Network connectivity, service availability, data persistence  
**Mitigation**: Fallback to basic content generation without memory

#### Fallback Strategy
```python
class ContentGenerationAgent:
    async def generate_content(self, activity_data: ActivityData, user_id: str) -> str:
        try:
            # Attempt memory-enhanced generation
            personal_style = await self.memory.get_user_style(user_id)
            return await self.generate_with_memory(activity_data, personal_style)
        except MemoryServiceError:
            # Fallback to basic generation
            logger.warning("Memory service unavailable, using basic generation")
            return await self.generate_basic_content(activity_data)
```

### 3. Local Web Interface Connection Issues

**Risk Level**: 🟡 Medium - Local environment dependent  
**Potential Issues**: Port conflicts, firewall restrictions, certificate issues  
**Mitigation**: Configurable ports, clear error messages, troubleshooting guide

#### Common Solutions
```python
# Configurable port binding
app.run(
    host='127.0.0.1',
    port=int(os.getenv('FLASK_PORT', 8000)),
    ssl_context='adhoc' if os.getenv('FLASK_SSL', 'true') == 'true' else None
)
```

## Troubleshooting Procedures

### Infrastructure Issues

#### 1. CDK Deployment Failures

**Symptoms**: CDK deploy command fails with CloudFormation errors

**Diagnostic Steps**:
```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks --stack-name StravaAIBoost-Core --profile your-aws-profile

# View stack events for error details
aws cloudformation describe-stack-events --stack-name StravaAIBoost-Core --profile your-aws-profile

# Check CDK diff for changes
cdk diff --profile your-aws-profile
```

**Common Solutions**:
- Verify AWS credentials and permissions
- Check for resource naming conflicts
- Ensure CDK bootstrap is completed
- Review IAM permissions for deployment role

#### 2. Lambda Function Errors

**Symptoms**: Lambda functions failing with timeout or permission errors

**Diagnostic Steps**:
```bash
# View Lambda function logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile

# Check function configuration
aws lambda get-function --function-name StravaAIBoost-WebhookHandler --profile your-aws-profile

# Test function invocation
aws lambda invoke --function-name StravaAIBoost-WebhookHandler --payload '{}' response.json --profile your-aws-profile
```

**Common Solutions**:
- Increase timeout values if processing takes longer
- Verify IAM role permissions
- Check environment variable configuration
- Review dependency packaging

#### 3. DynamoDB Access Issues

**Symptoms**: DynamoDB operations failing with access denied or throttling

**Diagnostic Steps**:
```bash
# Check table status
aws dynamodb describe-table --table-name strava-ai-boost-activities --profile your-aws-profile

# Monitor table metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions Name=TableName,Value=strava-ai-boost-activities \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --profile your-aws-profile
```

**Common Solutions**:
- Verify IAM permissions for DynamoDB access
- Check for throttling and adjust capacity if needed
- Review GSI configuration and usage patterns
- Ensure proper error handling and retries

### Application Issues

#### 1. Webhook Processing Failures

**Symptoms**: Strava webhooks not being processed correctly

**Diagnostic Steps**:
```bash
# Check SQS queue for messages
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile your-aws-profile --query 'QueueUrl' --output text) \
  --attribute-names All \
  --profile your-aws-profile

# Check dead letter queue
aws sqs receive-message \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --profile your-aws-profile

# Monitor webhook handler logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
```

**Common Solutions**:
- Verify webhook subscription with Strava
- Check API Gateway configuration and logs
- Review webhook payload validation logic
- Ensure proper error handling and retry logic

#### 2. AgentCore Integration Issues

**Symptoms**: AgentCore agents not responding or failing to deploy

**Diagnostic Steps**:
```bash
# Check AgentCore agent status
agentcore agent list --profile your-aws-profile --region eu-west-1

# View agent logs
aws logs tail /aws/bedrock-agentcore/runtimes/strava-ai-boost-* --follow --profile your-aws-profile --region eu-west-1

# Test agent invocation
agentcore invoke strava-ai-boost-content-generator --input '{"test": true}' --profile your-aws-profile
```

**Common Solutions**:
- Verify AgentCore CLI installation and configuration
- Check AWS permissions for AgentCore operations
- Review agent deployment scripts and configurations
- Implement retry logic for agent invocations

### Performance Issues

#### 1. Slow Response Times

**Symptoms**: API responses or processing taking longer than expected

**Diagnostic Steps**:
```bash
# Monitor Lambda function duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=StravaAIBoost-WebhookHandler \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 3600 \
  --statistics Average,Maximum \
  --profile your-aws-profile

# Check DynamoDB response times
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name SuccessfulRequestLatency \
  --dimensions Name=TableName,Value=strava-ai-boost-activities Name=Operation,Value=GetItem \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 3600 \
  --statistics Average \
  --profile your-aws-profile
```

**Common Solutions**:
- Optimize Lambda function memory allocation
- Review DynamoDB query patterns and indexes
- Implement caching where appropriate
- Consider connection pooling and reuse

## Monitoring and Alerting

### Key Metrics to Monitor

#### System Health Metrics
```bash
# Lambda function errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=StravaAIBoost-WebhookHandler \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 300 \
  --statistics Sum \
  --profile your-aws-profile

# DynamoDB throttling
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ThrottledRequests \
  --dimensions Name=TableName,Value=strava-ai-boost-activities \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 300 \
  --statistics Sum \
  --profile your-aws-profile

# SQS queue depth
aws cloudwatch get-metric-statistics \
  --namespace AWS/SQS \
  --metric-name ApproximateNumberOfVisibleMessages \
  --dimensions Name=QueueName,Value=strava-ai-boost-activity-processing \
  --start-time 2025-12-21T00:00:00Z \
  --end-time 2025-12-21T23:59:59Z \
  --period 300 \
  --statistics Average \
  --profile your-aws-profile
```

#### Business Logic Metrics
```bash
# Activity processing success rate
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-ActivityProcessor \
  --filter-pattern "SUCCESS" \
  --start-time 1640995200000 \
  --profile your-aws-profile | jq '.events | length'

# Campus Coach invocation success rate
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-CampusCoachInvoker \
  --filter-pattern "SUCCESS" \
  --start-time 1640995200000 \
  --profile your-aws-profile | jq '.events | length'
```

### Recommended Alarms

#### High Error Rate Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "StravaAIBoost-HighErrorRate" \
  --alarm-description "High error rate in Lambda functions" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --statistic "Sum" \
  --period 300 \
  --threshold 5 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 2 \
  --profile your-aws-profile
```

#### Campus Coach Failure Alarm
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "StravaAIBoost-CampusCoachFailures" \
  --alarm-description "High failure rate in Campus Coach invocations" \
  --metric-name "Errors" \
  --namespace "AWS/Lambda" \
  --dimensions Name=FunctionName,Value=StravaAIBoost-CampusCoachInvoker \
  --statistic "Sum" \
  --period 900 \
  --threshold 3 \
  --comparison-operator "GreaterThanThreshold" \
  --evaluation-periods 1 \
  --profile your-aws-profile
```

## Issue Reporting Template

When reporting new issues, please include:

### Issue Information
- **Title**: Brief description of the issue
- **Severity**: Critical/High/Medium/Low
- **Component**: Affected system component
- **Environment**: Development/Testing/Production

### Reproduction Steps
1. Step-by-step instructions to reproduce
2. Expected behavior
3. Actual behavior
4. Frequency of occurrence

### Technical Details
- Error messages and stack traces
- Relevant log entries with timestamps
- AWS resource configurations
- Environment variables and settings

### Diagnostic Information
```bash
# Include output of relevant diagnostic commands
aws sts get-caller-identity --profile your-aws-profile
cdk --version
python --version
# Relevant CloudWatch logs
# Relevant metrics
```

### Example Issue Report

**Title**: Campus Coach Agent Invocation Timeout  
**Severity**: Medium  
**Component**: AgentCore Browser Tool Integration  
**Environment**: Development  

**Reproduction Steps**:
1. Trigger Campus Coach session extraction
2. Observe first invocation timeout after 30 seconds
3. Retry succeeds on second attempt

**Expected Behavior**: First invocation should succeed within timeout  
**Actual Behavior**: First invocation times out, requires retry  
**Frequency**: ~30% of first invocations  

**Error Message**:
```
AgentCoreError: Agent invocation timeout after 30 seconds
```

**Logs**:
```
2025-12-21T10:00:00.000Z [ERROR] Campus Coach agent invocation failed: timeout
2025-12-21T10:00:02.000Z [INFO] Retrying Campus Coach invocation (attempt 2)
2025-12-21T10:00:15.000Z [INFO] Campus Coach invocation successful
```

---

**Version:** v1.3.0 - AgentCore Integration Complete  
**Last Updated:** 2025-12-23  
**Next Review:** 2025-12-30 (Weekly review cycle)