import { useState } from 'react';
import { ExternalLink, Link2 } from 'lucide-react';
import { useTranslation, Trans } from 'react-i18next';
import { Button, InfoTooltip, Input, Label } from '@/ui';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';

interface Props {
  onConfigured: () => void;
}

export function StravaAppSetup({ onConfigured }: Props) {
  const { t } = useTranslation();
  const flash = useFlash();
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!clientId.trim() || !clientSecret.trim()) {
      flash('error', t('oauth.setup.requiredError'));
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/strava', {
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: `${window.location.origin}/oauth/callback`,
      });
      flash('success', t('oauth.setup.successFlash'));
      onConfigured();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : t('oauth.setup.unknownError');
      flash('error', t('oauth.setup.failurePrefix', { error: errorMessage }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Link2 className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-1.5">
            <h3 className="text-base font-semibold text-foreground">{t('oauth.setup.step1Title')}</h3>
            <InfoTooltip i18nKey="config.strava.help" align="start" />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            <Trans
              i18nKey="oauth.setup.step1Description"
              components={{ code: <code className="rounded bg-muted px-1 py-0.5 text-xs" /> }}
            />
          </p>
        </div>
      </div>

      <a
        href="https://www.strava.com/settings/api"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 self-start text-sm font-medium text-primary hover:underline"
      >
        {t('oauth.setup.openStrava')}
        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
      </a>

      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void handleSubmit();
        }}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="strava-client-id">{t('oauth.setup.clientIdLabel')}</Label>
              <InfoTooltip i18nKey="config.strava.clientId.help" align="start" />
            </div>
            <Input
              id="strava-client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder={t('oauth.setup.clientIdPlaceholder')}
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="strava-client-secret">{t('oauth.setup.clientSecretLabel')}</Label>
              <InfoTooltip i18nKey="config.strava.clientSecret.help" align="start" />
            </div>
            <Input
              id="strava-client-secret"
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder={t('oauth.setup.clientSecretPlaceholder')}
              autoComplete="off"
            />
          </div>
        </div>
        <div>
          <Button type="submit" loading={saving}>
            {t('oauth.setup.saveCredentials')}
          </Button>
        </div>
      </form>
    </div>
  );
}
