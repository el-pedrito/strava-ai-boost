import { describe, it, expect } from 'vitest';
import { formatDateTime, computeProcessingTime } from '../formatDate';

describe('formatDateTime', () => {
  it('formats in Europe/Paris local time, French short form', () => {
    // 15:50 UTC is 17:50 in Paris (CEST, UTC+2).
    expect(formatDateTime('2026-10-16T15:50:00Z', 'fr')).toBe('ven. 16 oct., 17:50');
  });

  it('applies winter time (UTC+1) after the DST change', () => {
    expect(formatDateTime('2026-12-04T07:05:30.123Z', 'fr')).toBe('ven. 4 déc., 08:05');
  });

  it('uses an English short form when the language is en', () => {
    expect(formatDateTime('2026-10-16T15:50:00Z', 'en')).toBe('Fri 16 Oct, 17:50');
  });

  it('follows the current i18n language by default', () => {
    // The test setup switches i18n to English.
    expect(formatDateTime('2026-10-16T15:50:00Z')).toBe('Fri 16 Oct, 17:50');
  });

  it('parses microsecond ISO strings with an offset', () => {
    expect(formatDateTime('2026-10-16T16:46:19.860518+00:00', 'fr')).toBe('ven. 16 oct., 18:46');
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
