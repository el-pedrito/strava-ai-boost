import { useState, useEffect, useCallback, type ComponentType } from 'react';
import {
  Activity as ActivityIcon,
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
import { Alert, Badge, Button, Card, KPI } from '../../ui';
import { useAutoRefresh } from '../../hooks/useAutoRefresh.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import { formatDateTime, computeProcessingTime } from '../../utils/formatDate.ts';
import { cn } from '../../lib/cn.ts';
import type { DashboardStats, SystemStatus, Activity } from '../../types/index.ts';

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
  return raw.slice(0, 10).map((act) => ({
    name: act.enhanced_title || act.original_name || 'Unknown',
    date: act.created_at ? formatDateTime(act.created_at) : 'N/A',
    processing_time: computeProcessingTime(act.created_at, act.updated_at),
    status: (act.processing_status as Activity['status']) || 'unknown',
    modules_used: act.modules_used || [],
    activity_type: act.activity_type,
    confidence: act.confidence,
    description_modified: act.description_modified,
    similarity_score: act.similarity_score,
    feedback_analyzed: act.feedback_analyzed,
    generated_at: act.generated_at,
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

function statusBadge(status: string): { label: string; variant: BadgeVariant } {
  const lower = status.toLowerCase();
  if (lower === 'completed') return { label: 'Completed', variant: 'success' };
  if (lower === 'failed' || lower === 'error') return { label: 'Failed', variant: 'danger' };
  if (lower === 'processing' || lower === 'pending') return { label: 'Processing', variant: 'info' };
  if (lower === 'paused') return { label: 'Paused', variant: 'warning' };
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
}: {
  enabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="switch"
      aria-checked={enabled}
      aria-label={enabled ? 'Pause enhancement' : 'Resume enhancement'}
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        enabled
          ? 'border-success/30 bg-success/10 text-success hover:bg-success/15'
          : 'border-warning/30 bg-warning/10 text-warning hover:bg-warning/15',
      )}
    >
      <Power className="h-3.5 w-3.5" />
      <span>Enhancement: {enabled ? 'On' : 'Off'}</span>
    </button>
  );
}

export function DashboardPage() {
  const flash = useFlash();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setError('Failed to load dashboard data');
      }

      setStatus((prev) => ({
        strava_connected: prev?.strava_connected ?? false,
        agentcore_status: prev?.agentcore_status ?? 'unknown',
        enhancement_enabled: enhRes?.enhancement_enabled ?? true,
        enhancement_status: (enhRes?.status as 'active' | 'paused') ?? 'active',
      }));
    } catch {
      setError('Failed to load dashboard data');
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
          ? 'Enhancement has been paused. New activities will not be processed.'
          : 'Enhancement has been resumed. New activities will be processed automatically.',
      );
      fetchAll();
    } catch {
      flash('error', 'Failed to toggle enhancement. Please try again.');
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

  return (
    <div className="flex flex-col gap-6 md:gap-8 pb-10">
      {/* Header */}
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your activity processing at a glance.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {status ? (
            <EnhancementToggle
              enabled={status.enhancement_enabled}
              onClick={handleToggleEnhancement}
            />
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={refreshing}
            aria-label="Refresh dashboard"
          >
            <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
            <span>Refresh</span>
          </Button>
        </div>
      </header>

      {/* Error */}
      {error ? (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchAll}>
              Retry
            </Button>
          </div>
        </Alert>
      ) : null}

      {/* Hero KPIs */}
      <section
        aria-label="Last 30 days summary"
        className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 animate-fade-in-up"
      >
        <KPI
          label="Activities (30d)"
          value={loading ? '' : (stats?.total_activities ?? 0)}
          loading={loading}
          icon={<ActivityIcon className="h-4 w-4" />}
        />
        <KPI
          label="Success rate (30d)"
          value={loading ? '' : successRateValue}
          unit={loading ? undefined : successRateUnit}
          loading={loading}
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <KPI
          label="Completed (30d)"
          value={loading ? '' : (stats?.completed_activities ?? 0)}
          loading={loading}
          icon={<ListChecks className="h-4 w-4" />}
        />
        <KPI
          label="Avg processing"
          value={loading ? '' : avgProcessingTime}
          loading={loading}
          icon={<Zap className="h-4 w-4" />}
        />
      </section>

      {/* Connection status */}
      <section aria-label="Connections" className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ConnectionCard
          icon={Link2}
          title="Strava API"
          description="OAuth connection to Strava"
          statusLabel={
            !status ? 'Loading...' : status.strava_connected ? 'Connected' : 'Disconnected'
          }
          statusTone={stravaTone}
        />
        <ConnectionCard
          icon={Cpu}
          title="AgentCore"
          description="AI agents and memory"
          statusLabel={!status ? 'Loading...' : agentcoreLabel(status.agentcore_status)}
          statusTone={agentTone}
        />
        <ConnectionCard
          icon={Power}
          title="Enhancement"
          description="Activity processing pipeline"
          statusLabel={
            !status
              ? 'Loading...'
              : status.enhancement_status === 'active'
                ? 'Active'
                : 'Paused'
          }
          statusTone={enhancementTone}
          action={
            status ? (
              <Button variant="outline" size="sm" onClick={handleToggleEnhancement}>
                {status.enhancement_enabled ? 'Pause' : 'Resume'}
              </Button>
            ) : null
          }
        />
      </section>

      {/* Recent activities */}
      <section aria-label="Recent activities" className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              Recent activities
            </h2>
            <p className="text-xs text-muted-foreground">Latest enhancements processed.</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={fetchAll}
            disabled={refreshing}
            aria-label="Refresh activities"
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
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <ListChecks className="h-6 w-6" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">No recent activities</p>
                <p className="text-xs text-muted-foreground">
                  Activities will appear here after they are processed.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Desktop: table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-surface-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-3 text-left font-medium">Activity</th>
                      <th className="px-4 py-3 text-left font-medium">Date</th>
                      <th className="px-4 py-3 text-left font-medium">Modules</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                      <th className="px-4 py-3 text-right font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activities.map((act, idx) => {
                      const Icon = activityIcon(act.activity_type);
                      const sBadge = statusBadge(act.status);
                      return (
                        <tr
                          key={`${act.name}-${idx}`}
                          className="border-b border-border last:border-b-0 transition-colors hover:bg-surface-muted/40"
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
                {activities.map((act, idx) => {
                  const Icon = activityIcon(act.activity_type);
                  const sBadge = statusBadge(act.status);
                  return (
                    <li
                      key={`${act.name}-${idx}`}
                      className="flex flex-col gap-3 border-b border-border px-4 py-4 last:border-b-0"
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
