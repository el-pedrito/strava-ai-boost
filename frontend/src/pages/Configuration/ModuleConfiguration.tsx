import { useState, useEffect, type ReactNode } from 'react';
import { ExternalLink, BarChart3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, InfoTooltip, Input, Label, Toggle } from '@/ui';
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

type TFn = (key: string, options?: Record<string, unknown>) => string;

function statusBadge(status: ModuleStatus, t: TFn): ReactNode {
  if (status === 'connected') return <Badge variant="success">{t('modules.status.connected')}</Badge>;
  if (status === 'not_configured') return <Badge variant="warning">{t('modules.status.notConfigured')}</Badge>;
  return <Badge variant="default">{t('modules.status.disabled')}</Badge>;
}

function moduleStatus(enabled: boolean, configured: boolean, requiresCreds: boolean): ModuleStatus {
  if (!enabled) return 'disabled';
  if (requiresCreds && !configured) return 'not_configured';
  return 'connected';
}

export function ModuleConfiguration({ modules, onModuleChanged }: Props) {
  const { t } = useTranslation();
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
      const moduleName = MODULE_DISPLAY_NAMES[moduleId] ?? moduleId;
      flash(
        enabled ? 'success' : 'info',
        enabled
          ? t('modules.enabledFlash', { name: moduleName })
          : t('modules.disabledFlash', { name: moduleName }),
      );
      onModuleChanged();
    } catch {
      flash('error', t('modules.updateError'));
      if (moduleId === 'campus_coach') setCampusEnabled(!enabled);
      else if (moduleId === 'enduraw') setEndurawEnabled(!enabled);
      else if (moduleId === 'intervals_icu') setIntervalsEnabled(!enabled);
    }
  };

  const handleCampusToggle = (checked: boolean) => {
    setCampusEnabled(checked);
    if (checked && !campusConfigured) {
      setShowCredentials(true);
      flash('info', t('modules.campus.enabledPrompt'));
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
      flash('info', t('modules.intervals.enabledPrompt'));
    } else {
      void toggleModule('intervals_icu', checked);
    }
  };

  const handleIntervalsConfig = async () => {
    if (!apiKey.trim()) {
      flash('error', t('modules.intervals.requiredError'));
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'intervals_icu',
        enabled: true,
        config: { api_key: apiKey },
      });
      flash('success', t('modules.intervals.saveSuccess'));
      setIntervalsConfigured(true);
      setShowIntervalsKey(false);
      setApiKey('');
      onModuleChanged();
    } catch {
      flash('error', t('modules.intervals.saveError'));
    } finally {
      setSaving(false);
    }
  };

  const handleCampusConfig = async () => {
    if (!username.trim() || !password.trim()) {
      flash('error', t('modules.campus.requiredError'));
      return;
    }
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'campus_coach',
        enabled: true,
        config: { credentials: { username, password } },
      });
      flash('success', t('modules.campus.saveSuccess'));
      setCampusConfigured(true);
      setShowCredentials(false);
      setUsername('');
      setPassword('');
      onModuleChanged();
    } catch {
      flash('error', t('modules.campus.saveError'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {/* Campus Coach */}
      <ModuleCard
        logo={<CampusCoachLogo size={28} />}
        title={t('modules.campus.title')}
        description={t('modules.campus.description')}
        toggleId="campus-toggle"
        enabled={campusEnabled}
        onToggle={handleCampusToggle}
        status={moduleStatus(campusEnabled, campusConfigured, true)}
        helpKey="config.module.campus.help"
        t={t}
      >
        {campusEnabled && (
          <div className="mt-4 flex flex-col gap-3 animate-fade-in-up">
            <a
              href="https://app.campus.coach"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-primary hover:underline"
            >
              {t('modules.campus.visit')}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>

            {campusConfigured && !showCredentials ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-muted-foreground">
                  {t('modules.campus.storedNotice')}
                </p>
                <Button variant="outline" size="sm" onClick={() => setShowCredentials(true)}>
                  {t('modules.campus.updateCredentials')}
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
                  <div className="flex items-center gap-1.5">
                    <Label htmlFor="campus-username">{t('modules.campus.usernameLabel')}</Label>
                    <InfoTooltip i18nKey="config.module.campus.credentials.help" align="start" />
                  </div>
                  <Input
                    id="campus-username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder={t('modules.campus.usernamePlaceholder')}
                    autoComplete="off"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="campus-password">{t('modules.campus.passwordLabel')}</Label>
                  <Input
                    id="campus-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={t('modules.campus.passwordPlaceholder')}
                    autoComplete="off"
                  />
                </div>
                <Button type="submit" size="sm" loading={saving}>
                  {t('modules.save')}
                </Button>
              </form>
            )}
          </div>
        )}
      </ModuleCard>

      {/* Enduraw */}
      <ModuleCard
        logo={<EndurawLogo size={28} />}
        title={t('modules.enduraw.title')}
        description={t('modules.enduraw.description')}
        toggleId="enduraw-toggle"
        enabled={endurawEnabled}
        onToggle={handleEndurawToggle}
        status={moduleStatus(endurawEnabled, true, false)}
        helpKey="config.module.enduraw.help"
        t={t}
      >
        {endurawEnabled && (
          <div className="mt-4 flex flex-col gap-2 rounded-lg bg-info/5 border border-info/20 p-3 animate-fade-in-up">
            <p className="text-xs text-muted-foreground">
              {t('modules.enduraw.notice')}
            </p>
            <a
              href="https://enduraw-report-strava.onrender.com"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-primary hover:underline"
            >
              {t('modules.enduraw.openReport')}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        )}
      </ModuleCard>

      {/* Intervals.icu */}
      <ModuleCard
        logo={
          <BarChart3 className="h-7 w-7 text-primary" aria-hidden="true" />
        }
        title={t('modules.intervals.title')}
        description={t('modules.intervals.description')}
        toggleId="intervals-toggle"
        enabled={intervalsEnabled}
        onToggle={handleIntervalsToggle}
        status={moduleStatus(intervalsEnabled, intervalsConfigured, true)}
        helpKey="config.module.intervals.help"
        t={t}
      >
        {intervalsEnabled && (
          <div className="mt-4 flex flex-col gap-3 animate-fade-in-up">
            <p className="text-xs text-muted-foreground">
              {t('modules.intervals.apiKeyHint')}
            </p>
            {intervalsConfigured && !showIntervalsKey ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-muted-foreground">
                  {t('modules.intervals.storedNotice')}
                </p>
                <Button variant="outline" size="sm" onClick={() => setShowIntervalsKey(true)}>
                  {t('modules.intervals.updateApiKey')}
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
                  <div className="flex items-center gap-1.5">
                    <Label htmlFor="intervals-api-key">{t('modules.intervals.apiKeyLabel')}</Label>
                    <InfoTooltip i18nKey="config.module.intervals.apiKey.help" align="start" />
                  </div>
                  <Input
                    id="intervals-api-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={t('modules.intervals.apiKeyPlaceholder')}
                    autoComplete="off"
                  />
                </div>
                <Button type="submit" size="sm" loading={saving}>
                  {t('modules.save')}
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
  helpKey?: string;
  t: TFn;
  children?: ReactNode;
}

function ModuleCard({ logo, title, description, toggleId, enabled, onToggle, status, helpKey, t, children }: ModuleCardProps) {
  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 min-w-10 shrink-0 items-center justify-start">{logo}</div>
        <Toggle id={toggleId} checked={enabled} onCheckedChange={onToggle} aria-label={t('modules.toggleAria', { name: title })} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h4 className="text-base font-semibold text-foreground">{title}</h4>
          {helpKey ? <InfoTooltip i18nKey={helpKey} align="start" /> : null}
        </div>
        {statusBadge(status, t)}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {children}
    </div>
  );
}
