/**
 * Pure decision helpers for the Home dashboard: data-trust checks, label maps
 * and text parsing. No React, no i18n: every function is unit-tested.
 */
import type { HealthSeriesPoint, HomeWeekSession } from '@/types/home';

/* ------------------------------------------------------- load gap check */

export interface LoadGap {
  /** First day of the run, `YYYY-MM-DD`. */
  start: string;
  /** Last day of the run, `YYYY-MM-DD`. */
  end: string;
  days: number;
}

/** ATL below this is "no training load at all" for a runner who trains weekly. */
export const LOAD_GAP_ATL_MAX = 2;
/** A run must last at least this many consecutive days to be flagged. */
export const LOAD_GAP_MIN_DAYS = 14;

const DAY_MS = 86_400_000;

function dayIndex(isoDate: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return null;
  return Math.round(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS);
}

/**
 * Find the runs of consecutive days where intervals.icu's ATL stays below
 * `LOAD_GAP_ATL_MAX` for at least `LOAD_GAP_MIN_DAYS` days.
 *
 * Why: when intervals.icu stops receiving activities, ATL decays to ~0 while
 * the athlete keeps running, so CTL and form (TSB) become silently wrong.
 * A real 2-week break would also match; the caller words the warning so the
 * athlete can tell. A null ATL or a missing calendar day breaks the run: we
 * only flag what the data actually shows.
 */
export function detectLoadGaps(
  series: ReadonlyArray<Pick<HealthSeriesPoint, 'date' | 'atl'>> | null | undefined,
  { atlMax = LOAD_GAP_ATL_MAX, minDays = LOAD_GAP_MIN_DAYS } = {}
): LoadGap[] {
  if (!series || series.length === 0) return [];
  const sorted = [...series].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const gaps: LoadGap[] = [];
  let runStart: string | null = null;
  let runEnd: string | null = null;
  let runDays = 0;
  let prevIdx: number | null = null;

  const close = () => {
    if (runStart && runEnd && runDays >= minDays) {
      gaps.push({ start: runStart, end: runEnd, days: runDays });
    }
    runStart = null;
    runEnd = null;
    runDays = 0;
  };

  for (const p of sorted) {
    const idx = dayIndex(p.date);
    const low = idx != null && p.atl != null && Number.isFinite(p.atl) && p.atl < atlMax;
    const contiguous = idx != null && prevIdx != null && idx - prevIdx === 1;
    if (low) {
      if (runStart && !contiguous) close();
      if (!runStart) runStart = p.date;
      runEnd = p.date;
      runDays += 1;
    } else {
      close();
    }
    prevIdx = idx;
  }
  close();
  return gaps;
}

/** CTL is a 42-day average: a load gap keeps biasing it this long after it ends. */
export const CTL_WINDOW_DAYS = 42;

/**
 * True when one of `gaps` still biases today's CTL / freshness: it ended less
 * than `windowDays` days before `latestDate` (the newest point of the series).
 */
export function loadGapAffectsLatest(
  gaps: ReadonlyArray<LoadGap>,
  latestDate: string | null | undefined,
  windowDays = CTL_WINDOW_DAYS
): boolean {
  if (!latestDate || gaps.length === 0) return false;
  const latest = dayIndex(latestDate);
  if (latest == null) return false;
  return gaps.some((g) => {
    const end = dayIndex(g.end);
    return end != null && latest - end < windowDays;
  });
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

/* ------------------------------------------------------- coach words */

export type CoachSegment =
  | { kind: 'text'; text: string }
  | { kind: 'bold'; text: string }
  | { kind: 'link'; href: string };

const URL_RE = /https?:\/\/[^\s<>"')\]]+/g;

function linkSegments(text: string, out: CoachSegment[], bold: boolean) {
  let last = 0;
  for (const m of text.matchAll(URL_RE)) {
    const start = m.index ?? 0;
    // Trailing punctuation belongs to the sentence, not the URL.
    const href = m[0].replace(/[.,;:!?]+$/, '');
    if (start > last) out.push({ kind: bold ? 'bold' : 'text', text: text.slice(last, start) });
    out.push({ kind: 'link', href });
    last = start + href.length;
  }
  if (last < text.length) out.push({ kind: bold ? 'bold' : 'text', text: text.slice(last) });
}

/**
 * Parse the Campus coach word into lines of safe segments: `**x**` becomes
 * bold, http(s) URLs become links. Everything else stays plain text, rendered
 * by React (escaped), never as HTML. Empty lines are dropped.
 */
export function parseCoachText(raw: string | null | undefined): CoachSegment[][] {
  if (!raw) return [];
  const lines = raw.replace(/\r\n?/g, '\n').split('\n');
  const result: CoachSegment[][] = [];
  for (const line of lines) {
    if (!line.trim()) continue;
    const segs: CoachSegment[] = [];
    const parts = line.split('**');
    // An odd number of parts means every `**` is paired; otherwise keep the
    // stray markers as text rather than bolding half a sentence.
    const paired = parts.length % 2 === 1;
    if (!paired) {
      linkSegments(line, segs, false);
    } else {
      parts.forEach((part, i) => {
        if (part) linkSegments(part, segs, i % 2 === 1);
      });
    }
    result.push(segs);
  }
  return result;
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
