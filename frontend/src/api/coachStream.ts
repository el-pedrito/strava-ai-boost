/**
 * Coach streaming client — AG-UI protocol over SSE.
 *
 * Transport: AgentCore Runtime (agentic). The browser POSTs the AG-UI event
 * stream directly to the AgentCore data plane
 * (`bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/invocations`) with a
 * Bearer Cognito ID token (customJWT authorizer, no SigV4). The agent runs tool
 * loops server-side; `user_id` is derived from the `custom:strava_id` JWT claim,
 * not the request body.
 *
 * The server emits AG-UI events:
 *   RUN_STARTED → TEXT_MESSAGE_START → TEXT_MESSAGE_CONTENT* → TEXT_MESSAGE_END → RUN_FINISHED
 * (or RUN_ERROR), plus TOOL_CALL_START/END around tool loops, surfaced via
 * callbacks so the UI can show a progress indicator.
 */
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

function getRegion(): string {
  return getConfig().cognitoRegion || 'us-east-1';
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

  // AgentCore may deliver several SSE events in a single network chunk. Dispatching
  // them all synchronously makes React batch the state updates into one paint, so
  // transient states (tool-call indicator, per-token text) never render and the
  // answer appears as a block. Yielding to a macrotask between events forces a
  // paint frame, restoring the token-by-token surface regardless of chunk size.
  const yieldToPaint = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const [events, remainder] = parseSseBuffer(buffer);
    buffer = remainder;
    for (const event of events) {
      if (handleEvent(event, callbacks) === 'stop') return;
      await yieldToPaint();
    }
  }
  // Flush a final frame not terminated by a blank line (non-\n\n-terminated SSE).
  const tail = buffer.trim();
  if (tail) {
    const [events] = parseSseBuffer(`${tail}\n\n`);
    for (const event of events) {
      if (handleEvent(event, callbacks) === 'stop') return;
      await yieldToPaint();
    }
  }
  callbacks.onDone?.();
}

/**
 * Stream a coach answer from the AgentCore Runtime data plane (sole transport).
 * POSTs an AG-UI RunAgentInput with a Bearer Cognito JWT (customJWT authorizer);
 * no SigV4. Resolves when the stream finishes; rejects on transport failure so
 * the caller can surface an error to the user.
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

