import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mock the push API module -----------------------------------------------
const getVapidMock = vi.fn();
const subscribeMock = vi.fn();
const unsubscribeMock = vi.fn();
vi.mock('../../../api/push.ts', () => ({
  getApplicationServerKey: (...a: unknown[]) => getVapidMock(...a),
  subscribePush: (...a: unknown[]) => subscribeMock(...a),
  unsubscribePush: (...a: unknown[]) => unsubscribeMock(...a),
  // Keep a pure decoder — the component only forwards its result.
  urlBase64ToUint8Array: () => new Uint8Array([1, 2, 3]),
}));

// The card only exists when config.json sets pushEnabled: true.
const pushFlag = vi.hoisted(() => ({ enabled: true }));
vi.mock('../../../config.ts', () => ({ isPushEnabled: () => pushFlag.enabled }));

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

  const created = {
    endpoint: 'https://push/ep',
    unsubscribe: vi.fn().mockResolvedValue(true),
    toJSON: () => ({ endpoint: 'https://push/ep', keys: { p256dh: 'p256', auth: 'authk' } }),
  };
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(existing),
    subscribe: vi.fn().mockResolvedValue(created),
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

  return { pushManager, serviceWorker, requestPermission, registration, created };
}

describe('NotificationsCard', () => {
  beforeEach(() => {
    pushFlag.enabled = true;
    getVapidMock.mockReset().mockResolvedValue({ application_server_key: 'APP_SERVER_KEY_B64' });
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
    const env = installPushEnv();
    getVapidMock.mockRejectedValue(new ApiError('Not Found', 404));
    render(<NotificationsCard />);

    const toggle = await screen.findByRole('switch');
    await userEvent.click(toggle);

    await waitFor(() =>
      expect(screen.getByText(/not enabled on this deployment/i)).toBeInTheDocument()
    );
    expect(subscribeMock).not.toHaveBeenCalled();
    // No key: the service worker is never registered.
    expect(env.serviceWorker.register).not.toHaveBeenCalled();
  });

  it('asks for permission inside the tap, before any network call', async () => {
    const env = installPushEnv();
    render(<NotificationsCard />);
    const toggle = await screen.findByRole('switch');
    await waitFor(() => expect(getVapidMock).toHaveBeenCalledTimes(1)); // mount prefetch
    getVapidMock.mockClear();

    await userEvent.click(toggle);

    await waitFor(() => expect(subscribeMock).toHaveBeenCalledTimes(1));
    // The prefetched key is reused: the click itself makes no key request.
    expect(getVapidMock).not.toHaveBeenCalled();
    const permissionOrder = env.requestPermission.mock.invocationCallOrder[0];
    const registerOrder = env.serviceWorker.register!.mock.invocationCallOrder[0];
    expect(permissionOrder).toBeLessThan(registerOrder);
  });

  it('re-sends an existing subscription to the server on mount', async () => {
    installPushEnv({ existingSubscription: true });
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(subscribeMock).toHaveBeenCalledWith({
        endpoint: 'https://push/ep',
        keys: { p256dh: 'p', auth: 'a' },
      })
    );
  });

  it('drops a subscription made with an older server key on mount', async () => {
    const env = installPushEnv();
    const stale = {
      endpoint: 'https://push/old',
      options: { applicationServerKey: new Uint8Array([9, 9, 9]).buffer },
      unsubscribe: vi.fn().mockResolvedValue(true),
      toJSON: () => ({ endpoint: 'https://push/old', keys: { p256dh: 'p', auth: 'a' } }),
    };
    env.pushManager.getSubscription.mockResolvedValue(stale);
    render(<NotificationsCard />);

    await waitFor(() =>
      expect(screen.getByText(/reset on the server/i)).toBeInTheDocument()
    );
    expect(stale.unsubscribe).toHaveBeenCalledTimes(1);
    // The old row is removed on the server too: no orphan left behind.
    expect(unsubscribeMock).toHaveBeenCalledWith('https://push/old');
    expect(subscribeMock).not.toHaveBeenCalled();
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('turning off waits for the mount re-POST, so DELETE always lands last', async () => {
    installPushEnv({ existingSubscription: true });
    let releasePost: () => void = () => undefined;
    subscribeMock.mockImplementationOnce(
      () => new Promise((resolve) => (releasePost = () => resolve({ subscribed: true })))
    );
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true')
    );

    await userEvent.click(screen.getByRole('switch'));
    expect(unsubscribeMock).not.toHaveBeenCalled(); // still waiting for the POST
    releasePost();

    await waitFor(() => expect(unsubscribeMock).toHaveBeenCalledTimes(1));
    expect(subscribeMock.mock.invocationCallOrder[0]).toBeLessThan(
      unsubscribeMock.mock.invocationCallOrder[0]
    );
  });

  it('keeps a subscription made with the current server key', async () => {
    const env = installPushEnv();
    const current = {
      endpoint: 'https://push/ep',
      options: { applicationServerKey: new Uint8Array([1, 2, 3]).buffer },
      unsubscribe: vi.fn().mockResolvedValue(true),
      toJSON: () => ({ endpoint: 'https://push/ep', keys: { p256dh: 'p', auth: 'a' } }),
    };
    env.pushManager.getSubscription.mockResolvedValue(current);
    render(<NotificationsCard />);

    await waitFor(() => expect(subscribeMock).toHaveBeenCalledTimes(1));
    expect(current.unsubscribe).not.toHaveBeenCalled();
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('true');
  });

  it('explains the device cap when the server answers 409', async () => {
    installPushEnv();
    subscribeMock.mockRejectedValueOnce(new ApiError('too many devices', 409));
    render(<NotificationsCard />);

    await userEvent.click(await screen.findByRole('switch'));

    await waitFor(() => expect(screen.getByText(/too many devices/i)).toBeInTheDocument());
  });

  it('drops an older subscription before subscribing again', async () => {
    const env = installPushEnv();
    const stale = { unsubscribe: vi.fn().mockResolvedValue(true) };
    // Mount sees nothing (toggle off); the click then finds a stale one.
    env.pushManager.getSubscription.mockResolvedValueOnce(null).mockResolvedValueOnce(stale);
    render(<NotificationsCard />);

    await userEvent.click(await screen.findByRole('switch'));

    await waitFor(() => expect(subscribeMock).toHaveBeenCalledTimes(1));
    expect(stale.unsubscribe).toHaveBeenCalledTimes(1);
    expect(stale.unsubscribe.mock.invocationCallOrder[0]).toBeLessThan(
      env.pushManager.subscribe.mock.invocationCallOrder[0]
    );
  });

  it('shows the home-screen note in Safari, where Push is unavailable', async () => {
    Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true });
    delete (window as unknown as { PushManager?: unknown }).PushManager;
    Object.defineProperty(navigator, 'userAgent', {
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
      configurable: true,
    });
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(screen.getByText(/add this app to your home screen/i)).toBeInTheDocument()
    );
  });

  it('renders nothing when the deployment has push disabled', () => {
    pushFlag.enabled = false;
    const env = installPushEnv();
    const { container } = render(<NotificationsCard />);
    expect(container).toBeEmptyDOMElement();
    expect(env.serviceWorker.getRegistration).not.toHaveBeenCalled();
  });

  it('drops the local subscription when the server rejects it', async () => {
    const env = installPushEnv();
    subscribeMock.mockRejectedValueOnce(new ApiError('Server error', 500));
    render(<NotificationsCard />);

    await userEvent.click(await screen.findByRole('switch'));

    await waitFor(() => expect(env.created.unsubscribe).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('switch').getAttribute('aria-checked')).toBe('false');
  });

  it('shows the iOS home-screen note on iPhone', async () => {
    installPushEnv({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)' });
    render(<NotificationsCard />);
    await waitFor(() =>
      expect(screen.getByText(/add this app to your home screen/i)).toBeInTheDocument()
    );
  });
});
