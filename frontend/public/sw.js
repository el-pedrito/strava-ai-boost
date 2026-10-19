/* Strava AI Boost service worker — opt-in Web Push.
 *
 * Scope is intentionally minimal: this worker does NO caching and claims no
 * responsibility for offline/PWA behaviour. It only turns a server push into a
 * notification and routes a click back into the app.
 *
 * The server sends an encrypted payload shaped as:
 *   { title, body, url (starts with '/'), tag }
 * `push`              -> showNotification(title, { body, icon, tag, data:{ url } })
 * `notificationclick` -> focus an existing app window and navigate there,
 *                        otherwise open a new one. Internal URLs only.
 */

self.addEventListener('install', () => {
  // Activate this version immediately instead of waiting for old tabs to close.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

/**
 * Return a same-origin path for `raw`, or '/' if it points anywhere else.
 * A plain startsWith('/') check lets protocol-relative URLs such as
 * '//evil.example' (or '/\\evil.example') through, so resolve the URL against
 * our own origin and compare origins instead.
 */
function safeInternalPath(raw) {
  if (typeof raw !== 'string' || !raw.startsWith('/')) return '/';
  try {
    const resolved = new URL(raw, self.location.origin);
    if (resolved.origin !== self.location.origin) return '/';
    return resolved.pathname + resolved.search + resolved.hash;
  } catch {
    return '/';
  }
}

self.addEventListener('push', (event) => {
  // Every push MUST end in a visible notification: iOS revokes the subscription
  // of a web app that receives pushes without showing anything. So any payload
  // that is not a JSON object (bad JSON, null, an array, a string) falls back
  // to a neutral notification instead of throwing.
  let data = {};
  try {
    const parsed = event.data ? event.data.json() : null;
    data = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    data = {};
  }

  const title = typeof data.title === 'string' && data.title ? data.title : 'Strava AI Boost';
  const body =
    typeof data.body === 'string' && data.body ? data.body : 'Ta description enrichie est en ligne.';
  // Only ever navigate to internal, same-origin paths.
  const url = safeInternalPath(data.url);

  const options = {
    body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: typeof data.tag === 'string' && data.tag ? data.tag : 'strava-ai-boost',
    data: { url },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = event.notification.data && event.notification.data.url;
  // Guard again at click time: never open an external URL.
  const url = safeInternalPath(target);

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Reuse an open app window if there is one.
      const open = () => (self.clients.openWindow ? self.clients.openWindow(url) : undefined);
      for (const client of clientList) {
        if ('focus' in client) {
          // navigate() rejects on a window this worker does not control yet:
          // open the page instead of leaving the user on the wrong screen.
          const focused = Promise.resolve(client.focus()).catch(() => undefined);
          if ('navigate' in client) {
            return focused.then(() => client.navigate(url)).catch(open);
          }
          return focused;
        }
      }
      // Otherwise open a fresh window.
      return open();
    })
  );
});
