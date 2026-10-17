import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell } from 'lucide-react';
import { Alert, Card, CardDescription, CardHeader, CardTitle, Label, Toggle } from '@/ui';
import { ApiError } from '../../api/client.ts';
import { isPushEnabled } from '../../config.ts';
import {
  getApplicationServerKey,
  subscribePush,
  unsubscribePush,
  urlBase64ToUint8Array,
} from '../../api/push.ts';

type PushState = 'unsupported' | 'idle' | 'enabled' | 'busy';

/** True on iOS/iPadOS, where Web Push requires the app be added to the Home Screen. */
function isIos(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  const iOSDevice = /iPad|iPhone|iPod/.test(ua);
  // iPadOS 13+ reports as Macintosh; detect touch + Mac as a heuristic.
  const iPadOS =
    ua.includes('Macintosh') && typeof document !== 'undefined' && 'ontouchend' in document;
  return iOSDevice || iPadOS;
}

/** True when the app runs from the Home Screen (iOS needs it for Web Push). */
function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return (
    nav.standalone === true ||
    (typeof window.matchMedia === 'function' &&
      window.matchMedia('(display-mode: standalone)').matches)
  );
}

function toSubscriptionBody(sub: PushSubscription) {
  const json = sub.toJSON();
  return {
    endpoint: json.endpoint ?? '',
    keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
  };
}

/** Remove a subscription locally AND on the server (best-effort for both), so
 * no orphan row is left that would fail on every send and count toward the
 * device cap. */
async function dropSubscription(sub: PushSubscription): Promise<void> {
  const endpoint = sub.endpoint;
  try {
    await sub.unsubscribe();
  } catch {
    // The next getSubscription() check will tell.
  }
  if (endpoint) {
    try {
      await unsubscribePush(endpoint);
    } catch {
      // Server cleanup is best-effort.
    }
  }
}

