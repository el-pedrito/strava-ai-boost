# Known Issues References

This steering file provides references to known issues and troubleshooting documentation.

## Documentation References

For complete known issues and troubleshooting information, refer to:

```
#[[file:docs/KNOWN-ISSUES.md]]
```

## Current Critical Issues Summary

### AgentCore Browser Tool - Cold Start Problem (KNOWN ISSUE from strava-ai-coach)
- **Status**: � Knowen issue from strava-ai-coach project
- **Symptoms**: First invocation of AgentCore Browser Tool often fails, success after 2-3 retries
- **Impact**: ~30% success rate on first try, 90% after retries
- **Root Cause**: AgentCore Browser Tool runtime cold start issues
- **Workaround**: Implement retry logic in Campus Coach agent invocation
- **Mitigation Strategy**: 
  - Add exponential backoff retry in Lambda invoker
  - Consider warming strategy for Campus Coach agent
  - Monitor agent invocation success rates

### Potential Issues to Monitor

#### AgentCore CLI Deployment
- **Risk**: AgentCore CLI commands may fail during initial setup
- **Mitigation**: Use shell scripts with proper error handling and validation
- **Monitoring**: Check AgentCore agent status after deployment

#### AgentCore Memory Integration
- **Risk**: Memory service connectivity issues or data persistence problems
- **Mitigation**: Proper error handling and fallback to basic content generation
- **Monitoring**: Track memory lookup latency and success rates

#### Local Web Interface Connection
- **Risk**: Local interface may not connect to AWS resources
- **Mitigation**: Proper IAM roles and API Gateway configuration
- **Monitoring**: Test OAuth flow and dashboard loading

### Monitoring Commands Quick Reference

```bash
# Strava AI Boost specific monitoring commands

# Lambda function logs
aws logs tail /aws/lambda/StravaAIBoost-WebhookHandler* --follow --profile your-aws-profile

# Step Functions executions
aws stepfunctions list-executions --state-machine-arn <strava-ai-boost-workflow-arn> --profile your-aws-profile

# DynamoDB activity data
aws dynamodb scan --table-name strava-ai-boost-activities --profile your-aws-profile | jq '.Items | length'

# AgentCore Browser Tool logs (Campus Coach agent)
aws logs tail /aws/bedrock-agentcore/runtimes/strava-ai-boost-campus-coach-* --follow --profile your-aws-profile --region eu-west-1

# AgentCore Content Generation agent logs
aws logs tail /aws/bedrock-agentcore/runtimes/strava-ai-boost-content-generator-* --follow --profile your-aws-profile --region eu-west-1

# AgentCore agent status
agentcore agent list --profile your-aws-profile --region eu-west-1

# AgentCore Memory status
agentcore memory list --profile your-aws-profile --region eu-west-1

# Check Campus Coach agent invocation success rate
aws logs filter-log-events --log-group-name /aws/lambda/StravaAIBoost-CampusCoachInvoker --filter-pattern "ERROR" --profile your-aws-profile
```

## When to Reference Known Issues Documentation

### For Debugging Work
- Include `docs/KNOWN-ISSUES.md` when investigating system problems
- Reference for troubleshooting checklists and monitoring commands
- Use for understanding current active issues and workarounds

### For System Monitoring
- Check known issues before investigating new problems
- Use monitoring commands from the documentation
- Follow troubleshooting checklists for systematic debugging

### For Issue Reporting
- Use the issue reporting template from the documentation
- Check if the issue is already documented before creating new reports
- Follow the established format for consistency

This approach ensures all known issues are documented in the authoritative location while providing quick access to critical information for immediate troubleshooting.
