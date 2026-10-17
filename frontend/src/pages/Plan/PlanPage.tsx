import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity as ActivityIcon,
  Ban,
  CalendarDays,
  ChevronDown,
  Clock,
  Dumbbell,
  Flag,
  Footprints,
  HelpCircle,
  MessageCircle,
  RefreshCw,
  Watch,
  type LucideIcon,
} from 'lucide-react';
import { getPlanWorkouts } from '@/api/client';
import { downloadWorkout } from '@/lib/downloadWorkout';
import {
  athleteToday,
  daysBetween,
  formatDay,
  formatWeekRange,
  isoWeekLabel,
  isoWeekSunday,
  shiftedWeekLabel,
} from '@/lib/isoWeek';
import { CoachText } from '@/components/CoachText';
import { Alert, Badge, Button, Card, EmptyState } from '@/ui';
import { cn } from '@/lib/cn';
import type { PlanWorkoutItem, PlanWorkoutsResponse, WorkoutReasonCode } from '@/types/index';

const KNOWN_REASONS: ReadonlySet<WorkoutReasonCode> = new Set<WorkoutReasonCode>([
  'unsupported_sport',
  'no_intervals',
  'legacy_shape',
  'bad_repeat',
  'bad_shape',
  'too_many_steps',
  'too_large',
  'internal',
]);

const SPORT_ICONS: Record<string, LucideIcon> = {
  road: Footprints,
  ppg: Dumbbell,
};

/**
 * Campus `trainingType` of the goal race (same set as `campus_workout.RACE_TRAINING_TYPES`,
 * minus `low-priority-race`: an intermediate race is a plan session, not the goal).
 */
const RACE_TRAINING_TYPES: ReadonlySet<string> = new Set(['Competition', 'race']);
const RACE_TITLE_RE = /marathon/i;

const WEEK_NUMBER_RE = /W(\d{1,2})$/;

interface WeekGroup {
  /** null groups the sessions whose week label the server could not provide. */
  weekIso: string | null;
  items: PlanWorkoutItem[];
}

/**
 * Group sessions by ISO week, weeks in chronological order, API order kept inside
 * a week. Sessions without a week label go to one trailing "unknown week" group.
 */
function groupByWeek(items: PlanWorkoutItem[]): WeekGroup[] {
  const groups = new Map<string | null, PlanWorkoutItem[]>();
  for (const item of items) {
    const bucket = groups.get(item.week_iso);
    if (bucket) bucket.push(item);
    else groups.set(item.week_iso, [item]);
  }
  // `YYYY-Www` labels sort chronologically as plain strings; null goes last.
  return [...groups.entries()]
    .sort(([a], [b]) => {
      if (a === b) return 0;
      if (a === null) return 1;
      if (b === null) return -1;
      return a < b ? -1 : 1;
    })
    .map(([weekIso, weekItems]) => ({ weekIso, items: weekItems }));
}

/** A session can be sent to the Watch only if the server encoded it. */
function isDownloadable(item: PlanWorkoutItem): item is PlanWorkoutItem & { workout_b64: string } {
  return item.encodable && typeof item.workout_b64 === 'string' && item.workout_b64.length > 0;
}

/** The goal race: a Campus competition, or a session titled "...MARATHON...". */
function isRace(item: PlanWorkoutItem): boolean {
  return RACE_TRAINING_TYPES.has(item.training_type ?? '') || RACE_TITLE_RE.test(item.title ?? '');
}

function reasonKey(item: PlanWorkoutItem): string {
  const code = item.reason_code;
  // An encodable item without bytes, or an unknown code, gets the generic sentence.
  if (code && KNOWN_REASONS.has(code as WorkoutReasonCode)) return `plan.reason.${code}`;
  return 'plan.reason.internal';
}

function itemKey(item: PlanWorkoutItem): string {
  return `${item.week_iso ?? '?'}:${item.session_id ?? '?'}:${item.training_index ?? '?'}`;
}

/** An `id` attribute safe for `aria-describedby` (no spaces), derived from a key. */
function domId(prefix: string, key: string): string {
  return `${prefix}-${key.replace(/[^A-Za-z0-9_-]/g, '_')}`;
}

function nonEmpty(text: string | null | undefined): string | null {
  return typeof text === 'string' && text.trim().length > 0 ? text : null;
}

/** "J-29" / "Jour J" plus its spoken form, from today to the race's assumed day. */
interface Countdown {
  label: string;
  aria: string;
}

