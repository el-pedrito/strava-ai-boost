# Troubleshooting Guide

Common issues and solutions for Strava AI Boost.

## Quick Diagnostics

### System Health Check

```bash
# Check AWS connectivity
aws sts get-caller-identity --profile your-aws-profile

# Check frontend is running
curl http://localhost:3000

# Check recent Lambda logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile
```

## OAuth and Connection Issues

### "Failed to connect to Strava"

**Symptoms**: OAuth flow fails, can't authorize application

**Common Causes**:
1. Incorrect Client ID or Secret
2. Wrong callback domain in Strava app settings
3. Strava app in "Demo" mode

**Solutions**:
1. **Verify Strava App Settings**:
   - Go to https://www.strava.com/settings/api
   - Check Authorization Callback Domain is exactly: `localhost`
   - Ensure app is not in Demo mode

2. **Check Credentials**:
   - Copy Client ID and Secret exactly (no extra spaces)
   - Verify they match your Strava application

3. **Clear Browser Cache**:
   - Clear cookies for localhost:3000
   - Try incognito/private browsing mode

### "Invalid redirect URI"

**Symptoms**: OAuth callback fails with redirect URI error

**Solution**:
- In Strava app settings, set Authorization Callback Domain to: `localhost`
- Do NOT include `http://` or port numbers
- Just the domain: `localhost`

### "OAuth tokens expired"

**Symptoms**: System shows disconnected after working previously

**Solution**:
- Tokens refresh automatically
- If manual refresh needed: Go to Configuration → Disconnect → Reconnect

## Processing Issues

### "Activities not being enhanced"

**Check Enhancement Status**:
1. Dashboard shows "Enhancement: Active" (not paused)
2. Strava connection is green
3. No errors in recent activities list

**Check Webhook Subscription**:
```bash
# List current subscriptions
curl -X GET 'https://www.strava.com/api/v3/push_subscriptions' \
  -H 'Authorization: Bearer YOUR_CLIENT_SECRET'
```

**Solutions**:
1. **Resume Enhancement**: Click "Resume Enhancement" if paused
2. **Reconnect Strava**: Disconnect and reconnect OAuth
3. **Recreate Webhook**: Run `scripts/configure_strava_webhook.sh`

### "Processing takes too long"

**Normal Processing Times**:
- Basic enhancement: 30-60 seconds
- With Campus Coach: 2-3 minutes
- With Enduraw: 2 minutes wait + processing

**If Slower**:
1. **Check Queue Depth**: High activity volume causes delays
2. **Monitor AWS Services**: Check AWS status dashboard
3. **Review Module Settings**: Disable unused modules

### "Enhanced content is repetitive"

**Symptoms**: Same phrases used across multiple activities

**Solutions**:
1. **Update Personal Profile**: More specific interests and preferences
2. **Check AgentCore Memory**: Ensure memory service is working
3. **Vary Activity Data**: Include more detailed activity information

## Module Issues

### Campus Coach Module

**"Invalid credentials"**
- Test login at https://campus.coach manually
- Check for special characters in password
- Ensure subscription is active

**"No sessions found"**
- Verify Campus Coach has recent training plans
- Check session extraction logs
- Manually trigger extraction in dashboard

**"Session matching failed"**
- Upload activities with more detailed data (heart rate, GPS)
- Check activity timing matches planned sessions
- Review matching confidence thresholds

### Enduraw Report Module

**⚠️ Important**: Enduraw Report is an external service that must be configured separately at https://enduraw-report-strava.onrender.com

**"Enduraw data not available"**
- **First**: Ensure Enduraw Report is configured at https://enduraw-report-strava.onrender.com
- **Then**: Enable the module in our system (Configuration → Modules)
- System waits 2 minutes for Enduraw data using SQS delay mechanism
- **Graceful fallback**: Content generation proceeds without Enduraw data if not available
- Check Enduraw Report configuration and processing status

**"Activity stuck in waiting_enduraw status"**
- Check SQS queue for delayed messages:
  ```bash
  aws sqs get-queue-attributes \
    --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile your-aws-profile --query 'QueueUrl' --output text) \
    --attribute-names ApproximateNumberOfMessagesDelayed \
    --profile your-aws-profile
  ```
