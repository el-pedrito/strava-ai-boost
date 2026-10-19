/**
 * Pure decision helpers for the Home dashboard: data-trust checks, label maps
 * and chart helpers. No React, no i18n: every function is unit-tested.
 * Coach text is rendered by `components/CoachText.tsx` (shared with Plan).
 */
import type { HealthMetric, HealthSeriesPoint, HomeWeekSession } from '@/types/home';

/* ------------------------------------------------------- load gap check */

export interface LoadGap {
  /** First day of the run, `YYYY-MM-DD`. */
  start: string;
  /** Last day of the run, `YYYY-MM-DD`. */
  end: string;
  days: number;
}

/**
 * Daily decay of intervals.icu's ATL, a 7-day exponentially weighted average:
 * ATL_t = k * ATL_{t-1} + (1 - k) * load_t, with k = e^(-1/7).
 */
export const ATL_DECAY = Math.exp(-1 / 7);
/** An implied daily load below this is "nothing recorded that day". */
export const LOAD_GAP_MAX_LOAD = 1;
/** A run must span at least this many calendar days to be flagged. */
export const LOAD_GAP_MIN_DAYS = 14;
/** Missing days (no point, or a null ATL) tolerated inside a run. */
export const LOAD_GAP_MAX_HOLE_DAYS = 2;

const DAY_MS = 86_400_000;

function dayIndex(isoDate: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return null;
  return Math.round(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS);
}

function isoOfIndex(idx: number): string {
  return new Date(idx * DAY_MS).toISOString().slice(0, 10);
}

/**
 * Find the runs of days on which intervals.icu recorded no training load.
 *
 * The load is not in the payload, so it is read back from the ATL decay:
 * between two points `d` days apart, the load received is
 * `(ATL_t - k^d * ATL_prev) / (1 - k)` (for d = 1, the daily load). A run is
 * a stretch where that stays below `LOAD_GAP_MAX_LOAD` for at least
 * `LOAD_GAP_MIN_DAYS` calendar days. Reading the decay instead of an absolute
 * ATL threshold gives the true first day: from ATL 40, the average itself only
 * falls under 2 after three weeks.
 *
 * Holes of up to `LOAD_GAP_MAX_HOLE_DAYS` missing days are bridged (the check
 * then covers the whole interval); a longer hole ends the run. A real break
 * matches too: the caller words the warning conditionally.
 */
export function detectLoadGaps(
  series: ReadonlyArray<Pick<HealthSeriesPoint, 'date' | 'atl'>> | null | undefined,
  {
    maxLoad = LOAD_GAP_MAX_LOAD,
    minDays = LOAD_GAP_MIN_DAYS,
    maxHoleDays = LOAD_GAP_MAX_HOLE_DAYS,
    decay = ATL_DECAY,
  } = {}
): LoadGap[] {
  if (!series || series.length === 0) return [];
  const points = series
    .map((p) => ({ idx: dayIndex(p.date), atl: p.atl }))
    .filter((p): p is { idx: number; atl: number } => p.idx != null && p.atl != null && Number.isFinite(p.atl))
    .sort((a, b) => a.idx - b.idx);

  const gaps: LoadGap[] = [];
  let runStart: number | null = null;
  let runEnd: number | null = null;

  const close = () => {
    if (runStart != null && runEnd != null && runEnd - runStart + 1 >= minDays) {
      gaps.push({ start: isoOfIndex(runStart), end: isoOfIndex(runEnd), days: runEnd - runStart + 1 });
    }
    runStart = null;
    runEnd = null;
  };

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    const step = cur.idx - prev.idx;
    if (step === 0) continue; // duplicate day: keep the first reading
    if (step - 1 > maxHoleDays) {
      close();
      continue;
    }
    const load = (cur.atl - Math.pow(decay, step) * prev.atl) / (1 - decay);
    if (load < maxLoad) {
      if (runStart == null) runStart = prev.idx + 1;
      runEnd = cur.idx;
    } else {
      close();
    }
  }
  close();
  return gaps;
}

/** CTL is a 42-day average: a load gap keeps biasing it this long after it ends. */
export const CTL_WINDOW_DAYS = 42;

/**
 * The gaps that still bias today's CTL / freshness: those that ended less than
 * `windowDays` days before `latestDate` (the newest point of the series).
 */
export function gapsAffectingLatest(
  gaps: ReadonlyArray<LoadGap>,
  latestDate: string | null | undefined,
  windowDays = CTL_WINDOW_DAYS
): LoadGap[] {
  if (!latestDate || gaps.length === 0) return [];
  const latest = dayIndex(latestDate);
  if (latest == null) return [];
  return gaps.filter((g) => {
    const end = dayIndex(g.end);
    return end != null && latest - end < windowDays;
  });
}

/**
 * Date of the newest point carrying a finite ATL or CTL: the day the load
 * figures shown today refer to. A newer row holding only sleep or HRV does not
 * move it, so it cannot push a still-relevant gap out of the 42-day window.
 */
export function latestLoadDate(
  series: ReadonlyArray<Pick<HealthSeriesPoint, 'date' | 'atl' | 'ctl'>> | null | undefined
): string | null {
  let latest: string | null = null;
  for (const p of series ?? []) {
    const hasLoad = [p.atl, p.ctl].some((v) => v != null && Number.isFinite(v));
    if (hasLoad && dayIndex(p.date) != null && (latest == null || p.date > latest)) latest = p.date;
  }
  return latest;
}

