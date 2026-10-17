import { describe, it, expect } from 'vitest';
import { formatDistanceKm, formatMovingTime, formatActivityPace } from '../formatActivity';

describe('formatDistanceKm', () => {
  it('formats metres as km with two decimals', () => {
    expect(formatDistanceKm(10020)).toBe('10.02 km');
  });

  it('returns null for zero or missing distance', () => {
    expect(formatDistanceKm(0)).toBeNull();
    expect(formatDistanceKm(undefined)).toBeNull();
  });
});

describe('formatMovingTime', () => {
  it('formats under an hour as m:ss', () => {
    expect(formatMovingTime(3130)).toBe('52:10');
  });

  it('formats over an hour as h:mm:ss', () => {
    expect(formatMovingTime(3930)).toBe('1:05:30');
  });

  it('returns null for zero or missing time', () => {
    expect(formatMovingTime(0)).toBeNull();
    expect(formatMovingTime(null)).toBeNull();
  });
});

describe('formatActivityPace', () => {
  it('computes the average pace of a run from distance and moving time', () => {
    // 10 km in 52:00 -> 5:12/km
    expect(formatActivityPace(10000, 3120, 'Run')).toBe('5:12/km');
  });

  it('returns null for an activity that is not on foot', () => {
    expect(formatActivityPace(40000, 4800, 'Ride')).toBeNull();
  });

  it('returns null when distance is zero (gym session)', () => {
    expect(formatActivityPace(0, 3600, 'Run')).toBeNull();
  });
});
