import { memo } from 'react';
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

const ACTIVITY_TYPE_ICONS: Record<string, string> = {
  Run: '\u{1F3C3}',
  Ride: '\u{1F6B4}',
  Swim: '\u{1F3CA}',
  Walk: '\u{1F6B6}',
  Hike: '\u26F0\uFE0F',
  WeightTraining: '\u{1F3CB}\uFE0F',
  Workout: '\u{1F4AA}',
  Yoga: '\u{1F9D8}',
  VirtualRide: '\u{1F6B4}',
  VirtualRun: '\u{1F3C3}',
  TrailRun: '\u26F0\uFE0F',
};

function getActivityIcon(type?: string): string {
  if (!type) return '';
  return ACTIVITY_TYPE_ICONS[type] || '';
}

function formatModuleName(name: string): { label: string; className: string } {
  if (name === 'campus_coach' || name.toLowerCase().includes('campus')) {
    return { label: 'Campus Coach', className: 'badge-campus' };
  }
  if (name === 'enduraw' || name.toLowerCase().includes('enduraw')) {
    return { label: 'Enduraw', className: 'badge-enduraw' };
  }
  return { label: name, className: '' };
}

export const RecentActivities = memo(function RecentActivities({ activities, loading, onRefresh }: Props) {
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
            cell: (item) => (
              <span>
                {getActivityIcon(item.activity_type)}
                {item.activity_type ? ' ' : ''}
                {item.name}
              </span>
            ),
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
              item.modules_used?.length ? (
                <span style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {item.modules_used.map((m) => {
                    const { label, className } = formatModuleName(m);
                    return (
                      <span key={m} className={`badge-module ${className}`}>
                        {label}
                      </span>
                    );
                  })}
                </span>
              ) : (
                '-'
              ),
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
});
