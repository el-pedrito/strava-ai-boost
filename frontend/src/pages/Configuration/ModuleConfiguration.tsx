import { useState, useEffect } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Toggle from '@cloudscape-design/components/toggle';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import Alert from '@cloudscape-design/components/alert';
import Form from '@cloudscape-design/components/form';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import Link from '@cloudscape-design/components/link';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
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

export function ModuleConfiguration({ modules, onModuleChanged }: Props) {
  const flash = useFlash();
  const [campusEnabled, setCampusEnabled] = useState(modules?.campus_coach?.enabled ?? false);
  const [endurawEnabled, setEndurawEnabled] = useState(modules?.enduraw?.enabled ?? false);
  const [intervalsEnabled, setIntervalsEnabled] = useState(modules?.intervals_icu?.enabled ?? false);
  const [campusConfigured, setCampusConfigured] = useState(modules?.campus_coach?.configured ?? false);
  const [intervalsConfigured, setIntervalsConfigured] = useState(modules?.intervals_icu?.configured ?? false);
  const [showCredentials, setShowCredentials] = useState(false);
  const [showIntervalsKey, setShowIntervalsKey] = useState(false);

  // Sync state when modules prop loads asynchronously
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
      toggleModule('campus_coach', checked);
    }
  };

  const handleEndurawToggle = (checked: boolean) => {
    setEndurawEnabled(checked);
    toggleModule('enduraw', checked);
  };

  const handleIntervalsToggle = (checked: boolean) => {
    setIntervalsEnabled(checked);
    if (checked && !intervalsConfigured) {
      setShowIntervalsKey(true);
      flash('info', 'Intervals.icu enabled. Please enter your API key below.');
    } else {
      toggleModule('intervals_icu', checked);
    }
  };

  const handleIntervalsConfig = async () => {
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'intervals_icu',
        enabled: true,
        config: { api_key: apiKey },
      });
      flash('success', 'Intervals.icu configured successfully! API key stored securely.');
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
    setSaving(true);
    try {
      await api.post('/config/modules', {
        module_id: 'campus_coach',
        enabled: true,
        config: { credentials: { username, password } },
      });
      flash('success', 'Campus Coach configured successfully! Credentials stored securely.');
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
    <Container header={<Header variant="h2">Module Configuration</Header>}>
      <ColumnLayout columns={3}>
        {/* Campus Coach */}
        <div className="module-config-campus" style={{ padding: '16px', borderRadius: '8px' }}>
          <SpaceBetween size="m">
            <SpaceBetween direction="horizontal" size="xs">
              <span className="section-header-with-logo">
                <CampusCoachLogo size={22} />
                <Box variant="h3">Campus Coach</Box>
              </span>
              <Toggle checked={campusEnabled} onChange={({ detail }) => handleCampusToggle(detail.checked)} />
            </SpaceBetween>
            <Box color="text-body-secondary" fontSize="body-s">
              Training session matching and performance analysis
            </Box>

            {campusEnabled && (
              <SpaceBetween size="s">
                <Alert type="info">
                  <strong>Campus Coach</strong> is a French running training platform that requires a separate account.{' '}
                  <Link href="https://app.campus.coach" external>Visit Campus Coach</Link>
                </Alert>

                {campusConfigured && !showCredentials ? (
                  <SpaceBetween size="s">
                    <StatusIndicator type="success">Configured</StatusIndicator>
                    <Box color="text-body-secondary" fontSize="body-s">
                      Credentials stored securely. Sessions will be extracted automatically.
                    </Box>
                    <Button onClick={() => setShowCredentials(true)}>Update Credentials</Button>
                  </SpaceBetween>
                ) : (
                  <Form
                    actions={
                      <Button variant="primary" onClick={handleCampusConfig} loading={saving}>
                        Configure Campus Coach
                      </Button>
                    }
                  >
                    <SpaceBetween size="m">
                      <FormField label="Username">
                        <Input value={username} onChange={({ detail }) => setUsername(detail.value)} placeholder="Your Campus Coach username" />
                      </FormField>
                      <FormField label="Password" description="Credentials are stored securely in AWS Secrets Manager">
                        <Input value={password} type="password" onChange={({ detail }) => setPassword(detail.value)} placeholder="Your Campus Coach password" />
                      </FormField>
                    </SpaceBetween>
                  </Form>
                )}
              </SpaceBetween>
            )}
          </SpaceBetween>
        </div>

        {/* Enduraw */}
        <div className="module-config-enduraw" style={{ padding: '16px', borderRadius: '8px' }}>
          <SpaceBetween size="m">
            <SpaceBetween direction="horizontal" size="xs">
              <span className="section-header-with-logo">
                <EndurawLogo size={22} />
                <Box variant="h3">Enduraw Integration</Box>
              </span>
              <Toggle checked={endurawEnabled} onChange={({ detail }) => handleEndurawToggle(detail.checked)} />
            </SpaceBetween>
            <Box color="text-body-secondary" fontSize="body-s">
              Enhanced analytics with weather and wind impact
            </Box>

            {endurawEnabled && (
              <SpaceBetween size="s">
                <Alert type="info">
                  Enduraw Report must be configured separately.{' '}
                  <Link href="https://enduraw-report-strava.onrender.com" external>Configure Enduraw Report</Link>
                  <br /><br />
                  <strong>Important:</strong> Activating this module tells the system to wait 2 minutes for Enduraw data.
                  If Enduraw is not configured, content generation proceeds without it.
                </Alert>
                <Alert type="info">
                  <strong>How it works</strong>
                  <ul style={{ margin: '4px 0 0 0', paddingLeft: 20 }}>
                    <li>Processing delay: 2 minutes after activity upload</li>
                    <li>Provides pace without wind, weather impact, elevation cost</li>
                    <li>No credentials required in this system</li>
                    <li>Content generation proceeds with or without Enduraw data</li>
                  </ul>
                </Alert>
              </SpaceBetween>
            )}
          </SpaceBetween>
        </div>

        {/* Intervals.icu */}
        <div className="module-config-intervals" style={{ padding: '16px', borderRadius: '8px' }}>
          <SpaceBetween size="m">
            <SpaceBetween direction="horizontal" size="xs">
              <Box variant="h3">Intervals.icu</Box>
              <Toggle checked={intervalsEnabled} onChange={({ detail }) => handleIntervalsToggle(detail.checked)} />
            </SpaceBetween>
            <Box color="text-body-secondary" fontSize="body-s">
              Fitness metrics, training load, and recovery analysis
            </Box>

            {intervalsEnabled && (
              <SpaceBetween size="s">
                <Alert type="info">
                  <strong>Intervals.icu</strong> provides CTL/ATL/TSB (fitness/fatigue/form), HRV, efficiency factor,
                  decoupling, and more.{' '}
                  <Link href="https://intervals.icu" external>Visit Intervals.icu</Link>
                  <br /><br />
                  Get your API key from <strong>Settings &rarr; Developer Settings</strong> in Intervals.icu.
                </Alert>

                {intervalsConfigured && !showIntervalsKey ? (
                  <SpaceBetween size="s">
                    <StatusIndicator type="success">Configured</StatusIndicator>
                    <Box color="text-body-secondary" fontSize="body-s">
                      API key stored securely. Fitness data will be fetched automatically for each activity.
                    </Box>
                    <Button onClick={() => setShowIntervalsKey(true)}>Update API Key</Button>
                  </SpaceBetween>
                ) : (
                  <Form
                    actions={
                      <Button variant="primary" onClick={handleIntervalsConfig} loading={saving}>
                        Configure Intervals.icu
                      </Button>
                    }
                  >
                    <FormField label="API Key" description="Stored securely in AWS Secrets Manager">
                      <Input value={apiKey} type="password" onChange={({ detail }) => setApiKey(detail.value)} placeholder="Your Intervals.icu API key" />
                    </FormField>
                  </Form>
                )}
              </SpaceBetween>
            )}
          </SpaceBetween>
        </div>
      </ColumnLayout>
    </Container>
  );
}
