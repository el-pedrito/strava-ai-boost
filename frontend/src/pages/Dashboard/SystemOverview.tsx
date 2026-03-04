import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Box from '@cloudscape-design/components/box';
import type { DashboardStats } from '../../types/index.ts';

interface Props {
  stats: DashboardStats | null;
  loading: boolean;
}

export function SystemOverview({ stats, loading }: Props) {
  return (
    <Container header={<Header variant="h2">System Overview</Header>}>
      <ColumnLayout columns={2} variant="text-grid">
        <div>
          <Box variant="awsui-key-label">Total Activities</Box>
          <Box variant="awsui-value-large">
            {loading ? '...' : (stats?.total_activities ?? 0)}
          </Box>
        </div>
        <div>
          <Box variant="awsui-key-label">Success Rate (24h)</Box>
          <Box variant="awsui-value-large">
            {loading
              ? '...'
              : stats && stats.recent_activities_24h > 0
                ? `${stats.success_rate_24h.toFixed(1)}%`
                : 'N/A'}
          </Box>
        </div>
      </ColumnLayout>
    </Container>
  );
}
