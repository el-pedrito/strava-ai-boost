import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell } from 'lucide-react';
import { Alert, Card, CardDescription, CardHeader, CardTitle, Label, Toggle } from '@/ui';
import { ApiError } from '../../api/client.ts';
import {
  getVapidPublicKey,
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
 * default: the toggle registers the service worker, requests permission and
 * subscribes with the server VAPID key (POST /push/subscribe); turning it off
 * unsubscribes locally and server-side (DELETE /push/subscribe). State is
 * reflected from pushManager.getSubscription(). Errors are non-blocking; if the
 * push API is missing on this deployment we say so instead of failing loudly.
 */
export function NotificationsCard() {
  const { t } = useTranslation();
  const [state, setState] = useState<PushState>('idle');
  const [message, setMessage] = useState<{ variant: 'error' | 'warning'; text: string } | null>(
    null
  );

  // Reflect the current subscription on mount — no prompting, just reading.
  useEffect(() => {
    if (!pushSupported()) {
      setState('unsupported');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const reg = await navigator.serviceWorker.getRegistration();
        const sub = reg ? await reg.pushManager.getSubscription() : null;
        if (!cancelled) setState(sub ? 'enabled' : 'idle');
      } catch {
        if (!cancelled) setState('idle');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const enable = useCallback(async () => {
    setState('busy');
    setMessage(null);
    try {
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;

      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setState('idle');
        setMessage({ variant: 'warning', text: t('preferences.notifications.denied') });
        return;
      }

      let publicKey: string;
      try {
        const res = await getVapidPublicKey();
        publicKey = res.public_key;
      } catch {
        // 404 / error on the key endpoint means push isn't wired on this deployment.
        setState('idle');
        setMessage({ variant: 'warning', text: t('preferences.notifications.notDeployed') });
        return;
      }

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });

      const json = sub.toJSON();
      await subscribePush({
        endpoint: json.endpoint ?? '',
        keys: {
          p256dh: json.keys?.p256dh ?? '',
          auth: json.keys?.auth ?? '',
        },
      });
      setState('enabled');
    } catch (err) {
      setState('idle');
      setMessage({
        variant: 'error',
        text:
          err instanceof ApiError
            ? t('preferences.notifications.notDeployed')
            : t('preferences.notifications.error'),
      });
    }
  }, [t]);

  const disable = useCallback(async () => {
    setState('busy');
    setMessage(null);
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
        <Alert variant="info">{t('preferences.notifications.unsupported')}</Alert>
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

          {isIos() && (
            <p className="text-xs text-muted-foreground">{t('preferences.notifications.iosNote')}</p>
          )}
        </div>
      )}
    </Card>
  );
}
