import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Card, CardDescription, CardHeader, CardTitle, InfoTooltip } from '@/ui';
import { StravaAppSetup } from './StravaAppSetup.tsx';
import { OAuthConnection } from './OAuthConnection.tsx';
import { ModuleConfiguration } from './ModuleConfiguration.tsx';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import type { OAuthStatus, ModulesMap } from '../../types/index.ts';

export function ConfigurationPage() {
  const { t } = useTranslation();
  const flash = useFlash();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stravaConfigured, setStravaConfigured] = useState(false);
  const [oauthStatus, setOauthStatus] = useState<OAuthStatus>({ connected: false, configured: false });
  const [modules, setModules] = useState<ModulesMap | null>(null);

  // Handle OAuth callback query params
  useEffect(() => {
    const oauthResult = searchParams.get('oauth');
    if (oauthResult === 'success') {
      flash('success', t('configuration.oauth.successFlash'));
      setSearchParams({});
    } else if (oauthResult === 'error') {
      const message = searchParams.get('message') || t('configuration.oauth.errorFallback');
      flash('error', message);
      setSearchParams({});
    }
  }, [searchParams, setSearchParams, flash, t]);

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
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">{t('configuration.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('configuration.description')}</p>
      </header>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>{t('configuration.strava.title')}</CardTitle>
            <InfoTooltip i18nKey="config.strava.section.help" align="start" />
          </div>
          <CardDescription>{t('configuration.strava.description')}</CardDescription>
        </CardHeader>
        {!stravaConfigured ? (
          <StravaAppSetup onConfigured={fetchStatus} />
        ) : (
          <OAuthConnection oauthStatus={oauthStatus} onDisconnected={fetchStatus} />
        )}
      </Card>

      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>{t('configuration.modules.title')}</CardTitle>
            <InfoTooltip i18nKey="config.modules.section.help" align="start" />
          </div>
          <CardDescription>{t('configuration.modules.description')}</CardDescription>
        </CardHeader>
        <ModuleConfiguration modules={modules} onModuleChanged={fetchStatus} />
      </Card>
    </div>
  );
}
