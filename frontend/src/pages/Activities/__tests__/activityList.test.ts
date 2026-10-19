import { describe, it, expect } from 'vitest';
import {
  formatWeekSpan,
  formatWeekStart,
  groupByWeek,
  inWindow,
  matchesFilter,
  parisWeekLabel,
  parseTypeFilter,
  rowFigures,
  rowStatus,
  summarize,
  type ListActivity,
} from '../activityList';

/** Replace the narrow no-break space so expectations stay readable. */
const plain = (s: string | null) => (s == null ? s : s.replace(/\u202f/g, ' '));

const run = (id: string, start: string, distance = 10000, moving = 3000): ListActivity => ({
  activity_id: id,
  activity_type: 'Run',
  enhanced_title: `Run ${id}`,
  start_date: start,
  distance,
  moving_time: moving,
  processing_status: 'completed',
});

const gym = (id: string, start: string, moving = 2879): ListActivity => ({
  activity_id: id,
  activity_type: 'WeightTraining',
  enhanced_title: `Gym ${id}`,
  start_date: start,
  distance: 0,
  moving_time: moving,
  processing_status: 'completed',
});

describe('parisWeekLabel', () => {
  it('uses the Paris calendar day across the late-October DST change', () => {
    // Sunday 25 Oct 2026, 02:30 CEST (before the switch back): week 43.
    expect(parisWeekLabel('2026-10-25T00:30:00Z')).toBe('2026-W43');
    // Sunday 25 Oct, 23:30 CET (after the switch): still week 43.
    expect(parisWeekLabel('2026-10-25T22:30:00Z')).toBe('2026-W43');
    // Monday 26 Oct, 00:30 CET, while UTC still reads Sunday: week 44.
    expect(parisWeekLabel('2026-10-25T23:30:00Z')).toBe('2026-W44');
  });

  it('returns null for an unreadable date', () => {
    expect(parisWeekLabel('not a date')).toBeNull();
  });
});

describe('groupByWeek', () => {
  it('groups newest week first, flags the current week and sums run km only', () => {
    const now = new Date('2026-10-27T08:00:00Z');
    const items = inWindow(
      [
        run('a', '2026-10-26T06:00:00Z', 8000),
        gym('b', '2026-10-25T23:30:00Z'),
        run('c', '2026-10-25T22:30:00Z', 12500),
        run('d', '2026-10-20T17:00:00Z', 5200),
        gym('e', '2026-10-19T06:00:00Z'),
      ],
      now,
    );
    const groups = groupByWeek(items, now);
    expect(groups.map((g) => g.label)).toEqual(['2026-W44', '2026-W43']);
    expect(groups[0].isCurrent).toBe(true);
    expect(groups[1].isCurrent).toBe(false);
    // Monday 00:30 Paris opens the new week; Sunday 23:30 Paris closes the old one.
    expect(groups[0].items.map((a) => a.activity_id)).toEqual(['a', 'b']);
    expect(groups[1].items.map((a) => a.activity_id)).toEqual(['c', 'd', 'e']);
    expect(groups[0].runKm).toBeCloseTo(8);
    expect(groups[1].runKm).toBeCloseTo(17.7);
  });

  it('formats the week span in one month or across two', () => {
    const [w43] = groupByWeek([run('x', '2026-10-21T10:00:00Z')], new Date('2026-10-21T12:00:00Z'));
    expect(formatWeekSpan(w43.monday, w43.sunday, 'fr')).toBe('19\u201325 oct.');
    expect(formatWeekStart(w43.monday, 'fr')).toBe('19 oct.');
    const [w44] = groupByWeek([run('y', '2026-10-28T10:00:00Z')], new Date('2026-10-28T12:00:00Z'));
    expect(formatWeekSpan(w44.monday, w44.sunday, 'fr')).toBe('26 oct.\u20131 nov.');
  });
});

describe('inWindow', () => {
  it('keeps the last 30 days, newest first, and drops undated rows', () => {
    const now = new Date('2026-10-30T12:00:00Z');
    const kept = inWindow(
      [
        run('old', '2026-09-29T10:00:00Z'),
        run('mid', '2026-10-10T10:00:00Z'),
        { activity_id: 'nodate', activity_type: 'Run' },
        run('new', '2026-10-29T10:00:00Z'),
      ],
      now,
    );
    expect(kept.map((a) => a.activity_id)).toEqual(['new', 'mid']);
  });
});

describe('rowFigures', () => {
  it('shows distance with a decimal comma, time and pace for a run', () => {
    expect(plain(rowFigures(run('r', '2026-10-01T10:00:00Z', 10000, 3000), 'fr'))).toBe(
      '10,00 km \u00b7 50:00 \u00b7 5:00 /km',
    );
    expect(plain(rowFigures(run('r', '2026-10-01T10:00:00Z', 6420, 2112), 'fr'))).toBe(
      '6,42 km \u00b7 35:12 \u00b7 5:29 /km',
    );
  });

  it('shows only the moving time for a strength session', () => {
    expect(rowFigures(gym('g', '2026-10-01T10:00:00Z', 2879), 'fr')).toBe('47:59');
  });

  it('never shows a placeholder when a value is missing', () => {
    const noDistance = rowFigures(run('r', '2026-10-01T10:00:00Z', 0, 1800), 'fr');
    expect(noDistance).toBe('30:00');
    expect(rowFigures({ activity_type: 'Run' }, 'fr')).toBeNull();
  });
});

describe('filters and summary', () => {
  it('reads the filter from the URL value, defaulting to all', () => {
    expect(parseTypeFilter('run')).toBe('run');
    expect(parseTypeFilter('strength')).toBe('strength');
    expect(parseTypeFilter('swim')).toBe('all');
    expect(parseTypeFilter(null)).toBe('all');
  });

  it('matches runs and strength sessions', () => {
    const r = run('r', '2026-10-01T10:00:00Z');
    const g = gym('g', '2026-10-01T10:00:00Z');
    expect(matchesFilter(r, 'run')).toBe(true);
    expect(matchesFilter(g, 'run')).toBe(false);
    expect(matchesFilter(g, 'strength')).toBe(true);
    expect(matchesFilter({ activity_type: 'Ride' }, 'all')).toBe(true);
    expect(summarize([r, g, { activity_type: 'Ride' }])).toEqual({ total: 3, runs: 1, strength: 1 });
  });

  it('flags only failed and in-flight processing', () => {
    expect(rowStatus('completed')).toBeNull();
    expect(rowStatus(undefined)).toBeNull();
    expect(rowStatus('failed')).toBe('failed');
    expect(rowStatus('waiting_enduraw')).toBe('processing');
    expect(rowStatus('processing')).toBe('processing');
  });
});
