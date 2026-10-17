/**
 * Activity figures for list rows (Monitoring page). Null-safe: a missing or zero value
 * returns null so the caller renders a dash instead of "0.00 km" or "NaN".
 */

const FOOT_TYPES = new Set(['Run', 'TrailRun', 'VirtualRun', 'Walk', 'Hike']);

/** Metres → "10.02 km". */
export function formatDistanceKm(meters?: number | null): string | null {
  if (meters == null || !Number.isFinite(meters) || meters <= 0) return null;
  return `${(meters / 1000).toFixed(2)} km`;
}

/** Seconds → "52:10" or "1:05:30" (h:mm:ss above an hour). */
export function formatMovingTime(seconds?: number | null): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

/**
 * Average pace "5:12/km" from distance and moving time, for on-foot activities only
 * (a pace per km means nothing for a ride or a gym session).
 */
export function formatActivityPace(
  meters?: number | null,
  movingSeconds?: number | null,
  activityType?: string,
): string | null {
  if (activityType && !FOOT_TYPES.has(activityType)) return null;
  if (!meters || !movingSeconds || meters <= 0 || movingSeconds <= 0) return null;
  const secPerKm = Math.round(movingSeconds / (meters / 1000));
  if (!Number.isFinite(secPerKm)) return null;
  const m = Math.floor(secPerKm / 60);
  const s = secPerKm % 60;
  return `${m}:${String(s).padStart(2, '0')}/km`;
}
