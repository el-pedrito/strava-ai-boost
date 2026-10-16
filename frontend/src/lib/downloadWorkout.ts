/**
 * Download an Apple Watch custom workout (`.workout`) delivered as base64.
 *
 * iOS Safari only hands a file to the Workout app when the download is started
 * from a user gesture, so `downloadWorkout` is fully synchronous: call it
 * directly inside a click handler, never after an `await`.
 *
 * Pattern adapted from javierferrersb/dotworkout (MIT),
 * packages/pwa/src/application/workoutFile.ts.
 */

/** Delay before the anchor is removed and the object URL revoked. */
export const REVOKE_DELAY_MS = 30_000;

/** Maximum length of the sanitised filename, extension included. */
export const MAX_FILENAME_LENGTH = 60;

const WORKOUT_EXTENSION = '.workout';
const BASE64_RE = /^[A-Za-z0-9+/]*={0,2}$/;

/** Raised when the payload is not valid, non-empty base64. */
export class InvalidBase64Error extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'InvalidBase64Error';
  }
}

/** Decode standard base64 (whitespace tolerated) into raw bytes. */
export function base64ToBytes(b64: string): Uint8Array {
  if (typeof b64 !== 'string') {
    throw new InvalidBase64Error('base64 payload must be a string');
  }
  const clean = b64.replace(/\s+/g, '');
  if (clean.length === 0) {
    throw new InvalidBase64Error('base64 payload is empty');
  }
  if (clean.length % 4 !== 0 || !BASE64_RE.test(clean)) {
    throw new InvalidBase64Error('base64 payload is malformed');
  }
  let binary: string;
  try {
    binary = atob(clean);
  } catch {
    throw new InvalidBase64Error('base64 payload could not be decoded');
  }
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Make a filename safe for every browser: ASCII only (accents folded),
 * no path or shell-hostile characters, at most 60 chars, always `.workout`.
 */
export function sanitizeWorkoutFilename(filename: string): string {
  let base = String(filename ?? '').trim();
  if (base.toLowerCase().endsWith(WORKOUT_EXTENSION)) {
    base = base.slice(0, -WORKOUT_EXTENSION.length);
  }
  base = base
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // fold accents (é -> e)
    .replace(/[^A-Za-z0-9._-]+/g, '_') // anything else, spaces included
    .replace(/_+/g, '_')
    .replace(/^[._-]+|[._-]+$/g, ''); // no leading dot (hidden file) or trailing junk
  const maxBase = MAX_FILENAME_LENGTH - WORKOUT_EXTENSION.length;
  base = base.slice(0, maxBase).replace(/[._-]+$/g, '');
  return `${base || 'workout'}${WORKOUT_EXTENSION}`;
}

/**
 * Trigger the download of a `.workout` file. Synchronous by design (see module doc).
 * Throws `InvalidBase64Error` before touching the DOM if the payload is invalid.
 */
export function downloadWorkout(b64: string, filename: string): void {
  const bytes = base64ToBytes(b64);
  // Copy into a fresh ArrayBuffer-backed view so the Blob part type is exact.
  const blob = new Blob([new Uint8Array(bytes)], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = sanitizeWorkoutFilename(filename);
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();

  // iOS reads the blob asynchronously after the click: revoking immediately
  // would hand the Workout app an empty file.
  setTimeout(() => {
    anchor.remove();
    URL.revokeObjectURL(url);
  }, REVOKE_DELAY_MS);
}
