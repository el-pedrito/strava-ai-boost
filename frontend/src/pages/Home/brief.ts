/**
 * The morning brief (`/home/summary` `brief`) read the same way everywhere.
 * The backend computes the light and each signal status (morning_brief.py),
 * so the client never re-derives a readiness verdict from its own thresholds.
 * Used by the Home hero and the Santé "Prêt pour aujourd'hui ?" card.
 */
import type { BriefLight, BriefSignal, SignalStatus } from '@/types/home';
import type { Tone } from './blocks/tones';

export const LIGHT_TONE: Record<BriefLight, Tone> = {
  green: 'success',
  orange: 'warning',
  red: 'danger',
  unknown: 'muted',
};

/** `stale`: a known value the brief skipped as too old ("ancien", never "Indisponible"). */
export type BriefSignalStatus = SignalStatus | 'stale';

export const STATUS_TONE: Record<BriefSignalStatus, Tone> = {
  ok: 'success',
  warn: 'warning',
  bad: 'danger',
  missing: 'muted',
  stale: 'muted',
};

export function toLight(light: string | null | undefined): BriefLight {
  if (light === 'amber') return 'orange';
  return light === 'green' || light === 'orange' || light === 'red' ? light : 'unknown';
}

export function toStatus(status: string | null | undefined): SignalStatus {
  return status === 'ok' || status === 'warn' || status === 'bad' ? status : 'missing';
}

/** The status of one brief signal; an absent signal is `missing`. */
export function signalStatus(signal: BriefSignal | null | undefined): BriefSignalStatus {
  if (!signal) return 'missing';
  // Only the brief's own "missing" on a known value means too old; an unknown
  // status word is not evidence of anything and stays "Indisponible".
  if (signal.status === 'missing' && signal.value != null) return 'stale';
  return toStatus(signal.status);
}

/** i18n key of the status word: Normal / À surveiller / Alerte / Indisponible / ancien. */
export function statusLabelKey(status: BriefSignalStatus): string {
  return status === 'stale' ? 'home.health.stale' : `home.brief.status.${status}`;
}
