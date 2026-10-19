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
  /** Only on `form`: the TSB zone of the brief value, null when missing. */
  zone: FormZone | null;
}

export function briefSignal(brief: HomeBrief | null | undefined, key: ReadinessKey): BriefSignal | null {
  return brief?.signals?.find((s) => s.key === BRIEF_KEY[key]) ?? null;
}

export function readinessItems(
  brief: HomeBrief | null | undefined,
): ReadinessItem[] {
  return READINESS_KEYS.map((key) => {
    const signal = briefSignal(brief, key);
    const status = signalStatus(signal);
    const zone: FormZone | null = key === 'form' ? formZone(signal?.value) : null;
    return { key, status, signal, zone };
  });
}
