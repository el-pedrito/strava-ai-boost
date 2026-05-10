import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Spinner, Box } from '@cloudscape-design/components';
import { Shell } from './layouts/AppLayout.tsx';
import { ErrorBoundary } from './components/ErrorBoundary.tsx';
import { OAuthCallback } from './pages/Configuration/OAuthCallback.tsx';
import { AuthProvider } from './auth/AuthContext.tsx';
import { ProtectedRoute } from './auth/ProtectedRoute.tsx';

const DashboardPage = lazy(() => import('./pages/Dashboard/DashboardPage.tsx').then(m => ({ default: m.DashboardPage })));
const ConfigurationPage = lazy(() => import('./pages/Configuration/ConfigurationPage.tsx').then(m => ({ default: m.ConfigurationPage })));
const PreferencesPage = lazy(() => import('./pages/Preferences/PreferencesPage.tsx').then(m => ({ default: m.PreferencesPage })));
const ContentQualityPage = lazy(() => import('./pages/Quality/ContentQualityPage.tsx').then(m => ({ default: m.ContentQualityPage })));
const CoachPage = lazy(() => import('./pages/Coach/CoachPage.tsx').then(m => ({ default: m.CoachPage })));

function PageLoader() {
  return (
    <Box textAlign="center" padding="xxl">
      <Spinner size="large" />
    </Box>
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
                <Route index element={<DashboardPage />} />
                <Route path="/config" element={<ConfigurationPage />} />
                <Route path="/oauth/callback" element={<OAuthCallback />} />
                <Route path="/preferences" element={<PreferencesPage />} />
                <Route path="/quality" element={<ContentQualityPage />} />
                <Route path="/coach" element={<CoachPage />} />
              </Route>
            </Routes>
          </Suspense>
        </AuthProvider>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
