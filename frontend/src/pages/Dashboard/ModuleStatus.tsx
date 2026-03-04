import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { useNavigate } from 'react-router-dom';
import type { ModulesMap } from '../../types/index.ts';

interface Props {
  modules: ModulesMap | null;
  loading: boolean;
}

export function ModuleStatus({ modules, loading }: Props) {
  const navigate = useNavigate();

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={<Button onClick={() => navigate('/config')}>Configure Modules</Button>}
        >
          Module Status
        </Header>
      }
    >
      {loading || !modules ? (
        <StatusIndicator type="loading">Loading...</StatusIndicator>
      ) : (
        <ColumnLayout columns={2}>
          <SpaceBetween size="xs">
            <SpaceBetween direction="horizontal" size="xs">
              <Box variant="awsui-key-label">Campus Coach</Box>
              <StatusIndicator type={modules.campus_coach?.enabled ? 'success' : 'stopped'}>
                {modules.campus_coach?.enabled ? 'Enabled' : 'Disabled'}
              </StatusIndicator>
            </SpaceBetween>
            <Box color="text-body-secondary" fontSize="body-s">
              Training session matching and performance analysis
            </Box>
            <Box color="text-body-secondary" fontSize="body-s">
              {modules.campus_coach?.last_extraction
                ? `Last extraction: ${modules.campus_coach.last_extraction}`
                : 'No recent extractions'}
            </Box>
          </SpaceBetween>

          <SpaceBetween size="xs">
            <SpaceBetween direction="horizontal" size="xs">
              <Box variant="awsui-key-label">Enduraw</Box>
              <StatusIndicator type={modules.enduraw?.enabled ? 'success' : 'stopped'}>
                {modules.enduraw?.enabled ? 'Enabled' : 'Disabled'}
              </StatusIndicator>
            </SpaceBetween>
            <Box color="text-body-secondary" fontSize="body-s">
              Enhanced analytics with weather and wind impact
            </Box>
            <Box color="text-body-secondary" fontSize="body-s">
              Wait time: {modules.enduraw?.wait_time ?? '2-7 minutes'}
            </Box>
          </SpaceBetween>
        </ColumnLayout>
      )}
    </Container>
  );
}
