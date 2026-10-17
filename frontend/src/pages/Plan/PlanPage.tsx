import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Activity as ActivityIcon,
  Ban,
  Clock,
  Dumbbell,
  Footprints,
  HelpCircle,
  RefreshCw,
  Watch,
  type LucideIcon,
} from 'lucide-react';
import { getPlanWorkouts } from '@/api/client';
import { downloadWorkout } from '@/lib/downloadWorkout';
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

interface SessionCardProps {
  item: PlanWorkoutItem;
  failed: boolean;
  onAdd: (item: PlanWorkoutItem & { workout_b64: string }) => void;
}

function SessionCard({ item, failed, onAdd }: SessionCardProps) {
  const { t } = useTranslation();
  const downloadable = isDownloadable(item);
  const errorId = domId('plan-error', itemKey(item));
  const title = item.title ?? t('plan.untitled');
  const sport = item.sport ?? '';
  const SportIcon = SPORT_ICONS[sport] ?? ActivityIcon;
  const sportLabel = SPORT_ICONS[sport] ? t(`plan.sport.${sport}`) : t('plan.sport.other');

  return (
    <li>
      <Card
        padding="sm"
        variant={downloadable ? 'default' : 'flat'}
        data-testid="plan-session"
        data-encodable={downloadable ? 'true' : 'false'}
        className="flex h-full flex-col gap-3"
      >
        <div className="flex items-start gap-3">
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
              downloadable ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'
            )}
            aria-hidden="true"
          >
            <SportIcon className="h-5 w-5" />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <h3
              className={cn(
                'text-base font-semibold leading-tight',
                downloadable ? 'text-foreground' : 'text-muted-foreground'
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
          </div>
        </div>

        {item.summary && (
          <p className="break-words text-sm text-muted-foreground">{item.summary}</p>
        )}

        <div className="mt-auto flex flex-col gap-2">
          {downloadable ? (
            <>
              <Button
                variant="primary"
                size="md"
                className="w-full sm:w-auto sm:self-start"
                onClick={() => onAdd(item)}
                aria-label={t('plan.addAria', { title })}
                aria-describedby={failed ? errorId : undefined}
              >
                <Watch className="h-4 w-4" aria-hidden="true" />
                {t('plan.add')}
              </Button>
              {failed && (
                <p id={errorId} role="alert" className="text-sm text-danger">
                  {t('plan.downloadError')}
                </p>
              )}
            </>
          ) : (
            <p className="flex items-start gap-2 text-sm text-muted-foreground">
              <Ban className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                <span className="font-medium text-foreground">{t('plan.unavailable')}</span>
                {' · '}
                {t(reasonKey(item))}
              </span>
            </p>
          )}
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

/** Week number of an ISO label (`2026-W43` -> 43), or null if the label is malformed. */
function weekNumber(weekIso: string): number | null {
  const match = WEEK_NUMBER_RE.exec(weekIso);
  return match ? Number(match[1]) : null;
}

export function PlanPage() {
  const { t } = useTranslation();
  const [data, setData] = useState<PlanWorkoutsResponse | null>(null);
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

  return (
    <div className="flex flex-col gap-6 md:gap-8 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">{t('plan.title')}</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">{t('plan.description')}</p>
        </div>
        <Button
          variant="outline"
          size="md"
          onClick={reload}
          disabled={loading}
          className="self-start sm:self-auto"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('plan.refresh')}
        </Button>
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
        const heading =
          weekIso === null ? t('plan.unknownWeek') : week === null ? weekIso : t('plan.week', { week });
        return (
          <section key={weekIso ?? '\u0000unknown'} aria-labelledby={headingId} className="flex flex-col gap-3">
            <h2 id={headingId} className="text-lg font-semibold tracking-tight text-foreground">
              {heading}
            </h2>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {group.items.map((item, index) => (
                <SessionCard
                  // Position suffix: degenerate rows (null ids) must not share a React key.
                  key={`${itemKey(item)}#${index}`}
                  item={item}
                  failed={failedKey === itemKey(item)}
                  onAdd={handleAdd}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
