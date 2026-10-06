import { api } from './client.ts';

/**
 * Web Push API wrappers over the shared authenticated client (`api`), so these
 * calls carry the same Cognito ID token as every other request. The contract is
 * implemented by the backend:
 *   GET    /push/application-server-key -> { application_server_key }
 *          (VAPID, base64url uncompressed P-256, the W3C `applicationServerKey`)
 *   POST   /push/subscribe { endpoint, keys:{ p256dh, auth } } -> { subscribed:true }
 *   DELETE /push/subscribe { endpoint } -> { subscribed:false }
 */

export interface ApplicationServerKeyResponse {
  application_server_key: string;
}

export interface SubscribeResponse {
  subscribed: boolean;
}

/** Body shape the backend expects — the relevant subset of PushSubscription.toJSON(). */
export interface PushSubscriptionBody {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

export function getApplicationServerKey(): Promise<ApplicationServerKeyResponse> {
  return api.get<ApplicationServerKeyResponse>('/push/application-server-key');
}

export function subscribePush(body: PushSubscriptionBody): Promise<SubscribeResponse> {
  return api.post<SubscribeResponse>('/push/subscribe', body);
}

export function unsubscribePush(endpoint: string): Promise<SubscribeResponse> {
  // The shared client's delete() sends no body; this endpoint needs { endpoint }.
  return api.deleteWithBody<SubscribeResponse>('/push/subscribe', { endpoint });
}

/**
 * Convert a base64url VAPID application server key into the Uint8Array that
 * `pushManager.subscribe({ applicationServerKey })` requires.
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const output = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}
