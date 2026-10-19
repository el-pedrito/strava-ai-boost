/**
 * Enduraw: raw vs adjusted pace per run, on an axis hugging the data (the old
 * 0:00..5:40 axis flattened both lines at the bottom), reversed so faster is up.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import type { EndurawTrendPoint } from '@/types/home';
import { formatPace, formatShortDate } from '../format';
import { paceDomain } from '../insights';
import { CardHead, HomeCard } from './common';

export function EndurawCard({ trend }: { trend: EndurawTrendPoint[] }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const chartTheme = useChartTheme();

  const data = useMemo(
    () =>
      [...trend]
        .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
        .map((p) => ({ date: p.date, raw: p.raw_pace_s, adjusted: p.adjusted_pace_s })),
    [trend]
  );
  const domain = paceDomain(data.flatMap((p) => [p.raw, p.adjusted]));
  const latest = [...data].reverse().find((p) => p.raw != null && p.adjusted != null) ?? null;
  const latestRaw = formatPace(latest?.raw);
  const latestAdj = formatPace(latest?.adjusted);
  const latestDate = formatShortDate(latest?.date, lang);
  const fmtPace = (v: unknown) => formatPace(Number(v)) ?? String(v);

  return (
    <HomeCard labelledBy="home-enduraw-title" className="flex flex-col gap-3">
      <CardHead id="home-enduraw-title" title={t('home.enduraw.title')}>
        <span className="ml-auto text-xs text-muted-foreground">{t('home.enduraw.runs', { count: data.length })}</span>
      </CardHead>

      {latestRaw && latestAdj && latestDate && (
        <p className="text-sm text-foreground" data-testid="home-enduraw-summary">
          {t('home.enduraw.summary', { date: latestDate, adjusted: latestAdj, raw: latestRaw })}
        </p>
      )}

      <div role="img" aria-label={t('home.enduraw.chartAria', { count: data.length })}>
        <ResponsiveContainer width="100%" height={170}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
            <XAxis
              dataKey="date"
              stroke={chartTheme.axisColor}
              tick={{ fontSize: 12 }}
              minTickGap={32}
              tickFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)}
            />
            <YAxis
              stroke={chartTheme.axisColor}
              tick={{ fontSize: 12 }}
              width={44}
              reversed
              domain={domain ?? ['auto', 'auto']}
              allowDataOverflow={false}
              tickFormatter={fmtPace}
            />
            <Tooltip
              content={
                <ChartTooltip valueFormatter={fmtPace} labelFormatter={(d) => formatShortDate(String(d), lang) ?? String(d)} />
              }
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="raw" stroke={chartTheme.mutedColor} dot strokeWidth={2} name={t('home.enduraw.raw')} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="adjusted" stroke="var(--info)" dot strokeWidth={2} name={t('home.enduraw.adjusted')} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted-foreground">{t('home.enduraw.lowerIsFaster')}</p>
    </HomeCard>
  );
}
