import { useState, useEffect, useCallback, useMemo, type ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import {
  Activity as ActivityIcon,
  ArrowDown,
  ArrowUp,
  Bike,
  Cpu,
  Dumbbell,
  Flower2,
  Footprints,
  Link2,
  ListChecks,
  Mountain,
  Power,
  RefreshCw,
  TrendingUp,
  Waves,
  Zap,
} from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { Alert, Badge, Button, Card, EmptyState, KPI } from '../../ui';
import { OnboardingHint } from '../../components/OnboardingHint.tsx';
import { staggerContainer, staggerItem } from '../../lib/motion.ts';
import { useAutoRefresh } from '../../hooks/useAutoRefresh.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import { formatDateTime, computeProcessingTime } from '../../utils/formatDate.ts';
import { cn } from '../../lib/cn.ts';
import type { DashboardStats, SystemStatus, Activity } from '../../types/index.ts';

interface RawActivity {
  activity_id?: string;
  enhanced_title?: string;
  enhanced_description?: string;
  original_name?: string;
  start_date?: string;
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
  distance?: number;
  moving_time?: number;
  elapsed_time?: number;
  total_elevation_gain?: number;
  average_heartrate?: number;
  max_heartrate?: number;
  average_speed?: number;
  max_speed?: number;
  kudos_count?: number;
  comment_count?: number;
}

function processingSeconds(createdAt?: string, updatedAt?: string): number | undefined {
  if (!createdAt || !updatedAt) return undefined;
  const start = new Date(createdAt).getTime();
  const end = new Date(updatedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return undefined;
  return Math.max(0, Math.round((end - start) / 1000));
}

function transformActivities(raw: RawActivity[]): Activity[] {
  return raw.slice(0, 10).map((act) => ({
    name: act.enhanced_title || act.original_name || 'Unknown',
    date: act.start_date ? formatDateTime(act.start_date) : act.created_at ? formatDateTime(act.created_at) : 'N/A',
    processing_time: computeProcessingTime(act.created_at, act.updated_at),
    status: (act.processing_status as Activity['status']) || 'unknown',
    modules_used: act.modules_used || [],
    activity_type: act.activity_type,
    confidence: act.confidence,
    description_modified: act.description_modified,
    similarity_score: act.similarity_score,
    feedback_analyzed: act.feedback_analyzed,
    generated_at: act.generated_at,
    created_at_raw: act.created_at,
    start_date_raw: act.start_date,
    processing_time_seconds: processingSeconds(act.created_at, act.updated_at),
    activity_id: act.activity_id,
    enhanced_title: act.enhanced_title,
    enhanced_description: act.enhanced_description,
    original_name: act.original_name,
    distance: act.distance,
    moving_time: act.moving_time,
    elapsed_time: act.elapsed_time,
    total_elevation_gain: act.total_elevation_gain,
    average_heartrate: act.average_heartrate,
    max_heartrate: act.max_heartrate,
    average_speed: act.average_speed,
    max_speed: act.max_speed,
    kudos_count: act.kudos_count,
    comment_count: act.comment_count,
  }));
}

function computeAvgProcessingTime(activities: Activity[]): string {
  const times = activities
    .map((a) => parseInt(a.processing_time, 10))
    .filter((t) => !isNaN(t));
  if (times.length === 0) return 'N/A';
  const avg = Math.round(times.reduce((sum, t) => sum + t, 0) / times.length);
  return `${avg}s`;
}

function computeStatsFromActivities(raw: RawActivity[]): DashboardStats {
  const now = new Date();
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

  const recent = raw.filter((a) => {
    if (!a.created_at) return false;
    try {
      return new Date(a.created_at) >= thirtyDaysAgo;
    } catch {
      return false;
    }
  });

  const completed = recent.filter((a) => a.processing_status === 'completed').length;
  const failed = recent.filter((a) => a.processing_status === 'failed').length;
  const total = recent.length;
  const successRate = total > 0 ? (completed / total) * 100 : 0;

  return {
    total_activities: total,
    success_rate: Math.round(successRate * 10) / 10,
    completed_activities: completed,
    failed_activities: failed,
  };
}

type LucideIcon = ComponentType<{ className?: string }>;

function activityIcon(type?: string): LucideIcon {
  switch (type) {
    case 'Run':
    case 'TrailRun':
    case 'VirtualRun':
      return Footprints;
    case 'Ride':
    case 'VirtualRide':
    case 'EBikeRide':
      return Bike;
    case 'Swim':
      return Waves;
    case 'WeightTraining':
    case 'Workout':
    case 'Crossfit':
      return Dumbbell;
    case 'Hike':
    case 'Walk':
      return Mountain;
    case 'Yoga':
      return Flower2;
    default:
      return ActivityIcon;
  }
}

type BadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'outline';

function moduleBadge(name: string): { label: string; variant: BadgeVariant } {
  const lower = name.toLowerCase();
  if (name === 'campus_coach' || lower.includes('campus')) {
    return { label: 'Campus Coach', variant: 'success' };
  }
  if (name === 'enduraw' || lower.includes('enduraw')) {
    return { label: 'Enduraw', variant: 'info' };
  }
  if (name === 'intervals_icu' || lower.includes('intervals')) {
    return { label: 'Intervals.icu', variant: 'primary' };
  }
  return { label: name, variant: 'default' };
}

type TFn = (key: string, options?: Record<string, unknown>) => string;

function statusBadge(status: string, t: TFn): { label: string; variant: BadgeVariant } {
  const lower = status.toLowerCase();
  if (lower === 'completed') return { label: t('dashboard.status.completed'), variant: 'success' };
  if (lower === 'failed' || lower === 'error') return { label: t('dashboard.status.failed'), variant: 'danger' };
  if (lower === 'processing' || lower === 'pending') return { label: t('dashboard.status.processing'), variant: 'info' };
  if (lower === 'paused') return { label: t('dashboard.status.paused'), variant: 'warning' };
  return { label: status.charAt(0).toUpperCase() + status.slice(1), variant: 'default' };
}

function agentcoreLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

type StatusTone = 'success' | 'warning' | 'danger' | 'muted';

function toneClasses(tone: StatusTone): { bg: string; text: string; ring: string } {
  switch (tone) {
    case 'success':
      return { bg: 'bg-success/10', text: 'text-success', ring: 'ring-success/20' };
    case 'warning':
      return { bg: 'bg-warning/10', text: 'text-warning', ring: 'ring-warning/20' };
    case 'danger':
      return { bg: 'bg-danger/10', text: 'text-danger', ring: 'ring-danger/20' };
    default:
      return { bg: 'bg-muted', text: 'text-muted-foreground', ring: 'ring-border' };
  }
}

function StatusDot({ tone }: { tone: StatusTone }) {
  const colorMap: Record<StatusTone, string> = {
    success: 'bg-success',
    warning: 'bg-warning',
    danger: 'bg-danger',
    muted: 'bg-muted-foreground',
  };
  return (
    <span className="relative inline-flex h-2 w-2 flex-shrink-0">
      <span
        className={cn(
          'absolute inline-flex h-full w-full rounded-full opacity-50',
          tone === 'success' && 'animate-ping bg-success',
          tone === 'warning' && 'bg-warning',
          tone === 'danger' && 'bg-danger',
          tone === 'muted' && 'bg-muted-foreground',
        )}
      />
      <span className={cn('relative inline-flex h-2 w-2 rounded-full', colorMap[tone])} />
    </span>
  );
}

function ConnectionCard({
  icon: Icon,
  title,
  statusLabel,
  statusTone,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  statusLabel: string;
  statusTone: StatusTone;
  description: string;
  action?: React.ReactNode;
}) {
  const tone = toneClasses(statusTone);
  return (
    <Card padding="md" className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ring-1',
            tone.bg,
            tone.text,
            tone.ring,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2">
          <StatusDot tone={statusTone} />
          <span className={cn('text-sm font-medium', tone.text)}>{statusLabel}</span>
        </div>
        {action}
      </div>
    </Card>
  );
}

function EnhancementToggle({
  enabled,
  onClick,
  t,
}: {
  enabled: boolean;
  onClick: () => void;
  t: TFn;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="switch"
      aria-checked={enabled}
      aria-label={enabled ? t('dashboard.enhancement.pauseAria') : t('dashboard.enhancement.resumeAria')}
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        enabled
          ? 'border-success/30 bg-success/10 text-success hover:bg-success/15'
          : 'border-warning/30 bg-warning/10 text-warning hover:bg-warning/15',
      )}
    >
      <Power className="h-3.5 w-3.5" />
      <span>{enabled ? t('dashboard.enhancement.on') : t('dashboard.enhancement.off')}</span>
    </button>
  );
}

