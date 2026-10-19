/**
 * "Prêt pour aujourd'hui ?": each morning signal with the status the backend
 * morning brief gave it (`brief.signals[].status`), the same verdict the Home
 * hero shows. No client thresholds: a signal absent from the brief reads
 * "Indisponible", a known value the brief skipped as too old reads "ancien".
 * Pure, unit-tested.
 */
import type { BriefSignal, HomeBrief } from '@/types/home';
import { formZone, type FormZone, type UsualKey } from '../Home/insights';
import { signalStatus, type BriefSignalStatus } from '../Home/brief';

export type ReadinessKey = UsualKey;
export type ReadinessStatus = BriefSignalStatus;

export const READINESS_KEYS: ReadonlyArray<ReadinessKey> = ['hrv', 'resting_hr', 'sleep_s', 'form'];

/** The brief names sleep `sleep`, the health block `sleep_s`. */
const BRIEF_KEY: Record<ReadinessKey, string> = {
  hrv: 'hrv',
  resting_hr: 'resting_hr',
  sleep_s: 'sleep',
  form: 'form',
};

export interface ReadinessItem {
  key: ReadinessKey;
  status: ReadinessStatus;
  signal: BriefSignal | null;
  /**
   * Only on `form`: the TSB zone word to show, or null. Null while the load is
   * incomplete (the zone would be computed on biased CTL/ATL) and whenever the
   * zone would contradict the brief status dot.
   */
  zone: FormZone | null;
}

export function briefSignal(brief: HomeBrief | null | undefined, key: ReadinessKey): BriefSignal | null {
  return brief?.signals?.find((s) => s.key === BRIEF_KEY[key]) ?? null;
}

/**
 * Whether a TSB zone word can sit next to a brief status without saying the
 * opposite. The brief thresholds (−15 / −25) and the intervals.icu zones
 * (−10 / −30) differ, so "fatigue d'entraînement normale" next to "Alerte"
 * is possible on the numbers and must not be shown.
 */
export function zoneAgrees(zone: FormZone | null, status: ReadinessStatus): boolean {
  if (zone == null) return false;
  if (status === 'ok') return zone !== 'overload';
  if (status === 'warn') return zone === 'productive';
  if (status === 'bad') return zone === 'overload';
  return false;
}

export function readinessItems(
  brief: HomeBrief | null | undefined,
  { formIncomplete = false }: { formIncomplete?: boolean } = {}
): ReadinessItem[] {
  return READINESS_KEYS.map((key) => {
    const signal = briefSignal(brief, key);
    const status = signalStatus(signal);
    let zone: FormZone | null = null;
    if (key === 'form' && !formIncomplete) {
      const z = formZone(signal?.value);
      zone = zoneAgrees(z, status) ? z : null;
    }
    return { key, status, signal, zone };
  });
}
