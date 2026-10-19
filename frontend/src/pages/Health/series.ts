/**
 * Pure series helpers for the Santé page: one row per calendar day (so a
 * missing day is a gap, not a bridge), the 30 / 90-day window, the load gaps
 * clipped to it, and the per-chart summary figures read by screen readers.
 */
import type { HealthSeriesPoint, HomeHealth } from '@/types/home';
import type { LoadGap } from '../Home/insights';

export type RangeDays = 30 | 90;
export const RANGES: ReadonlyArray<RangeDays> = [30, 90];

const DAY_MS = 86_400_000;

function dayIndex(isoDate: string | null | undefined): number | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return null;
  return Math.round(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS);
}

function isoOfIndex(idx: number): string {
  return new Date(idx * DAY_MS).toISOString().slice(0, 10);
}

function emptyRow(date: string): HealthSeriesPoint {
  return { date, resting_hr: null, hrv: null, hrv_kind: null, sleep_s: null, ctl: null, atl: null, form: null };
}

/**
 * Sort by date and insert an all-null row for every calendar day with no
 * point, so the category X axis keeps real time spacing and a line breaks on
 * the missing day. Values are never filled in: null stays null. Unparseable
 * dates are dropped, a duplicate day keeps its first reading.
 */
export function fillDailySeries(series: ReadonlyArray<HealthSeriesPoint> | null | undefined): HealthSeriesPoint[] {
  const byDay = new Map<number, HealthSeriesPoint>();
  for (const p of series ?? []) {
    const idx = dayIndex(p.date);
    if (idx != null && !byDay.has(idx)) byDay.set(idx, p);
  }
  if (byDay.size === 0) return [];
  const keys = [...byDay.keys()];
  const first = Math.min(...keys);
  const last = Math.max(...keys);
  const out: HealthSeriesPoint[] = [];
  for (let i = first; i <= last; i++) out.push(byDay.get(i) ?? emptyRow(isoOfIndex(i)));
  return out;
}

/** The last `days` calendar days of a daily series, ending on its newest day. */
export function lastDays<T extends { date: string }>(series: ReadonlyArray<T>, days: number): T[] {
  if (series.length === 0) return [];
  const newest = Math.max(...series.map((p) => dayIndex(p.date) ?? -Infinity));
  if (!Number.isFinite(newest)) return [];
  const from = newest - days + 1;
  return series.filter((p) => {
    const idx = dayIndex(p.date);
    return idx != null && idx >= from && idx <= newest;
  });
}

/** Gaps overlapping `[first, last]` of the window, trimmed to it (dates stay on the axis). */
export function clipGaps(gaps: ReadonlyArray<LoadGap>, window: ReadonlyArray<{ date: string }>): LoadGap[] {
  if (window.length === 0) return [];
  const lo = dayIndex(window[0].date);
  const hi = dayIndex(window[window.length - 1].date);
  if (lo == null || hi == null) return [];
  const out: LoadGap[] = [];
  for (const g of gaps) {
    const s = dayIndex(g.start);
    const e = dayIndex(g.end);
    if (s == null || e == null || e < lo || s > hi) continue;
    const cs = Math.max(s, lo);
    const ce = Math.min(e, hi);
    out.push({ start: isoOfIndex(cs), end: isoOfIndex(ce), days: ce - cs + 1 });
  }
  return out;
}

/** The gaps (with their true dates) that overlap the window: what the warning text names. */
export function overlappingGaps(gaps: ReadonlyArray<LoadGap>, window: ReadonlyArray<{ date: string }>): LoadGap[] {
  if (window.length === 0) return [];
  const lo = window[0].date;
  const hi = window[window.length - 1].date;
  return gaps.filter((g) => g.end >= lo && g.start <= hi);
}

export interface SeriesStats {
  count: number;
  min: number | null;
  max: number | null;
  last: number | null;
  lastDate: string | null;
}

/** Measurement count, range and newest value of one column (nulls skipped). */
export function seriesStats<T extends { date: string }>(series: ReadonlyArray<T>, key: keyof T): SeriesStats {
  let count = 0;
  let min: number | null = null;
  let max: number | null = null;
  let last: number | null = null;
  let lastDate: string | null = null;
  for (const p of series) {
    const v = p[key];
    if (typeof v !== 'number' || !Number.isFinite(v)) continue;
    count += 1;
    min = min == null ? v : Math.min(min, v);
    max = max == null ? v : Math.max(max, v);
    last = v;
    lastDate = p.date;
  }
  return { count, min, max, last, lastDate };
}

const HEALTH_KEYS = ['hrv', 'resting_hr', 'sleep_s', 'sleep_score', 'ctl', 'atl', 'form', 'vo2max', 'weight'] as const;

/** Newest `as_of` among the health signals that carry a value: the page's "données au". */
export function newestAsOf(health: HomeHealth | null | undefined): string | null {
  if (!health) return null;
  let newest: string | null = null;
  for (const k of HEALTH_KEYS) {
    const m = health[k];
    if (m?.value != null && m.as_of && dayIndex(m.as_of) != null && (newest == null || m.as_of > newest)) newest = m.as_of;
  }
  return newest;
}
