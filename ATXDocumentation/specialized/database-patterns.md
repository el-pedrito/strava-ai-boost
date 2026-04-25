# Database Patterns (DynamoDB)

> See also: [Data Models](../reference/data-models.md) | [Components](../architecture/components.md)

## Table Design Summary

| Table | Partition Key | Sort Key | GSIs | Billing | Encryption | TTL | Streams |
|---|---|---|---|---|---|---|---|
| strava-ai-boost-activities | `activity_id` (S) | — | `ProcessingStatusIndex` | PAY_PER_REQUEST | AWS_MANAGED | `expires_at` | NEW_AND_OLD_IMAGES |
| strava-ai-boost-user-configuration | `user_id` (S) | — | — | PAY_PER_REQUEST | AWS_MANAGED | — | — |
| strava-ai-boost-campus-coaching-sessions | `session_date` (S) | `session_id` (S) | `WeekNumberIndex` | PAY_PER_REQUEST | AWS_MANAGED | — | — |

## Access Patterns

### Activities Table
| Access Pattern | Operation | Key Condition | Used By |
|---|---|---|---|
| Get activity by ID | GetItem | PK = activity_id | Fetcher, Generator, Updater, Processor |
| Update activity status | UpdateItem | PK = activity_id | Processor, Updater, ErrorHandler |
| Store complete data | PutItem | PK = activity_id | Fetcher |
| Query by status | Query (GSI) | processing_status, sorted by created_at | Dashboard, FeedbackAnalyzer |
| Scan recent activities | Scan with filter | filter on created_at or processing_status | Dashboard (limited) |

### User Configuration Table
| Access Pattern | Operation | Key Condition | Used By |
|---|---|---|---|
| Get user config | GetItem | PK = user_id | Processor, Fetcher, Generator, ConfigAPI |
| Update preferences | UpdateItem/PutItem | PK = user_id | PreferencesAPI, ConfigAPI |
| Check enhancement status | GetItem | PK = user_id (read enhancement_enabled) | WebhookHandler |

### Coaching Sessions Table
| Access Pattern | Operation | Key Condition | Used By |
|---|---|---|---|
| Get session by date+id | GetItem | PK = session_date, SK = session_id | — |
| Upsert session | PutItem | PK = session_date, SK = session_id | Campus Coach Agent |
| Query by week | Query (GSI) | PK = week_number, sorted by session_date | Content Generator |
| Scan recent sessions | Scan with filter | updated_at >= cutoff AND status = "À faire" | modules_processing |

## Key Design Decisions
- **PAY_PER_REQUEST billing**: Low-volume, bursty workload — on-demand pricing is more cost-effective than provisioned
- **JSON string storage**: Complete Strava activity data stored as JSON strings (`activity_data_json`) to avoid DynamoDB's 400KB item limit and complex nested attribute structures
- **Decimal conversion**: Python `float` types converted to `Decimal` for DynamoDB compatibility using recursive helpers
- **TTL on activities**: 365-day expiry prevents unbounded table growth
- **DynamoDB Streams**: Enabled on activities table for potential future event-driven processing