function useCountdown(item: PlanWorkoutItem, today: Date | null): Countdown | null {
  const { t } = useTranslation();
  const raceDay = item.week_iso ? isoWeekSunday(item.week_iso) : null;
  if (!raceDay || !today) return null;
  const days = daysBetween(today, raceDay);
  if (days < 0) return null;
  if (days === 0) return { label: t('plan.race.today'), aria: t('plan.race.today') };
  return {
    label: t('plan.race.countdown', { count: days }),
    aria: t('plan.race.countdownAria', { count: days }),
  };
}

/** Collapsed disclosure; `<details>` keeps it keyboard and screen-reader friendly with no state. */
function Disclosure({
  label,
  icon,
  defaultOpen = false,
  children,
}: {
  label: string;
  icon?: boolean;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group rounded-lg bg-info/10" open={defaultOpen || undefined}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm font-medium text-info focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
        {icon && <MessageCircle className="h-4 w-4 shrink-0" aria-hidden="true" />}
        <span className="flex-1">{label}</span>
        <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="flex flex-col gap-3 px-3 pb-3">{children}</div>
    </details>
  );
}

/** Coach word then instructions, inside one collapsed "Mot du coach" (ordinary sessions). */
function CoachDisclosure({ item }: { item: PlanWorkoutItem }) {
  const { t } = useTranslation();
  const advice = nonEmpty(item.coach_advice);
  const description = nonEmpty(item.description);
  if (!advice && !description) return null;
  return (
    <Disclosure label={advice ? t('plan.coachWord') : t('plan.instructions')} icon>
      {advice && <CoachText text={advice} />}
      {advice && description && (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {t('plan.instructions')}
          </p>
          <CoachText text={description} />
        </div>
      )}
      {!advice && description && <CoachText text={description} />}
    </Disclosure>
  );
}

/** Coach word shown open (next session, race), instructions collapsed under it. */
function CoachBox({ item, clampLines }: { item: PlanWorkoutItem; clampLines?: number }) {
  const { t } = useTranslation();
  const advice = nonEmpty(item.coach_advice);
  const description = nonEmpty(item.description);
  if (!advice && !description) return null;
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-info/10 p-3" data-testid="plan-coach-box">
      {advice && (
        <>
          <p className="flex items-center gap-2 text-xs font-semibold text-info">
            <MessageCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {t('plan.coachWordCampus')}
          </p>
          <CoachText text={advice} clampLines={clampLines} />
        </>
      )}
      {description && (
        <details className="group">
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-md text-sm font-medium text-info focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
            <span className="flex-1">{t('plan.instructions')}</span>
            <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <CoachText text={description} className="pt-1" />
        </details>
      )}
    </div>
  );
}

type CardRole = 'next' | 'race' | 'normal';

interface SessionCardProps {
  item: PlanWorkoutItem;
  role: CardRole;
  /** The next session gets the page's single filled Watch button. */
  primary: boolean;
  today: Date | null;
  lang: string;
  failed: boolean;
  onAdd: (item: PlanWorkoutItem & { workout_b64: string }) => void;
}