/** True when `sub` was created with this application server key (or we cannot tell). */
function sameKey(sub: PushSubscription, key: string): boolean {
  const current = sub.options?.applicationServerKey;
  if (!current) return true;
  const a = new Uint8Array(current);
  const b = urlBase64ToUint8Array(key);
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** Web Push is only usable when all three browser APIs are present. */
function pushSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/**
 * "Notifications" card for the Preferences screen. Opt-in Web Push, off by
 * default, and not rendered at all unless config.json sets `pushEnabled: true`.
 * Turning it on first asks for permission, inside the tap (iOS only prompts
 * during the user gesture), then uses the application server key prefetched
 * on mount, registers the service worker, subscribes and POSTs the
 * subscription. On mount, an existing subscription is re-sent to the server,
 * or dropped when it was made with an older server key.
 * If the server rejects it, the local subscription is removed again so the
 * toggle never shows "on" for a device the server does not know. Turning it
 * off unsubscribes locally and server-side (DELETE /push/subscribe).
 */
export function NotificationsCard() {
  if (!isPushEnabled()) return null;
  return <NotificationsCardInner />;
}

function NotificationsCardInner() {
  const { t } = useTranslation();
  const [state, setState] = useState<PushState>('idle');
  const [message, setMessage] = useState<{ variant: 'error' | 'warning'; text: string } | null>(
    null
  );

  // Fetched ahead of the click: iOS only shows the permission prompt while the
  // tap is still "fresh", so the click handler must not wait on the network.
  const serverKey = useRef<string | null>(null);
  // The mount reconciliation (re-POST or drop of an existing subscription).
  // Toggle actions wait for it, so a quick "off" can never DELETE before an
  // in-flight re-POST lands and recreates the row.
  const reconciling = useRef<Promise<void>>(Promise.resolve());

  // Reflect the current subscription on mount — no prompting, just reading.
  // An existing subscription is sent to the server again (idempotent): after a
  // table reset or an endpoint cleanup the toggle would otherwise read "on"
  // while nothing is delivered.
  useEffect(() => {
    if (!pushSupported()) {
      setState('unsupported');
      return;
    }
    let cancelled = false;
    const keyRequest = getApplicationServerKey()
      .then((res) => {
        serverKey.current = res.application_server_key;
        return res.application_server_key;
      })
      .catch(() => null); // Fetched again on click; a failure there shows "not deployed".
    reconciling.current = (async () => {
      try {
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = reg ? await reg.pushManager.getSubscription() : null;
        if (!sub) {
          if (!cancelled) setState('idle');
          return;
        }
        const key = await keyRequest;
        if (key && !sameKey(sub, key)) {
          // Bound to an older server key (VAPID rotation): it can never be
          // delivered again. Drop it and ask for a new opt-in.
          await dropSubscription(sub);
          if (!cancelled) {
            setState('idle');
            setMessage({ variant: 'warning', text: t('preferences.notifications.keyChanged') });
          }
          return;
        }
        if (!cancelled) setState('enabled');
        try {
          await subscribePush(toSubscriptionBody(sub));
        } catch {
          // Best-effort refresh; the toggle still lets the user re-subscribe.
        }
      } catch {
        if (!cancelled) setState('idle');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t]);

  const enable = useCallback(async () => {
    // 1. Ask for permission FIRST, before any await: iOS only shows the prompt
    //    inside the user's tap. The card is only rendered when config.json sets
    //    pushEnabled, so a deployment without push never reaches this prompt.
    const permissionRequest = Notification.requestPermission();
    setState('busy');
    setMessage(null);

    await reconciling.current;

    let permission: NotificationPermission;
    try {
      permission = await permissionRequest;
    } catch {
      permission = 'denied';
    }
    if (permission !== 'granted') {
      setState('idle');
      setMessage({ variant: 'warning', text: t('preferences.notifications.denied') });
      return;
    }

    // 2. The application server key (prefetched on mount when possible).
    let applicationServerKey = serverKey.current;
    if (!applicationServerKey) {
      try {
        applicationServerKey = (await getApplicationServerKey()).application_server_key;
        serverKey.current = applicationServerKey;
      } catch {
        setState('idle');
        setMessage({ variant: 'warning', text: t('preferences.notifications.notDeployed') });
        return;
      }
    }

    let sub: PushSubscription | null = null;
    try {
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;

      // A subscription bound to an older key (VAPID rotation) makes subscribe()
      // throw: drop it first.
      const previous = await reg.pushManager.getSubscription();
      if (previous) await dropSubscription(previous);

      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(applicationServerKey),
      });

      await subscribePush(toSubscriptionBody(sub));
      setState('enabled');
    } catch (err) {
      // The server does not know this device: drop the local subscription too,
      // otherwise the toggle would read "on" after a reload.
      if (sub) {
        try {
          await sub.unsubscribe();
        } catch {
          // Nothing more to do; the next getSubscription() check will tell.
        }
      }
      setState('idle');
      setMessage({
        variant: 'error',
        text:
          err instanceof ApiError && err.status === 409
            ? t('preferences.notifications.tooMany')
            : err instanceof ApiError && err.status === 404
              ? t('preferences.notifications.notDeployed')
              : t('preferences.notifications.error'),
      });
    }
  }, [t]);

  const disable = useCallback(async () => {
    setState('busy');
    setMessage(null);
    await reconciling.current;
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      const sub = reg ? await reg.pushManager.getSubscription() : null;
      const endpoint = sub?.endpoint ?? '';
      if (sub) await sub.unsubscribe();
      try {
        await unsubscribePush(endpoint);
      } catch {
        // Server-side cleanup is best-effort: the local subscription is already gone.
      }
      setState('idle');
    } catch {
      // Fall back to "off" so the UI never gets stuck in a busy state.
      setState('idle');
      setMessage({ variant: 'error', text: t('preferences.notifications.error') });
    }
  }, [t]);

  const onToggle = useCallback(
    (checked: boolean) => {
      if (state === 'busy') return;
      if (checked) void enable();
      else void disable();
    },
    [state, enable, disable]
  );

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-center gap-1.5">
          <Bell className="h-4 w-4 text-primary" aria-hidden="true" />
          <CardTitle>{t('preferences.notifications.title')}</CardTitle>
        </div>
        <CardDescription>{t('preferences.notifications.description')}</CardDescription>
      </CardHeader>

      {state === 'unsupported' ? (
        <div className="flex flex-col gap-2">
          <Alert variant="info">{t('preferences.notifications.unsupported')}</Alert>
          {isIos() && !isStandalone() && (
            <p className="text-xs text-muted-foreground">{t('preferences.notifications.iosNote')}</p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Label htmlFor="push-toggle" className="leading-snug">
              {t('preferences.notifications.toggle')}
            </Label>
            <Toggle
              id="push-toggle"
              checked={state === 'enabled'}
              disabled={state === 'busy'}
              onCheckedChange={onToggle}
              aria-label={t('preferences.notifications.toggle')}
            />
          </div>

          {message && <Alert variant={message.variant}>{message.text}</Alert>}

          {isIos() && !isStandalone() && (
            <p className="text-xs text-muted-foreground">{t('preferences.notifications.iosNote')}</p>
          )}
        </div>
      )}
    </Card>
  );
}
