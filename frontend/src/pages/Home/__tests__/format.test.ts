import { describe, it, expect } from 'vitest';
import {
  MINUS,
  NNBSP,
  fmtNumber,
  fmtSigned,
  formatClock,
  formatDiff,
  formatGap,
  formatMetricText,
  formatShortDate,
  formatSleep,
  formatSleepDelta,
  formatWeekdayDate,
  isoWeekNumber,
  sentenceCase,
} from '../format';

/** Swap the narrow no-break space for a plain one so expectations stay readable. */
const sp = (s: string | null) => (s == null ? s : s.split(NNBSP).join(' '));

describe('home formatters', () => {
  it('formats numbers the French way with a real minus sign', () => {
    expect(fmtNumber(-14.3, 1, 'fr')).toBe(`${MINUS}14,3`);
    expect(fmtNumber(56.61, 1, 'fr')).toBe('56,6');
    expect(fmtNumber(-0.04, 1, 'fr')).toBe('0,0');
    expect(fmtNumber(null, 1, 'fr')).toBeNull();
    expect(fmtNumber(Number.NaN, 1, 'fr')).toBeNull();
    expect(fmtNumber(13.2, 1, 'en')).toBe('13.2');
  });

  it('signs differences, and leaves a zero unsigned', () => {
    expect(fmtSigned(4.8, 1, 'fr')).toBe('+4,8');
    expect(fmtSigned(-3.2, 1, 'fr')).toBe(`${MINUS}3,2`);
    expect(fmtSigned(0.01, 1, 'fr')).toBe('0,0');
  });

  it('gives each metric its own unit and precision (never raw seconds)', () => {
    expect(sp(formatMetricText('sleep', 28890, 'fr'))).toBe('8 h 02');
    expect(sp(formatMetricText('sleep_s', 28412.2, 'fr'))).toBe('7 h 54');
    expect(sp(formatMetricText('hrv', 90.41, 'fr'))).toBe('90 ms');
    expect(sp(formatMetricText('resting_hr', 50, 'fr'))).toBe('50 bpm');
    expect(formatMetricText('form', -14.3, 'fr')).toBe(`${MINUS}14,3`);
    expect(formatMetricText('ctl', 10.25, 'fr')).toBe('10,3');
    expect(formatMetricText('vo2max', 56.61, 'fr')).toBe('56,6');
    expect(sp(formatMetricText('weight', 92, 'fr'))).toBe('92,0 kg');
    expect(formatMetricText('unknown', 1, 'fr')).toBeNull();
    expect(formatMetricText('hrv', null, 'fr')).toBeNull();
  });

  it('formats sleep as a duration, not a clock time', () => {
    expect(sp(formatSleep(27000))).toBe('7 h 30');
    expect(sp(formatSleep(1500))).toBe('25 min');
    expect(formatSleep(-1)).toBeNull();
    expect(sp(formatSleepDelta(477.8))).toBe('+8 min');
    expect(sp(formatSleepDelta(-3900))).toBe(`${MINUS}1 h 05`);
    expect(sp(formatSleepDelta(10))).toBe('0 min');
  });

  it('rounds the sleep value and its delta the same way (nearest minute)', () => {
    // 8 h 01 min 30 s: both round up to the next minute.
    expect(sp(formatSleep(28890))).toBe('8 h 02');
    expect(sp(formatSleepDelta(28890))).toBe('+8 h 02');
    expect(sp(formatSleep(89))).toBe('1 min');
    expect(sp(formatSleepDelta(89))).toBe('+1 min');
    expect(sp(formatSleep(29))).toBe('0 min');
    expect(sp(formatSleepDelta(-29))).toBe('0 min');
  });

  it('tones a difference by the good direction of each metric', () => {
    const hrv = formatDiff('hrv', 4.8, 'fr');
    expect(sp(hrv!.text)).toBe('+4,8 ms');
    expect(hrv!.direction).toBe('up');
    expect(hrv!.tone).toBe('good');

    // Resting HR going down is good news.
    const rhr = formatDiff('resting_hr', -3.2, 'fr');
    expect(sp(rhr!.text)).toBe(`${MINUS}3,2 bpm`);
    expect(rhr!.direction).toBe('down');
    expect(rhr!.tone).toBe('good');

    const sleep = formatDiff('sleep_s', -1100, 'fr');
    expect(sp(sleep!.text)).toBe(`${MINUS}18 min`);
    expect(sleep!.tone).toBe('bad');

    const flat = formatDiff('hrv', 0.02, 'fr');
    expect(flat!.direction).toBe('flat');
    expect(flat!.tone).toBe('neutral');

    expect(formatDiff('form', 2, 'fr')!.tone).toBe('neutral');
    expect(formatDiff('hrv', null, 'fr')).toBeNull();
  });

  it('formats a race gap with sign', () => {
    expect(formatGap(98)).toBe('+1:38');
    expect(formatGap(-20)).toBe(`${MINUS}0:20`);
    expect(formatGap(0)).toBe('0:00');
    expect(formatGap(null)).toBeNull();
  });

  it('formats calendar dates without timezone drift', () => {
    expect(formatShortDate('2026-10-16', 'fr')).toBe('16 oct.');
    expect(formatShortDate('2026-09-01', 'fr')).toBe('1 sept.');
    expect(formatWeekdayDate('2026-11-15', 'fr')).toBe('dim. 15 nov.');
    expect(formatShortDate('garbage', 'fr')).toBeNull();
    expect(formatShortDate(null, 'fr')).toBeNull();
  });

  it('shows timestamps on the Paris clock', () => {
    expect(formatClock('2026-10-17T05:30:00Z')).toBe('07:30');
    expect(formatClock('2026-01-17T05:30:00Z')).toBe('06:30');
    expect(formatClock('nope')).toBeNull();
  });

  it('reads ISO week numbers and sentence-cases shouted names', () => {
    expect(isoWeekNumber('2026-W42')).toBe(42);
    expect(isoWeekNumber('42')).toBeNull();
    expect(sentenceCase('SEMI-MARATHON')).toBe('Semi-marathon');
    expect(sentenceCase('Marathon de Paris')).toBe('Marathon de Paris');
    expect(sentenceCase('  ')).toBeNull();
  });
});
