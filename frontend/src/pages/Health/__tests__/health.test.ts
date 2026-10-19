import { describe, it, expect } from 'vitest';
import type { BriefSignal, HealthMetric, HealthSeriesPoint, HomeBrief, HomeHealth } from '@/types/home';
import { formWithBaseline, readinessItems, zoneAgrees } from '../readiness';
import { signalStatus } from '../../Home/brief';
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

const sig = (key: string, status: string, value: number | null = 1, baseline: number | null = null): BriefSignal => ({
  key,
  value,
  baseline,
  status,
  as_of: '2026-10-19',
});

const brief = (signals: BriefSignal[] | null, light = 'green'): HomeBrief => ({
  date: '2026-10-19',
  built_at: '2026-10-19T05:30:00Z',
  light,
  signals,
  missing: null,
  next_session: null,
  weather: null,
  weather_attribution: null,
});

describe('readinessItems', () => {
  it('takes each status from the brief, sleep included under its brief key', () => {
    const items = readinessItems(
      brief([sig('hrv', 'warn'), sig('resting_hr', 'ok'), sig('sleep', 'bad'), sig('form', 'ok', 2)])
    );
    expect(items.map((i) => i.key)).toEqual(['hrv', 'resting_hr', 'sleep_s', 'form']);
    expect(items.map((i) => i.status)).toEqual(['warn', 'ok', 'bad', 'ok']);
  });

  it('reads a known value the brief skipped as stale, an absent signal as missing', () => {
    const items = readinessItems(brief([sig('hrv', 'missing', 55), sig('resting_hr', 'missing', null)]));
    expect(items.map((i) => i.status)).toEqual(['stale', 'missing', 'missing', 'missing']);
    expect(readinessItems(null).map((i) => i.status)).toEqual(['missing', 'missing', 'missing', 'missing']);
    expect(readinessItems(brief(null)).map((i) => i.status)).toEqual(['missing', 'missing', 'missing', 'missing']);
  });

  it('never applies a client threshold: an unknown status stays unavailable', () => {
    // A 30 % HRV drop the brief did not rate is not turned into an alert here.
    expect(readinessItems(brief([sig('hrv', 'weird', 42, 60)]))[0].status).toBe('missing');
    expect(signalStatus(sig('hrv', 'bad', 59, 60))).toBe('bad');
  });
});

describe('TSB zone word', () => {
  it('is never shown while the load is incomplete', () => {
    const b = brief([sig('form', 'ok', 2)]);
    expect(readinessItems(b)[3].zone).toBe('neutral');
    expect(readinessItems(b, { formIncomplete: true })[3].zone).toBeNull();
    expect(readinessItems(brief([sig('form', 'bad', -35)]), { formIncomplete: true })[3].zone).toBeNull();
  });

  it('never contradicts the brief dot', () => {
    // −26,4: "normal training fatigue" for intervals.icu, "Alerte" for the brief.
    expect(readinessItems(brief([sig('form', 'bad', -26.4)]))[3].zone).toBeNull();
    expect(readinessItems(brief([sig('form', 'bad', -35)]))[3].zone).toBe('overload');
    expect(readinessItems(brief([sig('form', 'warn', -18)]))[3].zone).toBe('productive');
    expect(readinessItems(brief([sig('form', 'ok', -12)]))[3].zone).toBe('productive');
    expect(readinessItems(brief([sig('form', 'ok', 30)]))[3].zone).toBe('veryFresh');
    // Stale or missing: no dot to agree with, no zone.
    expect(readinessItems(brief([sig('form', 'missing', 3)]))[3].zone).toBeNull();
    expect(readinessItems(null)[3].zone).toBeNull();
  });

  it('pins the agreement table', () => {
    expect(zoneAgrees('fresh', 'warn')).toBe(false);
    expect(zoneAgrees('neutral', 'bad')).toBe(false);
    expect(zoneAgrees('overload', 'ok')).toBe(false);
    expect(zoneAgrees('productive', 'stale')).toBe(false);
    expect(zoneAgrees(null, 'ok')).toBe(false);
  });
});

describe('formWithBaseline', () => {
  it('carries the brief TSB baseline and the difference to the displayed value', () => {
    expect(formWithBaseline(m(-26.4), sig('form', 'bad', -26.4, -8.2))).toMatchObject({
      value: -26.4,
      baseline_60d: -8.2,
    });
    expect(formWithBaseline(m(-26.4), sig('form', 'bad', -26.4, -8.2))?.delta).toBeCloseTo(-18.2, 5);
  });

  it('returns null without a value or a baseline, never an invented usual', () => {
    expect(formWithBaseline(m(-26.4), sig('form', 'bad', -26.4, null))).toBeNull();
    expect(formWithBaseline(m(-26.4), null)).toBeNull();
    expect(formWithBaseline(m(null), sig('form', 'bad', -26.4, -8.2))).toBeNull();
    expect(formWithBaseline(null, sig('form', 'bad', -26.4, -8.2))).toBeNull();
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