type SortKey = 'name' | 'date' | 'time';
type SortDir = 'asc' | 'desc';

export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const flash = useFlash();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey | null>('date');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

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
        av = a.start_date_raw ? new Date(a.start_date_raw).getTime() : 0;
        bv = b.start_date_raw ? new Date(b.start_date_raw).getTime() : 0;
      } else if (sortKey === 'time') {
        av = a.processing_time_seconds ?? -1;
        bv = b.processing_time_seconds ?? -1;
      }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return arr;
  }, [activities, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) return null;
    return sortDir === 'asc' ? (
      <ArrowUp className="h-3 w-3" aria-hidden="true" />
    ) : (
      <ArrowDown className="h-3 w-3" aria-hidden="true" />
    );
  };

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      setRefreshing(true);
      const [actRes, enhRes] = await Promise.all([
        api.get<{ activities: RawActivity[] }>('/dashboard/activities?limit=100').catch(() => null),
        api
          .get<{ enhancement_enabled: boolean; status: string }>('/config/enhancement')
          .catch(() => null),
      ]);

      if (actRes?.activities) {
        setStats(computeStatsFromActivities(actRes.activities));
        setActivities(transformActivities(actRes.activities));
      } else if (!stats) {
        setError(t('dashboard.error.load'));
      }

      setStatus((prev) => ({
        strava_connected: prev?.strava_connected ?? false,
        agentcore_status: prev?.agentcore_status ?? 'unknown',
        enhancement_enabled: enhRes?.enhancement_enabled ?? true,
        enhancement_status: (enhRes?.status as 'active' | 'paused') ?? 'active',
      }));
    } catch {
      setError(t('dashboard.error.load'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchConnectionStatus = useCallback(async () => {
    try {
      const [oauthRes, agentRes] = await Promise.all([
        api.get<{ connected: boolean }>('/config/oauth').catch(() => ({ connected: false })),
        api.get<{ overall_status: string }>('/health/agentcore').catch(() => null),
      ]);

      setStatus((prev) => ({
        strava_connected: oauthRes?.connected ?? false,
        agentcore_status:
          (agentRes?.overall_status as SystemStatus['agentcore_status']) ?? 'unknown',
        enhancement_enabled: prev?.enhancement_enabled ?? true,
        enhancement_status: prev?.enhancement_status ?? 'active',
      }));
    } catch {
      // Silently handle
    }
  }, []);

  useEffect(() => {
    fetchAll();
    fetchConnectionStatus();
  }, [fetchAll, fetchConnectionStatus]);

  useAutoRefresh(() => {
    fetchAll();
    fetchConnectionStatus();
  }, 60000);

  const handleToggleEnhancement = async () => {
    const action = status?.enhancement_enabled ? 'pause' : 'resume';
    try {
      await api.post('/config/enhancement', { action });
      flash(
        action === 'pause' ? 'info' : 'success',
        action === 'pause'
          ? t('dashboard.enhancement.pausedFlash')
          : t('dashboard.enhancement.resumedFlash'),
      );
      fetchAll();
    } catch {
      flash('error', t('dashboard.enhancement.toggleError'));
    }
  };

  const avgProcessingTime = computeAvgProcessingTime(activities);
  const successRateValue =
    stats && stats.total_activities > 0 ? `${stats.success_rate.toFixed(0)}` : 'N/A';
  const successRateUnit = stats && stats.total_activities > 0 ? '%' : undefined;

  const stravaTone: StatusTone = status?.strava_connected ? 'success' : 'danger';
  const agentTone: StatusTone =
    status?.agentcore_status === 'healthy'
      ? 'success'
      : status?.agentcore_status === 'not_configured'
        ? 'warning'
        : status?.agentcore_status === 'error'
          ? 'danger'
          : 'muted';
  const enhancementTone: StatusTone = !status
    ? 'muted'
    : status.enhancement_enabled && status.enhancement_status === 'active'
      ? 'success'
      : 'warning';

  const reduceMotion = useReducedMotion();
  const containerVariants = reduceMotion ? undefined : staggerContainer;
  const itemVariants = reduceMotion ? undefined : staggerItem;

  return (
    <div className="flex flex-col gap-6 md:gap-8 pb-10">
      {/* Header */}
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t('dashboard.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('dashboard.description')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status ? (
            <EnhancementToggle
              enabled={status.enhancement_enabled}
              onClick={handleToggleEnhancement}
              t={t}
            />
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={refreshing}
            aria-label={t('dashboard.refreshAria')}
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
            <span>{t('common.refresh')}</span>
          </Button>
        </div>
      </header>

      {/* Onboarding hint (shown only if user hasn't finished setup) */}
      <OnboardingHint oauthConnected={status?.strava_connected} />

      {/* Error */}
      {error ? (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchAll}>
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      ) : null}

      {/* Hero KPIs */}
      <motion.section
        aria-label={t('dashboard.kpi.summaryAria')}
        className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('dashboard.kpi.activities')}
            value={loading ? '' : (stats?.total_activities ?? 0)}
            loading={loading}
            icon={<ActivityIcon className="h-4 w-4" />}
            info="metrics.activities"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('dashboard.kpi.successRate')}
            value={loading ? '' : successRateValue}
            unit={loading ? undefined : successRateUnit}
            loading={loading}
            icon={<TrendingUp className="h-4 w-4" />}
            info="metrics.successRate"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('dashboard.kpi.completed')}
            value={loading ? '' : (stats?.completed_activities ?? 0)}
            loading={loading}
            icon={<ListChecks className="h-4 w-4" />}
            info="metrics.completed"
          />
        </motion.div>
        <motion.div variants={itemVariants} className="h-full">
          <KPI
            label={t('dashboard.kpi.avgProcessing')}
            value={loading ? '' : avgProcessingTime}
            loading={loading}
            icon={<Zap className="h-4 w-4" />}
            info="metrics.avgProcessing"
          />
        </motion.div>
      </motion.section>

      {/* Connection status */}
      <section aria-label={t('dashboard.connections.aria')} className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ConnectionCard
          icon={Link2}
          title={t('dashboard.connections.strava.title')}
          description={t('dashboard.connections.strava.description')}
          statusLabel={
            !status
              ? t('dashboard.connections.loading')
              : status.strava_connected
                ? t('dashboard.connections.strava.connected')
                : t('dashboard.connections.strava.disconnected')
          }
          statusTone={stravaTone}
        />
        <ConnectionCard
          icon={Cpu}
          title={t('dashboard.connections.agentcore.title')}
          description={t('dashboard.connections.agentcore.description')}
          statusLabel={!status ? t('dashboard.connections.loading') : agentcoreLabel(status.agentcore_status)}
          statusTone={agentTone}
        />
        <ConnectionCard
          icon={Power}
          title={t('dashboard.connections.enhancement.title')}
          description={t('dashboard.connections.enhancement.description')}
          statusLabel={
            !status
              ? t('dashboard.connections.loading')
              : status.enhancement_status === 'active'
                ? t('dashboard.connections.enhancement.active')
                : t('dashboard.connections.enhancement.paused')
          }
          statusTone={enhancementTone}
          action={
            status ? (
              <Button variant="outline" size="sm" onClick={handleToggleEnhancement}>
                {status.enhancement_enabled ? t('dashboard.enhancement.pause') : t('dashboard.enhancement.resume')}
              </Button>
            ) : null
          }
        />
      </section>

      {/* Recent activities */}
      <section aria-label={t('dashboard.activities.aria')} className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {t('dashboard.activities.title')}
            </h2>
            <p className="text-xs text-muted-foreground">{t('dashboard.activities.subtitle')}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchAll}
            disabled={refreshing}
            aria-label={t('dashboard.refreshActivitiesAria')}
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
          </Button>
        </div>

        <Card padding="none" className="overflow-hidden">
          {/* Loading skeleton */}
          {loading ? (
            <div className="flex flex-col">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="flex items-center gap-4 border-b border-border px-4 py-4 last:border-b-0"
                >
                  <div className="h-9 w-9 flex-shrink-0 rounded-lg bg-muted animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-1/2 rounded bg-muted animate-pulse" />
                    <div className="h-2 w-1/3 rounded bg-muted animate-pulse" />
                  </div>
                  <div className="h-5 w-16 rounded-full bg-muted animate-pulse" />
                </div>
              ))}
            </div>
          ) : activities.length === 0 ? (
            <div className="px-4 py-6">
              <EmptyState
                illustration="activity"
                title={t('dashboard.activities.empty.title')}
                description={t('dashboard.activities.empty.description')}
                className="border-0 bg-transparent"
              />
            </div>
          ) : (
            <>
              {/* Desktop: table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-surface-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                      <th
                        className="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => handleSort('name')}
                      >
                        <span className="inline-flex items-center gap-1">
                          {t('dashboard.activities.col.activity')}
                          <SortIcon k="name" />
                        </span>
                      </th>
                      <th
                        className="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => handleSort('date')}
                      >
                        <span className="inline-flex items-center gap-1">
                          {t('dashboard.activities.col.date')}
                          <SortIcon k="date" />
                        </span>
                      </th>
                      <th className="px-4 py-3 text-left font-medium">{t('dashboard.activities.col.modules')}</th>
                      <th className="px-4 py-3 text-left font-medium">{t('dashboard.activities.col.status')}</th>
                      <th
                        className="px-4 py-3 text-right font-medium cursor-pointer select-none hover:text-foreground transition-colors"
                        onClick={() => handleSort('time')}
                      >
                        <span className="inline-flex items-center justify-end gap-1">
                          {t('dashboard.activities.col.time')}
                          <SortIcon k="time" />
                        </span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedActivities.map((act, idx) => {
                      const Icon = activityIcon(act.activity_type);
                      const sBadge = statusBadge(act.status, t);
                      const detailKey = act.activity_id ?? act.name;
                      const handleOpen = () =>
                        navigate(`/activities/${encodeURIComponent(detailKey)}`, {
                          state: { activity: act },
                        });
                      return (
                        <tr
                          key={`${act.name}-${idx}`}
                          onClick={handleOpen}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              handleOpen();
                            }
                          }}
                          tabIndex={0}
                          role="button"
                          aria-label={t('dashboard.activities.openAria', { name: act.name })}
                          className="cursor-pointer border-b border-border last:border-b-0 transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                                <Icon className="h-4 w-4" />
                              </div>
                              <span className="truncate font-medium text-foreground">
                                {act.name}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 font-numeric text-xs text-muted-foreground">
                            {act.date}
                          </td>
                          <td className="px-4 py-3">
                            {act.modules_used.length > 0 ? (
                              <div className="flex flex-wrap gap-1.5">
                                {act.modules_used.map((m) => {
                                  const mb = moduleBadge(m);
                                  return (
                                    <Badge key={m} variant={mb.variant} size="sm">
                                      {mb.label}
                                    </Badge>
                                  );
                                })}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant={sBadge.variant} size="sm">
                              {sBadge.label}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right font-numeric text-xs text-muted-foreground">
                            {act.processing_time}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile: cards */}
              <ul className="flex flex-col md:hidden">
                {sortedActivities.map((act, idx) => {
                  const Icon = activityIcon(act.activity_type);
                  const sBadge = statusBadge(act.status, t);
                  const detailKey = act.activity_id ?? act.name;
                  const handleOpen = () =>
                    navigate(`/activities/${encodeURIComponent(detailKey)}`, {
                      state: { activity: act },
                    });
                  return (
                    <li
                      key={`${act.name}-${idx}`}
                      onClick={handleOpen}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleOpen();
                        }
                      }}
                      tabIndex={0}
                      role="button"
                      aria-label={t('dashboard.activities.openAria', { name: act.name })}
                      className="flex cursor-pointer flex-col gap-3 border-b border-border px-4 py-4 transition-colors last:border-b-0 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                    >
                      <div className="flex items-start gap-3">
                        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                          <Icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">
                            {act.name}
                          </p>
                          <p className="mt-0.5 font-numeric text-[11px] text-muted-foreground">
                            {act.date} &middot; {act.processing_time}
                          </p>
                        </div>
                        <Badge variant={sBadge.variant} size="sm">
                          {sBadge.label}
                        </Badge>
                      </div>
                      {act.modules_used.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {act.modules_used.map((m) => {
                            const mb = moduleBadge(m);
                            return (
                              <Badge key={m} variant={mb.variant} size="sm">
                                {mb.label}
                              </Badge>
                            );
                          })}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </Card>
      </section>
    </div>
  );
}