/** True when one of `gaps` still biases today's CTL / freshness. */
export function loadGapAffectsLatest(
  gaps: ReadonlyArray<LoadGap>,
  latestDate: string | null | undefined,
  windowDays = CTL_WINDOW_DAYS
): boolean {
  return gapsAffectingLatest(gaps, latestDate, windowDays).length > 0;
}

/* ------------------------------------------------------- cycle themes */

/** Known Campus cycle themes → i18n suffix under `home.plan.cycleTheme.*`. */
const CYCLE_THEMES: ReadonlyArray<[RegExp, string]> = [
  [/^affutage/, 'taper'],
  [/^(recuperation|recup|regeneration)/, 'recovery'],
  [/^force/, 'strength'],
  [/^(foncier|endurance|base)/, 'base'],
  [/^(specifique|specific)/, 'specific'],
  [/^vitesse|^vma/, 'speed'],
  [/^seuil/, 'threshold'],
  [/^(competition|course|race)/, 'race'],
  [/^transition/, 'transition'],
  [/^(developpement|development)/, 'development'],
];

/**
 * Map a raw Campus `cycle_theme` (`Force_A21`, `affutage`...) to a label key,
 * or null for an unknown code, which the UI then hides rather than showing
 * an internal identifier.
 */
export function cycleThemeKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const norm = raw
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
  for (const [re, key] of CYCLE_THEMES) {
    if (re.test(norm)) return key;
  }
  return null;
}

/* ------------------------------------------------------------ HRV */

/** Keep only the latest hrv_kind's HRV values on a series (others -> null), so a
 * chart line never mixes SDNN and rMSSD scales. */
export function filterHrvByLatestKind<T extends { hrv: number | null; hrv_kind?: string | null }>(
  series: T[]
): Array<T & { hrv: number | null }> {
  const kinded = series.filter((p) => p.hrv != null && p.hrv_kind);
  const latest = kinded.length > 0 ? kinded[kinded.length - 1].hrv_kind : null;
  return series.map((p) => ({
    ...p,
    hrv: latest != null && p.hrv_kind !== latest ? null : p.hrv,
  }));
}

/* ------------------------------------------------------ usual value */

export type UsualKey = 'hrv' | 'resting_hr' | 'sleep_s' | 'form';

/** Sleep compares to the last 7 nights, the other signals to 60 days. */
export function usualBaseline(key: UsualKey, metric: HealthMetric): number | null {
  return (key === 'sleep_s' ? metric.baseline_7d : metric.baseline_60d) ?? null;
}

/** The payload's delta, or value − baseline when only those two are present. */
export function usualDelta(key: UsualKey, metric: HealthMetric): number | null {
  const baseline = usualBaseline(key, metric);
  if (metric.delta != null) return metric.delta;
  return metric.value != null && baseline != null ? metric.value - baseline : null;
}

/* --------------------------------------------------------- freshness */

export type FormZone = 'veryFresh' | 'fresh' | 'neutral' | 'productive' | 'overload';

/**
 * Training stress balance (CTL − ATL) in words, with the intervals.icu zone
 * bounds: > 25 transition, 5..25 fresh, −10..5 grey zone, −30..−10 optimal
 * training, < −30 high risk.
 */
export function formZone(form: number | null | undefined): FormZone | null {
  if (form == null || !Number.isFinite(form)) return null;
  if (form > 25) return 'veryFresh';
  if (form > 5) return 'fresh';
  if (form >= -10) return 'neutral';
  if (form >= -30) return 'productive';
  return 'overload';
}

/* --------------------------------------------------------- week */

export type SessionKind = 'done' | 'next' | 'todo' | 'missed';

export function sessionKind(s: Pick<HomeWeekSession, 'order' | 'status'>, nextOrder: number | null): SessionKind {
  if (s.status === 'done') return 'done';
  if (s.status === 'missed') return 'missed';
  if (nextOrder != null && s.order === nextOrder) return 'next';
  return 'todo';
}

/** Campus flags a tune-up race with this training type. */
export function isPrepRace(s: Pick<HomeWeekSession, 'training_type'>): boolean {
  return s.training_type === 'low-priority-race';
}

/** Sessions still to do this week (neither done nor missed). */
export function remainingSessions(sessions: ReadonlyArray<Pick<HomeWeekSession, 'status'>>): number {
  return sessions.filter((s) => s.status !== 'done' && s.status !== 'missed').length;
}

/* -------------------------------------------------------- charts */

/**
 * Y domain hugging a set of paces (s/km), padded and snapped to 5 s, so the
 * Enduraw lines are not flattened at the bottom of a 0:00..5:40 axis.
 */
export function paceDomain(values: ReadonlyArray<number | null | undefined>, pad = 5): [number, number] | null {
  const v = values.filter((x): x is number => x != null && Number.isFinite(x) && x > 0);
  if (v.length === 0) return null;
  const lo = Math.floor((Math.min(...v) - pad) / 5) * 5;
  const hi = Math.ceil((Math.max(...v) + pad) / 5) * 5;
  return [Math.max(0, lo), hi];
}

/** Position (0..100 %) of `value` inside `[low, high]`, clamped. */
export function rangePosition(value: number | null | undefined, low: number, high: number): number | null {
  if (value == null || !Number.isFinite(value) || !(high > low)) return null;
  const pct = ((value - low) / (high - low)) * 100;
  return Math.min(100, Math.max(0, pct));
}
