import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { StravaLogo } from '../../components/icons/StravaLogo.tsx';
import { AgentCoreLogo } from '../../components/icons/AgentCoreLogo.tsx';
import type { SystemStatus } from '../../types/index.ts';

interface Props {
  status: SystemStatus | null;
  loading: boolean;
  onToggleEnhancement: () => void;
}

function agentcoreType(s: string): 'success' | 'warning' | 'error' {
  if (s === 'healthy') return 'success';
  if (s === 'not_configured') return 'warning';
  return 'error';
}

function agentcoreLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ConnectionStatus({ status, loading, onToggleEnhancement }: Props) {
  if (loading || !status) {
    return (
      <Container header={<Header variant="h2">Connections</Header>}>
        <StatusIndicator type="loading">Loading...</StatusIndicator>
      </Container>
    );
  }

  const stravaAccent = status.strava_connected ? 'card-accent-green' : 'card-accent-red';

  return (
    <ColumnLayout columns={3}>
      <div className={`card-accent ${stravaAccent}`}>
        <Container
          header={
            <Header variant="h2">
              <span className="section-header-with-logo">
                <StravaLogo size={20} />
                Strava API
              </span>
            </Header>
          }
        >
          <SpaceBetween size="xs">
            <Box color="text-body-secondary" fontSize="body-s">OAuth connection to Strava</Box>
            <StatusIndicator type={status.strava_connected ? 'success' : 'error'}>
              {status.strava_connected ? 'Connected' : 'Disconnected'}
            </StatusIndicator>
          </SpaceBetween>
        </Container>
      </div>

      <div className="card-accent card-accent-purple">
        <Container
          header={
            <Header variant="h2">
              <span className="section-header-with-logo">
                <AgentCoreLogo size={20} />
                AgentCore
              </span>
            </Header>
          }
        >
          <SpaceBetween size="xs">
            <Box color="text-body-secondary" fontSize="body-s">AI agents and memory</Box>
            <StatusIndicator type={agentcoreType(status.agentcore_status)}>
              {agentcoreLabel(status.agentcore_status)}
            </StatusIndicator>
          </SpaceBetween>
        </Container>
      </div>

      <div className="card-accent card-accent-blue">
        <Container
          header={
            <Header
              variant="h2"
              actions={
                <Button variant="normal" onClick={onToggleEnhancement}>
                  {status.enhancement_enabled ? 'Pause' : 'Resume'}
                </Button>
              }
            >
              Enhancement
            </Header>
          }
        >
          <SpaceBetween size="xs">
            <Box color="text-body-secondary" fontSize="body-s">Activity processing pipeline</Box>
            <StatusIndicator type={status.enhancement_enabled ? 'success' : 'stopped'}>
              {status.enhancement_status === 'active' ? 'Active' : 'Paused'}
            </StatusIndicator>
          </SpaceBetween>
        </Container>
      </div>
    </ColumnLayout>
  );
}
