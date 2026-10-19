/**
 * "Charge et détails": CTL, ATL, VO2max and weight, collapsed by default.
 * The data-trust warning stays visible even when collapsed: when intervals.icu
 * records no load for weeks, CTL / freshness are wrong if the athlete did run,
 * so he must see it before reading those numbers. The caller passes only the
 * gaps that still bias the latest CTL.
 */
import { useId, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ChevronDown, Gauge } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { InfoTooltip } from '@/ui';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import { cn } from '@/lib/cn';
import type { HealthMetric, HealthSeriesPoint, HomeHealth } from '@/types/home';
import { fmtNumber, formatMetric, formatShortDate } from '../format';
import type { LoadGap } from '../insights';
import { HomeCard, Pill, ValueUnit } from './common';
import { INFO_HIT } from './tones';

type LoadKey = 'ctl' | 'atl' | 'vo2max' | 'weight';

const TILES: ReadonlyArray<{ key: LoadKey; label: string; info?: string }> = [
  { key: 'ctl', label: 'home.health.ctl', info: 'metrics.ctl' },
  { key: 'atl', label: 'home.health.atl', info: 'metrics.atl' },
  { key: 'vo2max', label: 'home.health.vo2max', info: 'metrics.vo2max' },
  { key: 'weight', label: 'home.health.weight' },
];

/** The muted data-trust warning, one line per detected gap. */
export function LoadGapWarning({ gaps }: { gaps: ReadonlyArray<LoadGap> }) {
  const { t, i18n } = useTranslation();
  if (gaps.length === 0) return null;
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-sm text-foreground"
      data-testid="home-load-gap-warning"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-text" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        {gaps.map((g) => (
          <p key={g.start}>
            {t('home.load.gapWarning', {
              start: formatShortDate(g.start, i18n.language) ?? g.start,
              end: formatShortDate(g.end, i18n.language) ?? g.end,
            })}
          </p>
        ))}
      </div>
    </div>
  );
}

function LoadTile({ tileKey, label, info, metric }: { tileKey: LoadKey; label: string; info?: string; metric: HealthMetric | null }) {
  const { t, i18n } = useTranslation();
  const value = formatMetric(tileKey, metric?.value, i18n.language);
  const asOf = formatShortDate(metric?.as_of, i18n.language);
  return (
    <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2.5" data-testid={`home-load-${tileKey}`}>
      <div className="flex min-h-5 items-center gap-1">
        <span className="text-xs text-muted-foreground">{t(label)}</span>
        {info && <InfoTooltip i18nKey={info} className={INFO_HIT} />}
        {metric?.stale && (
          <Pill tone="warning" className="ml-auto">
            {t('home.health.stale')}
          </Pill>
        )}
      </div>
      <p className="mt-0.5 text-xl font-semibold leading-tight text-foreground">
        {value ? <ValueUnit value={value.value} unit={value.unit} /> : <span className="text-muted-foreground">{t('home.na')}</span>}
      </p>
      {metric?.stale && asOf && <p className="mt-0.5 text-xs text-muted-foreground">{t('home.asOf', { date: asOf })}</p>}
    </div>
  );
}

export function LoadCard({
  health,
  series,
  gaps,
}: {
  health: HomeHealth;
  series: HealthSeriesPoint[] | null;
  gaps: ReadonlyArray<LoadGap>;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const chartTheme = useChartTheme();
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const data = useMemo(
    () => (series ?? []).map((p) => ({ date: p.date, ctl: p.ctl, atl: p.atl })),
    [series]
  );
  const hasChart = data.filter((p) => p.ctl != null || p.atl != null).length >= 2;
  const fmt = (v: unknown) => fmtNumber(Number(v), 1, lang) ?? String(v);
  const visibleTiles = TILES.filter((tile) => health[tile.key] != null);

  return (
    <HomeCard labelledBy="home-load-title" className="flex flex-col gap-3">
      <h2 id="home-load-title" className="text-lg font-semibold tracking-tight text-foreground">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-11 w-full items-center gap-2 rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Gauge className="h-5 w-5 text-info" aria-hidden="true" />
          <span className="flex-1">{t('home.load.title')}</span>
          <ChevronDown className={cn('h-5 w-5 text-muted-foreground transition-transform', open && 'rotate-180')} aria-hidden="true" />
        </button>
      </h2>

      <LoadGapWarning gaps={gaps} />

      <div id={panelId} hidden={!open} className="flex flex-col gap-4">
        {visibleTiles.length > 0 && (
          <div className="grid grid-cols-2 gap-2">
            {visibleTiles.map((tile) => (
              <LoadTile key={tile.key} tileKey={tile.key} label={tile.label} info={tile.info} metric={health[tile.key]} />
            ))}
          </div>
        )}
        {open && hasChart && (
          <div className="min-w-0">
            <h3 className="mb-2 text-sm font-semibold">{t('home.load.chart')}</h3>
            <div
              role="img"
              aria-label={t('home.load.chartAria', {
                ctl: fmtNumber(health.ctl?.value, 1, lang) ?? t('home.na'),
                atl: fmtNumber(health.atl?.value, 1, lang) ?? t('home.na'),
              })}
            >
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
                  {gaps.map((g) => (
                    <ReferenceArea key={g.start} x1={g.start} x2={g.end} fill="var(--warning)" fillOpacity={0.12} ifOverflow="hidden" />
                  ))}
                  <XAxis
                    dataKey="date"
                    stroke={chartTheme.axisColor}
                    tick={{ fontSize: 12 }}
                    interval="preserveStartEnd"
                    minTickGap={40}
                    tickFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)}
                  />
                  <YAxis stroke={chartTheme.axisColor} tick={{ fontSize: 12 }} width={32} tickFormatter={(v) => fmtNumber(Number(v), 0, lang) ?? ''} />
                  <Tooltip
                    content={
                      <ChartTooltip valueFormatter={fmt} labelFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)} />
                    }
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="ctl" stroke="var(--info)" dot={false} strokeWidth={2} name={t('home.health.ctl')} connectNulls={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="atl" stroke={chartTheme.mutedColor} dot={false} strokeWidth={2} name={t('home.health.atl')} connectNulls={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </HomeCard>
  );
}