function SessionCard({ item, role, primary, today, lang, failed, onAdd }: SessionCardProps) {
  const { t } = useTranslation();
  const downloadable = isDownloadable(item);
  const errorId = domId('plan-error', itemKey(item));
  const title = item.title ?? t('plan.untitled');
  const sport = item.sport ?? '';
  const SportIcon = role === 'race' ? Flag : SPORT_ICONS[sport] ?? ActivityIcon;
  const sportLabel = SPORT_ICONS[sport] ? t(`plan.sport.${sport}`) : t('plan.sport.other');
  const countdown = useCountdown(item, role === 'race' ? today : null);
  const weekEnd = item.week_iso ? isoWeekSunday(item.week_iso) : null;
  const addLabel = t('plan.addAria', { title });

  const iconButton = downloadable && !primary && (
    <Button
      variant="outline"
      size="icon"
      className="h-11 w-11 shrink-0"
      onClick={() => onAdd(item)}
      aria-label={addLabel}
      aria-describedby={failed ? errorId : undefined}
    >
      <Watch className="h-5 w-5" aria-hidden="true" />
    </Button>
  );

  return (
    <li className={cn(role !== 'normal' && 'md:col-span-2')}>
      <Card
        padding="sm"
        variant={downloadable ? 'default' : 'flat'}
        data-testid="plan-session"
        data-encodable={downloadable ? 'true' : 'false'}
        data-role={role}
        className={cn(
          'flex h-full flex-col gap-3',
          role === 'race' && 'border-primary/40 bg-primary/5',
          role === 'next' && 'border-primary/30'
        )}
      >
        <div className="flex items-start gap-3">
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
              role === 'race'
                ? 'bg-primary-strong text-primary-foreground'
                : downloadable
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
            )}
            aria-hidden="true"
          >
            <SportIcon className="h-5 w-5" />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            {role === 'next' && (
              <Badge size="sm" variant="primary" className="self-start">
                {t('plan.next')}
              </Badge>
            )}
            {role === 'race' && (
              <Badge size="sm" variant="primary" className="self-start">
                {t('plan.race.badge')}
              </Badge>
            )}
            <h3
              className={cn(
                'font-semibold leading-tight',
                role === 'normal' ? 'text-base' : 'text-lg',
                downloadable || role === 'race' ? 'text-foreground' : 'text-muted-foreground'
              )}
            >
              {title}
            </h3>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge size="sm" variant={downloadable ? 'primary' : 'default'}>
                {sportLabel}
              </Badge>
              {typeof item.duration_min === 'number' && Number.isFinite(item.duration_min) && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('plan.durationMin', { count: Math.round(item.duration_min) })}
                </span>
              )}
            </div>
            {role === 'race' && weekEnd && (
              <p className="text-xs text-muted-foreground">
                {t('plan.race.assumedDate', { date: formatDay(weekEnd, lang) })}
              </p>
            )}
          </div>
          {countdown && (
            <div className="flex shrink-0 flex-col items-end" aria-label={countdown.aria} role="img">
              <span className="text-2xl font-bold leading-none tabular-nums text-primary-strong">
                {countdown.label}
              </span>
              <span className="text-xs text-muted-foreground">{t('plan.race.beforeStart')}</span>
            </div>
          )}
          {iconButton}
        </div>

        {item.summary && <p className="break-words text-sm text-muted-foreground">{item.summary}</p>}

        {primary && downloadable && (
          <Button
            variant="primary"
            size="lg"
            className="w-full sm:w-auto sm:self-start"
            onClick={() => onAdd(item)}
            aria-label={addLabel}
            aria-describedby={failed ? errorId : undefined}
          >
            <Watch className="h-4 w-4" aria-hidden="true" />
            {t('plan.add')}
          </Button>
        )}

        {role === 'next' && weekEnd && (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <CalendarDays className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {t('plan.dueBy', { date: formatDay(weekEnd, lang) })}
          </p>
        )}

        {failed && (
          <p id={errorId} role="alert" className="text-sm text-danger">
            {t('plan.downloadError')}
          </p>
        )}

        {!downloadable && (
          <p className="flex items-start gap-2 text-sm text-muted-foreground">
            <Ban className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              <span className="font-medium text-foreground">{t('plan.unavailable')}</span>
              {' · '}
              {t(reasonKey(item))}
            </span>
          </p>
        )}

        <div className="mt-auto">
          {role === 'next' && <CoachBox item={item} clampLines={3} />}
          {role === 'race' && <CoachBox item={item} />}
          {role === 'normal' && <CoachDisclosure item={item} />}
        </div>
      </Card>
    </li>
  );
}

function IphoneHelp() {
  const { t } = useTranslation();
  return (
    <details className="group rounded-xl border border-border bg-surface px-4 py-3 text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <HelpCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        {t('plan.help.title')}
      </summary>
      <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-muted-foreground">
        <li>{t('plan.help.step1')}</li>
        <li>{t('plan.help.step2')}</li>
        <li>{t('plan.help.step3')}</li>
      </ol>
      <p className="mt-3 text-muted-foreground">{t('plan.help.note')}</p>
    </details>
  );
}

/** Header pill: goal race name, assumed day and countdown. */
function RaceStrip({ item, today, lang }: { item: PlanWorkoutItem; today: Date | null; lang: string }) {
  const { t } = useTranslation();
  const countdown = useCountdown(item, today);
  const raceDay = item.week_iso ? isoWeekSunday(item.week_iso) : null;
  if (!raceDay) return null;
  return (
    <div
      className="flex min-h-11 items-center gap-3 self-start rounded-xl border border-border bg-surface px-3 py-2 text-sm"
      data-testid="plan-race-strip"
    >
      <Flag className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="text-foreground">
        {t('plan.race.strip', { title: item.title ?? t('plan.untitled'), date: formatDay(raceDay, lang) })}
      </span>
      {countdown && (
        <span className="font-bold tabular-nums text-primary-strong" aria-label={countdown.aria} role="img">
          {countdown.label}
        </span>
      )}
    </div>
  );
}

/** Week number of an ISO label (`2026-W43` -> 43), or null if the label is malformed. */
function weekNumber(weekIso: string): number | null {
  const match = WEEK_NUMBER_RE.exec(weekIso);
  return match ? Number(match[1]) : null;
}

