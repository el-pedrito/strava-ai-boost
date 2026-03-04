import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { StravaAppSetup } from './StravaAppSetup.tsx';
import { OAuthConnection } from './OAuthConnection.tsx';
import { ModuleConfiguration } from './ModuleConfiguration.tsx';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import type { OAuthStatus, ModulesMap } from '../../types/index.ts';

export function ConfigurationPage() {
  const flash = useFlash();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stravaConfigured, setStravaConfigured] = useState(false);
  const [oauthStatus, setOauthStatus] = useState<OAuthStatus>({ connected: false, configured: false });
  const [modules, setModules] = useState<ModulesMap | null>(null);

  // Handle OAuth callback query params
  useEffect(() => {
    const oauthResult = searchParams.get('oauth');
    if (oauthResult === 'success') {
      flash('success', 'Successfully connected to Strava!');
      setSearchParams({});
    } else if (oauthResult === 'error') {
      const message = searchParams.get('message') || 'OAuth failed';
      flash('error', message);
      setSearchParams({});
    }
  }, [searchParams, setSearchParams, flash]);

  const fetchStatus = useCallback(async () => {
    try {
      const [stravaRes, oauthRes, modulesRes] = await Promise.all([
        api.get<{ configured: boolean }>('/config/strava').catch(() => ({ configured: false })),
        api.get<OAuthStatus>('/config/oauth').catch(() => ({ connected: false, configured: false })),
        api.get<{ modules: ModulesMap }>('/config/modules').catch(() => null),
      ]);
      setStravaConfigured(stravaRes.configured);
      setOauthStatus(oauthRes);
      if (modulesRes?.modules) setModules(modulesRes.modules);
    } catch {
      // Silently handle
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Configure Strava connection and modules">
          Configuration
        </Header>
      }
    >
      <SpaceBetween size="l">
        <StravaAppSetup configured={stravaConfigured} onConfigured={fetchStatus} />
        <OAuthConnection
          oauthStatus={oauthStatus}
          stravaConfigured={stravaConfigured}
          onDisconnected={fetchStatus}
        />
        <ModuleConfiguration modules={modules} onModuleChanged={fetchStatus} />
      </SpaceBetween>
    </ContentLayout>
  );
}
