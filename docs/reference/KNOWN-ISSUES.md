# ⚠️ Known Issues and Troubleshooting

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

### 2. Lambda Layer Cross-Stack Export Constraint (WORKAROUND IN PLACE)

**Status**: 🟡 Workaround active - Does not affect functionality
**Severity**: Low - Operational constraint for future layer updates
**Impact**: Lambda Layer cannot be replaced via CDK due to CloudFormation cross-stack export

#### Symptoms
- Changing `LAYER_ASSET_HASH` in `core_infrastructure_stack.py` causes deployment failure
- Error: `Cannot update export StravaAIBoost-Core:ExportsOutputRef...Layer... as it is in use by StravaAIBoost-API, StravaAIBoost-Content, StravaAIBoost-Feedback`

#### Root Cause
- Lambda Layer is exported from Core stack and imported by API, Content, and Feedback stacks
- CloudFormation prevents replacing an exported resource that is imported by other stacks
- This is a known CloudFormation limitation with cross-stack references

#### Current Workaround
- New dependencies (e.g., `aws-lambda-powertools`) are installed directly into `lambda_functions/` via `pip install -t`
- CDK bundles them with `Code.from_asset("lambda_functions")` alongside handler code
- Vendored directories are listed in `.gitignore` (e.g., `lambda_functions/aws_lambda_powertools/`)
- The Layer (`lambda_layer/`) still provides `requests` and other original dependencies

#### Resolution Plan
- To update the layer: deploy all dependent stacks first with inline code, then update the layer, then redeploy
- Or: restructure to avoid cross-stack layer references (use `Code.from_asset` with bundled deps everywhere)

### 3. CDK Feature Flags Warning (LOW PRIORITY)

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
**Mitigation**: Rate limiting managed via API Gateway Usage Plans and Lambda-level checks

#### Monitoring
```bash
# Monitor API call patterns in Lambda logs (structured JSON)
aws logs filter-log-events \
  --log-group-name /aws/lambda/StravaAIBoost-ActivityProcessor \
  --filter-pattern '{ $.message = "*rate*" }' \
  --profile your-aws-profile

# Check API Gateway usage plan throttling
aws apigateway get-usage --usage-plan-id YOUR_PLAN_ID \
  --key-id YOUR_KEY_ID \
  --start-date 2026-03-01 --end-date 2026-03-05 \
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

### 3. Frontend Development Server Connection Issues

**Risk Level**: 🟡 Low - Local environment dependent
**Potential Issues**: Port conflicts, missing dependencies, environment configuration
**Mitigation**: Standard Vite dev server with clear error messages

#### Common Solutions
```bash
# Verify Vite dev server is running
lsof -i :3000

# Start frontend
cd frontend && npm install && npm run dev

# Verify environment configuration
cat frontend/.env.local
# Should contain: VITE_API_GATEWAY_URL, VITE_API_GATEWAY_KEY, VITE_DEFAULT_USER_ID
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


## DLQ Troubleshooting

### Understanding DLQ Messages

The Dead Letter Queue (DLQ) captures two types of failures:

1. **Lambda Processing Failures**: Messages that failed after 3 retry attempts
2. **Step Functions Failures**: Executions that failed, timed out, or were aborted

### Checking DLQ Status

```bash
# Get DLQ message count
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --attribute-names ApproximateNumberOfMessages \
  --profile your-aws-profile

# Read messages without deleting (for inspection)
aws sqs receive-message \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --max-number-of-messages 10 \
  --attribute-names All \
  --message-attribute-names All \
  --profile your-aws-profile | jq '.'
```

### Common DLQ Scenarios

#### Scenario 1: Lambda Parsing Errors

**Symptoms**: Messages with malformed JSON or missing required fields

**DLQ Message Example**:
```json
{
  "activity_id": null,
  "error": "KeyError: 'activity_id'",
  "retry_count": 3,
  "original_message": "{\"invalid\": \"data\"}"
}
```

**Resolution**:
1. Check webhook handler validation logic
2. Verify Strava webhook format hasn't changed
3. Update message schema validation if needed

#### Scenario 2: Step Functions Timeout

**Symptoms**: Executions that exceed 30-minute timeout

**DLQ Message Example**:
```json
{
  "activity_id": "12345678",
  "failure_type": "step_functions_failure",
  "status": "TIMED_OUT",
  "cause": "Execution timed out after 30 minutes",
  "execution_details": {
    "startDate": "2025-12-30T10:00:00Z",
    "stopDate": "2025-12-30T10:30:00Z"
  }
}
```

