/**
 * "Récupération": the four morning signals (VFC, FC repos, Sommeil, Fraîcheur)
 * as a 2x2, each with its usual value and the coloured difference, plus one
 * small 90-day chart per metric (own scale, a toggle picks the metric). Gaps in
 * the series stay gaps: lines are never connected across missing days.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ChevronRight, HeartPulse } from 'lucide-react';
import { InfoTooltip } from '@/ui';
import { cn } from '@/lib/cn';
import type { HealthMetric, HealthSeriesPoint, HomeHealth } from '@/types/home';
import { formatMetric, formatMetricText, formatShortDate } from '../format';
import { filterHrvByLatestKind, formZone } from '../insights';
import { CardHead, HomeCard, Pill, ValueUnit } from './common';
import { MetricLineChart } from './charts';
import { INFO_HIT } from './tones';
import { UsualLine } from './UsualLine';

type RecoveryKey = 'hrv' | 'resting_hr' | 'sleep_s' | 'form';
type ChartKey = 'hrv' | 'resting_hr' | 'sleep_s';

const TILES: ReadonlyArray<{ key: RecoveryKey; label: string; info: string }> = [
  { key: 'hrv', label: 'home.health.hrv', info: 'metrics.hrv' },
  { key: 'resting_hr', label: 'home.health.restingHr', info: 'metrics.restinghr' },
  { key: 'sleep_s', label: 'home.health.sleep', info: 'metrics.sleep' },
  { key: 'form', label: 'home.health.form', info: 'metrics.tsb' },
];

const CHART_KEYS: ReadonlyArray<{ key: ChartKey; label: string }> = [
  { key: 'hrv', label: 'home.health.hrv' },
  { key: 'resting_hr', label: 'home.health.restingHr' },
  { key: 'sleep_s', label: 'home.health.sleep' },
];

function RecoveryTile({
  tileKey,
  label,
  info,
  metric,
  formIncomplete,
}: {
  tileKey: RecoveryKey;
  label: string;
  info: string;
  metric: HealthMetric | null;
  formIncomplete: boolean;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const value = formatMetric(tileKey, metric?.value, lang);
  const zone = tileKey === 'form' ? formZone(metric?.value) : null;

  return (
    <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2.5" data-testid={`home-recovery-${tileKey}`}>
      <div className="flex min-h-5 items-center gap-1">
        <span className="text-xs text-muted-foreground">{t(label)}</span>
        <InfoTooltip i18nKey={info} className={INFO_HIT} />
        {metric?.stale && (
          <Pill tone="warning" className="ml-auto">
            {t('home.health.stale')}
          </Pill>
        )}
      </div>
      <p className="mt-0.5 text-2xl font-semibold leading-tight text-foreground">
        {value ? <ValueUnit value={value.value} unit={value.unit} /> : <span className="text-muted-foreground">{t('home.na')}</span>}
      </p>
      {metric && tileKey !== 'form' && <UsualLine metricKey={tileKey} metric={metric} />}
      {tileKey === 'form' && formIncomplete && value && (
        <p className="mt-1 text-xs font-semibold text-warning-text">{t('home.recovery.formIncomplete')}</p>
      )}
      {tileKey === 'form' && !formIncomplete && zone && (
        <p className="mt-1 text-xs text-muted-foreground">{t(`home.recovery.formZone.${zone}`)}</p>
      )}
    </div>
  );
}

function MetricChart({ series }: { series: HealthSeriesPoint[] }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [metric, setMetric] = useState<ChartKey>('hrv');

  // HRV must plot a single kind (SDNN and rMSSD live on different scales).
  const data = useMemo(
    () =>
      filterHrvByLatestKind(series).map((p) => ({
        date: p.date,
        hrv: p.hrv,
        resting_hr: p.resting_hr,
        sleep_s: p.sleep_s,
      })),
    [series]
  );
  const points = data.filter((p) => p[metric] != null);
  const last = points.length > 0 ? points[points.length - 1][metric] : null;
  const label = t(CHART_KEYS.find((c) => c.key === metric)!.label);
  const fmt = (v: unknown) => formatMetricText(metric, Number(v), lang) ?? String(v);

  return (
    <div className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{t('home.health.chart90d')}</h3>
        <div role="group" aria-label={t('home.recovery.metricPicker')} className="ml-auto flex flex-wrap gap-1">
          {CHART_KEYS.map((c) => (
            <button
              key={c.key}
              type="button"
              aria-pressed={metric === c.key}
              onClick={() => setMetric(c.key)}
              className={cn(
                'min-h-11 rounded-full border px-3 text-xs font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                metric === c.key
                  ? 'border-foreground bg-foreground text-background'
                  : 'border-border bg-surface text-foreground hover:bg-muted'
              )}
            >
              {t(c.label)}
            </button>
          ))}
        </div>
      </div>
      {points.length < 2 ? (
        <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          {t('home.recovery.noHistory')}
        </p>
      ) : (
        <>
          <div
            role="img"
            aria-label={t('home.recovery.chartAria', { metric: label, count: points.length, last: fmt(last) })}
          >
            <MetricLineChart data={data} metric={metric} label={label} lang={lang} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{t('home.recovery.gapsNote')}</p>
        </>
      )}
    </div>
  );
}

export function RecoveryCard({
  health,
  series,
  formIncomplete,
}: {
  health: HomeHealth;
  series: HealthSeriesPoint[] | null;
  /** True when a load gap still biases today's freshness. */
  formIncomplete: boolean;
}) {
  const { t, i18n } = useTranslation();
  const dates = TILES.map((tile) => health[tile.key]?.as_of).filter((d): d is string => !!d).sort();
  const measuredOn = formatShortDate(dates[dates.length - 1], i18n.language);

  return (
    <HomeCard labelledBy="home-recovery-title" className="flex flex-col gap-4">
      <CardHead
        id="home-recovery-title"
        icon={<HeartPulse className="h-5 w-5 text-info" aria-hidden="true" />}
        title={
          <Link
            to="/health"
            className="group inline-flex min-h-11 items-center gap-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            data-testid="home-recovery-health-link"
          >
            <span className="group-hover:underline">{t('home.recovery.title')}</span>
            <span className="inline-flex items-center text-sm font-medium text-muted-foreground group-hover:text-foreground">
              {t('home.recovery.seeHealth')}
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </span>
          </Link>
        }
      >
        {measuredOn && (
          <span className="ml-auto text-xs text-muted-foreground">{t('home.recovery.measuredOn', { date: measuredOn })}</span>
        )}
      </CardHead>
      <div className="grid grid-cols-2 gap-2">
        {TILES.map((tile) => (
          <RecoveryTile
            key={tile.key}
            tileKey={tile.key}
            label={tile.label}
            info={tile.info}
            metric={health[tile.key]}
            formIncomplete={formIncomplete}
          />
        ))}
      </div>
      {series && series.length > 0 && <MetricChart series={series} />}
    </HomeCard>
  );
}
