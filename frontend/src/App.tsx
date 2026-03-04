import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Shell } from './layouts/AppLayout.tsx';
import { DashboardPage } from './pages/Dashboard/DashboardPage.tsx';
import { ConfigurationPage } from './pages/Configuration/ConfigurationPage.tsx';
import { OAuthCallback } from './pages/Configuration/OAuthCallback.tsx';
import { PreferencesPage } from './pages/Preferences/PreferencesPage.tsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/config" element={<ConfigurationPage />} />
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route path="/preferences" element={<PreferencesPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
