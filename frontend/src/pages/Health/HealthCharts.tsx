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

/** One measurement cannot form a line: show it as a dot with its value and date. */
function SinglePoint({ value, date, testId }: { value: string; date: string | null; testId: string }) {
  const { t, i18n } = useTranslation();
  const day = formatShortDate(date, i18n.language) ?? '';
  return (
    <p
      className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-foreground"
      data-testid={testId}
    >
      <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-info" aria-hidden="true" />
      {t('health.chart.single', { value, date: day })}
    </p>
  );
}

/**
 * The chart body by number of measurements: 0 says so, 1 is a dot with the
 * latest value, 2+ draws the line. The one-line screen-reader summary is
 * always present: as the chart's label, or as sr-only text next to the fallback.
 */
function ChartBody({
  count,
  summary,
  testId,
  single,
  extra,
  children,
}: {
  count: number;
  summary: string;
  testId: string;
  single: { value: string; date: string | null };
  extra?: Record<string, string | number>;
  children: React.ReactNode;
}) {
  if (count >= 2) {
    return (
      <div role="img" aria-label={summary} data-testid={testId} data-points={count} {...extra}>
        {children}
      </div>
    );
  }
  return (
    <div data-testid={`${testId}-fallback`} data-points={count}>
      <p className="sr-only" data-testid={`${testId}-summary`}>
        {summary}
      </p>
      {count === 1 ? <SinglePoint value={single.value} date={single.date} testId={`${testId}-single`} /> : <NoData />}
    </div>
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
      : stats.count === 1
        ? t('health.chart.summaryOne', { metric: name, days, last: fmt(stats.last), date: formatShortDate(stats.lastDate, lang) ?? '' })
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
      <ChartBody count={stats.count} summary={summary} testId={id} single={{ value: fmt(stats.last), date: stats.lastDate }}>
        <MetricLineChart data={series} metric={metric} label={name} lang={lang} height={170} />
      </ChartBody>
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
  const count = Math.max(ctl.count, atl.count);
  const na = t('home.na');
  const latest = t('health.chart.loadLatest', {
    ctl: fmtNumber(ctl.last, 1, lang) ?? na,
    atl: fmtNumber(atl.last, 1, lang) ?? na,
  });
  const lastDate = [ctl.lastDate, atl.lastDate].filter((d): d is string => d != null).sort().at(-1) ?? null;
  const summary = [
    count === 0
      ? t('health.chart.summaryEmpty', { metric: t('health.chart.load'), days })
      : t('health.chart.loadSummary', { days, latest }),
    gapSentences(named, t, lang),
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <ChartCard id="health-chart-load-title" title={t('health.chart.load')}>
      <div className="flex flex-col gap-3">
        <LoadGapWarning gaps={named} />
        <ChartBody
          count={count}
          summary={summary}
          testId="health-chart-load"
          single={{ value: latest, date: lastDate }}
          extra={{ 'data-gaps': shaded.map((g) => `${g.start}..${g.end}`).join(',') }}
        >
          <LoadLineChart
            data={series}
            gaps={shaded}
            ctlName={t('health.chart.ctl')}
            atlName={t('health.chart.atl')}
            lang={lang}
            height={200}
          />
        </ChartBody>
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
  const name = t('health.chart.form');
  const lastText = fmtNumber(stats.last, 1, lang) ?? t('home.na');
  const summary = [
    stats.count === 0
      ? t('health.chart.summaryEmpty', { metric: name, days })
      : stats.count === 1
        ? t('health.chart.summaryOne', { metric: name, days, last: lastText, date: formatShortDate(stats.lastDate, lang) ?? '' })
        : t('health.chart.formSummary', {
            days,
            min: fmtNumber(stats.min, 1, lang) ?? t('home.na'),
            max: fmtNumber(stats.max, 1, lang) ?? t('home.na'),
            last: lastText,
          }),
    gapSentences(named, t, lang),
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <ChartCard id="health-chart-form-title" title={name}>
      <ChartBody
        count={stats.count}
        summary={summary}
        testId="health-chart-form"
        single={{ value: lastText, date: stats.lastDate }}
        extra={{ 'data-gaps': shaded.map((g) => `${g.start}..${g.end}`).join(',') }}
      >
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
              name={name}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartBody>
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
