import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  CalendarDays,
  CloudSun,
  Flag,
  HeartPulse,
  RefreshCw,
  Trophy,
} from 'lucide-react';
import { Alert, Badge, Button, Card, EmptyState, InfoTooltip } from '@/ui';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import { cn } from '@/lib/cn';
import { ApiError, getHomeSummary } from '@/api/client';
import type {
  BriefLight,
  HealthMetric,
  HomeHealth,
  HomeSummary,
  SignalStatus,
} from '@/types/home';
import {
  formatClock,
  formatDayMonth,
  formatDuration,
  formatPace,
  formatRange,
  formatSleep,
  num,
} from './format';

/* ------------------------------------------------------------------ helpers */

/** "au JJ/MM" suffix, or empty string when the date is missing. */
function AsOf({ date }: { date: string | null | undefined }) {
  const { t } = useTranslation();
  const dm = formatDayMonth(date);
  if (!dm) return null;
  return <span className="text-xs text-muted-foreground">{t('home.asOf', { date: dm })}</span>;
}

const LIGHT_TONE: Record<BriefLight, string> = {
  green: 'bg-success/10 border-success/30 text-success',
  orange: 'bg-warning/10 border-warning/30 text-warning',
  red: 'bg-danger/10 border-danger/30 text-danger',
  unknown: 'bg-muted border-border text-muted-foreground',
};

const LIGHT_DOT: Record<BriefLight, string> = {
  green: 'bg-success',
  orange: 'bg-warning',
  red: 'bg-danger',
  unknown: 'bg-muted-foreground',
};

const SIGNAL_BADGE: Record<SignalStatus, 'success' | 'warning' | 'danger' | 'default'> = {
  ok: 'success',
  warn: 'warning',
  bad: 'danger',
  missing: 'default',
};

function toLight(light: string): BriefLight {
  return light === 'green' || light === 'orange' || light === 'red' ? light : 'unknown';
}

/* -------------------------------------------------------------- Brief block */

