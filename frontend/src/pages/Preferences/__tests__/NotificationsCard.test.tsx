import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mock the push API module -----------------------------------------------
const getVapidMock = vi.fn();
const subscribeMock = vi.fn();
const unsubscribeMock = vi.fn();
vi.mock('../../../api/push.ts', () => ({
  getVapidPublicKey: (...a: unknown[]) => getVapidMock(...a),
  subscribePush: (...a: unknown[]) => subscribeMock(...a),
  unsubscribePush: (...a: unknown[]) => unsubscribeMock(...a),
  // Keep a pure decoder — the component only forwards its result.
  urlBase64ToUint8Array: () => new Uint8Array([1, 2, 3]),
}));

// ApiError must be a real class so `instanceof ApiError` branches work.
import { ApiError } from '../../../api/client.ts';
import { NotificationsCard } from '../NotificationsCard';

// --- Web Push environment doubles -------------------------------------------
// Augment jsdom globals in place: replacing window/navigator wholesale wipes the
// test DOM and render() then fails.
type PushEnvServiceWorker = {
  getRegistration?: ReturnType<typeof vi.fn>;
  register?: ReturnType<typeof vi.fn>;
  ready?: Promise<unknown>;
};

function installPushEnv(options?: {
  existingSubscription?: boolean;
  permission?: NotificationPermission;
  userAgent?: string;
}) {
  const existing = options?.existingSubscription
    ? {
        endpoint: 'https://push/ep',
        unsubscribe: vi.fn().mockResolvedValue(true),
        toJSON: () => ({ endpoint: 'https://push/ep', keys: { p256dh: 'p', auth: 'a' } }),
      }
    : null;

  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(existing),
    subscribe: vi.fn().mockResolvedValue({
      endpoint: 'https://push/ep',
      toJSON: () => ({ endpoint: 'https://push/ep', keys: { p256dh: 'p256', auth: 'authk' } }),
    }),
  };
  const registration = { pushManager };

  const serviceWorker: PushEnvServiceWorker = {
    getRegistration: vi.fn().mockResolvedValue(registration),
    register: vi.fn().mockResolvedValue(registration),
    ready: Promise.resolve(registration),
  };

  Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorker, configurable: true });
  Object.defineProperty(navigator, 'userAgent', {
    value: options?.userAgent ?? 'Mozilla/5.0 (X11; Linux)',
    configurable: true,
  });

  const requestPermission = vi.fn().mockResolvedValue(options?.permission ?? 'granted');
  (window as unknown as { PushManager: unknown }).PushManager = function () {};
  (window as unknown as { Notification: unknown }).Notification = Object.assign(function () {}, {
    requestPermission,
  });

  return { pushManager, serviceWorker, requestPermission, registration };
}

describe('NotificationsCard', () => {
  beforeEach(() => {
    getVapidMock.mockReset().mockResolvedValue({ public_key: 'PUB_KEY_B64' });
    subscribeMock.mockReset().mockResolvedValue({ subscribed: true });
    unsubscribeMock.mockReset().mockResolvedValue({ subscribed: false });
  });

  afterEach(() => {
    delete (window as unknown as { PushManager?: unknown }).PushManager;
    delete (window as unknown as { Notification?: unknown }).Notification;
    Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true });
  });

  it('shows the unsupported message when Push is unavailable', async () => {
    Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true });
    delete (window as unknown as { PushManager?: unknown }).PushManager;
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(screen.getByText(/does not support push notifications/i)).toBeInTheDocument()
    );
  });

  it('enables push: registers SW, requests permission, subscribes, POSTs the right body', async () => {
    const env = installPushEnv();
    render(<NotificationsCard />);

    const toggle = await screen.findByRole('switch');
    await userEvent.click(toggle);

    await waitFor(() => expect(subscribeMock).toHaveBeenCalledTimes(1));
    expect(env.serviceWorker.register).toHaveBeenCalledWith('/sw.js');
    expect(env.requestPermission).toHaveBeenCalled();
    expect(getVapidMock).toHaveBeenCalled();
    expect(env.pushManager.subscribe).toHaveBeenCalledWith(
      expect.objectContaining({ userVisibleOnly: true })
    );
    // The POST body is the subset of PushSubscription.toJSON() the backend expects.
    expect(subscribeMock).toHaveBeenCalledWith({
      endpoint: 'https://push/ep',
      keys: { p256dh: 'p256', auth: 'authk' },
    });
    await waitFor(() =>
      expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true')
    );
  });

  it('shows the denied message and stays off when permission is denied', async () => {
    installPushEnv({ permission: 'denied' });
    render(<NotificationsCard />);

    const toggle = await screen.findByRole('switch');
    await userEvent.click(toggle);

    await waitFor(() => expect(screen.getByText(/permission was denied/i)).toBeInTheDocument());
    expect(subscribeMock).not.toHaveBeenCalled();
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('disables push: unsubscribes locally and sends DELETE server-side', async () => {
    const env = installPushEnv({ existingSubscription: true });
    render(<NotificationsCard />);

    // Starts enabled (an existing subscription is reflected on mount).
    await waitFor(() =>
      expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true')
    );
    await userEvent.click(screen.getByRole('switch'));

    await waitFor(() => expect(unsubscribeMock).toHaveBeenCalledTimes(1));
    expect(env.pushManager.getSubscription).toHaveBeenCalled();
    expect(unsubscribeMock).toHaveBeenCalledWith('https://push/ep');
    await waitFor(() =>
      expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false')
    );
  });

  it('shows the not-enabled message when the push API errors', async () => {
    installPushEnv();
    getVapidMock.mockRejectedValueOnce(new ApiError('Not Found', 404));
    render(<NotificationsCard />);

    const toggle = await screen.findByRole('switch');
    await userEvent.click(toggle);

    await waitFor(() =>
      expect(screen.getByText(/not enabled on this deployment/i)).toBeInTheDocument()
    );
    expect(subscribeMock).not.toHaveBeenCalled();
  });

  it('shows the iOS home-screen note on iPhone', async () => {
    installPushEnv({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)' });
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(screen.getByText(/add this app to your home screen/i)).toBeInTheDocument()
    );
  });
});
