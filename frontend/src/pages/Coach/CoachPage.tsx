import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  Legend,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowRight,
  Calendar,
  ChevronDown,
  ChevronUp,
  Dumbbell,
  Flame,
  Footprints,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Alert,
  AudioPlayer,
  Badge,
  Card,
  EmptyState,
  InfoTooltip,
  KPI,
  Pagination,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/ui';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import { cn } from '@/lib/cn';
import { staggerContainer, staggerItem } from '@/lib/motion';
import { api } from '../../api/client.ts';
import { CoachChat } from './CoachChat.tsx';
import { ErrorBoundary } from '@/components/ErrorBoundary';

interface CoachFeedbackItem {
  activity_id: string;
  date: string;
  title: string;
  coach_feedback: {
    detailed_analysis?: string;
    strava_block?: string;
    recommendation_next?: string;
  } | null;
}

interface PacePoint {
  date: string;
  pace: string;
  pace_sec: number;
  hr?: number;
}

interface CoachSummary {
  recent_feedback: CoachFeedbackItem[];
  current_week?: {
    runs: number;
    run_km: number;
    other: number;
    total: number;
  };
  trends: {
    weekly_volume_km: number[];
    sessions_per_week: number[];
    run_sessions_per_week?: number[];
    other_sessions_per_week?: number[];
    other_sessions_breakdown?: Record<string, number>;
    avg_pace_per_week: string[];
    interval_paces?: PacePoint[];
    ef_paces?: PacePoint[];
    ramp_rate?: number | null;
    compliance?: { planned: number; completed: number; percentage: number } | null;
    strength_history?: Array<{
      date: string;
      activity_id?: string;
      duration_min?: number | null;
      description: string;
    }>;
    strength_sessions?: StrengthSessionEntry[];
    strength_progression?: StrengthProgressionEntry[];
    strength_insights?: StrengthInsights | null;
    health_anomalies?: Array<{ id: string; severity: 'warning' | 'info'; message: string }>;
    recovery?: {
      form: number | null;
      ctl: number | null;
      atl: number | null;
      resting_hr: number | null;
      hrv: number | null;
      vo2max: number | null;
      vo2max_delta_7d: number | null;
      resting_hr_delta_7d: number | null;
      sleep_hours: number | null;
      sleep_display: string | null;
      sleep_delta_7d_min: number | null;
    } | null;
  };
  athlete_profile: string;
}

const WEEK_LABEL_KEYS = [
  'coach.trends.weekLabels.w4',
  'coach.trends.weekLabels.w3',
  'coach.trends.weekLabels.w2',
  'coach.trends.weekLabels.w1',
] as const;

function paceToSec(pace: string): number {
  const m = pace.match(/^(\d+):(\d{2})$/);
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : 0;
}

function formatPace(secs: number): string {
  if (!Number.isFinite(secs) || secs <= 0) return '-';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** Compact date label for axis ticks: "YYYY-MM-DD" -> "MM-DD" or "DD/MM" by locale. */
function formatShortDate(raw: string, locale: string): string {
  if (!raw) return '';
  const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return raw;
  return locale.startsWith('fr') ? `${m[3]}/${m[2]}` : `${m[2]}-${m[3]}`;
}

function KPISkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="h-28 rounded-xl border border-border bg-surface animate-pulse"
        />
      ))}
    </div>
  );
}

interface FeedbackCardProps {
  item: CoachFeedbackItem;
}

function formatFeedbackDate(raw: string, locale: string): string {
  if (!raw) return '';
  // Try parsing as ISO/Date first
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) {
    try {
      return new Intl.DateTimeFormat(locale, {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
      }).format(parsed);
    } catch {
      return raw;
    }
  }
  return raw;
}

