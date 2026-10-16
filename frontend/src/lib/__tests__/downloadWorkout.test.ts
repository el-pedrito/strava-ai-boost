import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  InvalidBase64Error,
  REVOKE_DELAY_MS,
  base64ToBytes,
  downloadWorkout,
  sanitizeWorkoutFilename,
} from '../downloadWorkout';

// Arbitrary binary payload, including bytes > 0x7f and NUL, like a real protobuf file.
const SAMPLE_BYTES = new Uint8Array([0x0a, 0x00, 0xff, 0x80, 0x12, 0x7f, 0xc3, 0xa9, 0x01]);
const SAMPLE_B64 = btoa(String.fromCharCode(...SAMPLE_BYTES));

describe('base64ToBytes', () => {
  it('decodes to exactly the original bytes', () => {
    expect(Array.from(base64ToBytes(SAMPLE_B64))).toEqual(Array.from(SAMPLE_BYTES));
  });

  it('throws InvalidBase64Error on malformed, empty or non-base64 input', () => {
    expect(() => base64ToBytes('not base64!')).toThrow(InvalidBase64Error);
    expect(() => base64ToBytes('abc')).toThrow(InvalidBase64Error);
    expect(() => base64ToBytes('')).toThrow(InvalidBase64Error);
    expect(() => base64ToBytes('ab=c')).toThrow(InvalidBase64Error);
  });
});

describe('sanitizeWorkoutFilename', () => {
  it('folds accents, strips unsafe characters and caps at 60 chars with .workout', () => {
    const name = sanitizeWorkoutFilename(
      'Séance fractionné 9x1\' à l\'allure 10 km / récup trottinée très longue.workout',
    );
    expect(name.endsWith('.workout')).toBe(true);
    expect(name.length).toBeLessThanOrEqual(60);
    expect(name).toMatch(/^[A-Za-z0-9._-]+$/);
    expect(name.startsWith('Seance_fractionne_9x1_a_l_allure')).toBe(true);
  });

  it('falls back to a default name and adds the extension when missing', () => {
    expect(sanitizeWorkoutFilename('***')).toBe('workout.workout');
    expect(sanitizeWorkoutFilename('VMA court')).toBe('VMA_court.workout');
  });
});

describe('downloadWorkout', () => {
  let createdBlobs: Blob[];
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.spyOn>;
  let clickedAnchors: HTMLAnchorElement[];

  beforeEach(() => {
    vi.useFakeTimers();
    createdBlobs = [];
    clickedAnchors = [];
    createObjectURL = vi.fn((blob: Blob) => {
      createdBlobs.push(blob);
      return 'blob:mock-url';
    });
    revokeObjectURL = vi.fn();
    // jsdom does not implement object URLs.
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clickedAnchors.push(this);
    });
  });

  afterEach(() => {
    clickSpy.mockRestore();
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('puts exactly the decoded bytes in an application/octet-stream Blob', async () => {
    downloadWorkout(SAMPLE_B64, 'test.workout');
    expect(createdBlobs).toHaveLength(1);
    const blob = createdBlobs[0];
    expect(blob.type).toBe('application/octet-stream');
    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(Array.from(bytes)).toEqual(Array.from(SAMPLE_BYTES));
  });

  it('clicks exactly one attached anchor with filename, href and rel=noopener', () => {
    downloadWorkout(SAMPLE_B64, 'Fractionné court.workout');
    expect(clickSpy).toHaveBeenCalledTimes(1);
    const anchor = clickedAnchors[0];
    expect(anchor.isConnected).toBe(true);
    expect(anchor.download).toBe('Fractionne_court.workout');
    expect(anchor.getAttribute('href')).toBe('blob:mock-url');
    expect(anchor.rel).toBe('noopener');
  });

  it('revokes the URL and removes the anchor only after 30 s', () => {
    downloadWorkout(SAMPLE_B64, 'test.workout');
    const anchor = clickedAnchors[0];

    vi.advanceTimersByTime(REVOKE_DELAY_MS - 1);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    expect(anchor.isConnected).toBe(true);

    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
    expect(anchor.isConnected).toBe(false);
    expect(document.body.querySelector('a')).toBeNull();
  });

  it('throws on invalid base64 without creating a URL or clicking', () => {
    expect(() => downloadWorkout('%%%', 'x.workout')).toThrow(InvalidBase64Error);
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });
});
