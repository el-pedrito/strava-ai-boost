import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Card, CardDescription, CardHeader, CardTitle } from '@/ui';
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
    void fetchStatus();
  }, [fetchStatus]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6 md:py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">Configuration</h1>
        <p className="text-sm text-muted-foreground">Connect Strava and configure modules.</p>
      </header>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Strava connection</CardTitle>
          <CardDescription>Configure your Strava app and authorize access to your activities.</CardDescription>
        </CardHeader>
        {!stravaConfigured ? (
          <StravaAppSetup onConfigured={fetchStatus} />
        ) : (
          <OAuthConnection oauthStatus={oauthStatus} onDisconnected={fetchStatus} />
        )}
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>Modules</CardTitle>
          <CardDescription>Enable optional integrations to enrich your activity descriptions.</CardDescription>
        </CardHeader>
        <ModuleConfiguration modules={modules} onModuleChanged={fetchStatus} />
      </Card>
    </div>
  );
}