function FeedbackCard({ item }: FeedbackCardProps) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const summary = item.coach_feedback?.strava_block ?? t('coach.feedback.noSummary');
  const detail = item.coach_feedback?.detailed_analysis;
  const recommendation = item.coach_feedback?.recommendation_next;
  const formattedDate = formatFeedbackDate(item.date, i18n.language);

  return (
    <Card variant="default" padding="md">
      <div className="flex flex-col gap-1 mb-2">
        <span className="text-xs text-muted-foreground font-medium">
          {formattedDate}
        </span>
        <span className="text-base font-medium leading-snug break-words">
          {item.title}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
        {summary}
      </p>
      {recommendation ? (
        <div className="mt-3 flex items-start gap-2 rounded-md bg-primary/5 border border-primary/20 px-3 py-2">
          <ArrowRight
            className="h-4 w-4 text-primary mt-0.5 flex-shrink-0"
            aria-hidden="true"
          />
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold text-primary">
              {t('coach.feedback.recommendationNext')}
            </span>
            <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
              {recommendation}
            </p>
          </div>
        </div>
      ) : null}
      {detail ? (
        <div className="mt-3 pt-3 border-t border-border">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            <span>
              {expanded
                ? t('coach.feedback.hideDetail')
                : t('coach.feedback.viewDetail')}
            </span>
          </button>
          {expanded ? (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {detail}
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

function useStaggerVariants() {
  const reduceMotion = useReducedMotion();
  return {
    container: reduceMotion ? undefined : staggerContainer,
    item: reduceMotion ? undefined : staggerItem,
  };
}

interface StrengthSessionEntry {
  date: string;
  activity_id?: string;
  duration_min?: number | null;
  total_sets: number | null;
  total_reps: number | null;
  volume_kg: number | null;
  body_weight_kg_used: number | null;
  volume_incomplete: boolean;
  excluded_exercises: string[];
}

interface StrengthProgressionPoint {
  date: string;
  top_weight_kg: number | null;
  volume_kg: number | null;
  e1rm_kg?: number | null;
}

interface StrengthProgressionEntry {
  exercise: string;
  points: StrengthProgressionPoint[];
  sessions: number;
  e1rm_eligible?: boolean;
  mixed?: boolean;
  notation_mixed?: boolean;
  load_label?: string | null;
}

type MuscleSegment = { logged?: number; campus_plan?: number };

interface StrengthWeek {
  week: string;
  partial?: boolean;
  groups: Record<string, MuscleSegment>;
  explosivite?: MuscleSegment;
  autre?: MuscleSegment;
}

interface PushPullPoint {
  week: string;
  push: number;
  pull: number;
  ratio: number | null;
}

interface StrengthRecord {
  exercise: string;
  kind?: 'loaded' | 'bodyweight';
  last_date: string;
  notation_mixed?: boolean;
  load_label?: string | null;
  top_weight_kg?: number | null;
  top_weight_date?: string | null;
  e1rm_kg?: number | null;
  e1rm_date?: string | null;
  best_volume_kg?: number | null;
  best_volume_date?: string | null;
  best_reps_bw?: { reps: number; date: string } | null;
  best_weighted_bw?: { reps: number; added_weight_kg: number; date: string } | null;
}

interface StrengthInsights {
  counting_rule?: string;
  weeks?: StrengthWeek[];
  push_pull?: PushPullPoint[];
  records?: StrengthRecord[];
  unmapped_exercises?: Array<{ exercise: string; reason: string }>;
  mixed_exercises?: Array<{ exercise: string; note_key: string }>;
}

type ProgressionMetric = 'weight' | 'volume' | 'e1rm';

const METRICS: Record<
  ProgressionMetric,
  { field: 'top_weight_kg' | 'volume_kg' | 'e1rm_kg'; labelKey: string; unitKey: string; hintKey: string }
> = {
  weight: {
    field: 'top_weight_kg',
    labelKey: 'coach.strength.metric.weight',
    unitKey: 'coach.strength.unit.weight',
    hintKey: 'coach.strength.hint.weight',
  },
  volume: {
    field: 'volume_kg',
    labelKey: 'coach.strength.metric.volume',
    unitKey: 'coach.strength.unit.volume',
    hintKey: 'coach.strength.hint.volume',
  },
  e1rm: {
    field: 'e1rm_kg',
    labelKey: 'coach.strength.metric.e1rm',
    unitKey: 'coach.strength.unit.e1rm',
    hintKey: 'coach.strength.hint.e1rm',
  },
};

/**
 * Per-exercise strength progression chart. Shows top weight, total volume or
 * estimated 1RM over time. The e1RM toggle appears only when the selected
 * exercise is e1rm_eligible; selecting a non-eligible exercise while on e1RM
 * resets to weight. A metric with fewer than 3 points shows a metric-level empty
 * state instead of silently hiding the component.
 */
function StrengthProgression({
  data,
  locale,
}: {
  data: StrengthProgressionEntry[];
  locale: string;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const [chosenMetric, setMetric] = useState<ProgressionMetric>('weight');
  const [selected, setSelected] = useState<string | null>(null);

  // Exercises chartable on the baseline metrics (weight or volume). The chip row
  // never depends on the e1RM metric so switching to e1RM cannot empty it.
  const chartable = useMemo(
    () =>
      data.filter(
        (e) =>
          e.points.filter((p) => p.top_weight_kg != null).length >= 3 ||
          e.points.filter((p) => p.volume_kg != null).length >= 3,
      ),
    [data],
  );

  const active = useMemo(
    () => chartable.find((e) => e.exercise === selected) ?? chartable[0],
    [chartable, selected],
  );

  const e1rmEligible = Boolean(active?.e1rm_eligible);

  // Selecting a non-eligible exercise while on e1RM falls back to weight, derived
  // (no setState-in-effect): the chosen metric is overridden rather than reset.
  const metric: ProgressionMetric =
    chosenMetric === 'e1rm' && !e1rmEligible ? 'weight' : chosenMetric;

  if (chartable.length === 0 || !active) return null;

  const metricConfig = METRICS[metric];
  const chartData = active.points
    .map((p) => ({
      date: p.date,
      value: p[metricConfig.field] ?? null,
    }))
    .filter((p): p is { date: string; value: number } => p.value != null);

  const unitLabel = t(metricConfig.unitKey);
  const activeMetricLabel = t(metricConfig.labelKey);
  const chartSummary = t('coach.strength.chartSummary', {
    exercise: active.exercise,
    metric: activeMetricLabel,
  });

  // The metrics available for the selected exercise (e1RM only when eligible).
  const availableMetrics: ProgressionMetric[] = e1rmEligible
    ? ['weight', 'volume', 'e1rm']
    : ['weight', 'volume'];

  return (
    <Card variant="default" padding="lg">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold tracking-tight">
          <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('coach.strength.progressionTitle')}
        </h3>
        <div
          className="flex gap-1 rounded-md border border-border p-0.5"
          role="group"
          aria-label={t('coach.strength.metricGroupLabel')}
        >
          {availableMetrics.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMetric(m)}
              aria-pressed={metric === m}
              className={cn(
                'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
                metric === m
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(METRICS[m].labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {chartable.slice(0, 6).map((e) => (
          <button
            key={e.exercise}
            type="button"
            onClick={() => {
              setSelected(e.exercise);
              // If this exercise is not e1RM-eligible and e1RM is the chosen
              // metric, store weight so the choice persists across reselection.
              if (chosenMetric === 'e1rm' && !e.e1rm_eligible) {
                setMetric('weight');
              }
            }}
            aria-pressed={active.exercise === e.exercise}
            className={cn(
              'cursor-pointer rounded-full border px-2.5 py-1 text-xs transition-colors',
              active.exercise === e.exercise
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            {e.exercise}
          </button>
        ))}
      </div>

      {chartData.length < 3 ? (
        <div
          className="flex h-[200px] items-center justify-center rounded-md border border-dashed border-border px-4 text-center text-xs text-muted-foreground"
          role="status"
        >
          {t('coach.strength.metricEmpty')}
        </div>
      ) : (
        <div role="img" aria-label={chartSummary}>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid
                horizontal
                vertical={false}
                strokeDasharray="3 3"
                stroke={chartTheme.gridColor}
              />
              <XAxis
                dataKey="date"
                tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: string) => formatShortDate(v, locale)}
                minTickGap={16}
              />
              <YAxis
                tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
                tickLine={false}
                axisLine={false}
                width={44}
                domain={['dataMin - 5', 'dataMax + 5']}
                tickFormatter={(v: number) => `${Math.round(v)}`}
              />
              <Tooltip
                content={
                  <ChartTooltip
                    valueFormatter={(v) =>
                      typeof v === 'number' ? `${v} ${unitLabel}` : String(v)
                    }
                  />
                }
              />
              <Line
                type="monotone"
                dataKey="value"
                name={active.exercise}
                stroke={chartTheme.primaryColor}
                strokeWidth={2.5}
                dot={{ r: 4, fill: chartTheme.primaryColor }}
                activeDot={{ r: 6, fill: chartTheme.primaryColor }}
                connectNulls
                animationDuration={600}
                animationEasing="ease-out"
                isAnimationActive
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="mt-2 text-xs text-muted-foreground">{t(metricConfig.hintKey)}</p>
      {metric === 'e1rm' && chartData.length >= 3 ? (
        <p className="mt-1 text-xs text-muted-foreground">{t('coach.strength.e1rmLabel')}</p>
      ) : null}
      {active.mixed ? (
        <p className="mt-1 text-xs text-warning">{t('coach.strength.note.mixed')}</p>
      ) : active.notation_mixed ? (
        <p className="mt-1 text-xs text-warning">{t('coach.strength.note.notationMixed')}</p>
      ) : active.load_label === 'total_noted' && metric === 'weight' ? (
        <p className="mt-1 text-xs text-muted-foreground">{t('coach.strength.note.totalNoted')}</p>
      ) : null}
    </Card>
  );
}

/**
 * Per-session strength totals: tonnage, sets or reps over time.
 *
 * Complements the per-exercise chart, which answers "am I progressing on the low
 * row". This one answers "how much did I move this session", which is the figure
 * the athlete asked for. Every value is computed server-side by
 * shared/strength_volume.py and merely read here: recomputing in the UI would
 * produce a second definition of tonnage that drifts from the coach's.
 *
 * Sessions whose tonnage is incomplete (an unknown load somewhere) are excluded
 * from the tonnage series rather than drawn low, which would show a drop that
 * never happened. Their sets and reps remain valid and are still plotted.
 */
function StrengthSessionTotals({
  data,
  locale,
}: {
  data: StrengthSessionEntry[];
  locale: string;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const [metric, setMetric] = useState<'tonnage' | 'sets' | 'reps'>('tonnage');

  const chartData = useMemo(
    () =>
      data
        .map((s) => ({
          date: s.date,
          value:
            metric === 'tonnage'
              ? s.volume_incomplete
                ? null
                : s.volume_kg
              : metric === 'sets'
                ? s.total_sets
                : s.total_reps,
        }))
        .filter((p): p is { date: string; value: number } => p.value != null),
    [data, metric],
  );

  const partialCount = useMemo(
    () => data.filter((s) => s.volume_incomplete).length,
    [data],
  );

  if (chartData.length < 3) return null;

  const unitLabel =
    metric === 'tonnage'
      ? t('coach.strength.unit.tonnage')
      : metric === 'sets'
        ? t('coach.strength.unit.sets')
        : t('coach.strength.unit.reps');

  const last = chartData[chartData.length - 1];
  const chartSummary = t('coach.strength.sessionSummary', {
    metric: unitLabel,
    count: chartData.length,
    last: last.value,
  });

  return (
    <Card variant="default" padding="lg">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold tracking-tight">
          <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('coach.strength.sessionTotalsTitle')}
        </h3>
        <div
          className="flex gap-1 rounded-md border border-border p-0.5"
          role="group"
          aria-label={t('coach.strength.metricGroupLabel')}
        >
          {(['tonnage', 'sets', 'reps'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMetric(m)}
              aria-pressed={metric === m}
              className={cn(
                'cursor-pointer rounded px-2 py-1 text-xs transition-colors',
                metric === m
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t(`coach.strength.metric.${m}`)}
            </button>
          ))}
        </div>
      </div>

      <div role="img" aria-label={chartSummary}>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid
              horizontal
              vertical={false}
              strokeDasharray="3 3"
              stroke={chartTheme.gridColor}
            />
            <XAxis
              dataKey="date"
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: string) => formatShortDate(v, locale)}
              minTickGap={16}
            />
            <YAxis
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickFormatter={(v: number) =>
                metric === 'tonnage' ? `${Math.round(v / 1000)}t` : `${Math.round(v)}`
              }
            />
            <Tooltip
              content={
                <ChartTooltip
                  valueFormatter={(v) =>
                    typeof v === 'number'
                      ? `${v.toLocaleString(locale)} ${unitLabel}`
                      : String(v)
                  }
                />
              }
            />
            <Line
              type="monotone"
              dataKey="value"
              name={unitLabel}
              stroke={chartTheme.primaryColor}
              strokeWidth={2.5}
              dot={{ r: 4, fill: chartTheme.primaryColor }}
              activeDot={{ r: 6, fill: chartTheme.primaryColor }}
              connectNulls
              animationDuration={600}
              animationEasing="ease-out"
              isAnimationActive
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {metric === 'tonnage' && partialCount > 0
          ? t('coach.strength.hint.tonnagePartial', { count: partialCount })
          : t(`coach.strength.hint.${metric}`)}
      </p>
    </Card>
  );
}

// Muscle groups rendered in the weekly stacked-bar block, in a stable order.
const WEEKLY_GROUP_ORDER = [
  'pectoraux', 'dos', 'epaules', 'biceps', 'triceps',
  'quadriceps', 'ischios', 'fessiers', 'mollets', 'abdos',
] as const;

function segTotal(seg?: { logged?: number; campus_plan?: number }): number {
  if (!seg) return 0;
  return (seg.logged ?? 0) + (seg.campus_plan ?? 0);
}

/** The API zero-fills 8 weeks; a block with only zeros is hidden. */
/** The API zero-fills 8 weeks; a block with only zeros is hidden. A malformed
 * entry keeps the block shown, so its local ErrorBoundary reports it. */
function hasWeeklySets(insights?: StrengthInsights | null): boolean {
  const weeks: unknown = insights?.weeks;
  if (!Array.isArray(weeks)) return false;
  return weeks.some((wk) => {
    if (!wk || typeof wk !== 'object') return true;
    const w = wk as StrengthWeek;
    const groups = w.groups && typeof w.groups === 'object' ? Object.values(w.groups) : [];
    return (
      groups.some((seg) => segTotal(seg) > 0) ||
      segTotal(w.explosivite) > 0 ||
      segTotal(w.autre) > 0
    );
  });
}

function hasPushPull(insights?: StrengthInsights | null): boolean {
  const rows: unknown = insights?.push_pull;
  if (!Array.isArray(rows)) return false;
  return rows.some((p) => {
    if (!p || typeof p !== 'object') return true;
    const r = p as PushPullPoint;
    return (r.push ?? 0) > 0 || (r.pull ?? 0) > 0;
  });
}

/**
 * Weekly stacked bars: logged vs Campus-plan sets per muscle group, with an
 * explosiveness bar and an "other" bar carrying the unmapped list. One stacked
 * bar per week; the metric picks which group (or bucket) to show.
 */
function StrengthWeeklyGroups({
  insights,
}: {
  insights: StrengthInsights;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const weeks = useMemo(() => insights.weeks ?? [], [insights]);

  // Groups that actually carry data across the window (keeps the selector short).
  const activeGroups = useMemo(() => {
    const used = new Set<string>();
    for (const wk of weeks) {
      for (const g of WEEKLY_GROUP_ORDER) {
        if (segTotal(wk.groups?.[g]) > 0) used.add(g);
      }
      if (segTotal(wk.explosivite) > 0) used.add('explosivite');
      if (segTotal(wk.autre) > 0) used.add('autre');
    }
    const ordered = WEEKLY_GROUP_ORDER.filter((g) => used.has(g)) as string[];
    if (used.has('explosivite')) ordered.push('explosivite');
    if (used.has('autre')) ordered.push('autre');
    return ordered;
  }, [weeks]);

  const [group, setGroup] = useState<string>(() => activeGroups[0] ?? 'pectoraux');
  const current = activeGroups.includes(group) ? group : activeGroups[0] ?? 'pectoraux';

  const groupLabel = (g: string): string => {
    if (g === 'explosivite') return t('coach.strength.insights.explosivite');
    if (g === 'autre') return t('coach.strength.insights.autre');
    return t(`coach.strength.muscle.${g}`, { defaultValue: g });
  };

  const chartData = weeks.map((wk) => {
    const seg =
      current === 'explosivite'
        ? wk.explosivite
        : current === 'autre'
          ? wk.autre
          : wk.groups?.[current];
    return {
      week: wk.week,
      logged: seg?.logged ?? 0,
      campus_plan: seg?.campus_plan ?? 0,
    };
  });

  // Weeks flagged partial (the current, in-progress week) get a suffix on the
  // axis tick so a lower bar reads as "not finished", not "a drop".
  const partialWeeks = useMemo(
    () => new Set(weeks.filter((wk) => wk.partial).map((wk) => wk.week)),
    [weeks],
  );
  const formatWeekTick = (w: string): string => {
    const short = w.replace(/^\d{4}-/, '');
    return partialWeeks.has(w) ? `${short} ${t('coach.strength.insights.inProgress')}` : short;
  };

  const unmapped = insights.unmapped_exercises ?? [];

  return (
    <Card variant="default" padding="lg">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold tracking-tight">
          <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('coach.strength.insights.weeklyTitle')}
        </h3>
      </div>

      {activeGroups.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {activeGroups.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGroup(g)}
              aria-pressed={current === g}
              className={cn(
                'cursor-pointer rounded-full border px-2.5 py-1 text-xs transition-colors',
                current === g
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {groupLabel(g)}
            </button>
          ))}
        </div>
      ) : null}

      <div role="img" aria-label={t('coach.strength.insights.weeklyTitle')}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal vertical={false} strokeDasharray="3 3" stroke={chartTheme.gridColor} />
            <XAxis
              dataKey="week"
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={formatWeekTick}
              minTickGap={8}
            />
            <YAxis
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              width={32}
              allowDecimals
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar
              dataKey="logged"
              name={t('coach.strength.insights.segment.logged')}
              stackId="s"
              fill={chartTheme.primaryColor}
            />
            <Bar
              dataKey="campus_plan"
              name={t('coach.strength.insights.segment.campusPlan')}
              stackId="s"
              fill={chartTheme.successColor}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <p className="mt-2 text-xs text-muted-foreground">{t('coach.strength.insights.weeklyHint')}</p>
      <p className="mt-1 text-xs text-muted-foreground">{t('coach.strength.insights.swingHint')}</p>
      <p className="mt-1 text-xs text-muted-foreground">{t('coach.strength.insights.countingRule')}</p>
      {unmapped.length > 0 ? (
        <div className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">{t('coach.strength.insights.unmappedTitle')}: </span>
          {unmapped
            .map(
              (u) =>
                `${u.exercise} (${t(`coach.strength.insights.unmapped.${u.reason}`, { defaultValue: u.reason })})`,
            )
            .join(', ')}
        </div>
      ) : null}
    </Card>
  );
}

/**
 * Records table: best top weight, e1RM, volume (loaded) or best reps / weighted
 * set (bodyweight), per exercise. Scrolls horizontally on narrow screens.
 */
function StrengthRecordsTable({
  insights,
  locale,
}: {
  insights: StrengthInsights;
  locale: string;
}) {
  const { t } = useTranslation();
  const records = insights.records ?? [];
  if (records.length === 0) return null;

  const fmtDate = (d?: string | null): string =>
    d ? new Date(d).toLocaleDateString(locale, { day: 'numeric', month: 'short' }) : '—';
  const fmtKg = (v?: number | null): string => (v != null ? `${v} kg` : '—');

  return (
    <Card variant="default" padding="lg">
      <h3 className="mb-4 flex items-center gap-1.5 text-sm font-semibold tracking-tight">
        <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('coach.strength.records.title')}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-xs">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="py-1.5 pr-2 font-medium">{t('coach.strength.records.exercise')}</th>
              <th className="py-1.5 pr-2 font-medium">{t('coach.strength.records.topWeight')}</th>
              <th className="py-1.5 pr-2 font-medium">{t('coach.strength.records.e1rm')}</th>
              <th className="py-1.5 pr-2 font-medium">{t('coach.strength.records.bestVolume')}</th>
              <th className="py-1.5 pr-2 font-medium">{t('coach.strength.records.lastDate')}</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.exercise} className="border-b border-border/50 last:border-0">
                <td className="py-1.5 pr-2 font-medium text-foreground">
                  {r.exercise}
                  {r.notation_mixed ? (
                    <span className="ml-1 text-warning" title={t('coach.strength.note.notationMixed')}>
                      *
                    </span>
                  ) : null}
                </td>
                {r.kind === 'bodyweight' ? (
                  <td className="py-1.5 pr-2" colSpan={3}>
                    {r.best_reps_bw
                      ? `${t('coach.strength.records.bestReps')}: ${t('coach.strength.records.reps', {
                          reps: r.best_reps_bw.reps,
                        })} (${fmtDate(r.best_reps_bw.date)})`
                      : '—'}
                    {r.best_weighted_bw
                      ? ` · ${t('coach.strength.records.bestWeighted')}: ${t(
                          'coach.strength.records.weighted',
                          { reps: r.best_weighted_bw.reps, weight: r.best_weighted_bw.added_weight_kg },
                        )} (${fmtDate(r.best_weighted_bw.date)})`
                      : ''}
                  </td>
                ) : (
                  <>
                    <td className="py-1.5 pr-2 text-foreground">
                      {fmtKg(r.top_weight_kg)}
                      {r.top_weight_kg != null ? (
                        <span className="ml-1 text-muted-foreground">({fmtDate(r.top_weight_date)})</span>
                      ) : null}
                      {r.load_label === 'total_noted' && r.top_weight_kg != null ? (
                        <span className="ml-1 text-muted-foreground">
                          ({t('coach.strength.records.totalNoted')})
                        </span>
                      ) : null}
                    </td>
                    <td className="py-1.5 pr-2 text-foreground">
                      {fmtKg(r.e1rm_kg)}
                      {r.e1rm_kg != null ? (
                        <span className="ml-1 text-muted-foreground">({fmtDate(r.e1rm_date)})</span>
                      ) : null}
                    </td>
                    <td className="py-1.5 pr-2 text-foreground">
                      {fmtKg(r.best_volume_kg)}
                      {r.best_volume_kg != null ? (
                        <span className="ml-1 text-muted-foreground">({fmtDate(r.best_volume_date)})</span>
                      ) : null}
                    </td>
                  </>
                )}
                <td className="py-1.5 pr-2 text-muted-foreground">{fmtDate(r.last_date)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/**
 * Push / pull balance over the last 4 weeks (logged sets only). No judgement
 * text; the ratio is null when there is no pull.
 */
function StrengthPushPull({
  insights,
}: {
  insights: StrengthInsights;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const points = insights.push_pull ?? [];
  if (points.length === 0) return null;

  const chartData = points.map((p) => ({
    week: p.week,
    push: p.push,
    pull: p.pull,
  }));

  return (
    <Card variant="default" padding="lg">
      <h3 className="mb-4 flex items-center gap-1.5 text-sm font-semibold tracking-tight">
        <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('coach.strength.pushPull.title')}
      </h3>
      <div role="img" aria-label={t('coach.strength.pushPull.title')}>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal vertical={false} strokeDasharray="3 3" stroke={chartTheme.gridColor} />
            <XAxis
              dataKey="week"
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: string) => v.replace(/^\d{4}-/, '')}
            />
            <YAxis
              tick={{ fill: chartTheme.axisColor, fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickLine={false}
              axisLine={false}
              width={28}
              allowDecimals
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="push"
              name={t('coach.strength.pushPull.push')}
              stroke={chartTheme.primaryColor}
              strokeWidth={2.5}
              dot={{ r: 3 }}
            />
            <Line
              type="monotone"
              dataKey="pull"
              name={t('coach.strength.pushPull.pull')}
              stroke={chartTheme.axisColor}
              strokeWidth={2.5}
              dot={{ r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {points.map((p) => (
          <span key={p.week}>
            {p.week.replace(/^\d{4}-/, '')} · {t('coach.strength.pushPull.ratio')}:{' '}
            {p.ratio != null ? p.ratio : '—'}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t('coach.strength.pushPull.hint')}</p>
    </Card>
  );
}

export function CoachPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const chartTheme = useChartTheme();
  const stagger = useStaggerVariants();

  const [data, setData] = useState<CoachSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const FEEDBACK_PAGE_SIZE_KEY = 'coach.feedback.pageSize';
  const [feedbackPage, setFeedbackPage] = useState<number>(1);
  const [feedbackPageSize, setFeedbackPageSize] = useState<number>(() => {
    if (typeof window === 'undefined') return 5;
    const stored = window.localStorage.getItem(FEEDBACK_PAGE_SIZE_KEY);
    const parsed = stored ? Number(stored) : NaN;
    return [3, 5, 10, 20].includes(parsed) ? parsed : 5;
  });

  useEffect(() => {
    let cancelled = false;
    api
      .get<CoachSummary>('/coach/summary')
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(`Unable to load coach data: ${msg}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Recaps state
  interface Recap { week: string; generated_at: string; duration_seconds: number; activity_count: number; audio_url: string; }
  const [recaps, setRecaps] = useState<Recap[]>([]);
  const [generating, setGenerating] = useState(false);

  const fetchRecaps = () => {
    api.get<{ recaps: Recap[] }>('/coach/recaps').then((d) => setRecaps(d.recaps || [])).catch(() => {});
  };
  useEffect(() => { fetchRecaps(); }, []);

  const handleGenerateRecap = () => {
    setGenerating(true);
    const prevCount = recaps.length;
    const prevLatest = recaps[0]?.generated_at;
    api.post('/coach/recaps', {}).then(() => {
      let attempts = 0;
      const poll = setInterval(() => {
        attempts++;
        api.get<{ recaps: Recap[] }>('/coach/recaps').then((d) => {
          const fresh = d.recaps || [];
          if (fresh.length > prevCount || (fresh[0]?.generated_at && fresh[0].generated_at !== prevLatest)) {
            clearInterval(poll);
            setRecaps(fresh);
            setGenerating(false);
          } else if (attempts >= 12) {
            clearInterval(poll);
            setRecaps(fresh);
            setGenerating(false);
          }
        }).catch(() => { if (attempts >= 12) { clearInterval(poll); setGenerating(false); } });
      }, 5000);
    }).catch(() => setGenerating(false));
  };

  const trends = data?.trends;
  const weekLabels = useMemo<string[]>(
    () => WEEK_LABEL_KEYS.map((k) => t(k)),
    [t],
  );
  const vol = useMemo<number[]>(() => trends?.weekly_volume_km ?? [], [trends]);
  const totalKm = vol.reduce((a, b) => a + b, 0);
  const runSessions = (trends?.run_sessions_per_week ?? []).reduce(
    (a: number, b: number) => a + b,
    0
  );
  const otherSessions = (trends?.other_sessions_per_week ?? []).reduce(
    (a: number, b: number) => a + b,
    0
  );
  const otherBreakdown: Record<string, number> = trends?.other_sessions_breakdown ?? {};
  // Group by translated label (e.g. WeightTraining + Workout + Crossfit → musculation)
  const groupedOther = useMemo(() => {
    const grouped: Record<string, number> = {};
    for (const [type, count] of Object.entries(otherBreakdown)) {
      const label = t(`coach.now.kpi.sportType.${type}`, { defaultValue: '' }) || t('coach.now.kpi.otherLabel');
      grouped[label] = (grouped[label] || 0) + (count as number);
    }
    // Sort by count desc, take top 2
    return Object.entries(grouped).sort((a, b) => b[1] - a[1]).slice(0, 2);
  }, [otherBreakdown, t]);
  const thisWeekKm = vol.length > 0 ? vol[vol.length - 1] : 0;
  const rampRate = trends?.ramp_rate ?? null;

  const volumeChartData = useMemo(
    () =>
      weekLabels.map((week, i) => ({
        week,
        km: vol[i] ?? 0,
      })),
    [vol, weekLabels]
  );

  const paceChartData = useMemo(() => {
    const paces = trends?.avg_pace_per_week ?? [];
    return weekLabels.map((week, i) => {
      const sec = paces[i] ? paceToSec(paces[i]) : 0;
      return { week, paceSec: sec > 0 ? sec : null };
    });
  }, [trends, weekLabels]);

  const validPaceSecs = paceChartData
    .map((p) => p.paceSec)
    .filter((s): s is number => typeof s === 'number' && s > 0);
  const paceMin = validPaceSecs.length > 0 ? Math.min(...validPaceSecs) : 300;
  const paceMax = validPaceSecs.length > 0 ? Math.max(...validPaceSecs) : 400;

  const intervalPaces = trends?.interval_paces ?? [];
  const efPaces = trends?.ef_paces ?? [];
  const efAvgHr = (() => {
    const hrs = efPaces.filter((p) => p.hr).map((p) => p.hr as number);
    if (hrs.length === 0) return null;
    return Math.round(hrs.reduce((a, b) => a + b, 0) / hrs.length);
  })();

  // Volume insight (computed on client from received trends)
  const volumeInsight = useMemo<string | null>(() => {
    if (vol.length < 2) return null;
    const first = vol[0] || 0;
    const last = vol[vol.length - 1] || 0;
    const avg = vol.reduce((a, b) => a + b, 0) / vol.length;
    const max = Math.max(...vol);
    const maxIdx = vol.findIndex((v) => v === max);
    if (first > 0 && last > first * 1.15) {
      const pct = Math.round(((last - first) / first) * 100);
      return t('coach.insights.volumeUp', { pct });
    }
    if (first > 0 && last < first * 0.85) {
      const pct = Math.round(((first - last) / first) * 100);
      return t('coach.insights.volumeDown', { pct });
    }
    const variance =
      avg > 0
        ? Math.sqrt(
            vol.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / vol.length,
          ) / avg
        : 0;
    if (variance < 0.1) {
      return t('coach.insights.volumeSteady', { avg: Math.round(avg) });
    }
    if (maxIdx >= 0 && max > 0) {
      return t('coach.insights.volumePeak', {
        week: weekLabels[maxIdx],
        km: Math.round(max),
      });
    }
    return null;
  }, [vol, t, weekLabels]);

  // Pace insight
  const paceInsight = useMemo<string | null>(() => {
    const paces = trends?.avg_pace_per_week ?? [];
    if (paces.length < 2) return null;
    const validSecs = paces.map(paceToSec).filter((s) => s > 0);
    if (validSecs.length < 2) return null;
    const firstSec = validSecs[0];
    const lastSec = validSecs[validSecs.length - 1];
    const diff = firstSec - lastSec;
    if (diff > 5) {
      return t('coach.insights.paceImproved', { diff: Math.round(diff) });
    }
    if (diff < -5) {
      return t('coach.insights.paceSlowed', { diff: Math.round(-diff) });
    }
    const avgSec = Math.round(
      validSecs.reduce((a, b) => a + b, 0) / validSecs.length,
    );
    return t('coach.insights.paceStable', { pace: formatPace(avgSec) });
  }, [trends, t]);

  // Ramp rate insight (with tone)
  const rampInsight = useMemo<{
    text: string;
    tone: 'warning' | 'info' | 'muted';
  } | null>(() => {
    if (rampRate === null) return null;
    if (rampRate > 10) {
      return {
        text: t('coach.insights.rampHigh', { rate: rampRate }),
        tone: 'warning',
      };
    }
    if (rampRate >= 5) {
      return {
        text: t('coach.insights.rampSteady', { rate: rampRate }),
        tone: 'info',
      };
    }
    if (rampRate < 0) {
      return {
        text: t('coach.insights.rampRecovery', { rate: Math.abs(rampRate) }),
        tone: 'muted',
      };
    }
    return {
      text: t('coach.insights.rampSteady', { rate: rampRate }),
      tone: 'info',
    };
  }, [rampRate, t]);

  // EF insight (pace + HR)
  const efInsight = useMemo<string | null>(() => {
    if (efPaces.length < 2) return null;
    const paceFirst = efPaces[0].pace_sec;
    const paceLast = efPaces[efPaces.length - 1].pace_sec;
    const hrs = efPaces.filter((p) => p.hr).map((p) => p.hr as number);
    if (hrs.length < 2) return null;
    const hrFirst = hrs[0];
    const hrLast = hrs[hrs.length - 1];
    const paceDelta = paceFirst - paceLast; // positive = faster
    const hrDelta = hrLast - hrFirst; // positive = HR up
    const hrStable = Math.abs(hrDelta) < 3;
    const paceStable = Math.abs(paceDelta) < 3;
    if (paceDelta > 3 && hrStable) return t('coach.insights.efAerobicGain');
    if (paceStable && hrDelta < -3) return t('coach.insights.efCardiacGain');
    if (paceDelta > 3 && hrDelta > 3) return t('coach.insights.efFatigue');
    if (paceStable && hrStable) return t('coach.insights.efStable');
    return null;
  }, [efPaces, t]);

  // Interval insight
  const intervalInsight = useMemo<string | null>(() => {
    if (intervalPaces.length < 2) return null;
    const first = intervalPaces[0].pace_sec;
    const last = intervalPaces[intervalPaces.length - 1].pace_sec;
    if (first - last > 3) return t('coach.insights.intervalImproved');
    if (last - first > 3) return t('coach.insights.intervalSlowed');
    return null;
  }, [intervalPaces, t]);

  // Robust pace-axis domain: snap to multiples of 10s, clamp tick count,
  // ensure a minimum span so flat lines don't get a zero-height domain.
  const computePaceAxis = (
    points: PacePoint[],
  ): { domain: [number, number]; ticks: number[] } => {
    const values = points.map((p) => p.pace_sec).filter((s) => Number.isFinite(s) && s > 0);
    if (values.length === 0) {
      return { domain: [0, 0], ticks: [] };
    }
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    // Snap to multiples of 10 seconds.
    let lo = Math.floor((rawMin - 5) / 10) * 10;
    let hi = Math.ceil((rawMax + 5) / 10) * 10;
    // Guarantee at least 30s of span so flat data isn't compressed.
    if (hi - lo < 30) {
      const mid = (hi + lo) / 2;
      lo = Math.floor((mid - 15) / 10) * 10;
      hi = Math.ceil((mid + 15) / 10) * 10;
    }
    if (lo < 0) lo = 0;
    // Choose a step that yields ~4-5 ticks, rounded to a multiple of 10.
    const span = hi - lo;
    const rawStep = span / 4;
    const step = Math.max(10, Math.round(rawStep / 10) * 10);
    const ticks: number[] = [];
    for (let v = lo; v <= hi; v += step) ticks.push(v);
    if (ticks[ticks.length - 1] !== hi) ticks.push(hi);
    return { domain: [lo, hi], ticks };
  };

  const { domain: intervalPaceDomain, ticks: intervalPaceTicks } = useMemo(
    () => computePaceAxis(intervalPaces),
    [intervalPaces],
  );

  const { domain: efPaceDomain, ticks: efPaceTicks } = useMemo(
    () => computePaceAxis(efPaces),
    [efPaces],
  );

  // Pace average for ReferenceLine
  const paceAvgSec = useMemo<number | null>(() => {
    if (validPaceSecs.length === 0) return null;
    return Math.round(
      validPaceSecs.reduce((a, b) => a + b, 0) / validPaceSecs.length,
    );
  }, [validPaceSecs]);

  // Volume max info for highlight
  const volumeMax = useMemo(() => {
    if (vol.length === 0) return { max: 0, idx: -1 };
    const max = Math.max(...vol);
    const idx = vol.findIndex((v) => v === max);
    return { max, idx };
  }, [vol]);

  const nextSession =
    data?.recent_feedback?.[0]?.coach_feedback?.recommendation_next ??
    t('coach.now.nextSession.fallback');

  // Real current-week tally (recomputed live on every /coach/summary load),
  // shown as the source of truth alongside the coach's frozen recommendation.
  const cw = data?.current_week;
  const currentWeekLabel = cw
    ? [
        cw.runs > 0 ? `${cw.runs} ${cw.runs > 1 ? t('coach.now.thisWeek.runs') : t('coach.now.thisWeek.run')} (${cw.run_km.toFixed(1)}km)` : null,
        cw.other > 0 ? `${cw.other} ${cw.other > 1 ? t('coach.now.thisWeek.others') : t('coach.now.thisWeek.other')}` : null,
      ].filter(Boolean).join(' + ') || t('coach.now.thisWeek.none')
    : null;

  const compliance = trends?.compliance ?? null;

  let rampTone: 'success' | 'danger' | 'muted' = 'muted';
  let RampIcon = TrendingUp;
  if (rampRate !== null) {
    if (rampRate > 10) {
      rampTone = 'danger';
      RampIcon = TrendingUp;
    } else if (rampRate > 0) {
      rampTone = 'success';
      RampIcon = TrendingUp;
    } else if (rampRate < 0) {
      rampTone = 'muted';
      RampIcon = TrendingDown;
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6 flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">
          {t('coach.header.title')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('coach.header.subtitle')}
        </p>
      </header>

      {error ? (
        <div className="mb-4">
          <Alert variant="error">{error}</Alert>
        </div>
      ) : null}

      <Tabs defaultValue="now">
        <TabsList>
          <TabsTrigger value="now">{t('coach.tabs.now')}</TabsTrigger>
          <TabsTrigger value="trends">{t('coach.tabs.trends')}</TabsTrigger>
          <TabsTrigger value="chat">{t('coach.tabs.chat')}</TabsTrigger>
        </TabsList>

        {/* TAB: NOW */}
        <TabsContent value="now">
          <div className="flex flex-col gap-6">
            <Card variant="elevated" padding="md">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-primary/10 p-2 text-primary">
                  <Calendar className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-1 mb-1">
                    <span className="text-xs font-semibold text-muted-foreground">
                      {t('coach.now.nextSession.title')}
                    </span>
                    <InfoTooltip i18nKey="metrics.nextSession" align="start" />
                  </div>
                  {currentWeekLabel ? (
                    <p className="text-xs text-muted-foreground mb-1">
                      {t('coach.now.thisWeek.label')}: {currentWeekLabel}
                    </p>
                  ) : null}
                  <p className="text-sm leading-relaxed">{nextSession}</p>
                </div>
              </div>
            </Card>

            {loading ? (
              <KPISkeleton />
            ) : (
              <motion.div
                className="grid grid-cols-2 lg:grid-cols-4 gap-3"
                variants={stagger.container}
                initial="hidden"
                animate="show"
              >
                <motion.div variants={stagger.item} className="h-full">
                  <KPI
                    label={t('coach.now.kpi.volumeLabel')}
                    value={Math.round(totalKm)}
                    unit="km"
                    info="metrics.volume"
                  />
                </motion.div>
                <motion.div variants={stagger.item} className="h-full">
                  <KPI
                    label={t('coach.now.kpi.sessionsLabel')}
                    info="metrics.sessions"
                    value={
                      <span className="text-2xl">
                        {runSessions}
                        <span className="text-muted-foreground">
                          {' '}
                          {t('coach.now.kpi.runsLabel')}
                        </span>
                        {otherSessions > 0 && groupedOther.map(([label, count]) => (
                          <span key={label}>
                            <span className="text-muted-foreground"> · </span>
                            {count}
                            <span className="text-muted-foreground">
                              {' '}{label}
                            </span>
                          </span>
                        ))}
                      </span>
                    }
                  />
                </motion.div>
                <motion.div variants={stagger.item} className="h-full">
                  <KPI
                    label={t('coach.now.kpi.thisWeekLabel')}
                    value={thisWeekKm}
                    unit="km"
                    info="metrics.thisWeek"
                  />
                </motion.div>
                <motion.div variants={stagger.item} className="h-full">
                  <KPI
                    label={t('coach.now.kpi.rampRateLabel')}
                    info="metrics.ramp"
                    value={
                      rampRate !== null ? (
                        <span
                          className={cn(
                            rampTone === 'danger' && 'text-danger',
                            rampTone === 'success' && 'text-success'
                          )}
                        >
                          {rampRate > 0 ? '+' : ''}
                          {rampRate}%
                        </span>
                      ) : (
                        '-'
                      )
                    }
                    icon={
                      rampRate !== null ? (
                        <RampIcon
                          className={cn(
                            'h-4 w-4',
                            rampTone === 'danger' && 'text-danger',
                            rampTone === 'success' && 'text-success'
                          )}
                          aria-hidden="true"
                        />
                      ) : undefined
                    }
                  />
                </motion.div>
              </motion.div>
            )}

            {rampRate !== null && rampRate > 10 ? (
              <Alert variant="warning">
                {t('coach.now.rampWarn', { rate: rampRate })}
              </Alert>
            ) : null}

            {(trends?.health_anomalies?.length ?? 0) > 0 && (
              <div className="flex flex-col gap-2">
                {trends!.health_anomalies!.map((a) => (
                  <Alert key={a.id} variant={a.severity === 'warning' ? 'warning' : 'info'}>
                    {a.message}
                  </Alert>
                ))}
              </div>
            )}

            {trends?.recovery && (
              <Card variant="default" padding="md">
                <span className="inline-flex items-center gap-1 text-sm font-medium mb-3">
                  {t('coach.now.recovery.title')}
                  <InfoTooltip i18nKey="metrics.recovery" align="start" />
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {trends.recovery.form !== null && (
                    <div className="text-center">
                      <div className={cn(
                        'text-xl font-numeric font-bold',
                        trends.recovery.form > 5 && 'text-success',
                        trends.recovery.form < -10 && 'text-danger',
                        trends.recovery.form >= -10 && trends.recovery.form <= 5 && 'text-warning',
                      )}>
                        {trends.recovery.form > 0 ? '+' : ''}{Math.round(trends.recovery.form)}
                      </div>
                      <div className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
                        {t('coach.now.recovery.form')}
                        <InfoTooltip i18nKey="metrics.tsb" />
                      </div>
                      <div className="text-xs mt-0.5">
                        {trends.recovery.form > 5 ? t('coach.now.recovery.fresh') : trends.recovery.form < -10 ? t('coach.now.recovery.fatigued') : t('coach.now.recovery.neutral')}
                      </div>
                    </div>
                  )}
                  {trends.recovery.vo2max !== null && (
                    <div className="text-center">
                      <div className="text-xl font-numeric font-bold">{trends.recovery.vo2max}</div>
                      <div className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
                        {t('coach.now.recovery.vo2max')}
                        <InfoTooltip i18nKey="metrics.vo2max" />
                      </div>
                      {trends.recovery.vo2max_delta_7d !== null && (
                        <div className={cn('text-xs mt-0.5', trends.recovery.vo2max_delta_7d >= 0 ? 'text-success' : 'text-danger')}>
                          {trends.recovery.vo2max_delta_7d > 0 ? '+' : ''}{trends.recovery.vo2max_delta_7d}/7j
                        </div>
                      )}
                    </div>
                  )}
                  {trends.recovery.resting_hr !== null && (
                    <div className="text-center">
                      <div className="text-xl font-numeric font-bold">{trends.recovery.resting_hr} <span className="text-sm font-normal">bpm</span></div>
                      <div className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
                        {t('coach.now.recovery.restingHr')}
                        <InfoTooltip i18nKey="metrics.restinghr" />
                      </div>
                      {trends.recovery.resting_hr_delta_7d !== null && (
                        <div className={cn('text-xs mt-0.5', trends.recovery.resting_hr_delta_7d <= 0 ? 'text-success' : 'text-danger')}>
                          {trends.recovery.resting_hr_delta_7d > 0 ? '+' : ''}{trends.recovery.resting_hr_delta_7d}/7j
                        </div>
                      )}
                    </div>
                  )}
                  {trends.recovery.sleep_display && (
                    <div className="text-center">
                      <div className="text-xl font-numeric font-bold">{trends.recovery.sleep_display}</div>
                      <div className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
                        {t('coach.now.recovery.sleep')}
                        <InfoTooltip i18nKey="metrics.sleep" />
                      </div>
                      {trends.recovery.sleep_delta_7d_min !== null && trends.recovery.sleep_delta_7d_min !== 0 && (
                        <div className={cn('text-xs mt-0.5', trends.recovery.sleep_delta_7d_min > 0 ? 'text-success' : 'text-danger')}>
                          {trends.recovery.sleep_delta_7d_min > 0 ? '+' : ''}{trends.recovery.sleep_delta_7d_min}min/7j
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {trends.recovery.form !== null && (
                  <p className="text-xs text-muted-foreground mt-3 border-t border-border pt-2">
                    {trends.recovery.form > 5
                      ? t('coach.now.recovery.insightFresh')
                      : trends.recovery.form < -10
                        ? t('coach.now.recovery.insightFatigued')
                        : t('coach.now.recovery.insightNeutral')}
                  </p>
                )}
              </Card>
            )}

            {/* Weekly Audio Recaps */}
            <Card variant="default" padding="md">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">{t('coach.recaps.title')}</span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={fetchRecaps}
                    aria-label={t('coach.recaps.refresh')}
                    title={t('coach.recaps.refresh')}
                    className="text-xs px-2 py-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                  >
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={handleGenerateRecap}
                    disabled={generating}
                    className="text-xs px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {generating ? t('coach.recaps.generating') : t('coach.recaps.generate')}
                  </button>
                </div>
              </div>
              {recaps.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t('coach.recaps.empty')}</p>
              ) : (
                <div className="space-y-3">
                  {recaps.slice(0, 5).map((recap) => (
                    <div key={recap.week} className="flex items-center gap-3 p-2 rounded-md bg-muted/50">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium">{t('coach.recaps.week', { week: recap.week })}</div>
                        <div className="text-xs text-muted-foreground">
                          {t('coach.recaps.activities', { count: recap.activity_count })}
                          {recap.duration_seconds > 0 && ` · ${Math.round(recap.duration_seconds / 60)}min`}
                        </div>
                      </div>
                      {recap.audio_url && (
                        <AudioPlayer src={recap.audio_url} duration={recap.duration_seconds} className="flex-shrink-0" />
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {compliance ? (
              <Card variant="default" padding="md">
                <div className="flex items-center justify-between mb-2">
                  <span className="inline-flex items-center gap-1 text-sm font-medium">
                    {t('coach.now.compliance.title')}
                    <InfoTooltip i18nKey="metrics.compliance" align="start" />
                  </span>
                  <span
                    className={cn(
                      'text-sm font-numeric font-semibold',
                      compliance.percentage >= 80 && 'text-success',
                      compliance.percentage >= 50 &&
                        compliance.percentage < 80 &&
                        'text-warning',
                      compliance.percentage < 50 && 'text-danger'
                    )}
                  >
                    {compliance.percentage}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn(
                      'h-full transition-all',
                      compliance.percentage >= 80 && 'bg-success',
                      compliance.percentage >= 50 &&
                        compliance.percentage < 80 &&
                        'bg-warning',
                      compliance.percentage < 50 && 'bg-danger'
                    )}
                    style={{
                      width: `${Math.min(100, Math.max(0, compliance.percentage))}%`,
                    }}
                  />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {t('coach.now.compliance.completed', {
                    completed: compliance.completed,
                    planned: compliance.planned,
                  })}
                </div>
              </Card>
            ) : null}

            <section className="flex flex-col gap-3">
              {(() => {
                const total = data?.recent_feedback?.length ?? 0;
                const totalPages = Math.max(1, Math.ceil(total / feedbackPageSize));
                const safePage = Math.min(Math.max(1, feedbackPage), totalPages);
                const start = (safePage - 1) * feedbackPageSize;
                const end = Math.min(start + feedbackPageSize, total);
                const shown = total === 0 ? 0 : end - start;
                const items = data?.recent_feedback?.slice(start, end) ?? [];
                const showPagination = total > 3;

                return (
                  <>
                    <div className="flex flex-col gap-1">
                      <h2 className="text-lg font-semibold tracking-tight">
                        {t('coach.feedback.title')}
                      </h2>
                      {total > 0 ? (
                        <p className="text-xs text-muted-foreground">
                          {t('coach.feedback.subtitle', {
                            shown,
                            total,
                          })}
                        </p>
                      ) : null}
                    </div>

                    {total === 0 ? (
                      <EmptyState
                        illustration="feedback"
                        title={t('coach.feedback.emptyTitle')}
                        description={t('coach.feedback.emptyDescription')}
                      />
                    ) : (
                      <div className="flex flex-col gap-3">
                        {items.map((item) => (
                          <FeedbackCard key={item.activity_id} item={item} />
                        ))}
                        {showPagination ? (
                          <Card variant="flat" padding="sm">
                            <Pagination
                              total={total}
                              page={safePage}
                              pageSize={feedbackPageSize}
                              onPageChange={setFeedbackPage}
                              onPageSizeChange={(size) => {
                                setFeedbackPageSize(size);
                                setFeedbackPage(1);
                                if (typeof window !== 'undefined') {
                                  window.localStorage.setItem(
                                    FEEDBACK_PAGE_SIZE_KEY,
                                    String(size),
                                  );
                                }
                              }}
                            />
                          </Card>
                        ) : null}
                      </div>
                    )}
                  </>
                );
              })()}
            </section>

          </div>
        </TabsContent>

        {/* TAB: TRENDS */}
        <TabsContent value="trends">
          <div className="flex flex-col gap-6">
            {loading ? (
              <Card variant="default" padding="lg">
                <p className="text-sm text-muted-foreground">
                  {t('coach.charts.loading')}
                </p>
              </Card>
            ) : !trends ? (
              <Card variant="flat" padding="md">
                <p className="text-sm text-muted-foreground">
                  {t('coach.charts.empty')}
                </p>
              </Card>
            ) : (
              <>
                <Card variant="default" padding="lg">
                  <div className="mb-4 flex flex-col gap-0.5">
                    <div className="flex items-center gap-1.5">
                      <h2 className="text-lg font-semibold tracking-tight">
                        {t('coach.charts.volume.title')}
                      </h2>
                      <InfoTooltip i18nKey="coach.charts.volume" />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {t('coach.charts.last4Weeks')}
                    </span>
                  </div>
                  <div
                    role="img"
                    aria-label={t('coach.charts.volume.chartSummary', {
                      values: volumeChartData
                        .map((point) => `${point.week}: ${point.km} ${t('coach.chart.kmUnit')}`)
                        .join(', '),
                    })}
                  >
                    <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={volumeChartData}
                      margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid
                        horizontal
                        vertical={false}
                        strokeDasharray="3 3"
                        stroke={chartTheme.gridColor}
                      />
                      <XAxis
                        dataKey="week"
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={{ stroke: chartTheme.gridColor }}
                      />
                      <YAxis
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: number) => `${v}`}
                      />
                      <Tooltip
                        cursor={{ fill: chartTheme.gridColor, opacity: 0.3 }}
                        content={
                          <ChartTooltip
                            valueFormatter={(v) =>
                              `${v} ${t('coach.chart.kmUnit')}`
                            }
                            subtextFormatter={(payload) => {
                              const entry = payload[0];
                              if (!entry) return null;
                              const value = Number(entry.value);
                              if (!Number.isFinite(value) || value === 0) {
                                return t('coach.chart.zeroLabel');
                              }
                              if (
                                volumeMax.max > 0 &&
                                value === volumeMax.max
                              ) {
                                return `${t('coach.chart.peakLabel')} - ${Math.round(value)} ${t('coach.chart.kmUnit')}`;
                              }
                              return null;
                            }}
                          />
                        }
                      />
                      <Bar
                        dataKey="km"
                        name={t('coach.chart.legendVolume')}
                        radius={[8, 8, 0, 0]}
                        animationDuration={500}
                        animationEasing="ease-out"
                        isAnimationActive
                      >
                        {volumeChartData.map((entry, idx) => (
                          <Cell
                            key={`vol-${idx}`}
                            fill={
                              entry.km > 0 &&
                              volumeMax.max > 0 &&
                              entry.km === volumeMax.max
                                ? chartTheme.primaryColor
                                : `${chartTheme.primaryColor}99`
                            }
                          />
                        ))}
                      </Bar>
                      {volumeMax.idx >= 0 && volumeMax.max > 0 ? (
                        <ReferenceDot
                          x={weekLabels[volumeMax.idx]}
                          y={volumeMax.max}
                          r={4}
                          fill={chartTheme.primaryColor}
                          stroke={chartTheme.tooltipBg}
                          strokeWidth={2}
                          ifOverflow="extendDomain"
                        />
                      ) : null}
                    </BarChart>
                  </ResponsiveContainer>
                  </div>
                </Card>

                {volumeInsight ? (
                  <Card variant="flat" padding="sm">
                    <div className="flex items-start gap-2.5">
                      <Sparkles
                        className="h-4 w-4 text-primary mt-0.5 flex-shrink-0"
                        aria-hidden="true"
                      />
                      <p className="text-sm leading-relaxed">{volumeInsight}</p>
                    </div>
                  </Card>
                ) : null}

                <Card variant="default" padding="lg">
                  <div className="mb-4 flex flex-col gap-0.5">
                    <div className="flex items-center gap-1.5">
                      <h2 className="text-lg font-semibold tracking-tight">
                        {t('coach.charts.pace.title')}
                      </h2>
                      <InfoTooltip i18nKey="coach.charts.pace" />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {t('coach.charts.lowerIsFaster')}
                    </span>
                  </div>
                  <div
                    role="img"
                    aria-label={t('coach.charts.pace.chartSummary', {
                      values: paceChartData
                        .map((point) => `${point.week}: ${formatPace(point.paceSec ?? 0)}${t('coach.chart.paceUnit')}`)
                        .join(', '),
                    })}
                  >
                    <ResponsiveContainer width="100%" height={240}>
                    <LineChart
                      data={paceChartData}
                      margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid
                        horizontal
                        vertical={false}
                        strokeDasharray="3 3"
                        stroke={chartTheme.gridColor}
                      />
                      <XAxis
                        dataKey="week"
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={{ stroke: chartTheme.gridColor }}
                      />
                      <YAxis
                        reversed
                        domain={[Math.max(0, paceMin - 15), paceMax + 15]}
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: number) => formatPace(v)}
                      />
                      <Tooltip
                        cursor={{ stroke: chartTheme.gridColor }}
                        content={
                          <ChartTooltip
                            valueFormatter={(v) =>
                              typeof v === 'number'
                                ? `${formatPace(v)}${t('coach.chart.paceUnit')}`
                                : String(v)
                            }
                            subtextFormatter={(payload, label) => {
                              const entry = payload[0];
                              if (!entry) return null;
                              const value = Number(entry.value);
                              if (!Number.isFinite(value) || value <= 0) return null;
                              const idx = paceChartData.findIndex(
                                (p) => p.week === label,
                              );
                              if (idx <= 0) return null;
                              const prev = paceChartData[idx - 1].paceSec;
                              if (!prev || prev <= 0) return null;
                              const diff = Math.round(prev - value);
                              if (diff > 0) {
                                return t('coach.chart.fasterByPrevWeek', { diff });
                              }
                              if (diff < 0) {
                                return t('coach.chart.slowerByPrevWeek', {
                                  diff: -diff,
                                });
                              }
                              return t('coach.chart.samePace');
                            }}
                          />
                        }
                      />
                      {paceAvgSec !== null ? (
                        <ReferenceLine
                          y={paceAvgSec}
                          stroke={chartTheme.mutedColor}
                          strokeDasharray="3 3"
                          label={{
                            value: `${t('coach.chart.averageLabel')} ${formatPace(paceAvgSec)}`,
                            position: 'insideTopRight',
                            fill: chartTheme.mutedColor,
                            fontSize: 10,
                            fontFamily: 'var(--font-mono)',
                          }}
                        />
                      ) : null}
                      <Line
                        type="monotone"
                        dataKey="paceSec"
                        name={t('coach.chart.legendPace')}
                        stroke={chartTheme.successColor}
                        strokeWidth={2.5}
                        dot={{
                          r: 4,
                          fill: chartTheme.primaryColor,
                          stroke: chartTheme.primaryColor,
                        }}
                        activeDot={{ r: 6, fill: chartTheme.primaryColor }}
                        connectNulls
                        animationDuration={700}
                        animationEasing="ease-out"
                        isAnimationActive
                      />
                    </LineChart>
                  </ResponsiveContainer>
                  </div>
                </Card>

                {paceInsight ? (
                  <Card variant="flat" padding="sm">
                    <div className="flex items-start gap-2.5">
                      <Sparkles
                        className="h-4 w-4 text-primary mt-0.5 flex-shrink-0"
                        aria-hidden="true"
                      />
                      <p className="text-sm leading-relaxed">{paceInsight}</p>
                    </div>
                  </Card>
                ) : null}

                {(intervalPaces.length > 0 || efPaces.length > 0) ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {intervalPaces.length > 0 ? (
                      <Card variant="default" padding="md">
                        <div className="mb-3 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Flame
                              className="h-4 w-4 text-primary"
                              aria-hidden="true"
                            />
                            <h3 className="text-sm font-semibold">
                              {t('coach.charts.intervalPace.title')}
                            </h3>
                            <InfoTooltip i18nKey="coach.charts.intervalPace" />
                          </div>
                        </div>
                        {intervalPaces.length < 3 ? (
                          <div className="flex items-center justify-center h-[160px] text-xs text-muted-foreground text-center px-4">
                            {t('coach.charts.notEnoughData')}
                          </div>
                        ) : (
                        <div
                          role="img"
                          aria-label={t('coach.charts.intervalPace.chartSummary', {
                            count: intervalPaces.length,
                            values: intervalPaces
                              .map((point) => `${formatShortDate(point.date, locale)}: ${point.pace}${t('coach.chart.paceUnit')}`)
                              .join(', '),
                          })}
                        >
                          <ResponsiveContainer width="100%" height={160}>
                          <LineChart
                            data={intervalPaces.map((p) => ({
                              date: p.date,
                              paceSec: p.pace_sec,
                            }))}
                            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                          >
                            <CartesianGrid
                              horizontal
                              vertical={false}
                              strokeDasharray="3 3"
                              stroke={chartTheme.gridColor}
                            />
                            <XAxis
                              dataKey="date"
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: string) => formatShortDate(v, locale)}
                              minTickGap={16}
                            />
                            <YAxis
                              reversed
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: number) => formatPace(v)}
                              width={40}
                              domain={intervalPaceDomain}
                              ticks={intervalPaceTicks}
                              allowDecimals={false}
                            />
                            <Tooltip
                              content={
                                <ChartTooltip
                                  valueFormatter={(v) =>
                                    typeof v === 'number'
                                      ? `${formatPace(v)}${t('coach.chart.paceUnit')}`
                                      : String(v)
                                  }
                                />
                              }
                            />
                            <Line
                              type="monotone"
                              dataKey="paceSec"
                              name={t('coach.chart.legendPace')}
                              stroke={chartTheme.primaryColor}
                              strokeWidth={2}
                              dot={{ r: 3, fill: chartTheme.primaryColor }}
                              animationDuration={600}
                              animationEasing="ease-out"
                              isAnimationActive
                            />
                          </LineChart>
                        </ResponsiveContainer>
                        </div>
                        )}
                        <p className="mt-2 text-xs text-muted-foreground">
                          {t('coach.charts.lowerIsFaster')}
                        </p>
                        {intervalInsight ? (
                          <div className="mt-3 flex items-start gap-2 rounded-md bg-surface px-2.5 py-1.5">
                            <Sparkles
                              className="h-3.5 w-3.5 text-primary mt-0.5 flex-shrink-0"
                              aria-hidden="true"
                            />
                            <p className="text-xs leading-relaxed">
                              {intervalInsight}
                            </p>
                          </div>
                        ) : null}
                      </Card>
                    ) : null}

                    {efPaces.length > 0 ? (
                      <Card variant="default" padding="md">
                        <div className="mb-3 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Footprints
                              className="h-4 w-4 text-success"
                              aria-hidden="true"
                            />
                            <h3 className="text-sm font-semibold">
                              {t('coach.charts.efPace.title')}
                            </h3>
                            <InfoTooltip i18nKey="coach.charts.efPace" />
                          </div>
                          {efAvgHr !== null ? (
                            <Badge variant="outline" size="sm">
                              {t('coach.charts.efPace.avgHr', { hr: efAvgHr })}
                            </Badge>
                          ) : null}
                        </div>
                        {efPaces.length < 3 ? (
                          <div className="flex items-center justify-center h-[160px] text-xs text-muted-foreground text-center px-4">
                            {t('coach.charts.notEnoughData')}
                          </div>
                        ) : (
                        <div
                          role="img"
                          aria-label={t('coach.charts.efPace.chartSummary', {
                            count: efPaces.length,
                            values: efPaces
                              .map((point) => `${formatShortDate(point.date, locale)}: ${point.pace}${t('coach.chart.paceUnit')}`)
                              .join(', '),
                          })}
                        >
                          <ResponsiveContainer width="100%" height={160}>
                          <LineChart
                            data={efPaces.map((p) => ({
                              date: p.date,
                              paceSec: p.pace_sec,
                            }))}
                            margin={{ top: 4, right: 4, bottom: 0, left: 0 }}
                          >
                            <CartesianGrid
                              horizontal
                              vertical={false}
                              strokeDasharray="3 3"
                              stroke={chartTheme.gridColor}
                            />
                            <XAxis
                              dataKey="date"
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: string) => formatShortDate(v, locale)}
                              minTickGap={16}
                            />
                            <YAxis
                              reversed
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: number) => formatPace(v)}
                              width={40}
                              domain={efPaceDomain}
                              ticks={efPaceTicks}
                              allowDecimals={false}
                            />
                            <Tooltip
                              content={
                                <ChartTooltip
                                  valueFormatter={(v) =>
                                    typeof v === 'number'
                                      ? `${formatPace(v)}${t('coach.chart.paceUnit')}`
                                      : String(v)
                                  }
                                />
                              }
                            />
                            <Line
                              type="monotone"
                              dataKey="paceSec"
                              name={t('coach.chart.legendPace')}
                              stroke={chartTheme.successColor}
                              strokeWidth={2}
                              dot={{ r: 3, fill: chartTheme.successColor }}
                              animationDuration={600}
                              animationEasing="ease-out"
                              isAnimationActive
                            />
                          </LineChart>
                        </ResponsiveContainer>
                        </div>
                        )}
                        <p className="mt-2 text-xs text-muted-foreground">
                          {t('coach.charts.efPace.aerobicHint')}
                        </p>
                        {efInsight ? (
                          <div className="mt-3 flex items-start gap-2 rounded-md bg-surface px-2.5 py-1.5">
                            <Sparkles
                              className="h-3.5 w-3.5 text-primary mt-0.5 flex-shrink-0"
                              aria-hidden="true"
                            />
                            <p className="text-xs leading-relaxed">{efInsight}</p>
                          </div>
                        ) : null}
                      </Card>
                    ) : null}
                  </div>
                ) : null}

                {/* Each strength block is isolated: a throwing block shows a
                    compact "block unavailable" card while its siblings render.
                    resetKey = the fetched summary reference (stable per fetch). */}
                {/* Strength progression charts (per exercise, weight/volume/e1rm) */}
                {(trends?.strength_progression?.length ?? 0) > 0 && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <StrengthProgression
                      data={trends!.strength_progression!}
                      locale={locale}
                    />
                  </ErrorBoundary>
                )}

                {/* Per-session totals: tonnage, sets, reps */}
                {(trends?.strength_sessions?.length ?? 0) > 0 && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <StrengthSessionTotals
                      data={trends!.strength_sessions!}
                      locale={locale}
                    />
                  </ErrorBoundary>
                )}

                {/* Weekly sets per muscle group (stacked logged vs Campus plan) */}
                {hasWeeklySets(trends?.strength_insights) && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <StrengthWeeklyGroups
                      insights={trends!.strength_insights!}
                    />
                  </ErrorBoundary>
                )}

                {/* Records table */}
                {(trends?.strength_insights?.records?.length ?? 0) > 0 && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <StrengthRecordsTable
                      insights={trends!.strength_insights!}
                      locale={locale}
                    />
                  </ErrorBoundary>
                )}

                {/* Push / pull balance */}
                {hasPushPull(trends?.strength_insights) && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <StrengthPushPull
                      insights={trends!.strength_insights!}
                    />
                  </ErrorBoundary>
                )}

                {/* Strength History */}
                {(trends?.strength_history?.length ?? 0) > 0 && (
                  <ErrorBoundary
                    resetKey={data}
                    fallback={
                      <Card padding="md">
                        <p className="text-xs text-muted-foreground">
                          {t('coach.strength.block.unavailable')}
                        </p>
                      </Card>
                    }
                  >
                    <Card padding="md">
                      <h3 className="flex items-center gap-1.5 text-sm font-semibold mb-3">
                        <Dumbbell className="h-4 w-4 text-primary" aria-hidden="true" />
                        {t('coach.strength.historyTitle')}
                      </h3>
                      <div className="space-y-2">
                        {trends!.strength_history!.map((entry, i) => (
                          <div key={i} className="flex items-start gap-3 text-xs border-b border-border/50 pb-2 last:border-0">
                            <span className="text-muted-foreground whitespace-nowrap font-medium">
                              {new Date(entry.date).toLocaleDateString(locale, { day: 'numeric', month: 'short' })}
                            </span>
                            <span className="text-foreground leading-relaxed">{entry.description}</span>
                          </div>
                        ))}
                      </div>
                      {(trends?.strength_history?.length ?? 0) < 3 && (
                        <p className="mt-3 text-xs text-muted-foreground italic">
                          {t('coach.strength.historyHint')}
                        </p>
                      )}
                    </Card>
                  </ErrorBoundary>
                )}

                {rampInsight && rampInsight.tone === 'warning' ? (
                  <Alert variant="warning">{rampInsight.text}</Alert>
                ) : rampInsight ? (
                  <Card variant="flat" padding="sm">
                    <div className="flex items-start gap-2.5">
                      <Sparkles
                        className={cn(
                          'h-4 w-4 mt-0.5 flex-shrink-0',
                          rampInsight.tone === 'info' && 'text-primary',
                          rampInsight.tone === 'muted' && 'text-muted-foreground',
                        )}
                        aria-hidden="true"
                      />
                      <p className="text-sm leading-relaxed">{rampInsight.text}</p>
                    </div>
                  </Card>
                ) : null}
              </>
            )}
          </div>
        </TabsContent>

        {/* TAB: CHAT */}
        <TabsContent value="chat">
          <CoachChat />
        </TabsContent>
      </Tabs>

      {/* Suppress unused i18n warning */}
      <span className="hidden">{t('coach.title')}</span>
    </div>
  );
}
