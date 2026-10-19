/**
 * The Santé page charts, lazy-loaded so recharts stays out of the page chunk.
 * One chart per metric, each on its own scale and unit: VFC, FC repos,
 * Sommeil, then the training load (CTL and ATL on one unitless scale) and the
 * freshness (TSB) around 0. Load-gap periods are shaded on both load charts,
 * under the existing warning text. Every chart carries a one-line summary for
 * screen readers. Rows are one per calendar day: a null is a gap in the line.
 */
import { useTranslation } from 'react-i18next';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card } from '@/ui';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import type { HealthSeriesPoint } from '@/types/home';
import { fmtNumber, formatMetricText, formatShortDate } from '../Home/format';
import type { LoadGap } from '../Home/insights';
import { LoadLineChart, MetricLineChart, type SeriesMetric } from '../Home/blocks/charts';
import { LoadGapWarning } from '../Home/blocks/LoadCard';
import { clipGaps, overlappingGaps, seriesStats } from './series';

export interface HealthChartsProps {
  /** Daily rows of the selected window (null days included). */
  series: HealthSeriesPoint[];
  /** Every load gap detected on the full series (true dates); clipped here for the shading. */
  gaps: LoadGap[];
  days: number;
}

const METRIC_CHARTS: ReadonlyArray<{ key: SeriesMetric; label: string; unit: string }> = [
  { key: 'hrv', label: 'health.chart.hrv', unit: 'health.chart.unit.hrv' },
  { key: 'resting_hr', label: 'health.chart.restingHr', unit: 'health.chart.unit.restingHr' },
  { key: 'sleep_s', label: 'health.chart.sleep', unit: 'health.chart.unit.sleep' },
];

function ChartCard({ id, title, unit, children }: { id: string; title: string; unit?: string; children: React.ReactNode }) {
  return (
    <Card variant="elevated" padding="none" role="region" aria-labelledby={id} className="min-w-0 p-4 md:p-5">
      <h3 id={id} className="mb-2 text-base font-semibold text-foreground">
        {title}
        {unit && <span className="ml-1.5 text-sm font-normal text-muted-foreground">({unit})</span>}
      </h3>
      {children}
    </Card>
  );
}

function NoData() {
  const { t } = useTranslation();
  return (
    <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
      {t('health.chart.noData')}
    </p>
  );
}

function gapSentences(gaps: ReadonlyArray<LoadGap>, t: (k: string, o?: Record<string, unknown>) => string, lang: string): string {
  return gaps
    .map((g) => t('health.chart.gapShaded', { start: formatShortDate(g.start, lang) ?? g.start, end: formatShortDate(g.end, lang) ?? g.end }))
    .join(' ');
}

function MetricChartCard({ metric, label, unit, series, days }: { metric: SeriesMetric; label: string; unit: string; series: HealthSeriesPoint[]; days: number }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const stats = seriesStats(series, metric);
  const name = t(label);
  const fmt = (v: number | null) => formatMetricText(metric, v, lang) ?? t('home.na');
  const summary =
    stats.count === 0
      ? t('health.chart.summaryEmpty', { metric: name, days })
      : t('health.chart.summary', {
          metric: name,
          days,
          count: stats.count,
          min: fmt(stats.min),
          max: fmt(stats.max),
          last: fmt(stats.last),
          date: formatShortDate(stats.lastDate, lang) ?? '',
        });
  const id = `health-chart-${metric}`;
  return (
    <ChartCard id={`${id}-title`} title={name} unit={t(unit)}>
      {stats.count < 2 ? (
        <>
          <p className="sr-only" data-testid={`${id}-summary`}>{summary}</p>
          <NoData />
        </>
      ) : (
        <div role="img" aria-label={summary} data-testid={id} data-points={stats.count}>
          <MetricLineChart data={series} metric={metric} label={name} lang={lang} height={170} />
        </div>
      )}
    </ChartCard>
  );
}

interface LoadChartProps {
  series: HealthSeriesPoint[];
  /** Gaps with their true dates, for the warning and the summary. */
  named: LoadGap[];
  /** The same gaps trimmed to the window, for the shading. */
  shaded: LoadGap[];
  days: number;
}

