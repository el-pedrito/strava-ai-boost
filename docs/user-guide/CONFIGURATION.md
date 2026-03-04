# Configuration Guide

Complete guide to configuring Strava AI Boost via the React frontend.

## Strava OAuth Setup

### 1. Create Strava Application

1. Go to https://www.strava.com/settings/api
2. Click "Create App"
3. Fill in details:
   - **Application Name**: "My Strava AI Boost"
   - **Category**: "Data Importer"
   - **Club**: Leave blank
   - **Website**: http://localhost:3000
   - **Application Description**: "Personal Strava activity enhancement"
   - **Authorization Callback Domain**: localhost

### 2. Configure Frontend Environment

1. Copy `.env.example` to `.env.local` in the `frontend/` directory
2. Set your `VITE_API_GATEWAY_URL`, `VITE_API_GATEWAY_KEY`, and `VITE_DEFAULT_USER_ID`
3. Start the frontend: `cd frontend && npm install && npm run dev`

### 3. Connect Your Account

1. Open http://localhost:3000
2. Click "Connect with Strava"
3. Complete the OAuth 2.0 PKCE flow
4. You'll be redirected back with a success message

## Module Configuration

### Campus Coach Module

**Purpose**: Matches your activities with planned training sessions from Campus Coach.

**Requirements**:
- Active Campus Coach subscription
- Campus Coach account credentials

**Setup**:
1. Go to Configuration → Modules
2. Enable "Campus Coach"
3. Enter your Campus Coach username and password
4. Click "Save Configuration"

**Security**:
- Credentials are encrypted and stored in AWS Secrets Manager
- Connection is validated during first session extraction
- Invalid credentials will cause extraction failures (check logs)

**Features**:
- Automatic session extraction (daily at 8:00 AM Paris time)
- Intelligent activity matching with confidence scoring
- Performance comparison analysis (actual vs planned)
- Flexible week number format support

**Troubleshooting**:
- **"Invalid credentials"**: Verify login works on campus.coach website
- **"No sessions found"**: Check if you have active training plans
- **"Connection timeout"**: Campus Coach website may be temporarily unavailable
- **"Extraction failed"**: Check CloudWatch logs for detailed error messages

### Enduraw Report Module

**Purpose**: Enhanced analytics with weather and wind impact analysis.

**⚠️ External Configuration Required**:
- **Enduraw Report is NOT configured by this system**
- **Must be set up separately** at: https://enduraw-report-strava.onrender.com
- Enduraw Report is an independent third-party service that connects directly to your Strava account
- This module only tells our system to wait for Enduraw data before generating content

**Requirements**:
- Enduraw Report app connected to your Strava account (configured externally)
- Enduraw Report must be processing your activities (independent of this system)

**Setup**:
1. **First**: Configure Enduraw Report at https://enduraw-report-strava.onrender.com
2. **Then**: In this system, go to Configuration → Modules
3. Enable "Enduraw Integration" toggle
4. System will wait 2 minutes for Enduraw data before generating content

**How It Works**:
- When enabled, our system waits 2 minutes after activity upload
- During this time, Enduraw Report (if configured) adds its analysis to your Strava activity description
- Our system then reads the Enduraw data and includes it in content generation
- **If Enduraw is not configured or times out**: Content generation proceeds without Enduraw data (graceful fallback)

**Features** (when Enduraw Report is configured):
- Pace without wind analysis
- Weather impact assessment
- Elevation cost analysis

## Enhancement Control

### Pause/Resume Enhancement

You can temporarily pause automatic enhancement:

1. Go to Dashboard
2. Click "Pause Enhancement"
3. New activities won't be processed until you resume
4. Click "Resume Enhancement" to reactivate

### Personal Profile Configuration

Customize how AI generates content for your activities:

1. Go to Configuration → Personal Profile
2. Configure:
   - **Age Range**: Affects tone and references
   - **Interests**: Technology, music, travel, etc.
   - **Sport Approach**: Health, performance, social, etc.
   - **Content Style**: Short, medium, detailed, adaptive
   - **Communication Tone**: Technical, motivational, casual, humorous
   - **Language Preferences**: Emoji usage, technical detail level

## Troubleshooting Configuration

### OAuth Issues

**Problem**: "Failed to connect to Strava"
**Solution**: 
1. Check Client ID and Secret are correct
2. Verify callback domain is set to "localhost"
3. Ensure Strava app is not in "Demo" mode

**Problem**: "Invalid redirect URI"
**Solution**: 
1. Check Authorization Callback Domain is exactly "localhost"
2. No http:// prefix needed in Strava settings

### Module Issues

**Problem**: "Campus Coach credentials invalid"
**Solution**:
1. Verify username/password work on campus.coach website
2. Check for special characters in password
3. Try logging in manually first

**Problem**: "Enduraw data not available"
**Solution**:
1. Ensure Enduraw app is connected to Strava
2. Wait 2-7 minutes after activity upload
3. Check Enduraw processing status

## Advanced Configuration

### API Gateway Endpoints

The frontend connects to these AWS API Gateway endpoints:
- Dashboard stats: `/dashboard/stats`
- Module configuration: `/config/modules`
- Enhancement control: `/config/enhancement`
- OAuth management: `/config/oauth`

### Environment Variables

Configure these in `frontend/.env.local` (copy from `.env.example`):
```bash
VITE_API_GATEWAY_URL=https://your-api-id.execute-api.eu-west-1.amazonaws.com/prod
VITE_API_GATEWAY_KEY=your-api-key
VITE_DEFAULT_USER_ID=YOUR_USER_ID
```

### Database Configuration

User configuration is stored in DynamoDB:
- **Table**: `strava-ai-boost-user-configuration`
- **Key**: `user_id` (Strava athlete ID)
- **Attributes**: 
  - `user_preferences`: Personal profile and content preferences
  - `modules_config`: Per-user module settings (campus_coach, enduraw)
  - `enhancement_enabled`: Per-user pause/resume status
  - `strava_connected`: OAuth connection status

**Architecture**: Per-user configuration
- Each user has isolated configuration
- User ID automatically retrieved from OAuth tokens
- Supports multi-user scenarios

## User Identification

The system automatically identifies users through:

1. **Webhook Flow**: `owner_id` from Strava webhook (athlete ID)
2. **Configuration API**: `athlete.id` from OAuth tokens in Secrets Manager
3. **Fallback**: `DEFAULT_USER_ID` environment variable (optional)

**OAuth Token Structure**:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "athlete": {
    "id": 12345678  // Your Strava athlete ID (used as user_id)
  }
}
```

## Security Notes

- OAuth tokens are stored securely in AWS Secrets Manager
- Campus Coach credentials are encrypted at rest
- Frontend runs locally on localhost:3000
- All API communication uses HTTPS
- No sensitive data is logged or cached locally