- Check Lambda logs for processing errors:
  ```bash
  aws logs tail /aws/lambda/StravaAIBoost-ActivityProcessor \
    --follow --filter-pattern "Enduraw" \
    --profile your-aws-profile
  ```
- Check DLQ for failed messages:
  ```bash
  aws sqs receive-message \
    --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing-dlq --profile your-aws-profile --query 'QueueUrl' --output text) \
    --max-number-of-messages 10 \
    --profile your-aws-profile
  ```

**"Processing timeout with Enduraw"**
- This is normal behavior - system waits 2 minutes then proceeds
- Check Enduraw Report service status at https://enduraw-report-strava.onrender.com
- Verify Enduraw Report is actually processing your activities
- **No action needed**: System generates content with or without Enduraw data

**"Module enabled but no Enduraw data in content"**
- Enduraw Report may not be configured on your Strava account
- Visit https://enduraw-report-strava.onrender.com to set up the integration
- Our system only waits for data; it doesn't configure Enduraw Report
- Content will still be generated using other available data sources

**"Enduraw wait loop - activity requeued multiple times"**
- Check if `enduraw_waited` flag is being set correctly
- Review Lambda logs for flag handling:
  ```bash
  aws logs filter-log-events \
    --log-group-name /aws/lambda/StravaAIBoost-ActivityProcessor \
    --filter-pattern "enduraw_waited" \
    --profile your-aws-profile
  ```
- If stuck in loop, manually purge queue (use with caution):
  ```bash
  aws sqs purge-queue \
    --queue-url $(aws sqs get-queue-url --queue-name strava-ai-boost-activity-processing --profile your-aws-profile --query 'QueueUrl' --output text) \
    --profile your-aws-profile
  ```

## Frontend Issues

### "Dashboard won't load"

**Check Dev Server**:
```bash
# Verify Vite dev server is running
lsof -i :3000
```

**Solutions**:
1. **Restart Frontend**: `cd frontend && npm run dev`
2. **Check Port**: Ensure port 3000 is available
3. **Check Dependencies**: `cd frontend && npm install`
4. **Verify Environment**: Ensure `frontend/.env.local` is configured (copy from `.env.example`)

### "API Gateway connection failed"

**Symptoms**: Dashboard shows "fallback" data, API calls fail

**Check API Gateway**:
```bash
# Test API endpoint
curl https://your-api-gateway-url/status

# Check environment variables
echo $API_GATEWAY_URL
```

**Solutions**:
1. **Update Environment**: Set correct API_GATEWAY_URL
2. **Check Deployment**: Ensure CDK deployment completed
3. **Verify Permissions**: Check Lambda execution roles

## AWS Service Issues

### Lambda Function Errors

**Check Logs**:
```bash
# Webhook handler logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler --follow --profile your-aws-profile

# Content generator logs
aws logs tail /aws/lambda/StravaAIBoost-ContentGenerator --follow --profile your-aws-profile
```

**Common Errors**:
- **Timeout**: Increase Lambda timeout in CDK
- **Memory**: Increase Lambda memory allocation
- **Permissions**: Check IAM roles and policies

### DynamoDB Issues

**Check Tables**:
```bash
# List tables
aws dynamodb list-tables --profile your-aws-profile | grep strava-ai-boost

# Check table status
aws dynamodb describe-table --table-name strava-ai-boost-activities --profile your-aws-profile
```

**Common Issues**:
- **Throttling**: Increase read/write capacity
- **Item Size**: Check for oversized items
- **Permissions**: Verify Lambda has DynamoDB access

### Step Functions Issues

#### Infinite Executions (Webhook Update Loops)

**Symptoms**:
- Hundreds of Step Functions executions for the same activity
- High AWS costs from excessive Lambda invocations
- Same activity being processed repeatedly
- SQS messages stuck "in flight" for extended periods

**Root Cause**:
Strava sends `update` webhooks when activities are modified. Our system updating an activity triggers a new webhook, creating an infinite loop:
```
Activity Update → Webhook 'update' → Processing → Strava Update → Webhook 'update' → ∞
```