function BriefBlock({ brief }: { brief: NonNullable<HomeSummary['brief']> }) {
  const { t } = useTranslation();
  const light = toLight(brief.light);
  const builtAt = formatClock(brief.built_at);
  const signals = brief.signals ?? [];
  const missing = brief.missing ?? [];
  const weather = brief.weather ?? [];

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-brief-title">
      <div className="flex items-center gap-2">
        <span className={cn('h-3 w-3 shrink-0 rounded-full', LIGHT_DOT[light])} aria-hidden="true" />
        <h2 id="home-brief-title" className="text-lg font-semibold tracking-tight">
          {t('home.brief.title')}
        </h2>
        <span className={cn('ml-auto rounded-full border px-2.5 py-0.5 text-xs font-medium', LIGHT_TONE[light])}>
          {t(`home.brief.light.${light}`)}
        </span>
      </div>

      {signals.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2">
          {signals.map((s) => {
            const status = (['ok', 'warn', 'bad', 'missing'].includes(s.status) ? s.status : 'missing') as SignalStatus;
            return (
              <li key={s.key} className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant={SIGNAL_BADGE[status]} size="sm">
                  {t(`home.brief.signal.${s.key}`, { defaultValue: s.key })}
                </Badge>
                <span className="font-numeric font-medium text-foreground">
                  {num(s.value, 1) ?? t('home.na')}
                </span>
                {s.baseline != null && (
                  <span className="text-xs text-muted-foreground">
                    {t('home.brief.baseline', { value: num(s.baseline, 1) })}
                  </span>
                )}
                <AsOf date={s.as_of} />
              </li>
            );
          })}
        </ul>
      )}

      {missing.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          {t('home.brief.missing', { list: missing.join(', ') })}
        </p>
      )}

      {brief.next_session?.title && (
        <p className="mt-3 text-sm">
          <span className="text-muted-foreground">{t('home.brief.nextSession')}: </span>
          <span className="font-medium">{brief.next_session.title}</span>
          {brief.next_session.duration_min != null && (
            <span className="text-muted-foreground"> · {t('home.minutes', { value: brief.next_session.duration_min })}</span>
          )}
        </p>
      )}

      {weather.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <CloudSun className="h-4 w-4" aria-hidden="true" />
            {t('home.brief.weather')}
          </div>
          <ul className="mt-2 flex flex-wrap gap-4">
            {weather.map((w) => (
              <li key={w.slot} className="text-sm">
                <span className="font-medium">{w.slot}</span>{' '}
                <span className="text-muted-foreground">
                  {num(w.temp_c, 0) != null ? t('home.brief.temp', { value: num(w.temp_c, 0) }) : t('home.na')}
                  {w.wind_kmh != null && ` · ${t('home.brief.wind', { value: num(w.wind_kmh, 0) })}`}
                  {w.precip_mm != null && ` · ${t('home.brief.precip', { value: num(w.precip_mm, 1) })}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {builtAt && <span>{t('home.brief.builtAt', { time: builtAt })}</span>}
        {brief.weather_attribution && weather.length > 0 && <span>{brief.weather_attribution}</span>}
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------- Race block */

function RaceBlock({ race }: { race: NonNullable<HomeSummary['race']> }) {
  const { t } = useTranslation();
  const target = formatDuration(race.target_time_s);
  const predicted = formatDuration(race.predicted_time_s);
  const range = formatRange(race.predicted_range_s);

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-race-title">
      <div className="flex items-center gap-2">
        <Trophy className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 id="home-race-title" className="text-lg font-semibold tracking-tight">
          {race.name ?? t('home.race.title')}
        </h2>
        {race.days_left != null && (
          <Badge variant="primary" size="md" className="ml-auto">
            {t('home.race.daysLeft', { count: race.days_left })}
          </Badge>
        )}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {target && (
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t('home.race.target')}</p>
            <p className="font-numeric text-2xl font-semibold">{target}</p>
          </div>
        )}
        {predicted && (
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">{t('home.race.predicted')}</p>
            <p className="font-numeric text-2xl font-semibold">{predicted}</p>
            {range && (
              <p className="text-xs text-muted-foreground">
                {t('home.estimation')}: {range}
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------- Plan block */

function PlanBlock({ plan }: { plan: NonNullable<HomeSummary['plan']> }) {
  const { t } = useTranslation();
  const expected = plan.week_km_expected ?? 0;
  const real = plan.week_km_real ?? 0;
  const pct = expected > 0 ? Math.min(100, Math.round((real / expected) * 100)) : 0;
  const volLow = plan.weekly_volume_low;
  const volHigh = plan.weekly_volume_high;

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-plan-title">
      <div className="flex items-center gap-2">
        <Flag className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 id="home-plan-title" className="text-lg font-semibold tracking-tight">
          {t('home.plan.title')}
        </h2>
        {plan.week_index != null && plan.weeks_total != null && (
          <Badge variant="default" size="md" className="ml-auto">
            {t('home.plan.week', { index: plan.week_index, total: plan.weeks_total })}
          </Badge>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {plan.cycle_theme && (
          <span className="text-muted-foreground">
            {t('home.plan.cycle')}: <span className="font-medium text-foreground">{plan.cycle_theme}</span>
          </span>
        )}
        {plan.trainings_done != null && plan.trainings_total != null && (
          <span className="text-muted-foreground">
            {t('home.plan.trainings')}:{' '}
            <span className="font-medium text-foreground">
              {plan.trainings_done}/{plan.trainings_total}
            </span>
          </span>
        )}
      </div>

      <div className="mt-4">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-muted-foreground">{t('home.plan.weekKm')}</span>
          <span className="font-numeric font-medium">
            {t('home.plan.kmRealExpected', {
              real: num(real, 1) ?? '0',
              expected: num(expected, 1) ?? '0',
            })}
          </span>
        </div>
        <div className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-muted" role="presentation">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {volLow != null && volHigh != null && (
        <p className="mt-3 text-xs text-muted-foreground">
          {t('home.plan.volumeRange', { low: volLow, high: volHigh })}
        </p>
      )}
    </Card>
  );
}

/* --------------------------------------------------------- This-week block */

const SESSION_CHIP: Record<string, 'success' | 'warning' | 'danger' | 'default'> = {
  done: 'success',
  todo: 'default',
  missed: 'danger',
};

function WeekSessionsBlock({
  sessions,
  nextOrder,
}: {
  sessions: NonNullable<HomeSummary['week_sessions']>;
  nextOrder: number | null;
}) {
  const { t } = useTranslation();
  const ordered = [...sessions].sort((a, b) => a.order - b.order);

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-week-title">
      <div className="flex items-center gap-2">
        <CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 id="home-week-title" className="text-lg font-semibold tracking-tight">
          {t('home.week.title')}
        </h2>
      </div>
      <ul className="mt-4 flex flex-col gap-2">
        {ordered.map((s) => {
          const isNext = nextOrder != null && s.order === nextOrder;
          const chip = SESSION_CHIP[s.status] ?? 'default';
          return (
            <li
              key={s.order}
              data-testid="home-week-session"
              data-next={isNext ? 'true' : undefined}
              className={cn(
                'flex items-center gap-2 rounded-lg border p-2.5 text-sm',
                isNext ? 'border-primary/40 bg-primary/5' : 'border-border'
              )}
            >
              <span className="font-numeric text-xs text-muted-foreground">{s.order}</span>
              <span className="font-medium text-foreground">{s.title ?? t('home.week.untitled')}</span>
              {s.duration_min != null && (
                <span className="text-xs text-muted-foreground">{t('home.minutes', { value: s.duration_min })}</span>
              )}
              {isNext && (
                <Badge variant="primary" size="sm" className="ml-auto">
                  {t('home.week.next')}
                </Badge>
              )}
              <Badge variant={chip} size="sm" className={cn(!isNext && 'ml-auto')}>
                {t(`home.week.status.${s.status}`, { defaultValue: s.status })}
              </Badge>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/* ------------------------------------------------------------- Health block */

interface HealthRow {
  key: keyof HomeHealth;
  labelKey: string;
  info?: string;
  render: (m: HealthMetric) => ReactNode;
}

function HealthMetricCell({ row, metric }: { row: HealthRow; metric: HealthMetric }) {
  const { t } = useTranslation();
  const value = row.render(metric);
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-center gap-1">
        <span className="text-xs uppercase tracking-wider text-muted-foreground">{t(row.labelKey)}</span>
        {row.info && <InfoTooltip i18nKey={row.info} />}
        {metric.stale && (
          <Badge variant="warning" size="sm" className="ml-auto">
            {t('home.health.stale')}
          </Badge>
        )}
      </div>
      <p className="mt-1 font-numeric text-xl font-semibold text-foreground">{value ?? t('home.na')}</p>
      <AsOf date={metric.as_of} />
    </div>
  );
}

function HealthBlock({
  health,
  series,
}: {
  health: NonNullable<HomeSummary['health']>;
  series: NonNullable<HomeSummary['health_series']> | null;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();

  const rows: HealthRow[] = [
    {
      key: 'resting_hr',
      labelKey: 'home.health.restingHr',
      info: 'metrics.restinghr',
      render: (m) => (num(m.value, 0) != null ? t('home.units.bpm', { value: num(m.value, 0) }) : null),
    },
    {
      key: 'hrv',
      labelKey: 'home.health.hrv',
      info: 'metrics.hrv',
      render: (m) => {
        const v = num(m.value, 0);
        if (v == null) return null;
        const kind = m.kind ? ` (${String(m.kind).toUpperCase()})` : '';
        return `${v}${kind}`;
      },
    },
    {
      key: 'sleep_s',
      labelKey: 'home.health.sleep',
      info: 'metrics.sleep',
      render: (m) => formatSleep(m.value),
    },
    {
      key: 'form',
      labelKey: 'home.health.form',
      info: 'metrics.tsb',
      render: (m) => num(m.value, 1),
    },
    {
      key: 'ctl',
      labelKey: 'home.health.ctl',
      info: 'metrics.ctl',
      render: (m) => num(m.value, 1),
    },
    {
      key: 'atl',
      labelKey: 'home.health.atl',
      info: 'metrics.atl',
      render: (m) => num(m.value, 1),
    },
    {
      key: 'vo2max',
      labelKey: 'home.health.vo2max',
      info: 'metrics.vo2max',
      render: (m) => num(m.value, 1),
    },
    {
      key: 'weight',
      labelKey: 'home.health.weight',
      render: (m) => (num(m.value, 1) != null ? t('home.units.kg', { value: num(m.value, 1) }) : null),
    },
  ];

  const chartData = useMemo(
    () =>
      (series ?? []).map((p) => ({
        date: formatDayMonth(p.date) ?? p.date,
        resting_hr: p.resting_hr,
        hrv: p.hrv,
        ctl: p.ctl,
        atl: p.atl,
        form: p.form,
      })),
    [series]
  );

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-health-title">
      <div className="flex items-center gap-2">
        <HeartPulse className="h-5 w-5 text-primary" aria-hidden="true" />
        <h2 id="home-health-title" className="text-lg font-semibold tracking-tight">
          {t('home.health.title')}
        </h2>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map((row) => {
          const metric = health[row.key];
          if (!metric) return null;
          return <HealthMetricCell key={row.key} row={row} metric={metric} />;
        })}
      </div>

      {chartData.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold text-muted-foreground">{t('home.health.chart90d')}</p>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
              <XAxis
                dataKey="date"
                stroke={chartTheme.axisColor}
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
                minTickGap={28}
              />
              <YAxis stroke={chartTheme.axisColor} tick={{ fontSize: 10 }} width={32} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="hrv" stroke={chartTheme.primaryColor} dot={false} strokeWidth={2} name={t('home.health.hrv')} connectNulls />
              <Line type="monotone" dataKey="resting_hr" stroke={chartTheme.successColor} dot={false} strokeWidth={2} name={t('home.health.restingHr')} connectNulls />
              <Line type="monotone" dataKey="ctl" stroke={chartTheme.mutedColor} dot={false} strokeWidth={1.5} name={t('home.health.ctl')} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

/* -------------------------------------------------------- Predictions block */

const PRED_LABEL: Record<string, string> = {
  '5km': 'home.predictions.d5k',
  '10km': 'home.predictions.d10k',
  'half-marathon': 'home.predictions.half',
  marathon: 'home.predictions.marathon',
};

function PredictionsBlock({
  predictions,
  history,
}: {
  predictions: NonNullable<HomeSummary['predictions']>;
  history: NonNullable<HomeSummary['predictions_history']> | null;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const items = predictions.items ?? [];

  const historyData = useMemo(
    () =>
      (history ?? [])
        .filter((h) => h.half_marathon_time_s != null)
        .map((h) => ({ week: h.week, time: h.half_marathon_time_s as number })),
    [history]
  );

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-pred-title">
      <h2 id="home-pred-title" className="text-lg font-semibold tracking-tight">
        {t('home.predictions.title')}
      </h2>

      {items.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {items.map((p) => {
            const time = formatDuration(p.time_s);
            const range = formatRange(p.range_s);
            return (
              <div key={p.distance} className="rounded-lg border border-border p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                  {t(PRED_LABEL[p.distance] ?? '', { defaultValue: p.distance })}
                </p>
                <p className="font-numeric text-xl font-semibold">{time ?? t('home.na')}</p>
                {range && <p className="text-[11px] text-muted-foreground">{range}</p>}
              </div>
            );
          })}
        </div>
      )}

      {historyData.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold text-muted-foreground">{t('home.predictions.halfCurve')}</p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={historyData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
              <XAxis dataKey="week" stroke={chartTheme.axisColor} tick={{ fontSize: 10 }} minTickGap={20} />
              <YAxis
                stroke={chartTheme.axisColor}
                tick={{ fontSize: 10 }}
                width={44}
                domain={['dataMin - 60', 'dataMax + 60']}
                tickFormatter={(v) => formatDuration(Number(v)) ?? String(v)}
              />
              <Tooltip
                content={
                  <ChartTooltip valueFormatter={(v) => formatDuration(Number(v)) ?? String(v)} />
                }
              />
              <Line type="monotone" dataKey="time" stroke={chartTheme.primaryColor} dot strokeWidth={2} name={t('home.predictions.half')} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-[11px] text-muted-foreground">{t('home.predictions.historyNote')}</p>
        </div>
      )}
    </Card>
  );
}

/* ----------------------------------------------------------- Enduraw block */

function EndurawBlock({ trend }: { trend: NonNullable<HomeSummary['enduraw_trend']> }) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();

  const data = useMemo(
    () =>
      trend.map((p) => ({
        date: formatDayMonth(p.date) ?? p.date,
        raw: p.raw_pace_s,
        adjusted: p.adjusted_pace_s,
      })),
    [trend]
  );

  return (
    <Card variant="elevated" padding="md" aria-labelledby="home-enduraw-title">
      <h2 id="home-enduraw-title" className="text-lg font-semibold tracking-tight">
        {t('home.enduraw.title')}
      </h2>
      <div className="mt-4">
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
            <XAxis dataKey="date" stroke={chartTheme.axisColor} tick={{ fontSize: 10 }} minTickGap={20} />
            <YAxis
              stroke={chartTheme.axisColor}
              tick={{ fontSize: 10 }}
              width={44}
              reversed
              tickFormatter={(v) => formatPace(Number(v)) ?? String(v)}
            />
            <Tooltip
              content={<ChartTooltip valueFormatter={(v) => formatPace(Number(v)) ?? String(v)} />}
            />
            <Line type="monotone" dataKey="raw" stroke={chartTheme.mutedColor} dot={false} strokeWidth={2} name={t('home.enduraw.raw')} connectNulls />
            <Line type="monotone" dataKey="adjusted" stroke={chartTheme.primaryColor} dot={false} strokeWidth={2} name={t('home.enduraw.adjusted')} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------------- page */

export function HomePage() {
  const { t } = useTranslation();
  const [data, setData] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'forbidden' | 'generic' | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getHomeSummary()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError && e.status === 403 ? 'forbidden' : 'generic');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = () => {
    setError(null);
    setLoading(true);
    setReloadToken((n) => n + 1);
  };

  const modules = data?.modules;
  const intervalsOn = modules?.intervals_icu ?? false;
  const campusOn = modules?.campus_coach ?? false;

  const raceVisible =
    !!data?.race && data.race.active && (data.race.days_left == null || data.race.days_left >= 0);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t('home.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('home.subtitle')}</p>
        </div>
        <Button variant="outline" size="md" onClick={reload} disabled={loading} className="shrink-0">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('home.refresh')}
        </Button>
      </div>

      {loading && !data && (
        <div role="status" className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground">
          <span
            className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary"
            aria-hidden="true"
          />
          {t('home.loading')}
        </div>
      )}

      {error === 'forbidden' && (
        <Alert variant="error">{t('home.error.forbidden')}</Alert>
      )}

      {error === 'generic' && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{t('home.error.load')}</span>
            <Button variant="outline" size="sm" onClick={reload} disabled={loading}>
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {data && !error && (
        <>
          {data.brief && <BriefBlock brief={data.brief} />}

          {raceVisible && data.race && <RaceBlock race={data.race} />}

          {campusOn ? (
            <>
              {data.plan && <PlanBlock plan={data.plan} />}
              {data.week_sessions && data.week_sessions.length > 0 && (
                <WeekSessionsBlock
                  sessions={data.week_sessions}
                  nextOrder={data.next_session?.order ?? null}
                />
              )}
            </>
          ) : (
            <EmptyState
              illustration="connect"
              title={t('home.empty.campus.title')}
              description={t('home.empty.campus.description')}
            />
          )}

          {intervalsOn ? (
            data.health && <HealthBlock health={data.health} series={data.health_series ?? null} />
          ) : (
            <EmptyState
              illustration="connect"
              title={t('home.empty.intervals.title')}
              description={t('home.empty.intervals.description')}
            />
          )}

          {data.predictions && (
            <PredictionsBlock
              predictions={data.predictions}
              history={data.predictions_history ?? null}
            />
          )}

          {data.enduraw_trend && data.enduraw_trend.length > 0 && (
            <EndurawBlock trend={data.enduraw_trend} />
          )}
        </>
      )}
    </div>
  );
}
