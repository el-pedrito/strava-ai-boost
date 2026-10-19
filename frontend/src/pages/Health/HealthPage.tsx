/**
 * Santé: the detailed view behind the Home "Récupération" card. Readiness for
 * today (four signals), one chart per metric over 30 or 90 days, the training
 * load with its data-trust warning, then VO2max and weight. Same data as the
 * Home (`GET /home/summary`); recharts is lazy-loaded inside the page so the
 * readiness card paints before the chart chunk arrives.
 */
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { Alert, Button, EmptyState } from '@/ui';
import { cn } from '@/lib/cn';
import { ApiError, getHomeSummary } from '@/api/client';
import type { HomeHealth, HomeSummary } from '@/types/home';
import { formatShortDate } from '../Home/format';
import { detectLoadGaps, filterHrvByLatestKind, gapsAffectingLatest, latestLoadDate } from '../Home/insights';
import { ReadinessCard } from './ReadinessCard';
import { BodyCard } from './BodyCard';
import { bodyTilesVisible } from './body';
import { fillDailySeries, lastDays, newestAsOf, RANGES, type RangeDays } from './series';

const HealthCharts = lazy(() => import('./HealthCharts'));

const RENDERED_KEYS = ['hrv', 'resting_hr', 'sleep_s', 'form', 'ctl', 'atl', 'vo2max', 'weight'] as const;

function hasValues(health: HomeHealth | null | undefined): health is HomeHealth {
  return !!health && RENDERED_KEYS.some((k) => health[k]?.value != null);
}

function RangeToggle({ value, onChange }: { value: RangeDays; onChange: (d: RangeDays) => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="group"
      aria-label={t('health.range.label')}
      className="inline-flex rounded-full border border-border bg-surface p-1"
      data-testid="health-range"
    >
      {RANGES.map((d) => (
        <button
          key={d}
          type="button"
          aria-pressed={value === d}
          aria-label={t(`health.range.${d}Long`)}
          onClick={() => onChange(d)}
          className={cn(
            'min-h-11 min-w-16 rounded-full px-4 text-sm font-semibold transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            value === d ? 'bg-foreground text-background' : 'text-foreground hover:bg-muted'
          )}
        >
          {t(`health.range.${d}`)}
        </button>
      ))}
    </div>
  );
}

function ChartsFallback() {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex items-center justify-center gap-3 py-12 text-sm text-muted-foreground">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-primary" aria-hidden="true" />
      {t('health.chart.loading')}
    </div>
  );
}

export function HealthPage() {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'forbidden' | 'generic' | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [range, setRange] = useState<RangeDays>(90);

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

  const rawSeries = data?.health_series ?? null;
  // HRV plots a single kind; every calendar day gets a row so a missing day is a gap.
  const daily = useMemo(() => fillDailySeries(filterHrvByLatestKind(rawSeries ?? [])), [rawSeries]);
  const windowed = useMemo(() => lastDays(daily, range), [daily, range]);
  const allGaps = useMemo(() => detectLoadGaps(rawSeries), [rawSeries]);
  // Same rule as the Home: a gap biases today's freshness for 42 days after it ends.
  const formIncomplete = useMemo(
    () => gapsAffectingLatest(allGaps, latestLoadDate(rawSeries)).length > 0,
    [allGaps, rawSeries]
  );

  const intervalsOn = data?.modules?.intervals_icu ?? false;
  const health = data?.health;
  const asOf = formatShortDate(newestAsOf(health), i18n.language);

  return (
    <div className="flex flex-col gap-5 md:gap-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{t('health.title')}</h1>
          <p className="text-sm text-muted-foreground" data-testid="health-subtitle">
            {asOf ? t('health.subtitle', { date: asOf }) : t('health.subtitleNoDate')}
          </p>
        </div>
        <Button variant="outline" size="md" onClick={reload} disabled={loading} className="min-h-11 shrink-0">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('home.refresh')}
        </Button>
      </div>

      {loading && !data && (
        <div role="status" className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary" aria-hidden="true" />
          {t('health.loading')}
        </div>
      )}

      {error === 'forbidden' && <Alert variant="error">{t('home.error.forbidden')}</Alert>}
      {error === 'generic' && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{t('health.error.load')}</span>
            <Button variant="outline" size="sm" onClick={reload} disabled={loading} className="min-h-11">
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {data && !error && !intervalsOn && (
        <EmptyState
          illustration="connect"
          title={t('home.empty.intervals.title')}
          description={t('home.empty.intervals.description')}
        />
      )}

      {data && !error && intervalsOn && !hasValues(health) && daily.length === 0 && (
        <EmptyState illustration="records" title={t('health.empty.noData.title')} description={t('health.empty.noData.description')} />
      )}

      {data && !error && intervalsOn && (hasValues(health) || daily.length > 0) && (
        <>
          {hasValues(health) && <ReadinessCard health={health} brief={data?.brief} formIncomplete={formIncomplete} />}

          {daily.length > 0 && (
            <section aria-labelledby="health-trends-title" className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 id="health-trends-title" className="text-lg font-semibold tracking-tight text-foreground">
                  {t(`health.range.${range}Long`)}
                </h2>
                <RangeToggle value={range} onChange={setRange} />
              </div>
              <Suspense fallback={<ChartsFallback />}>
                <HealthCharts series={windowed} gaps={allGaps} days={range} />
              </Suspense>
            </section>
          )}

          {hasValues(health) && bodyTilesVisible(health) && <BodyCard health={health} />}
        </>
      )}
    </div>
  );
}
