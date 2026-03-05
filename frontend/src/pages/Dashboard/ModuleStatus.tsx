import { memo } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Link from '@cloudscape-design/components/link';
import { useNavigate } from 'react-router-dom';
import { CampusCoachLogo } from '../../components/icons/CampusCoachLogo.tsx';
import { EndurawLogo } from '../../components/icons/EndurawLogo.tsx';
import type { ModulesMap } from '../../types/index.ts';

interface Props {
  modules: ModulesMap | null;
  loading: boolean;
}

export const ModuleStatus = memo(function ModuleStatus({ modules, loading }: Props) {
  const navigate = useNavigate();

  if (loading || !modules) {
    return (
      <Container header={<Header variant="h2">Modules</Header>}>
        <StatusIndicator type="loading">Loading...</StatusIndicator>
      </Container>
    );
  }

  return (
    <ColumnLayout columns={2}>
      <div className="card-accent card-accent-campus">
        <Container
          header={
            <Header
              variant="h2"
              actions={<Button onClick={() => navigate('/config')}>Configure</Button>}
            >
              <span className="section-header-with-logo">
                <CampusCoachLogo size={22} />
                <Link href="https://app.campus.coach" external variant="secondary" fontSize="heading-m">
                  Campus Coach
                </Link>
              </span>
            </Header>
          }
        >
          <SpaceBetween size="xs">
            <span className={`badge-module ${modules.campus_coach?.enabled ? 'badge-enabled' : 'badge-disabled'}`}>
              {modules.campus_coach?.enabled ? 'Enabled' : 'Disabled'}
            </span>
            <Box color="text-body-secondary" fontSize="body-s">
              Training session matching and performance analysis
            </Box>
            <Box color="text-body-secondary" fontSize="body-s">
              {modules.campus_coach?.last_extraction
                ? `Last extraction: ${modules.campus_coach.last_extraction}`
                : 'No recent extractions'}
            </Box>
          </SpaceBetween>
        </Container>
      </div>

      <div className="card-accent card-accent-enduraw">
        <Container
          header={
            <Header
              variant="h2"
              actions={<Button onClick={() => navigate('/config')}>Configure</Button>}
            >
              <span className="section-header-with-logo">
                <EndurawLogo size={22} />
                <Link href="https://enduraw-report-strava.onrender.com" external variant="secondary" fontSize="heading-m">
                  Enduraw
                </Link>
              </span>
            </Header>
          }
        >
          <SpaceBetween size="xs">
            <span className={`badge-module ${modules.enduraw?.enabled ? 'badge-enabled' : 'badge-disabled'}`}>
              {modules.enduraw?.enabled ? 'Enabled' : 'Disabled'}
            </span>
            <Box color="text-body-secondary" fontSize="body-s">
              Enhanced analytics with weather and wind impact
            </Box>
            <Box color="text-body-secondary" fontSize="body-s">
              Wait time: {modules.enduraw?.wait_time ?? '2-7 minutes'}
            </Box>
          </SpaceBetween>
        </Container>
      </div>
    </ColumnLayout>
  );
});