function LoadChartCard({ series, named, shaded, days }: LoadChartProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const ctl = seriesStats(series, 'ctl');
  const atl = seriesStats(series, 'atl');
  const hasChart = Math.max(ctl.count, atl.count) >= 2;
  const summary = [
    t('health.chart.loadSummary', {
      days,
      ctl: fmtNumber(ctl.last, 1, lang) ?? t('home.na'),
      atl: fmtNumber(atl.last, 1, lang) ?? t('home.na'),
    }),
    gapSentences(named, t, lang),
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <ChartCard id="health-chart-load-title" title={t('health.chart.load')}>
      <div className="flex flex-col gap-3">
        <LoadGapWarning gaps={named} />
        {hasChart ? (
          <div
            role="img"
            aria-label={summary}
            data-testid="health-chart-load"
            data-gaps={shaded.map((g) => `${g.start}..${g.end}`).join(',')}
          >
            <LoadLineChart
              data={series}
              gaps={shaded}
              ctlName={t('health.chart.ctl')}
              atlName={t('health.chart.atl')}
              lang={lang}
              height={200}
            />
          </div>
        ) : (
          <NoData />
        )}
        <p className="text-xs text-muted-foreground">{t('health.chart.loadNote')}</p>
      </div>
    </ChartCard>
  );
}

function FormChartCard({ series, named, shaded, days }: LoadChartProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const chartTheme = useChartTheme();
  const stats = seriesStats(series, 'form');
  const fmt = (v: unknown) => fmtNumber(Number(v), 1, lang) ?? String(v);
  const summary = [
    t('health.chart.formSummary', {
      days,
      min: fmtNumber(stats.min, 1, lang) ?? t('home.na'),
      max: fmtNumber(stats.max, 1, lang) ?? t('home.na'),
      last: fmtNumber(stats.last, 1, lang) ?? t('home.na'),
    }),
    gapSentences(named, t, lang),
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <ChartCard id="health-chart-form-title" title={t('health.chart.form')}>
      {stats.count < 2 ? (
        <NoData />
      ) : (
        <div role="img" aria-label={summary} data-testid="health-chart-form" data-gaps={shaded.map((g) => `${g.start}..${g.end}`).join(',')}>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
              {shaded.map((g) => (
                <ReferenceArea key={g.start} x1={g.start} x2={g.end} fill="var(--warning)" fillOpacity={0.12} ifOverflow="hidden" />
              ))}
              <ReferenceLine y={0} stroke={chartTheme.axisColor} />
              <XAxis
                dataKey="date"
                stroke={chartTheme.axisColor}
                tick={{ fontSize: 12 }}
                interval="preserveStartEnd"
                minTickGap={40}
                tickFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)}
              />
              <YAxis
                stroke={chartTheme.axisColor}
                tick={{ fontSize: 12 }}
                width={32}
                domain={([lo, hi]: readonly number[]) => [Math.min(Math.floor(lo), 0), Math.max(Math.ceil(hi), 0)]}
                tickFormatter={(v) => fmtNumber(Number(v), 0, lang) ?? ''}
              />
              <Tooltip
                content={<ChartTooltip valueFormatter={fmt} labelFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)} />}
              />
              <Line
                type="monotone"
                dataKey="form"
                stroke="var(--info)"
                dot={false}
                strokeWidth={2}
                name={t('health.chart.form')}
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <p className="mt-1 text-xs text-muted-foreground">{t('health.chart.formNote')}</p>
    </ChartCard>
  );
}

export default function HealthCharts({ series, gaps, days }: HealthChartsProps) {
  const { t } = useTranslation();
  const load = { series, days, named: overlappingGaps(gaps, series), shaded: clipGaps(gaps, series) };
  return (
    <div className="flex flex-col gap-3 md:gap-4" data-testid="health-charts">
      <div className="grid grid-cols-1 gap-3 md:gap-4 lg:grid-cols-3">
        {METRIC_CHARTS.map((c) => (
          <MetricChartCard key={c.key} metric={c.key} label={c.label} unit={c.unit} series={series} days={days} />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t('home.recovery.gapsNote')}</p>
      <LoadChartCard {...load} />
      <FormChartCard {...load} />
    </div>
  );
}
