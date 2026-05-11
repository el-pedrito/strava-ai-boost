import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  RefreshCw,
  Footprints,
  Bike,
  Waves,
  Mountain,
  Dumbbell,
  Flower2,
  Activity as ActivityIcon,
  FileSearch,
  type LucideIcon,
} from 'lucide-react';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { api } from '@/api/client';
import { formatDateTime, computeProcessingTime } from '@/utils/formatDate';
import { Alert, Badge, Button, Card, KPI } from '@/ui';
import type { Activity, QualityStats } from '@/types/index';

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
        ? withConfidence.reduce((sum, a) => sum + (a.confidence || 0), 0) /
          withConfidence.length
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

const ACTIVITY_ICONS: Record<string, LucideIcon> = {
  Run: Footprints,
  VirtualRun: Footprints,
  TrailRun: Footprints,
  Ride: Bike,
  VirtualRide: Bike,
  Swim: Waves,
  Hike: Mountain,
  Walk: Mountain,
  WeightTraining: Dumbbell,
  Workout: Dumbbell,
  Yoga: Flower2,
};

function getActivityLucideIcon(type?: string): LucideIcon {
  if (!type) return ActivityIcon;
  return ACTIVITY_ICONS[type] || ActivityIcon;
}

function confColor(value: number): string {
  if (value >= 0.85) return '#00c896';
  if (value >= 0.7) return '#84cc16';
  if (value >= 0.5) return '#f59e0b';
  return '#ef4444';
}

type EditStatus = {
  text: string;
  variant: 'default' | 'success' | 'warning';
};

function editStatus(
  modified: boolean | null | undefined,
  analyzed: boolean | undefined
): EditStatus {
  if (!analyzed) return { text: 'Pending', variant: 'default' };
  if (modified === true) return { text: 'Edited', variant: 'warning' };
  return { text: 'Kept as-is', variant: 'success' };
}

interface ConfidenceBarProps {
  value: number;
}

