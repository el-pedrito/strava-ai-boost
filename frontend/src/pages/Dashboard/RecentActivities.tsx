import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import type { Activity } from '../../types/index.ts';

interface Props {
  activities: Activity[];
  loading: boolean;
  onRefresh: () => void;
}

function statusType(s: string): 'success' | 'in-progress' | 'error' | 'info' {
  if (s === 'completed') return 'success';
  if (s === 'processing') return 'in-progress';
  if (s === 'error') return 'error';
  return 'info';
}

export function RecentActivities({ activities, loading, onRefresh }: Props) {
  return (
    <Container
      header={
        <Header variant="h2" actions={<Button iconName="refresh" onClick={onRefresh} />}>
          Recent Activities
        </Header>
      }
    >
      <Table
        loading={loading}
        loadingText="Loading activities..."
        items={activities}
        empty={
          <Box textAlign="center" color="inherit" padding="l">
            <Box variant="p" color="inherit">No recent activities found</Box>
            <Box variant="p" color="text-body-secondary">
              Activities will appear here after they are processed.
            </Box>
          </Box>
        }
        columnDefinitions={[
          {
            id: 'name',
            header: 'Name',
            cell: (item) => item.name,
            sortingField: 'name',
          },
          {
            id: 'date',
            header: 'Date',
            cell: (item) => item.date,
            sortingField: 'date',
          },
          {
            id: 'processing_time',
            header: 'Processing Time',
            cell: (item) => item.processing_time,
          },
          {
            id: 'modules',
            header: 'Modules',
            cell: (item) =>
              item.modules_used?.length ? item.modules_used.join(', ') : '-',
          },
          {
            id: 'status',
            header: 'Status',
            cell: (item) => (
              <StatusIndicator type={statusType(item.status)}>
                {item.status.charAt(0).toUpperCase() + item.status.slice(1)}
              </StatusIndicator>
            ),
          },
        ]}
      />
    </Container>
  );
}
