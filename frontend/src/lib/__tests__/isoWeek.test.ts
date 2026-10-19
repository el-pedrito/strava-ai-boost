import { describe, it, expect } from 'vitest';
import { athleteToday, formatWeekRange, isoWeekLabel, isoWeekMonday, isoWeekSunday } from '../isoWeek';

const day = (iso: string) => new Date(`${iso}T00:00:00Z`);

describe('isoWeek', () => {
  it('labels days around a year boundary with the ISO year', () => {
    expect(isoWeekLabel(day('2026-12-31'))).toBe('2026-W53');
    expect(isoWeekLabel(day('2027-01-03'))).toBe('2026-W53');
    expect(isoWeekLabel(day('2027-01-04'))).toBe('2027-W01');
    expect(isoWeekLabel(day('2025-12-29'))).toBe('2026-W01');
  });

  it('round-trips a label to its Monday and Sunday, and rejects malformed or missing weeks', () => {
    expect(isoWeekMonday('2026-W43')?.toISOString().slice(0, 10)).toBe('2026-10-19');
    expect(isoWeekSunday('2026-W43')?.toISOString().slice(0, 10)).toBe('2026-10-25');
    expect(isoWeekMonday('2027-W53')).toBeNull();
    expect(isoWeekMonday('2026-43')).toBeNull();
    expect(isoWeekMonday('2026-W00')).toBeNull();
  });

  it('formats a week spanning two months with both months', () => {
    expect(formatWeekRange('2026-W44', 'fr')).toBe('lun. 26 oct. – dim. 1 nov.');
    expect(formatWeekRange('2026-W43', 'en')).toBe('Mon 19 – Sun 25 Oct');
    expect(formatWeekRange('bad', 'fr')).toBeNull();
  });

  it('takes today in Paris, not in UTC', () => {
    // 23:30 UTC on Sunday 25 Oct 2026 is already Monday 26 Oct in Paris (UTC+1).
    expect(athleteToday(new Date('2026-10-25T23:30:00Z')).toISOString().slice(0, 10)).toBe('2026-10-26');
  });
});
