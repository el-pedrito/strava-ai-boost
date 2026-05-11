import { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Form from '@cloudscape-design/components/form';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Alert from '@cloudscape-design/components/alert';
import { StravaLogo } from '../../components/icons/StravaLogo.tsx';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';

interface Props {
  configured: boolean;
  onConfigured: () => void;
}

export function StravaAppSetup({ configured, onConfigured }: Props) {
  const flash = useFlash();
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await api.post('/config/strava', {
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: `${window.location.origin}/oauth/callback`,
      });
      flash('success', 'Strava app configured successfully!');
      onConfigured();
    } catch (err) {
      flash('error', `Configuration failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Container
      header={
        <Header
          variant="h2"
          info={
            <StatusIndicator type={configured ? 'success' : 'error'}>
              {configured ? 'Configured' : 'Not Configured'}
            </StatusIndicator>
          }
        >
          <span className="section-header-with-logo">
            <StravaLogo size={22} />
            Strava Application Setup
          </span>
        </Header>
      }
    >
      {configured ? (
        <Alert type="success">
          Strava application is configured. Ready to connect with OAuth.
        </Alert>
      ) : (
        <SpaceBetween size="l">
          <Alert type="info">
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>Go to <a href="https://www.strava.com/settings/api" target="_blank" rel="noreferrer">Strava API Settings</a></li>
              <li>Create an application or use an existing one</li>
              <li>Set the Authorization Callback Domain to <code>localhost</code></li>
              <li>Copy your Client ID and Client Secret below</li>
            </ol>
          </Alert>
          <Form
            actions={
              <Button variant="primary" onClick={handleSubmit} loading={saving}>
                Configure Strava App
              </Button>
            }
          >
            <SpaceBetween size="l">
              <FormField label="Client ID" description="Numeric value from your Strava application settings">
                <Input value={clientId} onChange={({ detail }) => setClientId(detail.value)} placeholder="Enter your Strava application Client ID" />
              </FormField>
              <FormField label="Client Secret" description="Long alphanumeric string from your Strava application settings">
                <Input value={clientSecret} type="password" onChange={({ detail }) => setClientSecret(detail.value)} placeholder="Enter your Strava application Client Secret" />
              </FormField>
              <FormField label="Redirect URI" description="Use this exact URL in your Strava application settings">
                <Input value="http://localhost:3000/oauth/callback" readOnly />
              </FormField>
            </SpaceBetween>
          </Form>
        </SpaceBetween>
      )}
    </Container>
  );
}
