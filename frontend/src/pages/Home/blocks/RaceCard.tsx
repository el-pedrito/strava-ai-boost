/**
 * Race card: name, date, J-x, target time + pace, predicted time with the gap
 * to the target, and the predicted range as a bar with both markers.
 */
import { useTranslation } from 'react-i18next';
import { Trophy } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { HomeRace } from '@/types/home';
import {
  formatDuration,
  formatGap,
  formatPace,
  formatWeekdayDate,
  isoWeekNumber,
  sentenceCase,
} from '../format';
import { rangePosition } from '../insights';
import { CardHead, HomeCard } from './common';

export function RaceCard({ race }: { race: HomeRace }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const name = sentenceCase(race.name) ?? t('home.race.title');
  const date = formatWeekdayDate(race.date, lang);
  const target = formatDuration(race.target_time_s);
  const targetPace = formatPace(race.target_pace_s);
  const predicted = formatDuration(race.predicted_time_s);
  const gapS =
    race.predicted_time_s != null && race.target_time_s != null
      ? race.predicted_time_s - race.target_time_s
      : null;
  const gap = formatGap(gapS);
  const gapTone = gapS == null || Math.round(gapS) === 0 ? 'text-muted-foreground' : gapS > 0 ? 'text-warning-text' : 'text-success-text';

  const range = race.predicted_range_s;
  const low = range ? formatDuration(range[0]) : null;
  const high = range ? formatDuration(range[1]) : null;
  const targetPos = range ? rangePosition(race.target_time_s, range[0], range[1]) : null;
  const predictedPos = range ? rangePosition(race.predicted_time_s, range[0], range[1]) : null;
  const week = isoWeekNumber(race.prediction_week);

  return (
    <HomeCard labelledBy="home-race-title">
      <div className="flex items-start gap-2">
        <Trophy className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0">
          <CardHead id="home-race-title" title={name} />
          {date && <p className="text-xs text-muted-foreground">{date}</p>}
        </div>
        {race.days_left != null && (
          <span className="ml-auto font-numeric text-[28px] font-bold leading-none text-primary">
            {t('home.race.daysLeft', { count: race.days_left })}
          </span>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3">
        {target && (
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">{t('home.race.target')}</dt>
            <dd className="font-numeric text-2xl font-semibold leading-tight">{target}</dd>
            {targetPace && (
              <dd className="font-numeric text-xs text-muted-foreground">{t('home.race.pace', { pace: targetPace })}</dd>
            )}
          </div>
        )}
        {predicted && (
          <div className="min-w-0">
            <dt className="text-xs text-muted-foreground">{t('home.race.predicted')}</dt>
            <dd className="font-numeric text-2xl font-semibold leading-tight">{predicted}</dd>
            {gap && (
              <dd className={cn('font-numeric text-xs font-semibold', gapTone)} data-testid="home-race-gap">
                {t('home.race.gap', { gap })}
              </dd>
            )}
          </div>
        )}
      </dl>

      {low && high && (
        <div className="mt-4">
          <div
            className="relative h-2 rounded-full bg-muted"
            role="img"
            aria-label={t('home.race.rangeAria', {
              low,
              high,
              target: target ?? t('home.na'),
              predicted: predicted ?? t('home.na'),
            })}
          >
            {targetPos != null && (
              <i
                className="absolute top-1/2 -ml-[7px] -mt-[7px] h-3.5 w-3.5 rounded-full border-2 border-surface bg-success-text"
                style={{ left: `${targetPos}%` }}
              />
            )}
            {predictedPos != null && (
              <i
                className="absolute top-1/2 -ml-[7px] -mt-[7px] h-3.5 w-3.5 rounded-full border-2 border-surface bg-info"
                style={{ left: `${predictedPos}%` }}
              />
            )}
          </div>
          <p className="mt-1 flex justify-between font-numeric text-xs text-muted-foreground" aria-hidden="true">
            <span>{low}</span>
            <span>{high}</span>
          </p>
          <p className="mt-2 flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <i className="h-2.5 w-2.5 rounded-full bg-success-text" aria-hidden="true" />
              {t('home.race.target')}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <i className="h-2.5 w-2.5 rounded-full bg-info" aria-hidden="true" />
              {t('home.race.predicted')}
            </span>
            {week != null && <span>{t('home.race.predictionWeek', { week })}</span>}
          </p>
        </div>
      )}
    </HomeCard>
  );
}
