# Event Patterns

> See also: [Workflows](../behavior/workflows.md) | [Components](../architecture/components.md)

## SQS Message Format (Activity Processing Queue)

```json
{
  "activity_id": "12345678",
  "user_id": "67890",
  "webhook_data": {
    "object_type": "activity",
    "object_id": 12345678,
    "aspect_type": "create",
    "owner_id": 67890,
    "event_time": 1704067200,
    "subscription_id": 12345
  },
  "event_time": 1704067200,
  "enduraw_waited": false,
  "enduraw_delay_started_at": null
}
```

**Message Attributes**: `ActivityId` (String), `UserId` (String)

## Step Functions Input

```json
{
  "activity_id": "12345678",
  "user_id": "67890",
  "webhook_data": { "...same as SQS..." },
  "enduraw_waited": true,
  "processing_started_at": "2026-01-01T00:00:00Z"
}
```

## EventBridge Events

### Step Functions Failure Event
```json
{
  "source": "aws.states",
  "detail-type": "Step Functions Execution Status Change",
  "detail": {
    "status": "FAILED",
    "stateMachineArn": "arn:aws:states:eu-west-1:...:stateMachine:StravaAIBoost-ActivityProcessing",
    "executionArn": "arn:aws:states:eu-west-1:...:execution:StravaAIBoost-ActivityProcessing:activity-123-..."
  }
}
```

### Campus Coach Scheduler Event
```json
{
  "action": "extract_sessions",
  "source": "eventbridge_scheduler"
}
```

### Feedback Analyzer Schedule
Triggered by EventBridge cron (`0 3 * * ? *`) with no custom payload — Lambda receives standard EventBridge scheduled event.

## Strava Webhook Events

### Activity Created
```json
{
  "object_type": "activity",
  "object_id": 12345678,
  "aspect_type": "create",
  "owner_id": 67890,
  "event_time": 1704067200,
  "subscription_id": 12345
}
```

### Activity Updated (triggers infinite loop prevention)
```json
{
  "object_type": "activity",
  "object_id": 12345678,
  "aspect_type": "update",
  "owner_id": 67890,
  "event_time": 1704067300,
  "subscription_id": 12345,
  "updates": {"description": "new value"}
}
```