function ConfidenceBar({ value }: ConfidenceBarProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 max-w-[120px] h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full transition-all"
          style={{ width: `${value * 100}%`, background: confColor(value) }}
        />
      </div>
      <span className="font-numeric text-xs tabular-nums w-10 text-right text-foreground">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

interface ActivityRowProps {
  item: Activity;
}

function DesktopRow({ item }: ActivityRowProps) {
  const Icon = getActivityLucideIcon(item.activity_type);
  const status = editStatus(item.description_modified, item.feedback_analyzed);
  const hasConfidence = item.confidence !== undefined && item.confidence > 0;
  const hasSimilarity = item.similarity_score !== undefined && item.similarity_score > 0;

  return (
    <tr className="hover:bg-muted transition-colors">
      <td className="py-3 px-4">
        <div className="flex items-center gap-2.5 max-w-[280px]">
          <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="text-foreground font-medium truncate">{item.name}</span>
        </div>
      </td>
      <td className="py-3 px-4 text-muted-foreground font-numeric tabular-nums text-xs">
        {item.date}
      </td>
      <td className="py-3 px-4">
        {hasConfidence ? (
          <ConfidenceBar value={item.confidence as number} />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-3 px-4">
        <Badge variant={status.variant} size="sm">
          {status.text}
        </Badge>
      </td>
      <td className="py-3 px-4">
        {hasSimilarity ? (
          <span
            className="font-numeric font-semibold tabular-nums"
            style={{ color: confColor(item.similarity_score as number) }}
          >
            {((item.similarity_score as number) * 100).toFixed(0)}%
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-3 px-4 font-numeric text-xs tabular-nums text-muted-foreground">
        {item.processing_time}
      </td>
    </tr>
  );
}

function MobileCard({ item }: ActivityRowProps) {
  const Icon = getActivityLucideIcon(item.activity_type);
  const status = editStatus(item.description_modified, item.feedback_analyzed);
  const hasConfidence = item.confidence !== undefined && item.confidence > 0;
  const hasSimilarity = item.similarity_score !== undefined && item.similarity_score > 0;

  return (
    <Card padding="sm" className="hover:bg-muted transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="text-foreground font-medium truncate">{item.name}</span>
        </div>
        <Badge variant={status.variant} size="sm">
          {status.text}
        </Badge>
      </div>
      <div className="text-xs text-muted-foreground font-numeric tabular-nums mb-3">
        {item.date} <span className="opacity-50">·</span> {item.processing_time}
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          {hasConfidence ? (
            <ConfidenceBar value={item.confidence as number} />
          ) : (
            <span className="text-xs text-muted-foreground">No confidence</span>
          )}
        </div>
        <div className="text-xs text-muted-foreground whitespace-nowrap">
          Sim:{' '}
          {hasSimilarity ? (
            <span
              className="font-numeric font-semibold tabular-nums"
              style={{ color: confColor(item.similarity_score as number) }}
            >
              {((item.similarity_score as number) * 100).toFixed(0)}%
            </span>
          ) : (
            <span>—</span>
          )}
        </div>
      </div>
    </Card>
  );
}

function SkeletonRows() {
  return (
    <div className="flex flex-col gap-2 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="bg-muted animate-pulse h-12 rounded-md" />
      ))}
    </div>
  );
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

  const avgConfidenceValue =
    !loading && stats.avg_confidence > 0
      ? `${(stats.avg_confidence * 100).toFixed(0)}%`
      : 'N/A';
  const editRateValue =
    !loading && stats.total_feedback > 0
      ? `${(stats.edit_rate * 100).toFixed(0)}%`
      : 'N/A';
  const avgSimilarityValue =
    !loading && stats.avg_similarity > 0
      ? `${(stats.avg_similarity * 100).toFixed(0)}%`
      : 'N/A';
  const feedbackValue = `${stats.total_feedback}/${stats.total_analyzed}`;

  return (
    <div className="flex flex-col gap-6 md:gap-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Content quality
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            How good are AI-generated descriptions, and how often do you edit them?
          </p>
        </div>
        <Button
          variant="outline"
          size="md"
          onClick={fetchAll}
          className="self-start sm:self-auto"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchAll}>
              Retry
            </Button>
          </div>
        </Alert>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <KPI label="Avg confidence" value={avgConfidenceValue} loading={loading} />
        <KPI
          label="Edit rate (lower is better)"
          value={editRateValue}
          loading={loading}
        />
        <KPI label="Avg similarity" value={avgSimilarityValue} loading={loading} />
        <KPI label="Feedback analyzed" value={feedbackValue} loading={loading} />
      </div>

      {/* Activities section */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              Activity quality details
            </h2>
            <p className="text-xs text-muted-foreground">
              Lower edit rate = better content.
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchAll}
            aria-label="Refresh activities"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {loading && activities.length === 0 ? (
          <Card padding="none">
            <SkeletonRows />
          </Card>
        ) : activities.length === 0 ? (
          <Card padding="lg" className="flex flex-col items-center text-center gap-2">
            <FileSearch
              className="h-10 w-10 text-muted-foreground"
              aria-hidden="true"
            />
            <h3 className="text-base font-semibold text-foreground">
              No completed activities yet
            </h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Process some Strava activities first to see quality metrics here.
            </p>
          </Card>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block rounded-xl border border-border bg-surface overflow-hidden">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border bg-surface-muted">
                  <tr>
                    <th className="text-left py-3 px-4 font-medium">Activity</th>
                    <th className="text-left py-3 px-4 font-medium">Date</th>
                    <th className="text-left py-3 px-4 font-medium">Confidence</th>
                    <th className="text-left py-3 px-4 font-medium">User edit</th>
                    <th className="text-left py-3 px-4 font-medium">Similarity</th>
                    <th className="text-left py-3 px-4 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {activities.map((item, idx) => (
                    <DesktopRow key={`${item.name}-${idx}`} item={item} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-3">
              {activities.map((item, idx) => (
                <MobileCard key={`${item.name}-${idx}`} item={item} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
