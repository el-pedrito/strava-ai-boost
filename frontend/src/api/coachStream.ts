/**
 * Coach streaming client — AG-UI protocol over SSE.
 *
 * Two transports share the same AG-UI event parser and token-by-token surface:
 *
 *   1. AgentCore Runtime (Phase A, agentic) — when `coachRuntimeArn` is set.
 *      POSTs SSE directly to the AgentCore data plane
 *      (`bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations`)
 *      with a Bearer Cognito ID token (customJWT authorizer, no SigV4). The
 *      agent runs tool loops server-side; `user_id` is derived from the
 *      `custom:strava_id` JWT claim, not the request body.
 *
 *   2. Lambda Function URL (legacy fallback) — when only `coachStreamUrl` is
 *      set. Calls the coach Lambda (AWS_IAM auth) using SigV4-signed requests;
 *      temporary IAM credentials come from the Cognito Identity Pool.
 *
 * Both servers emit AG-UI events:
 *   RUN_STARTED → TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT* → TEXT_MESSAGE_END → RUN_FINISHED
 * (or RUN_ERROR). The Runtime path additionally emits TOOL_CALL_START/END around
 * tool loops, surfaced via callbacks so the UI can show a progress indicator.
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
  // Tool loop events (AgentCore Runtime path).
  toolCallId?: string;
  toolCallName?: string;
}

export interface CoachStreamCallbacks {
  onDelta: (text: string) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
  /** Fired on TOOL_CALL_START (Runtime path); `toolName` is the invoked tool. */
  onToolCallStart?: (toolName?: string) => void;
  /** Fired on TOOL_CALL_END (Runtime path). */
  onToolCallEnd?: (toolName?: string) => void;
}

export interface CoachStreamRequest {
  question: string;
  user_id: string;
  session_id: string;
  history: { role: string; content: string }[];
}

/** AG-UI RunAgentInput message. */
interface AgUiMessage {
  id: string;
  role: string;
  content: string;
}

/** AG-UI RunAgentInput payload accepted by the AgentCore Runtime (AGUI protocol). */
interface RunAgentInput {
  threadId: string;
  runId: string;
  messages: AgUiMessage[];
  state: Record<string, unknown>;
  tools: unknown[];
  context: unknown[];
  forwardedProps: Record<string, unknown>;
}

/** True when the agentic AgentCore Runtime chat is configured (Phase A). */
export function isRuntimeStreamingEnabled(): boolean {
  return Boolean(getConfig().coachRuntimeArn);
}

/** True when the legacy SigV4 streaming path is configured (Identity Pool + Function URL). */
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

/** Dispatch a single AG-UI event to the callbacks. Returns 'stop' to end the stream. */
function handleEvent(event: AgUiEvent, callbacks: CoachStreamCallbacks): 'continue' | 'stop' {
  switch (event.type) {
    case 'TEXT_MESSAGE_CONTENT':
      if (event.delta) callbacks.onDelta(event.delta);
      return 'continue';
    case 'TOOL_CALL_START':
      callbacks.onToolCallStart?.(event.toolCallName);
      return 'continue';
    case 'TOOL_CALL_END':
      callbacks.onToolCallEnd?.(event.toolCallName);
      return 'continue';
    case 'RUN_ERROR':
      callbacks.onError?.(event.message || 'stream error');
      return 'stop';
    case 'RUN_FINISHED':
      callbacks.onDone?.();
      return 'stop';
    default:
      return 'continue';
  }
}

/**
 * Read an SSE response body to completion, dispatching AG-UI events.
 * Throws on a non-2xx / bodyless response so the caller can fall back.
 */
async function pumpSse(
  response: Response,
  callbacks: CoachStreamCallbacks,
  errorPrefix: string,
): Promise<void> {
  if (!response.ok || !response.body) {
    let detail = '';
    try {
      detail = await response.text();
    } catch {
      /* ignore */
    }
    throw new Error(`${errorPrefix}: ${response.status} ${detail}`);
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
      if (handleEvent(event, callbacks) === 'stop') return;
    }
  }
  // Flush a final frame not terminated by a blank line (non-\n\n-terminated SSE).
  const tail = buffer.trim();
  if (tail) {
    const [events] = parseSseBuffer(`${tail}\n\n`);
    for (const event of events) {
      if (handleEvent(event, callbacks) === 'stop') return;
    }
  }
  callbacks.onDone?.();
}

/**
 * Stream a coach answer from the AgentCore Runtime data plane (Phase A path).
 * POSTs an AG-UI RunAgentInput with a Bearer Cognito JWT (customJWT authorizer);
 * no SigV4. Resolves when the stream finishes; rejects on transport failure so
 * the caller can fall back to the buffered endpoint.
 */
export async function streamCoachAnswerRuntime(
  body: CoachStreamRequest,
  idToken: string,
  callbacks: CoachStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const config = getConfig();
  const region = getRegion();
  const arn = config.coachRuntimeArn;
  if (!arn) throw new Error('coachRuntimeArn not configured');
  const url =
    `https://bedrock-agentcore.${region}.amazonaws.com` +
    `/runtimes/${encodeURIComponent(arn)}/invocations?qualifier=DEFAULT`;

  const messages: AgUiMessage[] = [
    ...body.history.map((m) => ({ id: crypto.randomUUID(), role: m.role, content: m.content })),
    { id: crypto.randomUUID(), role: 'user', content: body.question },
  ];

  const payload: RunAgentInput = {
    threadId: body.session_id,
    runId: crypto.randomUUID(),
    messages,
    state: {},
    tools: [],
    context: [],
    forwardedProps: {},
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${idToken}`,
      // Runtime session id must be 33+ chars — satisfied by the coach chat session id.
      // Runtime constraint: runtimeSessionId must be >= 33 chars.
      'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id':
        body.session_id.length >= 33
          ? body.session_id
          : `${body.session_id}-${crypto.randomUUID()}`,
    },
    body: JSON.stringify(payload),
    signal,
  });

  await pumpSse(response, callbacks, 'Coach runtime stream failed');
}

/**
 * Stream a coach answer from the legacy Lambda Function URL (SigV4, fallback).
 * Resolves when the stream finishes; rejects on transport or signing failure so
 * the caller can fall back to the buffered endpoint.
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

  await pumpSse(response, callbacks, 'Coach stream failed');
}
