/**
 * Activités: the last 30 days of Strava activities, grouped by ISO week (Paris),
 * filterable by family (Tout · Course · Renfo/Muscu, kept in `?type=`). A card
 * list on phone and tablet, a dense table from 1024 px. Every row opens the
 * activity detail page.
 */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { Alert, Badge, Button, EmptyState } from '@/ui';
import { api } from '@/api/client';
import { cn } from '@/lib/cn';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { formatDateTime } from '@/utils/formatDate';
import { activityIcon, activityTypeLabel, isStrengthType } from '@/utils/activityType';
import { fmtNumber } from '@/pages/Home/format';
import {
  formatKm,
  formatMoving,
  formatRunPace,
  formatWeekSpan,
  formatWeekStart,
  groupByWeek,
  inWindow,
  matchesFilter,
  parseTypeFilter,
  rowFigures,
  rowStatus,
  summarize,
  TYPE_FILTERS,
  WINDOW_DAYS,
  type ListActivity,
  type TypeFilter,
  type WeekGroup,
} from './activityList';

type LoadState = 'loading' | 'error' | 'ready';

function activityTitle(a: ListActivity, fallback: string): string {
  return a.enhanced_title?.trim() || a.original_name?.trim() || fallback;
}

function detailPath(a: ListActivity): string | null {
  return a.activity_id ? `/activities/${encodeURIComponent(a.activity_id)}` : null;
}

function StatusBadge({ status }: { status: string | undefined }) {
  const { t } = useTranslation();
  const s = rowStatus(status);
  if (!s) return null;
  return (
    <Badge variant={s === 'failed' ? 'danger' : 'warning'} size="sm" className="shrink-0">
      {t(`activities.status.${s}`)}
    </Badge>
  );
}

function SportIcon({ type, className }: { type?: string; className?: string }) {
  const Icon = activityIcon(type);
  return (
    <span
      className={cn('grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground', className)}
      aria-hidden="true"
    >
      {/* eslint-disable-next-line react-hooks/static-components -- Icon is a module-level Lucide component picked by activityIcon(), not created during render. */}
      <Icon className="h-5 w-5" />
    </span>
  );
}

function FilterChips({ value, onChange }: { value: TypeFilter; onChange: (f: TypeFilter) => void }) {
  const { t } = useTranslation();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + TYPE_FILTERS.length) % TYPE_FILTERS.length;
    onChange(TYPE_FILTERS[next]);
    refs.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label={t('activities.filter.aria')} className="flex flex-wrap gap-2">
      {TYPE_FILTERS.map((f, i) => {
        const checked = f === value;
        return (
          <button
            key={f}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(f)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              'inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
              checked
                ? 'border-foreground bg-foreground text-background'
                : 'border-border-strong bg-transparent text-foreground hover:bg-muted',
            )}
          >
            {t(`activities.filter.${f}`)}
          </button>
        );
      })}
    </div>
  );
}

function useWeekText() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  return (g: WeekGroup) => {
    const heading = g.isCurrent
      ? t('activities.week.current', { span: formatWeekSpan(g.monday, g.sunday, lang) })
      : t('activities.week.past', { start: formatWeekStart(g.monday, lang) });
    const km = g.runKm > 0 ? fmtNumber(g.runKm, 1, lang) : null;
    const count = t('activities.week.count', { count: g.items.length });
    const totals = km ? `${t('activities.week.runKm', { km })} \u00b7 ${count}` : count;
    return { heading, totals };
  };
}

