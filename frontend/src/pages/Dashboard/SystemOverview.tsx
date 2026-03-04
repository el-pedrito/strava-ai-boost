import ColumnLayout from '@cloudscape-design/components/column-layout';
import Box from '@cloudscape-design/components/box';
import type { DashboardStats } from '../../types/index.ts';

interface Props {
  stats: DashboardStats | null;
  loading: boolean;
  avgProcessingTime?: string;
}

export function SystemOverview({ stats, loading, avgProcessingTime }: Props) {
  return (
    <ColumnLayout columns={4}>
      <div className="metric-card metric-card-blue">
        <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
          {loading ? '...' : (stats?.total_activities ?? 0)}
        </Box>
        <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
          Activities (30d)
        </Box>
      </div>

      <div className="metric-card metric-card-green">
        <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
          {loading
            ? '...'
            : stats && stats.total_activities > 0
              ? `${stats.success_rate.toFixed(0)}%`
              : 'N/A'}
        </Box>
        <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
          Success Rate (30d)
        </Box>
      </div>

      <div className="metric-card metric-card-orange">
        <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
          {loading ? '...' : (stats?.completed_activities ?? 0)}
        </Box>
        <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
          Completed (30d)
        </Box>
      </div>

      <div className="metric-card metric-card-purple">
        <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
          {loading ? '...' : (avgProcessingTime || 'N/A')}
        </Box>
        <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
          Avg Processing
        </Box>
      </div>
    </ColumnLayout>
  );
}
