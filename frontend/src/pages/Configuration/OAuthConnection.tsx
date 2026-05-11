import { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import Alert from '@cloudscape-design/components/alert';
import Modal from '@cloudscape-design/components/modal';
import { StravaLogo } from '../../components/icons/StravaLogo.tsx';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import type { OAuthStatus } from '../../types/index.ts';

interface Props {
  oauthStatus: OAuthStatus;
  stravaConfigured: boolean;
  onDisconnected: () => void;
}

export function OAuthConnection({ oauthStatus, stravaConfigured, onDisconnected }: Props) {
  const flash = useFlash();
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const config = await api.get<{ configured: boolean; client_id: string; redirect_uri: string }>('/config/strava');
      if (!config.configured || !config.client_id) {
        flash('error', 'Strava app not configured. Please configure first.');
        return;
      }

      const state = crypto.randomUUID();
      const codeVerifier = crypto.randomUUID() + crypto.randomUUID();
      const codeChallenge = await sha256Hex(codeVerifier);

      sessionStorage.setItem('oauth_state', state);
      sessionStorage.setItem('oauth_code_verifier', codeVerifier);
      sessionStorage.setItem('oauth_client_id', config.client_id);

      const redirectUri = config.redirect_uri || `${window.location.origin}/oauth/callback`;
      const params = new URLSearchParams({
        client_id: config.client_id,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: 'activity:read_all,activity:write',
        state,
        code_challenge: codeChallenge,
        code_challenge_method: 'S256',
      });

      window.location.href = `https://www.strava.com/oauth/authorize?${params}`;
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

  const handleTest = async () => {
    setTesting(true);
    flash('info', 'Testing connection to Strava...');
    try {
      const data = await api.get<{
        success: boolean;
        athlete?: { firstname?: string; lastname?: string; city?: string; country?: string };
        api_usage?: { daily_usage: number; daily_limit: number };
      }>('/test/strava-connection');
      if (data.success) {
        const name = [data.athlete?.firstname, data.athlete?.lastname].filter(Boolean).join(' ');
        let msg = 'Connection test successful!';
        if (name) msg += ` Connected as ${name}`;
        if (data.athlete?.city && data.athlete?.country) msg += ` from ${data.athlete.city}, ${data.athlete.country}`;
        flash('success', msg);
        if (data.api_usage) {
          flash('info', `API Usage: ${data.api_usage.daily_usage}/${data.api_usage.daily_limit} daily requests used`);
        }
      }
    } catch {
      flash('error', 'Connection test failed. Please try reconnecting.');
    } finally {
      setTesting(false);
    }
  };

  return (
    <>
      <Container
        header={
          <Header
            variant="h2"
            info={
              <StatusIndicator type={oauthStatus.connected ? 'success' : 'error'}>
                {oauthStatus.connected ? 'Connected' : 'Not Connected'}
              </StatusIndicator>
            }
          >
            Strava Account Connection
          </Header>
        }
      >
        {oauthStatus.connected ? (
          <SpaceBetween size="m">
            <Alert type="success">
              <SpaceBetween size="xxs">
                <Box fontWeight="bold">Connected to Strava</Box>
                <Box color="text-body-secondary" fontSize="body-s">
                  {oauthStatus.obtained_at && `Connected on ${oauthStatus.obtained_at}`}
                  {oauthStatus.last_refreshed && ` - Last refreshed: ${oauthStatus.last_refreshed}`}
                </Box>
              </SpaceBetween>
            </Alert>
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={handleTest} loading={testing}>Test Connection</Button>
              <Button onClick={() => setShowDisconnect(true)}>Disconnect</Button>
            </SpaceBetween>
          </SpaceBetween>
        ) : stravaConfigured ? (
          <Box textAlign="center" padding="l">
            <SpaceBetween size="m">
              <Box color="text-body-secondary">
                Connect your Strava account to enable automatic activity enhancement
              </Box>
              <button
                className="strava-connect-btn"
                onClick={handleConnect}
                disabled={connecting}
              >
                <StravaLogo size={18} />
                {connecting ? 'Connecting...' : 'Connect with Strava'}
              </button>
            </SpaceBetween>
          </Box>
        ) : (
          <Box textAlign="center" padding="l" color="text-body-secondary">
            Please configure your Strava application first
          </Box>
        )}
      </Container>

      <Modal
        visible={showDisconnect}
        onDismiss={() => setShowDisconnect(false)}
        header="Disconnect from Strava"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={() => setShowDisconnect(false)}>Cancel</Button>
              <Button variant="primary" onClick={handleDisconnect} loading={disconnecting}>
                Disconnect
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        Are you sure you want to disconnect from Strava? Your OAuth tokens will be revoked.
      </Modal>
    </>
  );
}

async function sha256Hex(message: string): Promise<string> {
  const data = new TextEncoder().encode(message);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
