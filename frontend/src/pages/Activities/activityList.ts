/**
 * Pure helpers for the Activités page: 30-day window, type filter, grouping by
 * ISO week in Europe/Paris and the one-line figures of a row. No React here, so
 * every rule is unit-tested on its own.
 *
 * Weeks are computed on the athlete's calendar day in Paris, never on the UTC
 * date: a session started on Monday 00:30 in Paris is still Sunday in UTC, yet
 * it opens the new week.
 */
import i18n from '@/i18n';
import { athleteToday, isoWeekLabel, isoWeekMonday, isoWeekSunday } from '@/lib/isoWeek';
import { fmtNumber, formatDuration, formatPace, NNBSP } from '@/pages/Home/format';
import { isRunType, isStrengthType } from '@/utils/activityType';

/** The list fields this page reads from GET /dashboard/activities. */
export interface ListActivity {
  activity_id?: string;
  activity_type?: string;
  enhanced_title?: string;
  original_name?: string;
  start_date?: string;
  distance?: number | null;
  moving_time?: number | null;
  processing_status?: string;
}

export type TypeFilter = 'all' | 'run' | 'strength';

export const TYPE_FILTERS: TypeFilter[] = ['all', 'run', 'strength'];

/** Length of the window the page lists (and the subtitle announces). */
export const WINDOW_DAYS = 30;

const DAY_MS = 86_400_000;

/** `?type=` value → filter. Anything unknown falls back to "Tout". */
export function parseTypeFilter(value: string | null | undefined): TypeFilter {
  return value === 'run' || value === 'strength' ? value : 'all';
}

export function matchesFilter(a: ListActivity, filter: TypeFilter): boolean {
  if (filter === 'run') return isRunType(a.activity_type);
  if (filter === 'strength') return isStrengthType(a.activity_type);
  return true;
}

function startMs(a: ListActivity): number | null {
  if (!a.start_date) return null;
  const ms = Date.parse(a.start_date);
  return Number.isNaN(ms) ? null : ms;
}

/** Activities started within the last `WINDOW_DAYS` days, newest first. */
export function inWindow(activities: ListActivity[], now: Date = new Date()): ListActivity[] {
  const from = now.getTime() - WINDOW_DAYS * DAY_MS;
  return activities
    .filter((a) => {
      const ms = startMs(a);
      return ms != null && ms >= from && ms <= now.getTime();
    })
    .sort((a, b) => (startMs(b) ?? 0) - (startMs(a) ?? 0));
}

/** ISO week label (`2026-W43`) of the activity's start, on the Paris calendar. */
export function parisWeekLabel(iso: string): string | null {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  return isoWeekLabel(athleteToday(new Date(ms)));
}

export interface WeekGroup {
  label: string;
  monday: Date;
  sunday: Date;
  isCurrent: boolean;
  items: ListActivity[];
  /** Kilometres run this week, among the listed items. */
  runKm: number;
}

/** Group activities (already sorted newest first) by Paris ISO week, newest week first. */
export function groupByWeek(activities: ListActivity[], now: Date = new Date()): WeekGroup[] {
  const current = isoWeekLabel(athleteToday(now));
  const groups = new Map<string, WeekGroup>();
  for (const a of activities) {
    const label = a.start_date ? parisWeekLabel(a.start_date) : null;
    if (!label) continue;
    let group = groups.get(label);
    if (!group) {
      const monday = isoWeekMonday(label);
      const sunday = isoWeekSunday(label);
      if (!monday || !sunday) continue;
      group = { label, monday, sunday, isCurrent: label === current, items: [], runKm: 0 };
      groups.set(label, group);
    }
    group.items.push(a);
    if (isRunType(a.activity_type) && a.distance && a.distance > 0) {
      group.runKm += a.distance / 1000;
    }
  }
  return [...groups.values()].sort((x, y) => y.monday.getTime() - x.monday.getTime());
}

function intlLocale(lang?: string): string {
  return (lang ?? i18n.language ?? 'fr').split('-')[0] === 'en' ? 'en-GB' : 'fr-FR';
}

function dayMonth(day: Date, lang?: string): string {
  return new Intl.DateTimeFormat(intlLocale(lang), { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(day);
}

/** "12–18 oct." or "28 sept.–4 oct." when the week spans two months. */
export function formatWeekSpan(monday: Date, sunday: Date, lang?: string): string {
  if (monday.getUTCMonth() === sunday.getUTCMonth()) {
    return `${monday.getUTCDate()}\u2013${dayMonth(sunday, lang)}`;
  }
  return `${dayMonth(monday, lang)}\u2013${dayMonth(sunday, lang)}`;
}

/** "5 oct.": the Monday of a past week, for "Semaine du 5 oct.". */
export function formatWeekStart(monday: Date, lang?: string): string {
  return dayMonth(monday, lang);
}

/** "7,39 km" with a decimal comma in French, null for no distance. */
export function formatKm(meters: number | null | undefined, decimals = 2, lang?: string): string | null {
  if (meters == null || !Number.isFinite(meters) || meters <= 0) return null;
  const v = fmtNumber(meters / 1000, decimals, lang);
  return v == null ? null : `${v}${NNBSP}km`;
}

/** Moving time "41:07" / "1:02:03", null when absent. */
export function formatMoving(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  return formatDuration(seconds);
}

/** "5:34 /km" for a run with both distance and time, null otherwise. */
export function formatRunPace(a: ListActivity): string | null {
  if (!isRunType(a.activity_type)) return null;
  if (!a.distance || !a.moving_time || a.distance <= 0 || a.moving_time <= 0) return null;
  const p = formatPace(a.moving_time / (a.distance / 1000));
  return p == null ? null : `${p}${NNBSP}/km`;
}

/**
 * The figures line of a row. Run: "7,39 km · 41:07 · 5:34 /km". Strength: "47:59".
 * Other sports: distance (if any) and time. Missing values are dropped, never
 * replaced by a placeholder; null when nothing is known.
 */
export function rowFigures(a: ListActivity, lang?: string): string | null {
  const parts: string[] = [];
  if (!isStrengthType(a.activity_type)) {
    const km = formatKm(a.distance, 2, lang);
    if (km) parts.push(km);
  }
  const time = formatMoving(a.moving_time);
  if (time) parts.push(time);
  const pace = formatRunPace(a);
  if (pace) parts.push(pace);
  return parts.length > 0 ? parts.join(' \u00b7 ') : null;
}

export interface WindowSummary {
  total: number;
  runs: number;
  strength: number;
}

export function summarize(activities: ListActivity[]): WindowSummary {
  return {
    total: activities.length,
    runs: activities.filter((a) => isRunType(a.activity_type)).length,
    strength: activities.filter((a) => isStrengthType(a.activity_type)).length,
  };
}

/** Status worth a badge: anything but a completed (or unknown) processing. */
export type RowStatus = 'failed' | 'processing' | null;

/** Pipeline steps before `completed` (see lambda_functions/processing). */
const IN_FLIGHT = new Set(['processing', 'fetched', 'waiting_enduraw', 'pending', 'queued']);

export function rowStatus(status: string | null | undefined): RowStatus {
  if (!status || status === 'completed') return null;
  if (status === 'failed' || status === 'error' || status === 'processing_error') return 'failed';
  if (IN_FLIGHT.has(status)) return 'processing';
  return null;
}

/** A quality score as a percentage, or null when it is not a real measure ("" or a bad value is not 0 %). */
export function qualityPct(raw: unknown): number | null {
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw < 0) return null;
  const pct = raw <= 1 ? raw * 100 : raw;
  return pct > 100 ? null : pct;
}
