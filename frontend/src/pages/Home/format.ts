/**
 * Pure formatters for the Home dashboard. Kept out of the component file so they
 * can be unit-tested and reused by the block sub-components. Everything is
 * null-safe: the contract allows every value to be missing.
 */

/** `92310` → `"25:38:30"` is wrong for sport; we only need h:mm / mm:ss here. */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Sleep is shown as `h:mm` (e.g. 27000 s → "7:30"). */
export function formatSleep(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h}:${String(m).padStart(2, '0')}`;
}

/** Pace s/km → `"4:33"` (min:sec per km). */
export function formatPace(secPerKm: number | null | undefined): string | null {
  if (secPerKm == null || !Number.isFinite(secPerKm) || secPerKm <= 0) return null;
  const total = Math.round(secPerKm);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** `[low, high]` seconds → `"1:35:14 – 1:40:01"`, null if either bound missing. */
export function formatRange(range: [number, number] | null | undefined): string | null {
  if (!range || range.length !== 2) return null;
  const lo = formatDuration(range[0]);
  const hi = formatDuration(range[1]);
  if (lo == null || hi == null) return null;
  return `${lo} \u2013 ${hi}`;
}

/**
 * ISO date `YYYY-MM-DD` → `"JJ/MM"`. Returns null for a missing/garbled date so
 * the caller can drop the "au ..." suffix entirely rather than show "au NaN".
 */
export function formatDayMonth(isoDate: string | null | undefined): string | null {
  if (!isoDate) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!m) return null;
  return `${m[3]}/${m[2]}`;
}

/** ISO timestamp → local `HH:MM`, null if unparseable. */
export function formatClock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${h}:${min}`;
}

/** A number for display, trimmed to one decimal, or null. */
export function num(value: number | null | undefined, decimals = 0): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  return decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
}
