/**
 * Predictions: the other distances (the race distance already lives in the
 * race card), each with its pace and range, plus the half-marathon trend.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import type { HomePredictions, PredictionsHistoryPoint } from '@/types/home';
import { formatDuration, formatPace, formatRange, isoWeekNumber } from '../format';
import { CardHead, HomeCard } from './common';

const PRED_LABEL: Record<string, string> = {
  '5km': 'home.predictions.d5k',
  '10km': 'home.predictions.d10k',
  'half-marathon': 'home.predictions.half',
  marathon: 'home.predictions.marathon',
};

export function PredictionsCard({
  predictions,
  history,
  excludeDistance,
}: {
  predictions: HomePredictions | null;
  history: PredictionsHistoryPoint[] | null;
  /** Distance already shown by the race card, left out to avoid a duplicate. */
  excludeDistance: string | null;
}) {
  const { t } = useTranslation();
  const chartTheme = useChartTheme();
  const items = (predictions?.items ?? []).filter((p) => p.distance !== excludeDistance);
  const week = isoWeekNumber(predictions?.week);

  const historyData = useMemo(
    () =>
      (history ?? [])
        .filter((h) => h.half_marathon_time_s != null)
        .map((h) => ({ week: `S${isoWeekNumber(h.week) ?? h.week}`, time: h.half_marathon_time_s as number })),
    [history]
  );

  return (
    <HomeCard labelledBy="home-pred-title" className="@container">
      <CardHead id="home-pred-title" title={t('home.predictions.title')}>
        {week != null && <span className="ml-auto text-xs text-muted-foreground">{t('home.predictions.week', { week })}</span>}
      </CardHead>

      {items.length === 0 && <p className="mt-4 text-sm text-muted-foreground">{t('home.predictions.empty')}</p>}

      {items.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-2 @lg:grid-cols-3">
          {items.map((p) => {
            const time = formatDuration(p.time_s);
            const pace = formatPace(p.pace_s);
            const range = formatRange(p.range_s);
            return (
              <div key={p.distance} className="min-w-0 rounded-lg border border-border px-3 py-2.5">
                <dt className="text-xs text-muted-foreground">
                  {t(PRED_LABEL[p.distance] ?? '', { defaultValue: p.distance })}
                </dt>
                <dd className="font-numeric text-xl font-semibold leading-snug [overflow-wrap:anywhere]">
                  {time ?? t('home.na')}
                </dd>
                {pace && (
                  <dd className="font-numeric text-xs text-muted-foreground">{t('home.predictions.pace', { pace })}</dd>
                )}
                {range && (
                  <dd className="font-numeric text-xs text-muted-foreground">
                    {t('home.estimation')} {range}
                  </dd>
                )}
              </div>
            );
          })}
        </dl>
      )}

      {historyData.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-semibold">{t('home.predictions.halfCurve')}</h3>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={historyData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridColor} vertical={false} />
              <XAxis dataKey="week" stroke={chartTheme.axisColor} tick={{ fontSize: 12 }} minTickGap={20} />
              <YAxis
                stroke={chartTheme.axisColor}
                tick={{ fontSize: 12 }}
                width={52}
                domain={['dataMin - 60', 'dataMax + 60']}
                tickFormatter={(v) => formatDuration(Number(v)) ?? String(v)}
              />
              <Tooltip content={<ChartTooltip valueFormatter={(v) => formatDuration(Number(v)) ?? String(v)} />} />
              <Line type="monotone" dataKey="time" stroke={chartTheme.primaryColor} dot strokeWidth={2} name={t('home.predictions.half')} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-muted-foreground">{t('home.predictions.historyNote')}</p>
        </div>
      )}
    </HomeCard>
  );
}
