import { useState } from 'react';
import { CheckCircle2, ExternalLink, Link2 } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { Button } from '@/ui';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import type { OAuthStatus } from '../../types/index.ts';

interface Props {
  oauthStatus: OAuthStatus;
  onDisconnected: () => void;
}

export function OAuthConnection({ oauthStatus, onDisconnected }: Props) {
  const flash = useFlash();
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const config = await api.get<{ configured: boolean; client_id: string; redirect_uri: string }>('/config/strava');
      if (!config.configured || !config.client_id) {
        flash('error', 'Strava app not configured. Please configure first.');
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
      flash('error', 'Failed to initiate OAuth flow.');
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      await api.delete('/config/oauth');
      flash('success', 'Successfully disconnected from Strava.');
      onDisconnected();
    } catch {
      flash('error', 'Failed to disconnect. Please try again.');
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
            <h3 className="text-base font-semibold text-foreground">Connected</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Connected to your Strava account.
              {oauthStatus.obtained_at ? ` Authorized on ${oauthStatus.obtained_at}.` : ''}
              {oauthStatus.last_refreshed ? ` Last refresh: ${oauthStatus.last_refreshed}.` : ''}
            </p>
          </div>
        </div>
        <div>
          <Button
            variant="outline"
            className="border-danger text-danger hover:bg-danger hover:text-danger-foreground"
            onClick={() => setShowDisconnect(true)}
          >
            Disconnect
          </Button>
        </div>

        <Dialog.Root open={showDisconnect} onOpenChange={setShowDisconnect}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 animate-fade-in" />
            <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[90vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-lg animate-fade-in-up">
              <Dialog.Title className="text-lg font-semibold text-foreground">Disconnect from Strava</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm text-muted-foreground">
                Are you sure? Your OAuth tokens will be revoked and Strava AI Boost will lose access to your account.
              </Dialog.Description>
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowDisconnect(false)}>
                  Cancel
                </Button>
                <Button variant="destructive" onClick={handleDisconnect} loading={disconnecting}>
                  Disconnect
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
          <h3 className="text-base font-semibold text-foreground">Step 2 — Connect your Strava account</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Authorize Strava AI Boost to read your activities.
          </p>
        </div>
      </div>
      <div>
        <Button onClick={handleConnect} loading={connecting}>
          Connect with Strava
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
