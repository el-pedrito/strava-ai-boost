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
import type { ModulesMap } from '../../types/index.ts';

interface Props {
  modules: ModulesMap | null;
  onModuleChanged: () => void;
}

export function ModuleConfiguration({ modules, onModuleChanged }: Props) {
  const flash = useFlash();
  const [campusEnabled, setCampusEnabled] = useState(modules?.campus_coach?.enabled ?? false);
  const [endurawEnabled, setEndurawEnabled] = useState(modules?.enduraw?.enabled ?? false);
  const [campusConfigured, setCampusConfigured] = useState(modules?.campus_coach?.configured ?? false);
  const [showCredentials, setShowCredentials] = useState(false);

  // Sync state when modules prop loads asynchronously
  useEffect(() => {
    if (modules) {
      setCampusEnabled(modules.campus_coach?.enabled ?? false);
      setEndurawEnabled(modules.enduraw?.enabled ?? false);
      setCampusConfigured(modules.campus_coach?.configured ?? false);
    }
  }, [modules]);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  const toggleModule = async (moduleId: string, enabled: boolean) => {
    try {
      await api.post('/config/modules', { module_id: moduleId, enabled });
      const name = moduleId === 'campus_coach' ? 'Campus Coach' : 'Enduraw';
      flash(enabled ? 'success' : 'info', `${name} ${enabled ? 'enabled' : 'disabled'}`);
      onModuleChanged();
    } catch {
      flash('error', 'Failed to update module');
      if (moduleId === 'campus_coach') setCampusEnabled(!enabled);
      else setEndurawEnabled(!enabled);
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
      <ColumnLayout columns={2}>
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
      </ColumnLayout>
    </Container>
  );
}
