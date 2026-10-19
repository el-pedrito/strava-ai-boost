import { describe, it, expect } from 'vitest';
import type { HealthSeriesPoint } from '@/types/home';
import {
  cycleThemeKey,
  detectLoadGaps,
  formZone,
  gapsAffectingLatest,
  isPrepRace,
  latestLoadDate,
  loadGapAffectsLatest,
  paceDomain,
  rangePosition,
  remainingSessions,
  sessionKind,
} from '../insights';

type AtlPoint = Pick<HealthSeriesPoint, 'date' | 'atl'>;

const K = Math.exp(-1 / 7);
/** A training week of daily loads with single rest days, as a runner logs them. */
const TRAINING_WEEK = [55, 0, 70, 45, 0, 90, 40];

function isoPlus(start: string, days: number): string {
  return new Date(Date.parse(`${start}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
}

/**
 * Daily ATL as intervals.icu computes it (EWMA, k = e^(-1/7)) from `atl0` the
 * day before `start`, rounded to one decimal like the stored values.
 */
function ewmaSeries(start: string, loads: number[], atl0: number): AtlPoint[] {
  let atl = atl0;
  return loads.map((load, i) => {
    atl = K * atl + (1 - K) * load;
    return { date: isoPlus(start, i), atl: Math.round(atl * 10) / 10 };
  });
}

function training(days: number): number[] {
  return Array.from({ length: days }, (_, i) => TRAINING_WEEK[i % TRAINING_WEEK.length]);
}

function zeros(days: number): number[] {
  return Array.from({ length: days }, () => 0);
}

describe('detectLoadGaps', () => {
  it('reports the true first day of a 37-day outage from a realistic ATL decay', () => {
    // Training through 31 Aug (a 70 load that day), nothing recorded 1 Sep..7 Oct,
    // training again from 8 Oct.
    const series = ewmaSeries('2026-08-01', [...training(31), ...zeros(37), ...training(10)], 35);
    expect(series[30]).toEqual({ date: '2026-08-31', atl: expect.any(Number) });
    expect(series[30].atl).toBeGreaterThan(30);
    // The ATL itself is still above 2 for about three weeks into the outage...
    expect(series.find((p) => p.date === '2026-09-15')!.atl!).toBeGreaterThan(2);
    // ...but the decay shows nothing was recorded from the very first day.
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-09-01', end: '2026-10-07', days: 37 }]);
  });

  it('flags an outage that starts from ATL 60, which an ATL threshold never reaches in 3 weeks', () => {
    const series = ewmaSeries('2026-08-01', [...training(20).map((l) => l * 2), ...zeros(21), ...training(5)], 60);
    const lastBefore = series[19].atl!;
    expect(lastBefore).toBeGreaterThan(55);
    expect(Math.min(...series.slice(20, 41).map((p) => p.atl!))).toBeGreaterThan(2);
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-08-21', end: '2026-09-10', days: 21 }]);
  });

  it('bridges a one-day hole and a null ATL inside an outage', () => {
    const full = ewmaSeries('2026-09-01', [...training(14), ...zeros(20), ...training(3)], 30);
    // 15 Sep..4 Oct has no load; drop 22 Sep and blank 28 Sep.
    const series = full
      .filter((p) => p.date !== '2026-09-22')
      .map((p) => (p.date === '2026-09-28' ? { ...p, atl: null } : p));
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-09-15', end: '2026-10-04', days: 20 }]);
  });

  it('ends a run on a hole longer than two days', () => {
    const full = ewmaSeries('2026-09-01', [...training(14), ...zeros(24), ...training(3)], 30);
    // 15 Sep..8 Oct has no load; a 3-day hole (25..27 Sep) splits it into 10 + 11 days.
    const series = full.filter((p) => !['2026-09-25', '2026-09-26', '2026-09-27'].includes(p.date));
    expect(detectLoadGaps(series)).toEqual([]);
  });

  it('does not flag a real 10-day break', () => {
    const series = ewmaSeries('2026-09-01', [...training(21), ...zeros(10), ...training(14)], 35);
    expect(detectLoadGaps(series)).toEqual([]);
  });

  it('flags a genuine 21-day break like an outage (the caller words it conditionally)', () => {
    // The ATL decay cannot tell a real rest from missing data: both read as "no load".
    const series = ewmaSeries('2026-09-01', [...training(21), ...zeros(21), ...training(7)], 35);
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-09-22', end: '2026-10-12', days: 21 }]);
  });

  it('flags from exactly 14 days, not 13', () => {
    const at14 = ewmaSeries('2026-09-01', [...training(7), ...zeros(14), ...training(2)], 30);
    expect(detectLoadGaps(at14)).toEqual([{ start: '2026-09-08', end: '2026-09-21', days: 14 }]);
    const at13 = ewmaSeries('2026-09-01', [...training(7), ...zeros(13), ...training(2)], 30);
    expect(detectLoadGaps(at13)).toEqual([]);
  });

  it('finds nothing in steady training, and tolerates unordered, empty or null input', () => {
    expect(detectLoadGaps(ewmaSeries('2026-07-01', training(90), 35))).toEqual([]);
    const outage = ewmaSeries('2026-09-01', [...training(7), ...zeros(15), ...training(2)], 30);
    expect(detectLoadGaps([...outage].reverse())).toEqual([{ start: '2026-09-08', end: '2026-09-22', days: 15 }]);
    expect(detectLoadGaps([])).toEqual([]);
    expect(detectLoadGaps(null)).toEqual([]);
  });

  it('keeps only the gaps that still bias the latest CTL (42-day window)', () => {
    const gap = { start: '2026-09-01', end: '2026-10-07', days: 37 };
    expect(gapsAffectingLatest([gap], '2026-10-17')).toEqual([gap]);
    expect(gapsAffectingLatest([gap], '2026-11-17')).toEqual([gap]);
    expect(gapsAffectingLatest([gap], '2026-11-18')).toEqual([]);
    expect(loadGapAffectsLatest([gap], '2026-11-18')).toBe(false);
    expect(loadGapAffectsLatest([gap], '2026-10-17')).toBe(true);
    expect(loadGapAffectsLatest([], '2026-10-17')).toBe(false);
    expect(loadGapAffectsLatest([gap], null)).toBe(false);
  });
});

describe('latestLoadDate', () => {
  it('anchors on the newest row with a finite ATL or CTL, ignoring sleep-only rows', () => {
    const rows = [
      { date: '2026-10-10', atl: 20, ctl: 30 },
      { date: '2026-10-12', atl: null, ctl: 31 },
      { date: '2026-10-14', atl: null, ctl: null },
      { date: '2026-10-15', atl: Number.NaN, ctl: null },
    ];
    expect(latestLoadDate(rows)).toBe('2026-10-12');
    expect(latestLoadDate([...rows].reverse())).toBe('2026-10-12');
    expect(latestLoadDate([{ date: '2026-10-14', atl: null, ctl: null }])).toBeNull();
    expect(latestLoadDate([])).toBeNull();
    expect(latestLoadDate(null)).toBeNull();
  });
});

describe('cycleThemeKey', () => {
  it('maps Campus cycle codes to words and hides unknown codes', () => {
    expect(cycleThemeKey('Force_A21')).toBe('strength');
    expect(cycleThemeKey('affutage')).toBe('taper');
    expect(cycleThemeKey('Affûtage')).toBe('taper');
    expect(cycleThemeKey('Récupération')).toBe('recovery');
    expect(cycleThemeKey('XQ_17')).toBeNull();
    expect(cycleThemeKey(null)).toBeNull();
  });
});

describe('week helpers', () => {
  it('classifies sessions as done, next, todo or missed', () => {
    expect(sessionKind({ order: 1, status: 'done' }, 3)).toBe('done');
    expect(sessionKind({ order: 2, status: 'missed' }, 3)).toBe('missed');
    expect(sessionKind({ order: 3, status: 'todo' }, 3)).toBe('next');
    expect(sessionKind({ order: 4, status: 'todo' }, 3)).toBe('todo');
    expect(sessionKind({ order: 4, status: 'todo' }, null)).toBe('todo');
  });

  it('counts the remaining sessions and flags the tune-up race', () => {
    expect(remainingSessions([{ status: 'done' }, { status: 'todo' }, { status: 'missed' }, { status: 'todo' }])).toBe(2);
    expect(isPrepRace({ training_type: 'low-priority-race' })).toBe(true);
    expect(isPrepRace({ training_type: 'EF' })).toBe(false);
  });
});

describe('number helpers', () => {
  it('names the freshness zone with the intervals.icu bounds', () => {
    expect(formZone(30)).toBe('veryFresh');
    expect(formZone(10)).toBe('fresh');
    expect(formZone(-10)).toBe('neutral');
    expect(formZone(-14.3)).toBe('productive');
    expect(formZone(-31)).toBe('overload');
    expect(formZone(null)).toBeNull();
  });

  it('hugs the pace axis around the data', () => {
    expect(paceDomain([335, 334, 326, 328])).toEqual([320, 340]);
    expect(paceDomain([null, undefined])).toBeNull();
  });

  it('places a value inside a range, clamped', () => {
    expect(rangePosition(5857, 5714, 6001)).toBeCloseTo(49.8, 1);
    expect(rangePosition(5000, 5714, 6001)).toBe(0);
    expect(rangePosition(5800, 6000, 6000)).toBeNull();
  });
});