**Solution** (Fixed in v1.6.4):
The system now checks activity processing status before launching Step Functions:
- ✅ Skip if activity status is `completed` or `processing`
- ✅ Skip `update` webhooks for already-processed activities  
- ✅ 1-hour cooldown for failed activities on update webhooks
- ✅ Allow `create` webhooks and legitimate retries

**Verification**:
```bash
# Check if protection is working
aws logs filter-log-events \
  --log-group-name "/aws/lambda/StravaAIBoost-ActivityProcessor" \
  --filter-pattern "Skipping activity" \
  --profile your-aws-profile

# Monitor Step Functions executions
aws stepfunctions list-executions \
  --state-machine-arn YOUR_STATE_MACHINE_ARN \
  --status-filter RUNNING \
  --profile your-aws-profile
```

**Check Executions**:
```bash
# List recent executions
aws stepfunctions list-executions --state-machine-arn YOUR_STATE_MACHINE_ARN --profile your-aws-profile

# Get execution details
aws stepfunctions describe-execution --execution-arn YOUR_EXECUTION_ARN --profile your-aws-profile
```

**Common Issues**:
- **Failed States**: Check individual step errors
- **Timeouts**: Increase state timeouts
- **Input Validation**: Check input data format

## Performance Issues

### High AWS Costs

**Monitor Usage**:
```bash
# Check Lambda invocations
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/StravaAIBoost --profile your-aws-profile

# Check DynamoDB usage
aws dynamodb describe-table --table-name strava-ai-boost-activities --profile your-aws-profile
```

**Cost Optimization**:
1. **Reduce Lambda Memory**: If not CPU-bound
2. **Optimize DynamoDB**: Use on-demand billing
3. **Limit Bedrock Calls**: Cache results when possible
4. **Monitor Step Functions**: Reduce unnecessary executions

### Slow Processing

**Identify Bottlenecks**:
1. **Lambda Cold Starts**: Use provisioned concurrency
2. **DynamoDB Throttling**: Increase capacity or use on-demand
3. **Bedrock Rate Limits**: Implement exponential backoff
4. **Network Latency**: Check region configuration

## Error Codes Reference

### HTTP Status Codes

- **400**: Bad request - check input data
- **401**: Unauthorized - OAuth token issue
- **403**: Forbidden - permissions problem
- **429**: Rate limited - wait and retry
- **500**: Internal error - check logs

### Custom Error Codes

- **OAUTH_EXPIRED**: Refresh OAuth tokens
- **MODULE_DISABLED**: Enable required module
- **PROCESSING_PAUSED**: Resume enhancement
- **INVALID_WEBHOOK**: Recreate webhook subscription

## Getting Help

### Log Collection

```bash
# Collect system logs
mkdir troubleshooting-logs
aws logs filter-log-events --log-group-name /aws/lambda/StravaAIBoost-WebhookHandler --start-time $(date -d '1 hour ago' +%s)000 --profile your-aws-profile > troubleshooting-logs/webhook.log
aws logs filter-log-events --log-group-name /aws/lambda/StravaAIBoost-ContentGenerator --start-time $(date -d '1 hour ago' +%s)000 --profile your-aws-profile > troubleshooting-logs/content.log
```

### System Information

```bash
# System status (via API Gateway directly)
curl -H "x-api-key: your-api-key" https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod/dashboard/stats > troubleshooting-logs/status.json

# Configuration
curl -H "x-api-key: your-api-key" https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod/config/modules > troubleshooting-logs/modules.json
```

### Support Checklist

When reporting issues, include:

- [ ] Error message and timestamp
- [ ] System status from dashboard
- [ ] Recent activity processing attempts
- [ ] Module configuration
- [ ] AWS region and profile
- [ ] Frontend browser console logs
- [ ] Lambda function logs (if accessible)

## Prevention

### Regular Maintenance

1. **Monitor Dashboard**: Check system health daily
2. **Review Logs**: Weekly log review for patterns
3. **Update Credentials**: Refresh tokens before expiry
4. **Test Modules**: Monthly module functionality tests
5. **Backup Configuration**: Export settings regularly

### Best Practices

1. **Gradual Rollout**: Test with few activities first
2. **Monitor Costs**: Set up AWS billing alerts
3. **Keep Updated**: Update dependencies regularly
4. **Document Changes**: Track configuration modifications
5. **Test Recovery**: Practice troubleshooting procedures