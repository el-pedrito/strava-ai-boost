import { describe, it, expect } from 'vitest';
import type { HealthSeriesPoint } from '@/types/home';
import {
  cycleThemeKey,
  detectLoadGaps,
  formZone,
  isPrepRace,
  loadGapAffectsLatest,
  paceDomain,
  parseCoachText,
  rangePosition,
  remainingSessions,
  sessionKind,
} from '../insights';

type AtlPoint = Pick<HealthSeriesPoint, 'date' | 'atl'>;

/** `days` consecutive points from `start` with the ATL given by `atl(i)`. */
function atlRun(start: string, days: number, atl: (i: number) => number | null): AtlPoint[] {
  const t0 = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: days }, (_, i) => ({
    date: new Date(t0 + i * 86_400_000).toISOString().slice(0, 10),
    atl: atl(i),
  }));
}

describe('detectLoadGaps', () => {
  it('finds the run of 37 days with ATL < 2 seen in the real data', () => {
    const series = [
      ...atlRun('2026-07-19', 44, () => 15),
      ...atlRun('2026-09-01', 37, (i) => 1.9 - i * 0.04),
      ...atlRun('2026-10-08', 10, () => 22),
    ];
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-09-01', end: '2026-10-07', days: 37 }]);
  });

  it('ignores a short dip under the 14-day minimum', () => {
    const series = [...atlRun('2026-09-01', 13, () => 0.5), ...atlRun('2026-09-14', 5, () => 10)];
    expect(detectLoadGaps(series)).toEqual([]);
    // Exactly 14 days is flagged.
    expect(detectLoadGaps(atlRun('2026-09-01', 14, () => 0.5))).toHaveLength(1);
  });

  it('breaks a run on a missing calendar day or a null ATL', () => {
    const missingDay = [...atlRun('2026-09-01', 10, () => 0.5), ...atlRun('2026-09-12', 10, () => 0.5)];
    expect(detectLoadGaps(missingDay)).toEqual([]);
    const nullAtl = atlRun('2026-09-01', 21, (i) => (i === 10 ? null : 0.5));
    expect(detectLoadGaps(nullAtl)).toEqual([]);
  });

  it('sorts unordered input and tolerates empty or null series', () => {
    const series = atlRun('2026-09-01', 15, () => 1).reverse();
    expect(detectLoadGaps(series)).toEqual([{ start: '2026-09-01', end: '2026-09-15', days: 15 }]);
    expect(detectLoadGaps([])).toEqual([]);
    expect(detectLoadGaps(null)).toEqual([]);
  });

  it('says whether a gap still biases the latest CTL (42-day window)', () => {
    const gap = [{ start: '2026-09-01', end: '2026-10-07', days: 37 }];
    expect(loadGapAffectsLatest(gap, '2026-10-17')).toBe(true);
    expect(loadGapAffectsLatest(gap, '2026-11-17')).toBe(true);
    expect(loadGapAffectsLatest(gap, '2026-11-18')).toBe(false);
    expect(loadGapAffectsLatest([], '2026-10-17')).toBe(false);
    expect(loadGapAffectsLatest(gap, null)).toBe(false);
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

describe('parseCoachText', () => {
  it('turns **bold** and URLs into safe segments, line by line', () => {
    const lines = parseCoachText('Reste **relâché** ici.\n\nVoir https://example.com/v1. Merci');
    expect(lines).toEqual([
      [
        { kind: 'text', text: 'Reste ' },
        { kind: 'bold', text: 'relâché' },
        { kind: 'text', text: ' ici.' },
      ],
      [
        { kind: 'text', text: 'Voir ' },
        { kind: 'link', href: 'https://example.com/v1' },
        { kind: 'text', text: '. Merci' },
      ],
    ]);
  });

  it('keeps an unpaired ** and HTML as plain text', () => {
    expect(parseCoachText('a ** b <b>x</b>')).toEqual([[{ kind: 'text', text: 'a ** b <b>x</b>' }]]);
    expect(parseCoachText(null)).toEqual([]);
    expect(parseCoachText('  \n ')).toEqual([]);
  });

  it('does not turn a javascript: scheme into a link', () => {
    const lines = parseCoachText('javascript:alert(1)');
    expect(lines.flat().some((s) => s.kind === 'link')).toBe(false);
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
