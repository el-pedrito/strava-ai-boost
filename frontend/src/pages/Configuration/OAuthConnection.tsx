import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, ExternalLink, Link2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import * as Dialog from '@radix-ui/react-dialog';
import { Alert, Button } from '@/ui';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import type { OAuthStatus } from '../../types/index.ts';

interface TestResult {
  success: boolean;
  message?: string;
  athlete?: {
    id?: number;
    name?: string;
    city?: string | null;
    country?: string | null;
  };
}

interface Props {
  oauthStatus: OAuthStatus;
  onDisconnected: () => void;
}

export function OAuthConnection({ oauthStatus, onDisconnected }: Props) {
  const { t } = useTranslation();
  const flash = useFlash();
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    if (!testResult && !testError) return;
    const timer = window.setTimeout(() => {
      setTestResult(null);
      setTestError(null);
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [testResult, testError]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const data = await api.get<TestResult>('/test/strava-connection');
      if (data.success) {
        setTestResult(data);
      } else {
        setTestError(data.message ?? t('oauth.connection.testFailed'));
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('oauth.connection.testFailed');
      setTestError(msg);
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const config = await api.get<{ configured: boolean; client_id: string; redirect_uri: string }>('/config/strava');
      if (!config.configured || !config.client_id) {
        flash('error', t('oauth.connection.notConfiguredError'));
        setConnecting(false);
        return;
      }

      const state = crypto.randomUUID();
      const codeVerifier = crypto.randomUUID() + crypto.randomUUID();
      const codeChallenge = await sha256Hex(codeVerifier);

      sessionStorage.setItem('oauth_state', state);
      sessionStorage.setItem('oauth_code_verifier', codeVerifier);
      sessionStorage.setItem('oauth_client_id', config.client_id);

      const redirectUri = `${window.location.origin}/oauth/callback`;
      const params = new URLSearchParams({
        client_id: config.client_id,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: 'activity:read_all,activity:write',
        state,
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
      });

      window.location.href = `https://www.strava.com/oauth/authorize?${params.toString()}`;
    } catch {
      flash('error', t('oauth.connection.initiateError'));
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await api.delete('/config/oauth');
      flash('success', t('oauth.connection.disconnectSuccess'));
      onDisconnected();
    } catch {
      flash('error', t('oauth.connection.disconnectError'));
    } finally {
      setDisconnecting(false);
      setShowDisconnect(false);
    }
  };

  if (oauthStatus.connected) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-success/10 text-success">
            <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-foreground">{t('oauth.connection.connectedTitle')}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {t('oauth.connection.connectedTo')}
              {oauthStatus.obtained_at ? t('oauth.connection.authorizedOn', { date: oauthStatus.obtained_at }) : ''}
              {oauthStatus.last_refreshed ? t('oauth.connection.lastRefresh', { date: oauthStatus.last_refreshed }) : ''}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleTest} loading={testing}>
            <Activity className="h-4 w-4" aria-hidden="true" />
            {t('oauth.connection.testConnection')}
          </Button>
          <Button
            variant="outline"
            className="border-danger text-danger hover:bg-danger hover:text-danger-foreground"
            onClick={() => setShowDisconnect(true)}
          >
            {t('oauth.connection.disconnect')}
          </Button>
        </div>

        {testResult ? (
          <div className="rounded-lg border border-success/30 bg-success/5 p-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-success shrink-0" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-foreground">{t('oauth.connection.healthy')}</p>
                {testResult.athlete?.name ? (
                  <p className="mt-0.5 text-sm font-medium text-foreground">
                    {testResult.athlete.name}
                  </p>
                ) : null}
                {testResult.athlete?.city || testResult.athlete?.country ? (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {[testResult.athlete?.city, testResult.athlete?.country]
                      .filter(Boolean)
                      .join(', ')}
                  </p>
                ) : null}
                {testResult.athlete?.id !== undefined ? (
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <p className="text-muted-foreground">{t('oauth.connection.athleteId')}</p>
                      <p className="font-numeric font-medium text-foreground">
                        {testResult.athlete.id}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">{t('oauth.connection.statusLabel')}</p>
                      <p className="font-medium text-success">{t('oauth.connection.authenticated')}</p>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {testError ? <Alert variant="error">{testError}</Alert> : null}

        <Dialog.Root open={showDisconnect} onOpenChange={setShowDisconnect}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 animate-fade-in" />
            <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-lg animate-fade-in-up">
              <Dialog.Title className="text-lg font-semibold text-foreground">{t('oauth.connection.dialogTitle')}</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-muted-foreground">
                {t('oauth.connection.dialogDescription')}
              </Dialog.Description>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowDisconnect(false)}>
                  {t('oauth.connection.dialogCancel')}
                </Button>
                <Button variant="destructive" onClick={handleDisconnect} loading={disconnecting}>
                  {t('oauth.connection.disconnect')}
                </Button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Link2 className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">{t('oauth.connection.step2Title')}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('oauth.connection.step2Description')}
          </p>
        </div>
      </div>
      <div>
        <Button onClick={handleConnect} loading={connecting}>
          {t('oauth.connection.connectButton')}
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

async function sha256Hex(message: string): Promise<string> {
  const data = new TextEncoder().encode(message);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
