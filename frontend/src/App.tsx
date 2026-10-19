import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router';
import { Shell } from './layouts/AppLayout.tsx';
import { ErrorBoundary } from './components/ErrorBoundary.tsx';
import { OAuthCallback } from './pages/Configuration/OAuthCallback.tsx';
import { AuthProvider } from './auth/AuthContext.tsx';
import { ProtectedRoute } from './auth/ProtectedRoute.tsx';
import { PlanGate } from './pages/Plan/PlanGate.tsx';

const HomePage = lazy(() => import('./pages/Home/HomePage.tsx').then(m => ({ default: m.HomePage })));
// The old technical dashboard, now the "Monitoring" tab (/monitoring; /system kept as an alias).
const DashboardPage = lazy(() => import('./pages/Dashboard/DashboardPage.tsx').then(m => ({ default: m.DashboardPage })));
const ConfigurationPage = lazy(() => import('./pages/Configuration/ConfigurationPage.tsx').then(m => ({ default: m.ConfigurationPage })));
const PreferencesPage = lazy(() => import('./pages/Preferences/PreferencesPage.tsx').then(m => ({ default: m.PreferencesPage })));
const ContentQualityPage = lazy(() => import('./pages/Quality/ContentQualityPage.tsx').then(m => ({ default: m.ContentQualityPage })));
const CoachPage = lazy(() => import('./pages/Coach/CoachPage.tsx').then(m => ({ default: m.CoachPage })));
const OnboardingPage = lazy(() => import('./pages/Onboarding/OnboardingPage.tsx').then(m => ({ default: m.OnboardingPage })));
const ActivityDetailPage = lazy(() => import('./pages/Activity/ActivityDetailPage.tsx').then(m => ({ default: m.ActivityDetailPage })));
// Post-session RPE + summary, opened from the push notification (/activities/<id>/feedback).
const ActivityFeedbackPage = lazy(() => import('./pages/Activity/ActivityFeedbackPage.tsx').then(m => ({ default: m.ActivityFeedbackPage })));

function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary"
        aria-label="Loading"
      />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <AuthProvider>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route element={<ProtectedRoute><Shell /></ProtectedRoute>}>
                <Route index element={<HomePage />} />
                <Route path="/monitoring" element={<DashboardPage />} />
                <Route path="/system" element={<DashboardPage />} />
                <Route path="/config" element={<ConfigurationPage />} />
                <Route path="/oauth/callback" element={<OAuthCallback />} />
                <Route path="/preferences" element={<PreferencesPage />} />
                <Route path="/quality" element={<ContentQualityPage />} />
                <Route path="/coach" element={<CoachPage />} />
                <Route path="/plan" element={<PlanGate />} />
                <Route path="/onboarding" element={<OnboardingPage />} />
                <Route path="/activities/:id" element={<ActivityDetailPage />} />
                <Route path="/activities/:id/feedback" element={<ActivityFeedbackPage />} />
              </Route>
            </Routes>
          </Suspense>
        </AuthProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
