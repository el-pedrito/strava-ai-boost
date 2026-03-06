import { describe, it, expect } from 'vitest';
import { formatDateTime, computeProcessingTime } from '../formatDate';

describe('formatDateTime', () => {
  it('formats ISO string to readable date', () => {
    expect(formatDateTime('2026-03-06T14:30:00Z')).toBe('2026-03-06 14:30');
  });

  it('handles date with milliseconds', () => {
    expect(formatDateTime('2026-01-15T09:05:30.123Z')).toBe('2026-01-15 09:05');
  });

  it('returns N/A for invalid date', () => {
    expect(formatDateTime('not-a-date')).toBe('N/A');
  });

  it('returns N/A for empty string', () => {
    expect(formatDateTime('')).toBe('N/A');
  });
});

describe('computeProcessingTime', () => {
  it('computes difference in seconds', () => {
    const created = '2026-03-06T14:00:00Z';
    const updated = '2026-03-06T14:00:45Z';
    expect(computeProcessingTime(created, updated)).toBe('45s');
  });

  it('rounds to nearest second', () => {
    const created = '2026-03-06T14:00:00.000Z';
    const updated = '2026-03-06T14:00:02.600Z';
    expect(computeProcessingTime(created, updated)).toBe('3s');
  });

  it('returns N/A when createdAt is missing', () => {
    expect(computeProcessingTime(undefined, '2026-03-06T14:00:00Z')).toBe('N/A');
  });

  it('returns N/A when updatedAt is missing', () => {
    expect(computeProcessingTime('2026-03-06T14:00:00Z', undefined)).toBe('N/A');
  });

  it('returns N/A when both are missing', () => {
    expect(computeProcessingTime(undefined, undefined)).toBe('N/A');
  });
});
