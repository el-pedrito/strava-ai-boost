/**
 * Pure formatters for the Home dashboard. Kept out of the component file so they
 * can be unit-tested and reused by the block sub-components. Everything is
 * null-safe: the contract allows every value to be missing.
 *
 * Numbers follow the reader's locale (decimal comma in French) and negative
 * values use the true minus sign U+2212, never a hyphen. No formatter ever
 * returns raw seconds or an unrounded float: Pierre's "28890.0 base 28412.2"
 * was the sleep in seconds with a forced decimal.
 */
import i18n from '@/i18n';
import { DISPLAY_TIME_ZONE } from '@/utils/formatDate';

/** U+2212, the typographic minus sign. */
export const MINUS = '\u2212';
/** U+202F, narrow no-break space between a number and its unit. */
export const NNBSP = '\u202F';

function intlLocale(lang?: string): string {
  const base = (lang ?? i18n.language ?? 'fr').split('-')[0];
  return base === 'en' ? 'en-GB' : 'fr-FR';
}

/* ------------------------------------------------------------ numbers */

/**
 * Locale number with a fixed number of decimals and a real minus sign:
 * `fmtNumber(-14.3, 1, 'fr')` → `"−14,3"`. Null for a missing value.
 */
export function fmtNumber(
  value: number | null | undefined,
  decimals = 0,
  lang?: string
): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const factor = 10 ** decimals;
  const rounded = Math.round(Math.abs(value) * factor) / factor;
  const body = new Intl.NumberFormat(intlLocale(lang), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(rounded);
  // A value that rounds to zero is shown unsigned ("0", never "−0").
  return value < 0 && rounded !== 0 ? `${MINUS}${body}` : body;
}

/** Like `fmtNumber` but always signed: `"+4,8"`, `"−3,2"`, `"0"`. */
export function fmtSigned(
  value: number | null | undefined,
  decimals = 0,
  lang?: string
): string | null {
  const body = fmtNumber(value, decimals, lang);
  if (body == null) return null;
  if (body.startsWith(MINUS)) return body;
  const factor = 10 ** decimals;
  return Math.round(Math.abs(value as number) * factor) === 0 ? body : `+${body}`;
}

/* --------------------------------------------------------- per metric */

export type MetricKey =
  | 'hrv'
  | 'resting_hr'
  | 'sleep'
  | 'form'
  | 'ctl'
  | 'atl'
  | 'vo2max'
  | 'weight';

interface MetricSpec {
  decimals: number;
  /** Decimals of a difference vs the usual value. */
  diffDecimals: number;
  unit: string;
  /** True when a higher value is the good direction (false: resting HR). */
  higherIsBetter: boolean | null;
}

const METRIC_SPEC: Record<Exclude<MetricKey, 'sleep'>, MetricSpec> = {
  hrv: { decimals: 0, diffDecimals: 1, unit: 'ms', higherIsBetter: true },
  resting_hr: { decimals: 0, diffDecimals: 1, unit: 'bpm', higherIsBetter: false },
  form: { decimals: 1, diffDecimals: 1, unit: '', higherIsBetter: null },
  ctl: { decimals: 1, diffDecimals: 1, unit: '', higherIsBetter: null },
  atl: { decimals: 1, diffDecimals: 1, unit: '', higherIsBetter: null },
  vo2max: { decimals: 1, diffDecimals: 1, unit: '', higherIsBetter: true },
  weight: { decimals: 1, diffDecimals: 1, unit: 'kg', higherIsBetter: null },
};

/** Normalise the brief signal key `sleep` and the health key `sleep_s`. */
export function metricKey(key: string): MetricKey | null {
  if (key === 'sleep_s' || key === 'sleep') return 'sleep';
  return key in METRIC_SPEC ? (key as MetricKey) : null;
}

/** A displayed value split into number and unit, so the unit can be styled apart. */
export interface FormattedValue {
  value: string;
  unit: string;
}

/**
 * The single per-metric display rule:
 * sleep `8 h 01`, HRV `90 ms`, resting HR `50 bpm`, form/CTL/ATL `−14,3`,
 * VO2max `56,6`, weight `92,0 kg`.
 */
export function formatMetric(
  key: string,
  value: number | null | undefined,
  lang?: string
): FormattedValue | null {
  const k = metricKey(key);
  if (k == null) return null;
  if (k === 'sleep') {
    const s = formatSleep(value);
    return s == null ? null : { value: s, unit: '' };
  }
  const spec = METRIC_SPEC[k];
  const v = fmtNumber(value, spec.decimals, lang);
  return v == null ? null : { value: v, unit: spec.unit };
}

/** `formatMetric` joined into one string: `"90 ms"`. */
export function formatMetricText(
  key: string,
  value: number | null | undefined,
  lang?: string
): string | null {
  const f = formatMetric(key, value, lang);
  if (f == null) return null;
  return f.unit ? `${f.value}${NNBSP}${f.unit}` : f.value;
}

export type DiffTone = 'good' | 'bad' | 'neutral';

export interface FormattedDiff {
  /** Signed text with its unit: `"+4,8 ms"`, `"−3,2 bpm"`, `"+8 min"`. */
  text: string;
  direction: 'up' | 'down' | 'flat';
  tone: DiffTone;
}

/**
 * Difference today − usual value, signed, with unit, and whether it is good
 * news. Resting HR going down is good; HRV and sleep going up are good.
 */
