import { describe, it, expect } from 'vitest';
import source from '../../public/sw.js?raw';

// public/sw.js is a classic service-worker script, not a module: load its URL
// guard in isolation with a fake `self.location`.
const fn = source.match(/function safeInternalPath\(raw\) \{[\s\S]*?\n\}/);
if (!fn) throw new Error('safeInternalPath not found in public/sw.js');
const safeInternalPath = new Function(
  'self',
  `${fn[0]}; return safeInternalPath;`
)({ location: { origin: 'https://app.example' } }) as (raw: unknown) => string;

describe('sw.js safeInternalPath', () => {
  it('keeps internal paths', () => {
    expect(safeInternalPath('/activities/123')).toBe('/activities/123');
    expect(safeInternalPath('/activities/123?x=1#top')).toBe('/activities/123?x=1#top');
  });

  it('rejects protocol-relative and backslash tricks', () => {
    expect(safeInternalPath('//evil.example/x')).toBe('/');
    expect(safeInternalPath('/\\evil.example/x')).toBe('/');
  });

  it('rejects absolute and non-string URLs', () => {
    expect(safeInternalPath('https://evil.example')).toBe('/');
    expect(safeInternalPath('javascript:alert(1)')).toBe('/');
    expect(safeInternalPath(undefined)).toBe('/');
  });
});
