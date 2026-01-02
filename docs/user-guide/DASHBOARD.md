# Dashboard Guide

Complete guide to using the Strava AI Boost local web interface.

## Overview

The dashboard at http://localhost:3000 provides real-time monitoring and control of your Strava AI Boost system.

## Main Dashboard

### System Status Panel

**Strava Connection**
- 🟢 **Connected**: OAuth tokens valid, API accessible
- 🟡 **Expiring**: Tokens need refresh (automatic)
- 🔴 **Disconnected**: OAuth setup required

**AgentCore Status**
- 🟢 **Healthy**: Agents accessible and functional
- 🟡 **Not Configured**: Agents not deployed yet
- 🔴 **Error**: Agent connectivity issues

**Enhancement Status**
- 🟢 **Active**: Processing new activities automatically
- 🟡 **Paused**: Manual pause activated
- 🔴 **Error**: System issue requiring attention

### Activity Statistics

**Processing Metrics**
- **Total Activities**: All-time processed count
- **Success Rate (24h)**: Percentage of successful enhancements in last 24 hours (shows "N/A" if no recent activities)

**Module Status**
- **Campus Coach**: Enabled/Disabled with last extraction timestamp
- **Enduraw**: Enabled/Disabled with wait time configuration

### Recent Activities

**Activity List**
- **Name**: Original activity title
- **Date**: Upload timestamp
- **Status**: Processing status (completed, failed, in-progress)
- **Modules**: Which modules were used
- **Processing Time**: How long enhancement took

**Status Indicators**
- ✅ **Completed**: Successfully enhanced
- ⏳ **Processing**: Currently being enhanced
- ❌ **Failed**: Enhancement failed (click for details)
- ⏸️ **Skipped**: Enhancement was paused

## Configuration Tab

### Strava App Setup

**Initial Configuration**
1. **Client ID**: From your Strava API application
2. **Client Secret**: From your Strava API application
3. **Redirect URI**: Automatically set to localhost

**Connection Management**
- **Connect**: Initiate OAuth flow
- **Disconnect**: Revoke tokens and disconnect
- **Refresh**: Manually refresh expired tokens

### Module Management

**Campus Coach Module**
- **Enable/Disable**: Toggle module activation
- **Credentials**: Username and password for Campus Coach (encrypted storage)
- **Update Credentials**: Button to reconfigure credentials if needed
- **Status**: Shows "✓ Configured" when credentials are stored
- **External Service Notice**: Information about Campus Coach subscription requirement
- **Automatic Extraction**: When enabled, sessions are extracted daily at 6 AM Paris time
- **EventBridge Scheduler**: Automatically activated/deactivated with module toggle
- **Last Extraction**: When sessions were last fetched

**Enduraw Module**
- **Enable/Disable**: Toggle integration
- **Wait Time**: 2 minutes for Enduraw data processing
- **External Service Notice**: Information about Enduraw app requirement
- **Status**: Shows "✓ Ready" when enabled

### Enhancement Control

**Global Controls**
- **Pause Enhancement**: Stop processing new activities
- **Resume Enhancement**: Reactivate automatic processing
- **Status Display**: Current enhancement state with timestamp

**Personal Profile**
- **Age Range**: Affects content tone and references
- **Interests**: Influences content themes and style
- **Sport Approach**: Health, performance, social focus
- **Content Style**: Length and detail preferences
- **Communication Tone**: Technical, casual, motivational
- **Language Preferences**: Emoji usage, technical detail

## Real-time Monitoring

The dashboard automatically refreshes every 60 seconds to show the latest data.

### Activity List

**Live Updates**
- Recent activities with processing status
- Processing time for each activity
- Modules used for enhancement
- Success/failure indicators

### Performance Metrics

The dashboard shows key performance indicators:
- **Total Activities**: All-time count
- **Success Rate (24h)**: Recent processing success (N/A if no recent activities)
- **Processing Time**: Shown per activity in the activity list

## Troubleshooting via Dashboard

### Common Issues

**"No activities being processed"**
1. Check enhancement status (not paused)
2. Verify Strava connection (green status)
3. Check webhook subscription status
4. Review recent error logs

**"Processing taking too long"**
1. Check queue depth (high load)
2. Review module wait times (2 min Enduraw wait)
3. Monitor AWS service health
4. Check for failed retries

**"Enhanced content is repetitive"**
1. Update personal profile settings
2. Check AgentCore Memory status
3. Review content generation logs
4. Adjust communication preferences

### Error Details

**Processing Errors**
- Click on failed activities for detailed error information
- Review suggested solutions and retry options
- Check module-specific error messages
- Access CloudWatch logs directly

**System Errors**
- AWS service connectivity issues
- OAuth token problems
- Module configuration errors
- Resource limit warnings

## Advanced Features

### Manual Processing

**Trigger Processing**
- Select specific activities for reprocessing
- Override enhancement pause for single activities
- Test module configurations with sample data
- Force refresh of cached data

### Export/Import

**Configuration Backup**
- Export current module configurations
- Save personal profile settings
- Backup OAuth application settings
- Create system configuration snapshots

**Data Export**
- Export activity processing history
- Download performance metrics
- Generate usage reports
- Extract engagement statistics

### API Integration

**Direct API Access**
- Dashboard API endpoints for custom integrations
- Real-time status API for monitoring tools
- Configuration API for automated management
- Processing API for external triggers

## Mobile Access

The dashboard is responsive and works on mobile devices:

- **Monitoring**: Check system status on the go
- **Control**: Pause/resume enhancement remotely
- **Configuration**: Basic module management
- **Troubleshooting**: View errors and status

**Note**: Full configuration features work best on desktop/tablet.

## Security Features

**Local Access Only**
- Interface only accessible from localhost
- No external network exposure
- Secure token storage in AWS
- Encrypted communication with AWS services

**Session Management**
- Automatic session timeout
- Secure cookie handling
- CSRF protection for forms
- Input validation and sanitization