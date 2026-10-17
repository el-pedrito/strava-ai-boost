/**
 * ISO-week helpers for the Plan page. Every date here is a calendar day carried as
 * a `Date` at 00:00 UTC, so arithmetic never trips on a DST change and formatting
 * uses `timeZone: 'UTC'` to print that same calendar day back.
 */

const DAY_MS = 86_400_000;
const ISO_WEEK_RE = /^(\d{4})-W(\d{2})$/;

/** Same zone as `utils/formatDate` and the backend's week boundary (`plan_workouts.paris_date`). */
const ATHLETE_TIME_ZONE = 'Europe/Paris';

function addDays(day: Date, days: number): Date {
  return new Date(day.getTime() + days * DAY_MS);
}

/** Monday = 0 ... Sunday = 6. */
function isoWeekday(day: Date): number {
  return (day.getUTCDay() + 6) % 7;
}

/** Today's calendar day in Paris, as 00:00 UTC of that day. */
export function athleteToday(now: Date = new Date()): Date {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: ATHLETE_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return new Date(Date.UTC(get('year'), get('month') - 1, get('day')));
}

/** ISO week label `YYYY-Www` of a calendar day. */
export function isoWeekLabel(day: Date): string {
  // The ISO year is the one holding the Thursday of the week.
  const thursday = addDays(day, 3 - isoWeekday(day));
  const year = thursday.getUTCFullYear();
  const week = Math.floor((thursday.getTime() - Date.UTC(year, 0, 1)) / DAY_MS / 7) + 1;
  return `${year}-W${String(week).padStart(2, '0')}`;
}

/** Monday of an ISO week label, or null if the label is malformed or does not exist (e.g. W53 of a 52-week year). */
export function isoWeekMonday(label: string): Date | null {
  const match = ISO_WEEK_RE.exec(label);
  if (!match) return null;
  const year = Number(match[1]);
  const week = Number(match[2]);
  if (week < 1 || week > 53) return null;
  // 4 January is always in week 1.
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const monday = addDays(jan4, (week - 1) * 7 - isoWeekday(jan4));
  return isoWeekLabel(monday) === label ? monday : null;
}

/** Sunday of an ISO week label, or null. */
export function isoWeekSunday(label: string): Date | null {
  const monday = isoWeekMonday(label);
  return monday ? addDays(monday, 6) : null;
}

/** Label of the week `offset` weeks after the one holding `day`. */
export function shiftedWeekLabel(day: Date, offset: number): string {
  return isoWeekLabel(addDays(day, offset * 7));
}

/** Whole days from `from` to `to` (both calendar days at 00:00 UTC). */
export function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / DAY_MS);
}

function intlLocale(lang: string): string {
  return lang.split('-')[0] === 'en' ? 'en-GB' : 'fr-FR';
}

/** "dim. 18 oct." / "Sun 18 Oct". */
export function formatDay(day: Date, lang: string): string {
  return new Intl.DateTimeFormat(intlLocale(lang), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(day);
}

/**
 * Monday-to-Sunday range of an ISO week: "lun. 19 – dim. 25 oct.", or
 * "lun. 26 oct. – dim. 1 nov." when the week spans two months. Null if the label is malformed.
 */
export function formatWeekRange(label: string, lang: string): string | null {
  const monday = isoWeekMonday(label);
  if (!monday) return null;
  const sunday = addDays(monday, 6);
  const sameMonth = monday.getUTCMonth() === sunday.getUTCMonth();
  const start = new Intl.DateTimeFormat(intlLocale(lang), {
    weekday: 'short',
    day: 'numeric',
    ...(sameMonth ? {} : { month: 'short' as const }),
    timeZone: 'UTC',
  }).format(monday);
  return `${start} – ${formatDay(sunday, lang)}`;
}
