/// <reference types="node" />
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Read from disk: a `?raw` CSS import is emptied by Vitest's CSS handling. Vitest runs from frontend/.
const tokensCss = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8');

/**
 * WCAG 2.x contrast guard for the token pairs used as TEXT.
 * Parses styles/tokens.css so a token edit that drops a pair below AA (4.5:1) fails here.
 */

const AA = 4.5;

function themeBlock(selector: ':root' | '.dark'): Record<string, string> {
  const escaped = selector.replace('.', '\\.');
  const match = new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(tokensCss);
  if (!match) throw new Error(`no ${selector} block in tokens.css`);
  const vars: Record<string, string> = {};
  for (const m of match[1].matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    vars[m[1]] = m[2].toLowerCase();
  }
  return vars;
}

type RGB = [number, number, number];

function hexToRgb(hex: string): RGB {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function luminance([r, g, b]: RGB): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `bg-x/10` over a surface: alpha-blend `tint` at `alpha` onto `base`. */
function blend(tint: RGB, base: RGB, alpha: number): RGB {
  return tint.map((c, i) => Math.round(c * alpha + base[i] * (1 - alpha))) as RGB;
}

function token(vars: Record<string, string>, name: string): RGB {
  const hex = vars[name];
  if (!hex) throw new Error(`token --${name} missing`);
  return hexToRgb(hex);
}

const light = themeBlock(':root');
const dark = themeBlock('.dark');

describe('token contrast (WCAG AA)', () => {
  it('parses both theme blocks with the new tokens', () => {
    for (const vars of [light, dark]) {
      expect(vars['primary-strong']).toBeDefined();
      expect(vars['success-text']).toBeDefined();
      expect(vars['warning-text']).toBeDefined();
    }
    expect(light['primary-strong']).toBe('#d23c00');
    expect(light['success-text']).toBe('#047857');
    expect(light['warning-text']).toBe('#b45309');
  });

  it('white text on the filled button (primary-strong, rest and hover) clears AA in both themes', () => {
    for (const vars of [light, dark]) {
      const fg = token(vars, 'primary-foreground');
      expect(ratio(fg, token(vars, 'primary-strong'))).toBeGreaterThanOrEqual(AA);
      expect(ratio(fg, token(vars, 'primary-strong-hover'))).toBeGreaterThanOrEqual(AA);
    }
  });

  it('orange text (primary-text) clears AA on surface and background in both themes', () => {
    expect(light['primary-text']).toBe('#b93c0b');
    expect(dark['primary-text']).toBe('#fd6224');
    for (const vars of [light, dark]) {
      for (const bg of ['surface', 'background']) {
        expect(ratio(token(vars, 'primary-text'), token(vars, bg)), `primary-text on ${bg}`).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it('status text clears AA on surface and background in both themes', () => {
    for (const vars of [light, dark]) {
      for (const text of ['success-text', 'warning-text', 'danger']) {
        for (const bg of ['surface', 'background']) {
          expect(ratio(token(vars, text), token(vars, bg)), `${text} on ${bg}`).toBeGreaterThanOrEqual(AA);
        }
      }
    }
  });

  it('badge text clears AA on its own 10% tint (Badge success / warning)', () => {
    for (const vars of [light, dark]) {
      const surface = token(vars, 'surface');
      for (const [text, fill] of [['success-text', 'success'], ['warning-text', 'warning']] as const) {
        const tinted = blend(token(vars, fill), surface, 0.1);
        expect(ratio(token(vars, text), tinted), `${text} on ${fill}/10`).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it('primary-text and info text clear AA on the info / primary tints over surface (both themes)', () => {
    // Coach text links sit on bg-info/10 (Home CoachWords, Plan CoachBox), the info pill
    // on bg-info/10, active nav and the primary pill on bg-primary/10, the race card
    // countdown on bg-primary/5.
    const tints: ReadonlyArray<[string, number]> = [
      ['info', 0.1],
      ['primary', 0.1],
      ['primary', 0.05],
    ];
    for (const [themeName, vars] of [['light', light], ['dark', dark]] as const) {
      const surface = token(vars, 'surface');
      for (const text of ['primary-text', 'info']) {
        for (const [fill, alpha] of tints) {
          const tinted = blend(token(vars, fill), surface, alpha);
          expect(
            ratio(token(vars, text), tinted),
            `${themeName}: ${text} on ${fill}/${Math.round(alpha * 100)}`
          ).toBeGreaterThanOrEqual(AA);
        }
      }
    }
  });

  it('dark theme status text matches the base status colours', () => {
    expect(dark['success-text']).toBe(dark['success']);
    expect(dark['warning-text']).toBe(dark['warning']);
  });
});
