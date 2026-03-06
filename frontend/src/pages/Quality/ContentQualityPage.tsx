import { useState, useEffect, useCallback, useMemo } from 'react';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Container from '@cloudscape-design/components/container';
import Table from '@cloudscape-design/components/table';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Box from '@cloudscape-design/components/box';
import Button from '@cloudscape-design/components/button';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Alert from '@cloudscape-design/components/alert';
import ProgressBar from '@cloudscape-design/components/progress-bar';
import { useAutoRefresh } from '../../hooks/useAutoRefresh.ts';
import { api } from '../../api/client.ts';
import { formatDateTime, computeProcessingTime } from '../../utils/formatDate.ts';
import { getActivityIcon } from '../../utils/statusMapper.ts';
import type { Activity, QualityStats } from '../../types/index.ts';

interface RawActivity {
  enhanced_title?: string;
  original_name?: string;
  created_at?: string;
  updated_at?: string;
  processing_status?: string;
  modules_used?: string[];
  activity_type?: string;
  confidence?: number;
  description_modified?: boolean | null;
  similarity_score?: number;
  feedback_analyzed?: boolean;
  generated_at?: string;
}

function transformActivities(raw: RawActivity[]): Activity[] {
  return raw
    .filter((a) => a.processing_status === 'completed')
    .map((act) => ({
      name: act.enhanced_title || act.original_name || 'Unknown',
      date: act.created_at ? formatDateTime(act.created_at) : 'N/A',
      processing_time: computeProcessingTime(act.created_at, act.updated_at),
      status: 'completed' as const,
      modules_used: act.modules_used || [],
      activity_type: act.activity_type,
      confidence: act.confidence,
      description_modified: act.description_modified,
      similarity_score: act.similarity_score,
      feedback_analyzed: act.feedback_analyzed,
      generated_at: act.generated_at,
    }));
}

function computeQualityStats(activities: Activity[]): QualityStats {
  const withConfidence = activities.filter((a) => a.confidence && a.confidence > 0);
  const withFeedback = activities.filter((a) => a.feedback_analyzed);
  const modified = withFeedback.filter((a) => a.description_modified === true);
  const withSimilarity = withFeedback.filter(
    (a) => a.similarity_score !== undefined && a.similarity_score > 0
  );

  return {
    avg_confidence:
      withConfidence.length > 0
        ? withConfidence.reduce((sum, a) => sum + (a.confidence || 0), 0) / withConfidence.length
        : 0,
    edit_rate: withFeedback.length > 0 ? modified.length / withFeedback.length : 0,
    avg_similarity:
      withSimilarity.length > 0
        ? withSimilarity.reduce((sum, a) => sum + (a.similarity_score || 0), 0) /
          withSimilarity.length
        : 0,
    total_analyzed: activities.length,
    total_feedback: withFeedback.length,
  };
}

function confidenceColor(value: number): string {
  if (value >= 0.85) return '#4CAF50';
  if (value >= 0.7) return '#8BC34A';
  if (value >= 0.5) return '#FFC107';
  return '#F44336';
}

function editStatusLabel(
  modified: boolean | null | undefined,
  analyzed: boolean | undefined
): { text: string; type: 'success' | 'warning' | 'info' | 'stopped' } {
  if (!analyzed) return { text: 'Pending', type: 'info' };
  if (modified === true) return { text: 'Edited', type: 'warning' };
  return { text: 'Kept as-is', type: 'success' };
}

export function ContentQualityPage() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      const res = await api
        .get<{ activities: RawActivity[] }>('/dashboard/activities?limit=100')
        .catch(() => null);

      if (res?.activities) {
        setActivities(transformActivities(res.activities));
      } else {
        setError('Failed to load quality data');
      }
    } catch {
      setError('Failed to load quality data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useAutoRefresh(fetchAll, 60000);

  const stats = useMemo(() => computeQualityStats(activities), [activities]);

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Track content generation quality and user edit patterns">
          Content Quality
        </Header>
      }
    >
      <SpaceBetween size="l">
        {error && (
          <Alert type="error" action={<Button onClick={fetchAll}>Retry</Button>}>
            {error}
          </Alert>
        )}

        <ColumnLayout columns={4}>
          <div className="metric-card metric-card-green" role="status">
            <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
              {loading ? '...' : stats.avg_confidence > 0 ? `${(stats.avg_confidence * 100).toFixed(0)}%` : 'N/A'}
            </Box>
            <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
              Avg Confidence
            </Box>
          </div>

          <div className="metric-card metric-card-orange" role="status">
            <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
              {loading
                ? '...'
                : stats.total_feedback > 0
                  ? `${(stats.edit_rate * 100).toFixed(0)}%`
                  : 'N/A'}
            </Box>
            <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
              Edit Rate
            </Box>
          </div>

          <div className="metric-card metric-card-blue" role="status">
            <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
              {loading
                ? '...'
                : stats.avg_similarity > 0
                  ? `${(stats.avg_similarity * 100).toFixed(0)}%`
                  : 'N/A'}
            </Box>
            <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
              Avg Similarity
            </Box>
          </div>

          <div className="metric-card metric-card-purple" role="status">
            <Box fontSize="display-l" fontWeight="heavy" textAlign="center">
              {loading ? '...' : `${stats.total_feedback}/${stats.total_analyzed}`}
            </Box>
            <Box color="text-body-secondary" textAlign="center" fontSize="body-s" fontWeight="bold">
              Feedback Analyzed
            </Box>
          </div>
        </ColumnLayout>

        <Container
          header={
            <Header
              variant="h2"
              description="Lower edit rate = better content quality"
              actions={<Button iconName="refresh" onClick={fetchAll} />}
            >
              Activity Quality Details
            </Header>
          }
        >
          <Table
            loading={loading}
            loadingText="Loading quality data..."
            items={activities}
            sortingDisabled={false}
            empty={
              <Box textAlign="center" color="inherit" padding="l">
                <Box variant="p" color="inherit">
                  No completed activities found
                </Box>
              </Box>
            }
            columnDefinitions={[
              {
                id: 'name',
                header: 'Activity',
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
                id: 'confidence',
                header: 'Confidence',
                cell: (item) =>
                  item.confidence && item.confidence > 0 ? (
                    <ProgressBar
                      value={item.confidence * 100}
                      additionalInfo={`${(item.confidence * 100).toFixed(0)}%`}
                      variant="standalone"
                      status={item.confidence >= 0.7 ? undefined : 'error'}
                    />
                  ) : (
                    <Box color="text-body-secondary">-</Box>
                  ),
                sortingField: 'confidence',
              },
              {
                id: 'edit_status',
                header: 'User Edit',
                cell: (item) => {
                  const { text, type } = editStatusLabel(
                    item.description_modified,
                    item.feedback_analyzed
                  );
                  return <StatusIndicator type={type}>{text}</StatusIndicator>;
                },
              },
              {
                id: 'similarity',
                header: 'Similarity',
                cell: (item) =>
                  item.similarity_score && item.similarity_score > 0 ? (
                    <span
                      style={{
                        color: confidenceColor(item.similarity_score),
                        fontWeight: 'bold',
                      }}
                    >
                      {(item.similarity_score * 100).toFixed(0)}%
                    </span>
                  ) : (
                    <Box color="text-body-secondary">-</Box>
                  ),
                sortingField: 'similarity_score',
              },
              {
                id: 'processing_time',
                header: 'Processing',
                cell: (item) => item.processing_time,
              },
            ]}
          />
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
