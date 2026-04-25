# API Documentation

> See also: [Interfaces](../reference/interfaces.md) | [Components](../architecture/components.md)

## Local Interface API Endpoints

All endpoints require `x-api-key` header with the API Gateway key value.

### GET /config/strava
Check if Strava app is configured (client_id and client_secret present).
```json
// Response 200
{"configured": true, "client_id": "12345", "message": "Strava app configured"}
```

### POST /config/oauth
Exchange authorization code for OAuth tokens.
```json
// Request
{"code": "authorization_code_from_strava"}
// Response 200
{"connected": true, "athlete_id": "67890", "obtained_at": "2026-01-01T00:00:00Z"}
```

### GET /dashboard/stats
Activity processing statistics.
```json
// Response 200
{"total_activities": 42, "completed_activities": 38, "failed_activities": 2, "success_rate": 90.5}
```

### GET /dashboard/system
System health status.
```json
// Response 200
{"strava_connected": true, "agentcore_status": "healthy", "enhancement_enabled": true, "enhancement_status": "active"}
```

### POST /preferences
Update user preferences.
```json
// Request
{"age_range": "26-35", "sport_approach": "health & wellness", "content_length": "medium", "content_tone": "motivational & energetic", "emoji_usage": "moderate", "technical_detail": "intermediate", "content_language": "french", "interests": ["music", "technology"]}
// Response 200
{"message": "Preferences updated successfully"}
```

## Webhook API Endpoints

### GET /webhook
Strava subscription verification (public, no auth).
```
// Query params: hub.mode=subscribe&hub.challenge=abc123&hub.verify_token=mytoken
// Response 200
{"hub.challenge": "abc123"}
```

### POST /webhook
Strava event notification (public, HMAC-SHA1 verified).
```json
// Request (from Strava)
{"object_type": "activity", "object_id": 12345, "aspect_type": "create", "owner_id": 67890, "event_time": 1704067200}
// Response 200
{"status": "received"}
```
