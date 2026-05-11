import { useState, useEffect, type ReactNode } from 'react';
import { ExternalLink } from 'lucide-react';
import { Badge, Button, Input, Label, Toggle } from '@/ui';
import { CampusCoachLogo } from '../../components/icons/CampusCoachLogo.tsx';
import { EndurawLogo } from '../../components/icons/EndurawLogo.tsx';
import { api } from '../../api/client.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { MODULE_DISPLAY_NAMES } from '../../utils/statusMapper.ts';
import type { ModulesMap } from '../../types/index.ts';

interface Props {
  modules: ModulesMap | null;
  onModuleChanged: () => void;
}

type ModuleStatus = 'connected' | 'not_configured' | 'disabled';

function statusBadge(status: ModuleStatus): ReactNode {
  if (status === 'connected') return <Badge variant="success">Connected</Badge>;
  if (status === 'not_configured') return <Badge variant="warning">Not configured</Badge>;
  return <Badge variant="default">Disabled</Badge>;
}

function moduleStatus(enabled: boolean, configured: boolean, requiresCreds: boolean): ModuleStatus {
  if (!enabled) return 'disabled';
  if (requiresCreds && !configured) return 'not_configured';
  return 'connected';
}

export function ModuleConfiguration({ modules, onModuleChanged }: Props) {
  const flash = useFlash();
  const [campusEnabled, setCampusEnabled] = useState(modules?.campus_coach?.enabled ?? false);
  const [endurawEnabled, setEndurawEnabled] = useState(modules?.enduraw?.enabled ?? false);
  const [intervalsEnabled, setIntervalsEnabled] = useState(modules?.intervals_icu?.enabled ?? false);
  const [campusConfigured, setCampusConfigured] = useState(modules?.campus_coach?.configured ?? false);
  const [intervalsConfigured, setIntervalsConfigured] = useState(modules?.intervals_icu?.configured ?? false);
  const [showCredentials, setShowCredentials] = useState(false);
  const [showIntervalsKey, setShowIntervalsKey] = useState(false);

  useEffect(() => {
    if (modules) {
      setCampusEnabled(modules.campus_coach?.enabled ?? false);
      setEndurawEnabled(modules.enduraw?.enabled ?? false);
      setIntervalsEnabled(modules.intervals_icu?.enabled ?? false);
      setCampusConfigured(modules.campus_coach?.configured ?? false);
      setIntervalsConfigured(modules.intervals_icu?.configured ?? false);
    }
  }, [modules]);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);

  const toggleModule = async (moduleId: string, enabled: boolean) => {
    try {
      await api.post('/config/modules', { module_id: moduleId, enabled });
      flash(enabled ? 'success' : 'info', `${MODULE_DISPLAY_NAMES[moduleId] ?? moduleId} ${enabled ? 'enabled' : 'disabled'}`);
      onModuleChanged();
    } catch {
      flash('error', 'Failed to update module');
      if (moduleId === 'campus_coach') setCampusEnabled(!enabled);
      else if (moduleId === 'enduraw') setEndurawEnabled(!enabled);
      else if (moduleId === 'intervals_icu') setIntervalsEnabled(!enabled);
    }
  };

  const handleCampusToggle = (checked: boolean) => {
    setCampusEnabled(checked);
    if (checked && !campusConfigured) {
      setShowCredentials(true);
      flash('info', 'Campus Coach enabled. Please configure your credentials below.');
    } else {
      void toggleModule('campus_coach', checked);
    }
  };

  const handleEndurawToggle = (checked: boolean) => {
    setEndurawEnabled(checked);
    void toggleModule('enduraw', checked);
  };

  const handleIntervalsToggle = (checked: boolean) => {
    setIntervalsEnabled(checked);
    if (checked && !intervalsConfigured) {
      setShowIntervalsKey(true);
      flash('info', 'Intervals.icu enabled. Please enter your API key below.');
    } else {
      void toggleModule('intervals_icu', checked);
    }
  };

  const handleIntervalsConfig = async () => {
    if (!apiKey.trim()) {
      flash('error', 'API key is required.');
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'intervals_icu',
        enabled: true,
        config: { api_key: apiKey },
      });
      flash('success', 'Intervals.icu configured. API key stored securely.');
      setIntervalsConfigured(true);
      setShowIntervalsKey(false);
      setApiKey('');
      onModuleChanged();
    } catch {
      flash('error', 'Failed to configure Intervals.icu');
    } finally {
      setSaving(false);
    }
  };

  const handleCampusConfig = async () => {
    if (!username.trim() || !password.trim()) {
      flash('error', 'Username and password are required.');
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'campus_coach',
        enabled: true,
        config: { credentials: { username, password } },
      });
      flash('success', 'Campus Coach configured. Credentials stored securely.');
      setCampusConfigured(true);
      setShowCredentials(false);
      setUsername('');
      setPassword('');
      onModuleChanged();
    } catch {
      flash('error', 'Failed to configure Campus Coach');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {/* Campus Coach */}
      <ModuleCard
        logo={<CampusCoachLogo size={28} />}
        title="Campus Coach"
        description="Training session matching and performance analysis."
        toggleId="campus-toggle"
        enabled={campusEnabled}
        onToggle={handleCampusToggle}
        status={moduleStatus(campusEnabled, campusConfigured, true)}
      >
        {campusEnabled && (
          <div className="mt-4 flex flex-col gap-3 animate-fade-in-up">
            <a
              href="https://app.campus.coach"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-primary hover:underline"
            >
              Visit Campus Coach
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>

            {campusConfigured && !showCredentials ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-muted-foreground">
                  Credentials stored securely. Sessions are extracted automatically.
                </p>
                <Button variant="outline" size="sm" onClick={() => setShowCredentials(true)}>
                  Update credentials
                </Button>
              </div>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleCampusConfig();
                }}
              >
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="campus-username">Username</Label>
                  <Input
                    id="campus-username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Your Campus Coach username"
                    autoComplete="off"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="campus-password">Password</Label>
                  <Input
                    id="campus-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Your Campus Coach password"
                    autoComplete="off"
                  />
                </div>
                <Button type="submit" size="sm" loading={saving}>
                  Save
                </Button>
              </form>
            )}
          </div>
        )}
      </ModuleCard>

      {/* Enduraw */}
      <ModuleCard
        logo={<EndurawLogo size={28} />}
        title="Enduraw"
        description="Weather and wind impact on your performance."
        toggleId="enduraw-toggle"
        enabled={endurawEnabled}
        onToggle={handleEndurawToggle}
        status={moduleStatus(endurawEnabled, true, false)}
      >
        {endurawEnabled && (
          <div className="mt-4 flex flex-col gap-2 rounded-lg bg-info/5 border border-info/20 p-3 animate-fade-in-up">
            <p className="text-xs text-muted-foreground">
              Configure Enduraw separately. Activities wait 2 minutes for Enduraw data; generation continues without it if missing.
            </p>
            <a
              href="https://enduraw-report-strava.onrender.com"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-primary hover:underline"
            >
              Open Enduraw Report
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        )}
      </ModuleCard>

      {/* Intervals.icu */}
      <ModuleCard
        logo={
          <span className="font-mono text-sm font-semibold tracking-tight text-foreground">
            intervals.icu
          </span>
        }
        title="Intervals.icu"
        description="Fitness, fatigue, form (CTL/ATL/TSB), HRV and more."
        toggleId="intervals-toggle"
        enabled={intervalsEnabled}
        onToggle={handleIntervalsToggle}
        status={moduleStatus(intervalsEnabled, intervalsConfigured, true)}
      >
        {intervalsEnabled && (
          <div className="mt-4 flex flex-col gap-3 animate-fade-in-up">
            <p className="text-xs text-muted-foreground">
              Get your API key from <span className="font-medium">Settings → Developer Settings</span> on intervals.icu.
            </p>
            {intervalsConfigured && !showIntervalsKey ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-muted-foreground">
                  API key stored securely. Fitness data is fetched automatically.
                </p>
                <Button variant="outline" size="sm" onClick={() => setShowIntervalsKey(true)}>
                  Update API key
                </Button>
              </div>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleIntervalsConfig();
                }}
              >
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="intervals-api-key">API key</Label>
                  <Input
                    id="intervals-api-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Your intervals.icu API key"
                    autoComplete="off"
                  />
                </div>
                <Button type="submit" size="sm" loading={saving}>
                  Save
                </Button>
              </form>
            )}
          </div>
        )}
      </ModuleCard>
    </div>
  );
}

interface ModuleCardProps {
  logo: ReactNode;
  title: string;
  description: string;
  toggleId: string;
  enabled: boolean;
  onToggle: (checked: boolean) => void;
  status: ModuleStatus;
  children?: ReactNode;
}

function ModuleCard({ logo, title, description, toggleId, enabled, onToggle, status, children }: ModuleCardProps) {
  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center">{logo}</div>
        <Toggle id={toggleId} checked={enabled} onCheckedChange={onToggle} aria-label={`Toggle ${title}`} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <h4 className="text-base font-semibold text-foreground">{title}</h4>
        {statusBadge(status)}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {children}
    </div>
  );
}