function ActivityRow({ a }: { a: ListActivity }) {
  const { t, i18n } = useTranslation();
  const title = activityTitle(a, t('activity.untitled'));
  const date = a.start_date ? formatDateTime(a.start_date, i18n.language) : null;
  const figures = rowFigures(a, i18n.language);
  const typeLabel = activityTypeLabel(t, a.activity_type);
  const path = detailPath(a);

  const body = (
    <>
      <SportIcon type={a.activity_type} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex min-w-0 items-start gap-2">
          <span className="line-clamp-2 min-w-0 flex-1 text-[15px] font-semibold leading-snug text-foreground [overflow-wrap:anywhere]">
            {title}
          </span>
          <StatusBadge status={a.processing_status} />
        </span>
        {typeLabel && <span className="sr-only">{typeLabel}</span>}
        {date && <span className="font-numeric text-xs text-muted-foreground">{date}</span>}
        {figures && <span className="font-numeric text-sm text-foreground">{figures}</span>}
      </span>
    </>
  );

  const rowClass = 'flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-3';
  return (
    <li data-testid="activity-row">
      {path ? (
        <Link
          to={path}
          state={{ activity: a }}
          className={cn(
            rowClass,
            'transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          )}
        >
          {body}
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </Link>
      ) : (
        <div className={rowClass}>{body}</div>
      )}
    </li>
  );
}

function WeekList({ groups }: { groups: WeekGroup[] }) {
  const weekText = useWeekText();
  return (
    <div className="flex flex-col gap-5">
      {groups.map((g) => {
        const { heading, totals } = weekText(g);
        const id = `week-${g.label}`;
        return (
          <section key={g.label} aria-labelledby={id} className="flex flex-col gap-1" data-testid="activity-week">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-1">
              <h2 id={id} className="text-base font-semibold text-foreground">
                {heading}
              </h2>
              <p className="font-numeric text-xs text-muted-foreground" data-testid="activity-week-totals">
                {totals}
              </p>
            </div>
            <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface">
              {g.items.map((a, i) => (
                <ActivityRow key={a.activity_id ?? `${g.label}-${i}`} a={a} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function WeekTable({ groups }: { groups: WeekGroup[] }) {
  const { t, i18n } = useTranslation();
  const weekText = useWeekText();
  const lang = i18n.language;
  const th = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground';
  const num = 'px-3 py-2 text-right font-numeric whitespace-nowrap';

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{t('activities.title')}</caption>
        <thead className="border-b border-border bg-surface-muted">
          <tr>
            <th scope="col" className={th}>{t('activities.col.date')}</th>
            <th scope="col" className={th}>{t('activities.col.activity')}</th>
            <th scope="col" className={th}>{t('activities.col.type')}</th>
            <th scope="col" className={cn(th, 'text-right')}>{t('activities.col.distance')}</th>
            <th scope="col" className={cn(th, 'text-right')}>{t('activities.col.duration')}</th>
            <th scope="col" className={cn(th, 'text-right')}>{t('activities.col.pace')}</th>
          </tr>
        </thead>
        {groups.map((g) => {
          const { heading, totals } = weekText(g);
          return (
            <tbody key={g.label} data-testid="activity-week">
              <tr className="border-b border-border bg-muted/40">
                <th scope="colgroup" colSpan={6} className="px-3 py-2 text-left">
                  <span className="text-sm font-semibold text-foreground">{heading}</span>
                  <span className="ml-3 font-numeric text-xs font-normal text-muted-foreground" data-testid="activity-week-totals">
                    {totals}
                  </span>
                </th>
              </tr>
              {g.items.map((a, i) => {
                const path = detailPath(a);
                return (
                  <tr
                    key={a.activity_id ?? `${g.label}-${i}`}
                    data-testid="activity-row"
                    className={cn('relative h-11 border-b border-border last:border-b-0', path && 'cursor-pointer hover:bg-muted focus-within:bg-muted')}
                  >
                    <td className="px-3 py-2 whitespace-nowrap font-numeric text-muted-foreground">
                      {a.start_date ? formatDateTime(a.start_date, lang) : null}
                    </td>
                    <td className="px-3 py-2">
                      <span className="flex items-center gap-2">
                        {path ? (
                          <Link
                            to={path}
                            state={{ activity: a }}
                            // Stretched link: its ::after covers the whole row, so the row is one
                            // keyboard-operable target (44 px tall) with a visible focus ring.
                            className="line-clamp-2 font-medium text-foreground hover:underline focus-visible:outline-none after:absolute after:inset-0 after:content-[''] focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-ring"
                          >
                            {activityTitle(a, t('activity.untitled'))}
                          </Link>
                        ) : (
                          <span className="line-clamp-2 font-medium">{activityTitle(a, t('activity.untitled'))}</span>
                        )}
                        <StatusBadge status={a.processing_status} />
                      </span>
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">
                      {activityTypeLabel(t, a.activity_type)}
                    </td>
                    <td className={num}>{isStrengthType(a.activity_type) ? null : formatKm(a.distance, 2, lang)}</td>
                    <td className={num}>{formatMoving(a.moving_time)}</td>
                    <td className={num}>{formatRunPace(a)}</td>
                  </tr>
                );
              })}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}

function ListSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" aria-busy="true" className="flex flex-col gap-3" data-testid="activities-skeleton">
      <span className="sr-only">{t('activities.loading')}</span>
      {[0, 1].map((w) => (
        <div key={w} className="flex flex-col gap-2" aria-hidden="true">
          <div className="h-5 w-48 animate-pulse rounded bg-muted" />
          <div className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface">
            {[0, 1, 2].map((r) => (
              <div key={r} className="flex items-center gap-3 px-3 py-3">
                <div className="h-10 w-10 animate-pulse rounded-lg bg-muted" />
                <div className="flex flex-1 flex-col gap-2">
                  <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
                  <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ActivitiesPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const filter = parseTypeFilter(params.get('type'));
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  const [state, setState] = useState<LoadState>('loading');
  const [activities, setActivities] = useState<ListActivity[]>([]);
  const [now, setNow] = useState(() => new Date());
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ activities?: ListActivity[] }>('/dashboard/activities?limit=100')
      .then((res) => {
        if (cancelled) return;
        setActivities(res?.activities ?? []);
        setNow(new Date());
        setState('ready');
      })
      .catch(() => {
        if (!cancelled) setState('error');
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = () => {
    setState('loading');
    setReloadToken((n) => n + 1);
  };

  const windowed = useMemo(() => inWindow(activities, now), [activities, now]);
  const summary = useMemo(() => summarize(windowed), [windowed]);
  const groups = useMemo(
    () => groupByWeek(windowed.filter((a) => matchesFilter(a, filter)), now),
    [windowed, filter, now],
  );

  const setFilter = (f: TypeFilter) => {
    const next = new URLSearchParams(params);
    if (f === 'all') next.delete('type');
    else next.set('type', f);
    setParams(next, { replace: true });
  };

  const breakdown = [
    summary.runs > 0 ? t('activities.summary.runs', { count: summary.runs }) : null,
    summary.strength > 0 ? t('activities.summary.strength', { count: summary.strength }) : null,
  ].filter(Boolean);
  const subtitle =
    state === 'ready'
      ? [t('activities.summary.total', { count: summary.total, days: WINDOW_DAYS }), breakdown.join(', ')]
          .filter(Boolean)
          .join(' \u00b7 ')
      : null;

  return (
    <div className="flex flex-col gap-5 pb-10 md:gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{t('activities.title')}</h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground" data-testid="activities-subtitle">
            {subtitle}
          </p>
        )}
      </header>

      <FilterChips value={filter} onChange={setFilter} />

      {state === 'loading' && <ListSkeleton />}

      {state === 'error' && (
        <Alert variant="error">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{t('activities.error')}</span>
            <Button variant="outline" size="sm" onClick={reload} className="min-h-11">
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {state === 'ready' &&
        (groups.length === 0 ? (
          <EmptyState
            illustration="activity"
            title={
              summary.total === 0
                ? t('activities.empty.title', { days: WINDOW_DAYS })
                : t('activities.empty.filteredTitle', { days: WINDOW_DAYS })
            }
            description={summary.total === 0 ? t('activities.empty.description') : undefined}
            action={
              summary.total > 0 ? (
                <Button variant="outline" size="sm" className="min-h-11" onClick={() => setFilter('all')}>
                  {t('activities.empty.showAll')}
                </Button>
              ) : undefined
            }
          />
        ) : isDesktop ? (
          <WeekTable groups={groups} />
        ) : (
          <WeekList groups={groups} />
        ))}
    </div>
  );
}
