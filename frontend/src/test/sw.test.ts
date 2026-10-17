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

// Run the whole worker script against a fake `self` and capture its listeners.
type Listener = (event: unknown) => void;
function loadWorker(clients: unknown[] = []) {
  const listeners: Record<string, Listener> = {};
  const shown: Array<{ title: string; options: { body: string; data: { url: string } } }> = [];
  const opened: string[] = [];
  const self = {
    location: { origin: 'https://app.example' },
    addEventListener: (name: string, fn: Listener) => {
      listeners[name] = fn;
    },
    skipWaiting: () => undefined,
    registration: {
      showNotification: (title: string, options: { body: string; data: { url: string } }) => {
        shown.push({ title, options });
        return Promise.resolve();
      },
    },
    clients: {
      claim: () => Promise.resolve(),
      matchAll: () => Promise.resolve(clients),
      openWindow: (url: string) => {
        opened.push(url);
        return Promise.resolve(null);
      },
    },
  };
  new Function('self', source)(self);
  return { listeners, shown, opened };
}

async function firePush(worker: ReturnType<typeof loadWorker>, json: () => unknown) {
  let pending: Promise<unknown> = Promise.resolve();
  worker.listeners.push({ data: { json }, waitUntil: (p: Promise<unknown>) => (pending = p) });
  await pending;
}

describe('sw.js push handler', () => {
  it('shows the payload of a well-formed push', async () => {
    const w = loadWorker();
    await firePush(w, () => ({ title: 'Activité enrichie', body: 'Footing', url: '/plan', tag: 't' }));
    expect(w.shown).toHaveLength(1);
    expect(w.shown[0].title).toBe('Activité enrichie');
    expect(w.shown[0].options.data.url).toBe('/plan');
  });

  async function expectNeutralNotification(json: () => unknown) {
    const w = loadWorker();
    await firePush(w, json);
    expect(w.shown).toHaveLength(1);
    expect(w.shown[0].options.body).toBe('Ta description enrichie est en ligne.');
    expect(w.shown[0].options.data.url).toBe('/');
  }

  it('still shows a notification when the payload is null', async () => {
    await expectNeutralNotification(() => null);
  });

  it('still shows a notification when the payload is an array', async () => {
    await expectNeutralNotification(() => ['x']);
  });

  it('still shows a notification when the payload is a string', async () => {
    await expectNeutralNotification(() => 'hello');
  });

  it('still shows a notification when the payload is not JSON', async () => {
    await expectNeutralNotification(() => {
      throw new SyntaxError('bad');
    });
  });
});

describe('sw.js notificationclick', () => {
  async function click(worker: ReturnType<typeof loadWorker>, url: string) {
    let pending: Promise<unknown> = Promise.resolve();
    worker.listeners.notificationclick({
      notification: { close: () => undefined, data: { url } },
      waitUntil: (p: Promise<unknown>) => (pending = p),
    });
    await pending;
  }

  it('opens a new window when no app window exists', async () => {
    const w = loadWorker([]);
    await click(w, '/plan');
    expect(w.opened).toEqual(['/plan']);
  });

  it('falls back to openWindow when navigate() rejects', async () => {
    const client = {
      focus: () => Promise.resolve(),
      navigate: () => Promise.reject(new TypeError('not controlled')),
    };
    const w = loadWorker([client]);
    await click(w, '/activities/42');
    expect(w.opened).toEqual(['/activities/42']);
  });

  it('reuses an app window when navigate() works', async () => {
    const navigated: string[] = [];
    const client = {
      focus: () => Promise.resolve(),
      navigate: (u: string) => {
        navigated.push(u);
        return Promise.resolve(null);
      },
    };
    const w = loadWorker([client]);
    await click(w, '/plan');
    expect(navigated).toEqual(['/plan']);
    expect(w.opened).toEqual([]);
  });
});
