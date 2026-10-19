/**
 * "Prêt pour aujourd'hui ?": each morning signal mapped to a readiness status,
 * shown as a dot AND a word (never colour alone). Pure, unit-tested.
 *
 * The thresholds are deliberately coarse reading aids, not a medical verdict:
 * - VFC: drop vs the 60-day usual value, relative (SDNN moves ~5 % day to day).
 * - FC repos: rise vs the 60-day usual value, in bpm.
 * - Sommeil: absolute duration first (under 6 h is short whatever the usual),
 *   then the drop vs the last 7 nights.
 * - Fraîcheur: the intervals.icu TSB zone. While a load gap still biases CTL
 *   the zone is computed on wrong numbers, so the status is "incertain".
 */
import type { HealthMetric } from '@/types/home';
import { formZone, usualBaseline, usualDelta, type FormZone, type UsualKey } from '../Home/insights';

export type ReadinessKey = UsualKey;
export type ReadinessStatus = 'good' | 'watch' | 'bad' | 'uncertain' | 'missing';

export const READINESS_KEYS: ReadonlyArray<ReadinessKey> = ['hrv', 'resting_hr', 'sleep_s', 'form'];

/** HRV this far below usual (fraction) is worth watching / unfavourable. */
export const HRV_WATCH_DROP = 0.07;
export const HRV_BAD_DROP = 0.15;
/** Resting HR this many bpm above usual is worth watching / unfavourable. */
export const RHR_WATCH_RISE = 2;
export const RHR_BAD_RISE = 5;
/** Sleep (seconds): below 6 h unfavourable, below 7 h or 45 min under usual watch. */
export const SLEEP_BAD_S = 6 * 3600;
export const SLEEP_WATCH_S = 7 * 3600;
export const SLEEP_WATCH_DROP_S = 45 * 60;

export interface ReadinessItem {
  key: ReadinessKey;
  status: ReadinessStatus;
  /** Only on `form`: the TSB zone, null when the value is missing. */
  zone: FormZone | null;
}

export function readinessStatus(
  key: ReadinessKey,
  metric: HealthMetric | null | undefined,
  { formIncomplete = false }: { formIncomplete?: boolean } = {}
): ReadinessStatus {
  const value = metric?.value;
  if (metric == null || value == null || !Number.isFinite(value)) return 'missing';

  if (key === 'form') {
    if (formIncomplete) return 'uncertain';
    const zone = formZone(value);
    if (zone === 'overload') return 'bad';
    if (zone === 'productive') return 'watch';
    return 'good';
  }

  const baseline = usualBaseline(key, metric);
  const delta = usualDelta(key, metric);

  if (key === 'sleep_s') {
    if (value < SLEEP_BAD_S) return 'bad';
    if (value < SLEEP_WATCH_S) return 'watch';
    if (delta != null && delta < -SLEEP_WATCH_DROP_S) return 'watch';
    return 'good';
  }

  // HRV and resting HR are only judged against the athlete's own usual value.
  if (baseline == null || delta == null || !Number.isFinite(delta)) return 'uncertain';

  if (key === 'hrv') {
    if (baseline <= 0) return 'uncertain';
    const drop = -delta / baseline;
    if (drop > HRV_BAD_DROP) return 'bad';
    if (drop > HRV_WATCH_DROP) return 'watch';
    return 'good';
  }

  // resting_hr: higher than usual is the bad direction.
  if (delta > RHR_BAD_RISE) return 'bad';
  if (delta > RHR_WATCH_RISE) return 'watch';
  return 'good';
}

export function readinessItems(
  health: Partial<Record<ReadinessKey, HealthMetric | null>>,
  opts: { formIncomplete?: boolean } = {}
): ReadinessItem[] {
  return READINESS_KEYS.map((key) => ({
    key,
    status: readinessStatus(key, health[key], opts),
    zone: key === 'form' ? formZone(health.form?.value) : null,
  }));
}
