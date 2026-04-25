# UI Component Documentation

> See also: [Program Structure](../reference/program-structure.md)

## Technology Stack
- **React** 19.2.0 with functional components and hooks
- **TypeScript** 5.9.3 for type safety
- **Vite** 7.3.1 for build and development server
- **Cloudscape Design System** 3.x (AWS design system)
- **react-router-dom** 7.x for client-side routing

## Page Structure

### Dashboard (`/`)
- **DashboardPage**: Main dashboard container
  - **SystemOverview**: Strava connection status, AgentCore health, enhancement status
  - **ConnectionStatus**: OAuth connection details with connect/disconnect actions
  - **ModuleStatus**: Campus Coach, Enduraw, Intervals.icu module status cards
  - **RecentActivities**: Table of recent activities with processing status, modules used, confidence scores

### Configuration (`/configuration`)
- **ConfigurationPage**: Settings management
  - **StravaAppSetup**: Strava API app configuration (client_id, client_secret)
  - **OAuthConnection**: OAuth authorization button and status
  - **OAuthCallback**: Handles OAuth redirect with authorization code exchange
  - **ModuleConfiguration**: Toggle and configure individual modules

### Preferences (`/preferences`)
- **PreferencesPage**: User preference form with sections for:
  - Age range (dropdown)
  - Sport approach (dropdown: performance, health, social, challenge, stress relief, weight management)
  - Content tone (dropdown: technical, motivational, casual, humorous, authentic)
  - Content length (dropdown: short, medium, detailed, adaptive)
  - Emoji usage (dropdown: none, minimal, moderate, enthusiastic)
  - Technical detail (dropdown: basic, intermediate, advanced)
  - Content language (dropdown: french, english, etc.)
  - Interests (multi-select: technology, music, travel, food, nature, photography, family, competition)
  - Pace zones (expandable form with min/max fields per zone)

### Quality (`/quality`)
- **ContentQualityPage**: Content generation quality metrics
  - Average confidence score
  - User edit rate (how often users modify AI content)
  - Average similarity score (current vs generated)
  - Total activities analyzed / total feedback events

## Shared Components

### ErrorBoundary
React class component wrapping the entire app. Catches rendering errors and displays a fallback UI with error details and a reload option.

### Icons
Custom SVG icon components: `AppLogo`, `StravaLogo`, `AgentCoreLogo`, `CampusCoachLogo`, `EndurawLogo` — used in navigation, module cards, and branding.

### AppLayout
Cloudscape `AppLayout` with:
- Side navigation (Dashboard, Configuration, Preferences, Quality links)
- Header with app name and navigation
- Main content area for page components

## Hooks

### useAutoRefresh(callback, intervalMs)
Auto-refreshes data at a configurable interval. Used on Dashboard for live status updates.

### useFlashMessages()
Manages dismissible flash messages (success, error, warning, info). Used across pages for operation feedback.

## Routing

```typescript
// App.tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<DashboardPage />} />
    <Route path="/configuration" element={<ConfigurationPage />} />
    <Route path="/configuration/oauth-callback" element={<OAuthCallback />} />
    <Route path="/preferences" element={<PreferencesPage />} />
    <Route path="/quality" element={<ContentQualityPage />} />
  </Routes>
</BrowserRouter>
```
