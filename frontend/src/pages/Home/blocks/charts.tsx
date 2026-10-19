/**
 * The recharts line charts shared by the Home cards and the Santé page. Every
 * line keeps `connectNulls={false}`: a day without a measurement is a gap in
 * the line, never a zero and never a bridge.
 */
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
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import { fmtNumber, formatMetric, formatMetricText, formatShortDate } from '../format';
import type { LoadGap } from '../insights';

export type SeriesMetric = 'hrv' | 'resting_hr' | 'sleep_s';

type Row = { date: string };

const dateTick = (lang: string) => (d: unknown) => formatShortDate(String(d), lang) ?? String(d);

/** One recovery metric on its own scale and unit. */
export function MetricLineChart({
  data,
  metric,
  label,
  lang,
  height = 150,
}: {
  data: ReadonlyArray<Row>;
  metric: SeriesMetric;
  label: string;
  lang: string;
  height?: number;
}) {
  const chartTheme = useChartTheme();
  const fmt = (v: unknown) => formatMetricText(metric, Number(v), lang) ?? String(v);
  const tick = (v: unknown) => formatMetric(metric, Number(v), lang)?.value ?? String(v);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data as Row[]} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
        <XAxis
          dataKey="date"
          stroke={chartTheme.axisColor}
          tick={{ fontSize: 12 }}
          interval="preserveStartEnd"
          minTickGap={40}
          tickFormatter={dateTick(lang)}
        />
        <YAxis
          stroke={chartTheme.axisColor}
          tick={{ fontSize: 12 }}
          width={metric === 'sleep_s' ? 56 : 40}
          domain={['auto', 'auto']}
          tickFormatter={tick}
        />
        <Tooltip content={<ChartTooltip valueFormatter={fmt} labelFormatter={dateTick(lang)} />} />
        <Line
          type="monotone"
          dataKey={metric}
          stroke="var(--info)"
          dot={false}
          strokeWidth={2}
          name={label}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/**
 * CTL and ATL on one unitless scale, with the load-gap periods shaded. Each
 * gap must start and end on a date present in `data` (the X axis is a
 * category axis).
 */
export function LoadLineChart({
  data,
  gaps,
  ctlName,
  atlName,
  lang,
  height = 160,
}: {
  data: ReadonlyArray<Row>;
  gaps: ReadonlyArray<LoadGap>;
  ctlName: string;
  atlName: string;
  lang: string;
  height?: number;
}) {
  const chartTheme = useChartTheme();
  const fmt = (v: unknown) => fmtNumber(Number(v), 1, lang) ?? String(v);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data as Row[]} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
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
          tickFormatter={dateTick(lang)}
        />
        <YAxis stroke={chartTheme.axisColor} tick={{ fontSize: 12 }} width={32} tickFormatter={(v) => fmtNumber(Number(v), 0, lang) ?? ''} />
        <Tooltip content={<ChartTooltip valueFormatter={fmt} labelFormatter={dateTick(lang)} />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="ctl" stroke="var(--info)" dot={false} strokeWidth={2} name={ctlName} connectNulls={false} isAnimationActive={false} />
        <Line
          type="monotone"
          dataKey="atl"
          stroke={chartTheme.mutedColor}
          strokeDasharray="5 3"
          dot={false}
          strokeWidth={2}
          name={atlName}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