export function PlanPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language ?? 'fr';
  const [data, setData] = useState<PlanWorkoutsResponse | null>(null);
  // Today's Paris day, captured with each response so "this week" and the countdown
  // match the data they label (and render stays pure).
  const [today, setToday] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [failedKey, setFailedKey] = useState<string | null>(null);

  const [reloadToken, setReloadToken] = useState(0);

  // State is only written in the promise callbacks, never synchronously in the effect.
  useEffect(() => {
    let cancelled = false;
    getPlanWorkouts()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setToday(athleteToday());
        setError(false);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // A reload starts clean: no stale load error nor download error stays visible
  // while the request runs, and both Retry and Refresh are disabled until it ends.
  const reload = () => {
    setError(false);
    setFailedKey(null);
    setLoading(true);
    setReloadToken((n) => n + 1);
  };

  // Synchronous on purpose: iOS Safari only hands the file to the Workout app
  // when the download starts inside the user gesture, so nothing is awaited here.
  const handleAdd = (item: PlanWorkoutItem & { workout_b64: string }) => {
    try {
      downloadWorkout(item.workout_b64, item.filename);
      setFailedKey(null);
    } catch {
      setFailedKey(itemKey(item));
    }
  };

  const workouts = useMemo(() => data?.workouts ?? [], [data]);
  const groups = useMemo(() => groupByWeek(workouts), [workouts]);

  // The API lists only open sessions (done and skipped ones are filtered server-side),
  // in Campus order, nearest week first. So the next session is the first one of the
  // first dated week: the current week's first remaining session, or next week's
  // first if this week is already complete.
  const nextItem = groups.find((g) => g.weekIso !== null)?.items[0] ?? null;
  const raceItem = workouts.find(isRace) ?? null;
  const currentWeek = today ? isoWeekLabel(today) : null;
  const followingWeek = today ? shiftedWeekLabel(today, 1) : null;

  const weekTitle = (weekIso: string | null, items: PlanWorkoutItem[]): string => {
    if (weekIso === null) return t('plan.unknownWeek');
    if (weekIso === currentWeek) return t('plan.thisWeek');
    if (weekIso === followingWeek) return t('plan.nextWeek');
    if (items.some(isRace)) return t('plan.raceWeek');
    const week = weekNumber(weekIso);
    return week === null ? weekIso : t('plan.week', { week });
  };

  return (
    <div className="flex flex-col gap-6 md:gap-8 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t('plan.title')}</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">{t('plan.description')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
          {raceItem && <RaceStrip item={raceItem} today={today} lang={lang} />}
          <Button variant="outline" size="md" onClick={reload} disabled={loading}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {t('plan.refresh')}
          </Button>
        </div>
      </div>

      <IphoneHelp />

      {loading && !data && (
        <div role="status" className="flex items-center justify-center gap-3 py-12 text-sm text-muted-foreground">
          <span
            className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary"
            aria-hidden="true"
          />
          {t('plan.loading')}
        </div>
      )}

      {error && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{t('plan.error.load')}</span>
            <Button variant="outline" size="sm" onClick={reload} disabled={loading}>
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {data?.truncated && <Alert variant="info">{t('plan.truncated')}</Alert>}

      {data && !error && workouts.length === 0 && (
        <EmptyState
          illustration="activity"
          title={t('plan.empty.title')}
          description={t('plan.empty.description')}
        />
      )}

      {groups.map((group) => {
        const weekIso = group.weekIso;
        const headingId = weekIso === null ? 'plan-week-unknown' : domId('plan-week', weekIso);
        const week = weekIso === null ? null : weekNumber(weekIso);
        const range = weekIso === null ? null : formatWeekRange(weekIso, lang);
        return (
          <section key={weekIso ?? '\u0000unknown'} aria-labelledby={headingId} className="flex flex-col gap-3">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id={headingId} className="text-lg font-semibold tracking-tight text-foreground">
                {weekTitle(weekIso, group.items)}
              </h2>
              {range && (
                <p className="text-sm text-muted-foreground" data-testid="plan-week-range">
                  {range}
                  {week !== null && ` · ${t('plan.weekShort', { week })}`}
                </p>
              )}
            </div>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {group.items.map((item, index) => {
                const isNext = item === nextItem;
                const role: CardRole = isRace(item) ? 'race' : isNext ? 'next' : 'normal';
                return (
                  <SessionCard
                    // Position suffix: degenerate rows (null ids) must not share a React key.
                    key={`${itemKey(item)}#${index}`}
                    item={item}
                    role={role}
                    primary={isNext}
                    today={today}
                    lang={lang}
                    failed={failedKey === itemKey(item)}
                    onAdd={handleAdd}
                  />
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