**Resolution**:
1. Check which Lambda function timed out
2. Review CloudWatch Logs for that Lambda
3. Increase Lambda timeout if legitimate long-running task
4. Optimize code if inefficient processing

#### Scenario 3: Bedrock API Errors

**Symptoms**: Content generation failures due to Bedrock throttling or errors

**DLQ Message Example**:
```json
{
  "activity_id": "12345678",
  "failure_type": "step_functions_failure",
  "status": "FAILED",
  "cause": "ThrottlingException: Rate exceeded",
  "error": "States.TaskFailed"
}
```

**Resolution**:
1. Check Bedrock service quotas
2. Implement exponential backoff in Lambda
3. Request quota increase if needed
4. Consider using reserved capacity

#### Scenario 4: Strava API Rate Limits

**Symptoms**: Activities failing due to Strava API rate limits

**DLQ Message Example**:
```json
{
  "activity_id": "12345678",
  "failure_type": "step_functions_failure",
  "cause": "Strava API rate limit exceeded: 100 requests per 15 minutes",
  "error": "States.TaskFailed"
}
```

**Resolution**:
1. Check rate limits table in DynamoDB
2. Verify rate limit tracking logic
3. Implement better rate limit backoff
4. Consider spreading webhook processing over time

### Reprocessing DLQ Messages

#### Manual Reprocessing

```bash
# 1. Read message from DLQ
MESSAGE=$(aws sqs receive-message \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --max-number-of-messages 1 \
  --profile your-aws-profile)

# 2. Extract message body
BODY=$(echo $MESSAGE | jq -r '.Messages[0].Body')

# 3. Fix the issue (e.g., increase quotas, fix code, etc.)

# 4. Resend to processing queue
aws sqs send-message \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile your-aws-profile --query 'QueueUrl' --output text) \
  --message-body "$BODY" \
  --profile your-aws-profile

# 5. Delete from DLQ
RECEIPT_HANDLE=$(echo $MESSAGE | jq -r '.Messages[0].ReceiptHandle')
aws sqs delete-message \
  --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
  --receipt-handle "$RECEIPT_HANDLE" \
  --profile your-aws-profile
```

#### Bulk Reprocessing Script

```bash
#!/bin/bash
# scripts/reprocess_dlq.sh

PROFILE="your-aws-profile"
DLQ_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile $PROFILE --query 'QueueUrl' --output text)
PROCESSING_URL=$(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile $PROFILE --query 'QueueUrl' --output text)

echo "Reprocessing DLQ messages..."

while true; do
    # Receive message
    MESSAGE=$(aws sqs receive-message \
        --queue-url $DLQ_URL \
        --max-number-of-messages 1 \
        --profile $PROFILE)
    
    # Check if queue is empty
    if [ "$(echo $MESSAGE | jq '.Messages | length')" -eq "0" ]; then
        echo "DLQ is empty"
        break
    fi
    
    # Extract body and receipt handle
    BODY=$(echo $MESSAGE | jq -r '.Messages[0].Body')
    RECEIPT_HANDLE=$(echo $MESSAGE | jq -r '.Messages[0].ReceiptHandle')
    
    # Resend to processing queue
    aws sqs send-message \
        --queue-url $PROCESSING_URL \
        --message-body "$BODY" \
        --profile $PROFILE
    
    # Delete from DLQ
    aws sqs delete-message \
        --queue-url $DLQ_URL \
        --receipt-handle "$RECEIPT_HANDLE" \
        --profile $PROFILE
    
    echo "Reprocessed 1 message"
    sleep 1
done

echo "Reprocessing complete"
```

### DLQ Monitoring Best Practices

1. **Set up CloudWatch Alarms**: Alert on any message in DLQ
2. **Regular DLQ Reviews**: Check DLQ daily for patterns
3. **Log Analysis**: Correlate DLQ messages with CloudWatch Logs
4. **Metrics Tracking**: Monitor DLQ message age and count
5. **Automated Reprocessing**: Consider Lambda-based reprocessing for transient errors

### Preventing DLQ Messages

1. **Input Validation**: Validate webhook data before processing
2. **Retry Logic**: Implement exponential backoff for transient errors
3. **Rate Limiting**: Respect API rate limits proactively
4. **Timeout Tuning**: Set appropriate timeouts for each Lambda
5. **Error Handling**: Catch and handle specific exceptions gracefully
6. **Idempotency**: Design functions to be safely retried
7. **Monitoring**: Use CloudWatch Logs and X-Ray for early detection
