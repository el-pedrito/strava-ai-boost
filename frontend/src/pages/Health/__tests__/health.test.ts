import { describe, it, expect } from 'vitest';
import type { HealthMetric, HealthSeriesPoint, HomeHealth } from '@/types/home';
import { readinessItems, readinessStatus } from '../readiness';
import { bodyTilesVisible, visibleBodyTiles } from '../body';
import { clipGaps, fillDailySeries, lastDays, newestAsOf, overlappingGaps, seriesStats } from '../series';

const m = (value: number | null, extra: Partial<HealthMetric> = {}): HealthMetric => ({
  value,
  as_of: '2026-10-19',
  stale: false,
  ...extra,
});

const point = (date: string, extra: Partial<HealthSeriesPoint> = {}): HealthSeriesPoint => ({
  date,
  resting_hr: 50,
  hrv: 60,
  hrv_kind: 'sdnn',
  sleep_s: 27000,
  ctl: 20,
  atl: 20,
  form: 0,
  ...extra,
});

describe('readinessStatus', () => {
  it('maps HRV relative drops to good / watch / bad', () => {
    expect(readinessStatus('hrv', m(60, { baseline_60d: 60, delta: 0 }))).toBe('good');
    expect(readinessStatus('hrv', m(55, { baseline_60d: 60, delta: -5 }))).toBe('watch');
    expect(readinessStatus('hrv', m(48, { baseline_60d: 60, delta: -12 }))).toBe('bad');
    // A rise is never bad.
    expect(readinessStatus('hrv', m(75, { baseline_60d: 60, delta: 15 }))).toBe('good');
  });

  it('maps resting HR rises in bpm, a drop is good', () => {
    expect(readinessStatus('resting_hr', m(47, { baseline_60d: 50, delta: -3 }))).toBe('good');
    expect(readinessStatus('resting_hr', m(53, { baseline_60d: 50, delta: 3 }))).toBe('watch');
    expect(readinessStatus('resting_hr', m(57, { baseline_60d: 50, delta: 7 }))).toBe('bad');
  });

  it('judges sleep on its absolute duration first, then the 7-night usual', () => {
    expect(readinessStatus('sleep_s', m(5 * 3600))).toBe('bad');
    expect(readinessStatus('sleep_s', m(6.5 * 3600))).toBe('watch');
    expect(readinessStatus('sleep_s', m(8 * 3600, { baseline_7d: 9 * 3600, delta: -3600 }))).toBe('watch');
    expect(readinessStatus('sleep_s', m(8 * 3600, { baseline_7d: 8 * 3600, delta: 0 }))).toBe('good');
  });

  it('maps the TSB zone, and turns uncertain while a load gap biases it', () => {
    expect(readinessStatus('form', m(5))).toBe('good');
    expect(readinessStatus('form', m(-15))).toBe('watch');
    expect(readinessStatus('form', m(-35))).toBe('bad');
    expect(readinessStatus('form', m(-35), { formIncomplete: true })).toBe('uncertain');
  });

  it('says missing without a value and uncertain without a usual value', () => {
    expect(readinessStatus('hrv', null)).toBe('missing');
    expect(readinessStatus('hrv', m(null))).toBe('missing');
    expect(readinessStatus('resting_hr', m(50))).toBe('uncertain');
  });

  it('returns the four components in order with the form zone', () => {
    const items = readinessItems({ hrv: m(60, { baseline_60d: 60 }), resting_hr: null, sleep_s: m(28000), form: m(-15) });
    expect(items.map((i) => i.key)).toEqual(['hrv', 'resting_hr', 'sleep_s', 'form']);
    expect(items.map((i) => i.status)).toEqual(['good', 'missing', 'good', 'watch']);
    expect(items[3].zone).toBe('productive');
    expect(items[0].zone).toBeNull();
  });
});

describe('body tiles', () => {
  it('hides a tile whose value is null', () => {
    expect(visibleBodyTiles({ vo2max: m(55.2), weight: null })).toEqual(['vo2max']);
    expect(visibleBodyTiles({ vo2max: m(null), weight: m(71.4) })).toEqual(['weight']);
    expect(bodyTilesVisible({ vo2max: null, weight: m(null) })).toBe(false);
  });
});

describe('series helpers', () => {
  it('inserts an all-null row for a missing day and never fills a value', () => {
    const daily = fillDailySeries([point('2026-09-03'), point('2026-09-01', { hrv: null })]);
    expect(daily.map((p) => p.date)).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
    expect(daily[0].hrv).toBeNull();
    expect(daily[1]).toMatchObject({ hrv: null, resting_hr: null, sleep_s: null, ctl: null, atl: null, form: null });
    expect(seriesStats(daily, 'hrv').count).toBe(1);
  });

  it('keeps the last 30 or 90 calendar days', () => {
    const daily = fillDailySeries(
      Array.from({ length: 91 }, (_, i) => point(new Date(Date.UTC(2026, 6, 21 + i)).toISOString().slice(0, 10)))
    );
    expect(lastDays(daily, 30)).toHaveLength(30);
    expect(lastDays(daily, 30)[0].date).toBe('2026-09-20');
    expect(lastDays(daily, 90)).toHaveLength(90);
    expect(lastDays(daily, 90).at(-1)?.date).toBe('2026-10-19');
  });

  it('clips a gap to the window and keeps the true dates for the wording', () => {
    const win = [point('2026-09-20'), point('2026-10-19')];
    const gaps = [{ start: '2026-08-12', end: '2026-10-07', days: 57 }];
    expect(clipGaps(gaps, win)).toEqual([{ start: '2026-09-20', end: '2026-10-07', days: 18 }]);
    expect(overlappingGaps(gaps, win)).toEqual(gaps);
    expect(clipGaps([{ start: '2026-07-01', end: '2026-07-20', days: 20 }], win)).toEqual([]);
  });

  it('reads the newest as_of among valued signals', () => {
    const health = {
      hrv: m(60, { as_of: '2026-10-17' }),
      ctl: m(20, { as_of: '2026-10-19' }),
      weight: m(null, { as_of: '2026-10-20' }),
    } as unknown as HomeHealth;
    expect(newestAsOf(health)).toBe('2026-10-19');
    expect(newestAsOf(null)).toBeNull();
  });
});
