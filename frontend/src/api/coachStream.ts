/**
 * Coach streaming client — AG-UI protocol over SSE.
 *
 * Calls the coach Lambda Function URL (AWS_IAM auth) using SigV4-signed requests.
 * Temporary IAM credentials are obtained from the Cognito Identity Pool by
 * exchanging the User Pool ID token, per the project security policy
 * (frontend signs requests with SigV4; no unauthenticated endpoints).
 *
 * The server emits AG-UI events:
 *   RUN_STARTED → TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT* → TEXT_MESSAGE_END → RUN_FINISHED
 * (or RUN_ERROR). We surface text deltas to the caller via callbacks.
 */
import { SignatureV4 } from '@aws-sdk/signature-v4';
import { Sha256 } from '@aws-crypto/sha256-js';
import { fromCognitoIdentityPool } from '@aws-sdk/credential-provider-cognito-identity';
import { getConfig } from '../config.ts';

export interface AgUiEvent {
  type: string;
  delta?: string;
  message?: string;
  messageId?: string;
  runId?: string;
  role?: string;
}

export interface CoachStreamCallbacks {
  onDelta: (text: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
}

export interface CoachStreamRequest {
  question: string;
  user_id: string;
  session_id: string;
  history: { role: string; content: string }[];
}

/** True when streaming is configured (Identity Pool + Function URL present). */
export function isStreamingEnabled(): boolean {
  const config = getConfig();
  return Boolean(config.identityPoolId && config.coachStreamUrl);
}

function getRegion(): string {
  return getConfig().cognitoRegion || 'us-east-1';
}

/** Exchange the Cognito User Pool ID token for temporary IAM credentials. */
function getCredentials(idToken: string) {
  const config = getConfig();
  const region = getRegion();
  const providerKey = `cognito-idp.${region}.amazonaws.com/${config.cognitoUserPoolId}`;
  return fromCognitoIdentityPool({
    clientConfig: { region },
    identityPoolId: config.identityPoolId!,
    logins: { [providerKey]: idToken },
  });
}

/** Parse a raw SSE text buffer into complete events; returns [events, remainder]. */
export function parseSseBuffer(buffer: string): [AgUiEvent[], string] {
  const events: AgUiEvent[] = [];
  const frames = buffer.split('\n\n');
  const remainder = frames.pop() ?? '';

  for (const frame of frames) {
    const dataLines = frame
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart());
    if (dataLines.length === 0) continue;
    try {
      events.push(JSON.parse(dataLines.join('\n')) as AgUiEvent);
    } catch {
      // Ignore malformed frames (e.g. keep-alive comments)
    }
  }
  return [events, remainder];
}

/**
 * Stream a coach answer. Resolves when the stream finishes; rejects on transport
 * or signing failure so the caller can fall back to the buffered endpoint.
 */
export async function streamCoachAnswer(
  body: CoachStreamRequest,
  idToken: string,
  callbacks: CoachStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const config = getConfig();
  const region = getRegion();
  const url = new URL(config.coachStreamUrl!);
  const payload = JSON.stringify(body);

  const signer = new SignatureV4({
    service: 'lambda',
    region,
    credentials: getCredentials(idToken),
    sha256: Sha256,
  });

  const signed = await signer.sign({
    method: 'POST',
    protocol: url.protocol,
    hostname: url.hostname,
    path: url.pathname,
    headers: {
      host: url.hostname,
      'content-type': 'application/json',
    },
    body: payload,
  });

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers: signed.headers,
    body: payload,
    signal,
  });

  if (!response.ok || !response.body) {
    let detail = '';
    try {
      detail = await response.text();
    } catch {
      /* ignore */
    }
    throw new Error(`Coach stream failed: ${response.status} ${detail}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const [events, remainder] = parseSseBuffer(buffer);
    buffer = remainder;
    for (const event of events) {
      if (event.type === 'TEXT_MESSAGE_CONTENT' && event.delta) {
        callbacks.onDelta(event.delta);
      } else if (event.type === 'RUN_ERROR') {
        callbacks.onError?.(event.message || 'stream error');
        return;
      } else if (event.type === 'RUN_FINISHED') {
        callbacks.onDone?.();
        return;
      }
    }
  }
  callbacks.onDone?.();
}
