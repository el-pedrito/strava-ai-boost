import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  RefreshCw,
  ArrowUp,
  ArrowDown,
  Footprints,
  Bike,
  Waves,
  Mountain,
  Dumbbell,
  Flower2,
  Activity as ActivityIcon,
  Brain,
  CheckCircle2,
  Clock,
  type LucideIcon,
} from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import * as Tooltip from '@radix-ui/react-tooltip';
import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { api } from '@/api/client';
import { formatDateTime, computeProcessingTime } from '@/utils/formatDate';
import { Alert, Badge, Button, Card, EmptyState, KPI } from '@/ui';
import { InfoTooltip } from '@/ui/InfoTooltip';
import { cn } from '@/lib/cn';
import { staggerContainer, staggerItem } from '@/lib/motion';
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
      created_at_raw: act.created_at,
    }));
}

type QualitySortKey = 'name' | 'date' | 'confidence' | 'similarity';
type QualitySortDir = 'asc' | 'desc';

function SortIcon({ active, dir }: { active: boolean; dir: QualitySortDir }) {
  if (!active) return null;
  return dir === 'asc' ? (
    <ArrowUp className="h-3 w-3" aria-hidden="true" />
  ) : (
    <ArrowDown className="h-3 w-3" aria-hidden="true" />
  );
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

type TFn = (key: string, options?: Record<string, unknown>) => string;

function editStatus(
  modified: boolean | null | undefined,
  analyzed: boolean | undefined,
  t: TFn
): EditStatus {
  if (!analyzed) return { text: t('quality.editStatus.pending'), variant: 'default' };
  if (modified === true) return { text: t('quality.editStatus.edited'), variant: 'warning' };
  return { text: t('quality.editStatus.kept'), variant: 'success' };
}

type MemoryStatus = {
  text: string;
  variant: 'default' | 'success' | 'info';
  Icon: LucideIcon;
};

function memoryStatus(
  modified: boolean | null | undefined,
  analyzed: boolean | undefined,
  t: TFn
): MemoryStatus {
  if (!analyzed) {
    return { text: t('quality.memory.pending'), variant: 'default', Icon: Clock };
  }
  if (modified === true) {
    return { text: t('quality.memory.updated'), variant: 'success', Icon: Brain };
  }
  return { text: t('quality.memory.validated'), variant: 'info', Icon: CheckCircle2 };
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

function DesktopRow({ item, t }: ActivityRowProps & { t: TFn }) {
  const Icon = getActivityLucideIcon(item.activity_type);
  const status = editStatus(item.description_modified, item.feedback_analyzed, t);
  const memory = memoryStatus(item.description_modified, item.feedback_analyzed, t);
  const hasConfidence = item.confidence !== undefined && item.confidence > 0;
  const hasSimilarity = item.similarity_score !== undefined && item.similarity_score > 0;
  const MemoryIcon = memory.Icon;

  return (
    <tr className="hover:bg-muted transition-colors">
      <td className="py-3 px-4">
        <div className="flex items-center gap-2.5 max-w-[280px]">
          {/* eslint-disable-next-line react-hooks/static-components -- Icon references a module-level Lucide component returned by getActivityLucideIcon(); it is not created during render. */}
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
      <td className="py-3 px-4">
        <Tooltip.Provider delayDuration={150}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>
              <span
                className={cn(
                  'inline-flex h-7 w-7 items-center justify-center rounded-full border',
                  memory.variant === 'success' && 'border-success/30 bg-success/10 text-success',
                  memory.variant === 'info' && 'border-info/30 bg-info/10 text-info',
                  memory.variant === 'default' && 'border-border bg-muted text-muted-foreground',
                )}
                aria-label={memory.text}
              >
                <MemoryIcon className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                side="top"
                align="center"
                sideOffset={6}
                className="z-50 rounded-md border border-border bg-surface-elevated px-2.5 py-1.5 text-xs text-foreground shadow-lg"
              >
                {memory.text}
                <Tooltip.Arrow className="fill-surface-elevated" />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        </Tooltip.Provider>
      </td>
      <td className="py-3 px-4 font-numeric text-xs tabular-nums text-muted-foreground">
        {item.processing_time}
      </td>
    </tr>
  );
}

function MobileCard({ item, t }: ActivityRowProps & { t: TFn }) {
  const Icon = getActivityLucideIcon(item.activity_type);
  const status = editStatus(item.description_modified, item.feedback_analyzed, t);
  const memory = memoryStatus(item.description_modified, item.feedback_analyzed, t);
  const hasConfidence = item.confidence !== undefined && item.confidence > 0;
  const hasSimilarity = item.similarity_score !== undefined && item.similarity_score > 0;
  const MemoryIcon = memory.Icon;

  return (
    <Card padding="sm" className="hover:bg-muted transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          {/* eslint-disable-next-line react-hooks/static-components -- Icon references a module-level Lucide component returned by getActivityLucideIcon(); it is not created during render. */}
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
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          {hasConfidence ? (
            <ConfidenceBar value={item.confidence as number} />
          ) : (
            <span className="text-xs text-muted-foreground">{t('quality.mobile.noConfidence')}</span>
          )}
        </div>
        <div className="text-xs text-muted-foreground whitespace-nowrap">
          {t('quality.mobile.simLabel')}{' '}
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
      <div className="flex items-center justify-between gap-2 pt-2 border-t border-border">
        <span className="text-xs text-muted-foreground">{t('quality.mobile.memoryLabel')}</span>
        <Badge variant={memory.variant} size="sm">
          <MemoryIcon className="h-3 w-3" aria-hidden="true" />
          {memory.text}
        </Badge>
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
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();
  const containerVariants = reduceMotion ? undefined : staggerContainer;
  const itemVariants = reduceMotion ? undefined : staggerItem;
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<QualitySortKey | null>('date');
  const [sortDir, setSortDir] = useState<QualitySortDir>('desc');

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      const res = await api
        .get<{ activities: RawActivity[] }>('/dashboard/activities?limit=100')
        .catch(() => null);

      if (res?.activities) {
        setActivities(transformActivities(res.activities));
      } else {
        setError(t('quality.error.load'));
      }
    } catch {
      setError(t('quality.error.load'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useAutoRefresh(fetchAll, 60000);

  const stats = useMemo(() => computeQualityStats(activities), [activities]);

  const sortedActivities = useMemo(() => {
    if (!sortKey) return activities;
    const arr = [...activities];
    arr.sort((a, b) => {
      let av: number | string = 0;
      let bv: number | string = 0;
      if (sortKey === 'name') {
        av = a.name.toLowerCase();
        bv = b.name.toLowerCase();
      } else if (sortKey === 'date') {
        av = a.created_at_raw ? new Date(a.created_at_raw).getTime() : 0;
        bv = b.created_at_raw ? new Date(b.created_at_raw).getTime() : 0;
      } else if (sortKey === 'confidence') {
        av = a.confidence ?? -1;
        bv = b.confidence ?? -1;
      } else if (sortKey === 'similarity') {
        av = a.similarity_score ?? -1;
        bv = b.similarity_score ?? -1;
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return arr;
  }, [activities, sortKey, sortDir]);

  const handleSort = (key: QualitySortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

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
            {t('quality.title')}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            {t('quality.description')}
          </p>
        </div>
        <Button
          variant="outline"
          size="md"
          onClick={fetchAll}
          className="self-start sm:self-auto"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('quality.refresh')}
        </Button>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchAll}>
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {/* KPIs */}
      <motion.div
        className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('quality.kpi.avgConfidence')}
            value={avgConfidenceValue}
            loading={loading}
            info="metrics.confidence"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('quality.kpi.editRate')}
            value={editRateValue}
            loading={loading}
            info="metrics.editrate"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('quality.kpi.avgSimilarity')}
            value={avgSimilarityValue}
            loading={loading}
            info="metrics.similarity"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('quality.kpi.feedbackAnalyzed')}
            value={feedbackValue}
            loading={loading}
            info="metrics.feedbackAnalyzed"
          />
        </motion.div>
      </motion.div>

      {/* Activities section */}
      <div className="flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {t('quality.details.title')}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t('quality.details.subtitle')}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchAll}
            aria-label={t('quality.refreshActivitiesAria')}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {loading && activities.length === 0 ? (
          <Card padding="none">
            <SkeletonRows />
          </Card>
        ) : activities.length === 0 ? (
          <EmptyState
            illustration="activity"
            title={t('quality.empty.title')}
            description={t('quality.empty.description')}
          />
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block rounded-xl border border-border bg-surface overflow-hidden">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border bg-surface-muted">
                  <tr>
                    <th
                      className="text-left py-3 px-4 font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSort('name')}
                    >
                      <span className="inline-flex items-center gap-1">
                        {t('quality.col.activity')}
                        <SortIcon active={sortKey === 'name'} dir={sortDir} />
                      </span>
                    </th>
                    <th
                      className="text-left py-3 px-4 font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSort('date')}
                    >
                      <span className="inline-flex items-center gap-1">
                        {t('quality.col.date')}
                        <SortIcon active={sortKey === 'date'} dir={sortDir} />
                      </span>
                    </th>
                    <th
                      className="text-left py-3 px-4 font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSort('confidence')}
                    >
                      <span className="inline-flex items-center gap-1">
                        {t('quality.col.confidence')}
                        <SortIcon active={sortKey === 'confidence'} dir={sortDir} />
                      </span>
                    </th>
                    <th className="text-left py-3 px-4 font-medium">{t('quality.col.userEdit')}</th>
                    <th
                      className="text-left py-3 px-4 font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                      onClick={() => handleSort('similarity')}
                    >
                      <span className="inline-flex items-center gap-1">
                        {t('quality.col.similarity')}
                        <SortIcon active={sortKey === 'similarity'} dir={sortDir} />
                      </span>
                    </th>
                    <th className="text-left py-3 px-4 font-medium">
                      <span className="inline-flex items-center gap-1">
                        {t('quality.col.memory')}
                        <InfoTooltip i18nKey="metrics.memoryLearning" />
                      </span>
                    </th>
                    <th className="text-left py-3 px-4 font-medium">{t('quality.col.time')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {sortedActivities.map((item, idx) => (
                    <DesktopRow key={`${item.name}-${idx}`} item={item} t={t} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-3">
              {sortedActivities.map((item, idx) => (
                <MobileCard key={`${item.name}-${idx}`} item={item} t={t} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
