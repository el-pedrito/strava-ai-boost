import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
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
      <Container header={<Header variant="h2">Connection Status</Header>}>
        <StatusIndicator type="loading">Loading...</StatusIndicator>
      </Container>
    );
  }

  return (
    <Container header={<Header variant="h2">Connection Status</Header>}>
      <ColumnLayout columns={3} variant="text-grid">
        <SpaceBetween size="xs">
          <Box variant="awsui-key-label">Strava API</Box>
          <Box color="text-body-secondary" fontSize="body-s">OAuth connection status</Box>
          <StatusIndicator type={status.strava_connected ? 'success' : 'error'}>
            {status.strava_connected ? 'Connected' : 'Disconnected'}
          </StatusIndicator>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <Box variant="awsui-key-label">AgentCore</Box>
          <Box color="text-body-secondary" fontSize="body-s">AI agents and memory</Box>
          <StatusIndicator type={agentcoreType(status.agentcore_status)}>
            {agentcoreLabel(status.agentcore_status)}
          </StatusIndicator>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <Box variant="awsui-key-label">Enhancement</Box>
          <Box color="text-body-secondary" fontSize="body-s">Activity processing</Box>
          <SpaceBetween direction="horizontal" size="xs">
            <StatusIndicator type={status.enhancement_enabled ? 'success' : 'stopped'}>
              {status.enhancement_status === 'active' ? 'Active' : 'Paused'}
            </StatusIndicator>
            <Button variant="normal" onClick={onToggleEnhancement}>
              {status.enhancement_enabled ? 'Pause' : 'Resume'}
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </ColumnLayout>
    </Container>
  );
}
