import { useState } from 'react';
import { ExternalLink, Link2 } from 'lucide-react';
import { Button, Input, Label } from '@/ui';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';

interface Props {
  onConfigured: () => void;
}

export function StravaAppSetup({ onConfigured }: Props) {
  const flash = useFlash();
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!clientId.trim() || !clientSecret.trim()) {
      flash('error', 'Client ID and Client Secret are required.');
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/strava', {
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: `${window.location.origin}/oauth/callback`,
      });
      flash('success', 'Strava app configured successfully.');
      onConfigured();
    } catch (err) {
      flash('error', `Configuration failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
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
          <h3 className="text-base font-semibold text-foreground">Step 1 — Configure Strava app</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Create an app at strava.com, set the callback domain to <code className="rounded bg-muted px-1 py-0.5 text-xs">localhost</code>, then paste your Client ID and Client Secret below.
          </p>
        </div>
      </div>

      <a
        href="https://www.strava.com/settings/api"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 self-start text-sm font-medium text-primary hover:underline"
      >
        Open strava.com/settings/api
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
            <Label htmlFor="strava-client-id">Client ID</Label>
            <Input
              id="strava-client-id"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="Enter your Strava Client ID"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="strava-client-secret">Client Secret</Label>
            <Input
              id="strava-client-secret"
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder="Enter your Strava Client Secret"
              autoComplete="off"
            />
          </div>
        </div>
        <div>
          <Button type="submit" loading={saving}>
            Save credentials
          </Button>
        </div>
      </form>
    </div>
  );
}