export function formatDiff(
  key: string,
  diff: number | null | undefined,
  lang?: string
): FormattedDiff | null {
  const k = metricKey(key);
  if (k == null || diff == null || !Number.isFinite(diff)) return null;

  let text: string | null;
  let higherIsBetter: boolean | null;
  let flat: boolean;
  if (k === 'sleep') {
    text = formatSleepDelta(diff);
    higherIsBetter = true;
    flat = Math.round(Math.abs(diff) / 60) === 0;
  } else {
    const spec = METRIC_SPEC[k];
    const body = fmtSigned(diff, spec.diffDecimals, lang);
    text = body == null ? null : spec.unit ? `${body}${NNBSP}${spec.unit}` : body;
    higherIsBetter = spec.higherIsBetter;
    flat = Math.round(Math.abs(diff) * 10 ** spec.diffDecimals) === 0;
  }
  if (text == null) return null;

  const direction = flat ? 'flat' : diff > 0 ? 'up' : 'down';
  let tone: DiffTone = 'neutral';
  if (!flat && higherIsBetter != null) {
    tone = (diff > 0) === higherIsBetter ? 'good' : 'bad';
  }
  return { text, direction, tone };
}

/* ---------------------------------------------------------- durations */

/** `5759` → `"1:35:59"`, `1228` → `"20:28"`. Race and prediction times. */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Signed gap between two times: `98` → `"+1:38"`, `-20` → `"−0:20"`. */
export function formatGap(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  const body = formatDuration(Math.abs(seconds));
  if (body == null) return null;
  const rounded = Math.round(seconds);
  if (rounded === 0) return '0:00';
  return `${rounded > 0 ? '+' : MINUS}${body}`;
}

/**
 * Sleep duration, never a clock time: `28890` → `"8 h 01"`, `1500` → `"25 min"`.
 * Floors to the minute, like the watch apps.
 */
export function formatSleep(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const minutes = Math.floor(Math.round(seconds) / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}${NNBSP}min`;
  return `${h}${NNBSP}h${NNBSP}${String(m).padStart(2, '0')}`;
}

/** Signed sleep difference: `477.8` → `"+8 min"`, `-3900` → `"−1 h 05"`. */
export function formatSleepDelta(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds)) return null;
  const minutes = Math.round(Math.abs(seconds) / 60);
  if (minutes === 0) return `0${NNBSP}min`;
  const sign = seconds > 0 ? '+' : MINUS;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${sign}${m}${NNBSP}min`;
  return `${sign}${h}${NNBSP}h${NNBSP}${String(m).padStart(2, '0')}`;
}

/** Pace s/km → `"4:33"` (min:sec per km). */
export function formatPace(secPerKm: number | null | undefined): string | null {
  if (secPerKm == null || !Number.isFinite(secPerKm) || secPerKm <= 0) return null;
  const total = Math.round(secPerKm);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** `[low, high]` seconds → `"1:35:14 – 1:40:01"`, null if either bound missing. */
export function formatRange(range: [number, number] | null | undefined): string | null {
  if (!range || range.length !== 2) return null;
  const lo = formatDuration(range[0]);
  const hi = formatDuration(range[1]);
  if (lo == null || hi == null) return null;
  return `${lo} \u2013 ${hi}`;
}

/* -------------------------------------------------------------- dates */

function parseIsoDate(isoDate: string | null | undefined): Date | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!m) return null;
  // Calendar date, not an instant: build it at noon UTC and format in UTC so
  // no timezone can shift it to the previous or next day.
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12));
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * ISO date `YYYY-MM-DD` → `"JJ/MM"`. Kept for chart ticks. Returns null for a
 * missing/garbled date so the caller drops the suffix rather than show "NaN".
 */
export function formatDayMonth(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!m) return null;
  return `${m[3]}/${m[2]}`;
}

/** `"2026-10-16"` → `"16 oct."` (fr) / `"16 Oct"` (en). */
export function formatShortDate(isoDate: string | null | undefined, lang?: string): string | null {
  const d = parseIsoDate(isoDate);
  if (!d) return null;
  return new Intl.DateTimeFormat(intlLocale(lang), {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(d);
}

/** `"2026-11-15"` → `"dim. 15 nov."` (fr) / `"Sun 15 Nov"` (en). */
export function formatWeekdayDate(isoDate: string | null | undefined, lang?: string): string | null {
  const d = parseIsoDate(isoDate);
  if (!d) return null;
  return new Intl.DateTimeFormat(intlLocale(lang), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  }).format(d);
}

/** ISO timestamp → `HH:MM` in Europe/Paris (the athlete's clock), null if unparseable. */
export function formatClock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: DISPLAY_TIME_ZONE,
  }).formatToParts(d);
  const h = parts.find((p) => p.type === 'hour')?.value ?? '00';
  const min = parts.find((p) => p.type === 'minute')?.value ?? '00';
  return `${h}:${min}`;
}

/** ISO week `"2026-W42"` → `42`, null when garbled. */
export function isoWeekNumber(week: string | null | undefined): number | null {
  if (!week) return null;
  const m = /^\d{4}-W(\d{1,2})$/.exec(week);
  return m ? Number(m[1]) : null;
}

/* --------------------------------------------------------------- misc */

/** `"SEMI-MARATHON"` → `"Semi-marathon"`. Mixed-case names are left alone. */
export function sentenceCase(text: string | null | undefined): string | null {
  if (!text) return null;
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (trimmed !== trimmed.toUpperCase()) return trimmed;
  const lower = trimmed.toLocaleLowerCase('fr-FR');
  return lower.charAt(0).toLocaleUpperCase('fr-FR') + lower.slice(1);
}
