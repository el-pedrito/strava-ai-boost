/**
 * "Cette semaine": the Campus plan strip (cycle, plan progress, week km) and
 * this week's sessions in one card. One status icon per row, at most one badge,
 * the tune-up race named as such, and a single km target.
 */
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Check, ChevronRight, Flag, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { HomePlan, HomeWeekSession } from '@/types/home';
import { fmtNumber } from '../format';
import { cycleThemeKey, isPrepRace, remainingSessions, sessionKind, type SessionKind } from '../insights';
import { CardHead, HomeCard, Pill, ValueUnit } from './common';

function Progress({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, Math.round((value / max) * 100))) : 0;
  return (
    <div
      className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-label={label}
    >
      <span className="block h-full rounded-full bg-success" style={{ width: `${pct}%` }} />
    </div>
  );
}

function StatusIcon({ kind, prepRace }: { kind: SessionKind; prepRace: boolean }) {
  const base = 'grid h-6 w-6 shrink-0 place-items-center rounded-full';
  if (kind === 'done') {
    return (
      <span className={cn(base, 'bg-success/15 text-success-text')} aria-hidden="true">
        <Check className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    );
  }
  if (kind === 'missed') {
    return (
      <span className={cn(base, 'bg-danger/10 text-danger-text')} aria-hidden="true">
        <X className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    );
  }
  if (prepRace) {
    return (
      <span className={cn(base, 'border-2', kind === 'next' ? 'border-primary text-primary' : 'border-border-strong text-muted-foreground')} aria-hidden="true">
        <Flag className="h-3 w-3" />
      </span>
    );
  }
  return <span className={cn(base, 'border-2', kind === 'next' ? 'border-primary' : 'border-border-strong')} aria-hidden="true" />;
}

export function WeekCard({
  plan,
  sessions,
  nextOrder,
}: {
  plan: HomePlan | null;
  sessions: HomeWeekSession[];
  nextOrder: number | null;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const ordered = [...sessions].sort((a, b) => a.order - b.order);
  const done = ordered.filter((s) => s.status === 'done').length;
  const remaining = remainingSessions(ordered);

  const themeKey = cycleThemeKey(plan?.cycle_theme);
  const real = plan?.week_km_real ?? null;
  const expected = plan?.week_km_expected ?? null;
  const realText = fmtNumber(real, 1, lang);
  const expectedText = fmtNumber(expected, 1, lang);
  const hasTrainings = plan?.trainings_done != null && plan?.trainings_total != null;

  return (
    <HomeCard labelledBy="home-week-title" className="flex flex-col gap-3.5">
      <CardHead id="home-week-title" title={t('home.week.title')}>
        {ordered.length > 0 && (
          <span className="text-xs text-muted-foreground">
            {t('home.week.doneCount', { done, total: ordered.length })}
          </span>
        )}
        {plan?.week_index != null && plan.weeks_total != null && (
          <Pill className="ml-auto">{t('home.plan.week', { index: plan.week_index, total: plan.weeks_total })}</Pill>
        )}
      </CardHead>

      {plan && (themeKey || hasTrainings || realText) && (
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {themeKey && (
            <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">{t('home.plan.cycle')}</dt>
              <dd className="text-[15px] font-semibold leading-snug">{t(`home.plan.cycleTheme.${themeKey}`)}</dd>
            </div>
          )}
          {hasTrainings && (
            <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">{t('home.plan.trainings')}</dt>
              <dd className="text-lg font-semibold leading-snug">
                <ValueUnit value={String(plan.trainings_done)} unit={`/${plan.trainings_total}`} />
              </dd>
              <dd>
                <Progress
                  value={plan.trainings_done as number}
                  max={plan.trainings_total as number}
                  label={t('home.plan.trainingsAria', { done: plan.trainings_done, total: plan.trainings_total })}
                />
              </dd>
            </div>
          )}
          {realText && (
            <div className="min-w-0 rounded-lg bg-surface-muted px-3 py-2.5">
              <dt className="text-xs text-muted-foreground">{t('home.plan.weekKm')}</dt>
              <dd className="text-lg font-semibold leading-snug">
                {expectedText ? (
                  <span className="font-numeric">{t('home.plan.kmRealExpected', { real: realText, expected: expectedText })}</span>
                ) : (
                  <ValueUnit value={realText} unit="km" />
                )}
              </dd>
              {expectedText && real != null && expected != null && expected > 0 && (
                <dd>
                  <Progress
                    value={real}
                    max={expected}
                    label={t('home.plan.weekKmAria', { real: realText, expected: expectedText })}
                  />
                </dd>
              )}
            </div>
          )}
        </dl>
      )}

      {ordered.length > 0 && (
        <>
          <p className="text-sm font-medium text-foreground" data-testid="home-week-remaining">
            {remaining > 0 ? t('home.week.remaining', { count: remaining }) : t('home.week.allDone')}
          </p>
          <ol className="flex flex-col gap-1.5">
            {ordered.map((s) => {
              const kind = sessionKind(s, nextOrder);
              const prep = isPrepRace(s);
              const badge =
                kind === 'next' ? (
                  <Pill tone="primary">{t('home.week.next')}</Pill>
                ) : prep && kind === 'todo' ? (
                  <Pill tone="warning">{t('home.week.prepRace')}</Pill>
                ) : kind === 'missed' ? (
                  <Pill tone="danger">{t('home.week.status.missed')}</Pill>
                ) : null;
              return (
                <li
                  key={s.order}
                  data-testid="home-week-session"
                  data-next={kind === 'next' ? 'true' : undefined}
                  data-kind={kind}
                  aria-current={kind === 'next' ? 'step' : undefined}
                  className={cn(
                    'flex min-h-11 min-w-0 items-center gap-2.5 rounded-lg border px-2.5 py-2',
                    kind === 'next' ? 'border-primary/45 bg-primary/5' : 'border-border'
                  )}
                >
                  <StatusIcon kind={kind} prepRace={prep} />
                  <span className="sr-only">
                    {t(`home.week.status.${s.status}`, { defaultValue: s.status })}
                    {prep && kind !== 'todo' ? `, ${t('home.week.prepRace')}` : ''}
                  </span>
                  <span
                    className={cn(
                      'min-w-0 flex-1 text-sm font-medium [overflow-wrap:anywhere]',
                      kind === 'done' ? 'text-muted-foreground' : 'text-foreground'
                    )}
                  >
                    {kind === 'done' && s.activity_id ? (
                      <Link
                        to={`/activities/${encodeURIComponent(s.activity_id)}`}
                        className="rounded-sm hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {s.title ?? t('home.week.untitled')}
                      </Link>
                    ) : (
                      (s.title ?? t('home.week.untitled'))
                    )}
                  </span>
                  {s.duration_min != null && (
                    <span className="whitespace-nowrap text-xs text-muted-foreground">
                      {t('home.minutes', { value: s.duration_min })}
                    </span>
                  )}
                  {badge}
                </li>
              );
            })}
          </ol>
        </>
      )}

      <div className="-mb-1 flex justify-end border-t border-border pt-1">
        <Link
          to="/activities"
          className="inline-flex min-h-11 items-center gap-1 rounded-sm text-sm font-medium text-primary-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t('activities.seeAll')}
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </HomeCard>
  );
}
