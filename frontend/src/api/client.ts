import { getConfig } from '../config.ts';
import { CognitoUserPool } from 'amazon-cognito-identity-js';
import type { PlanWorkoutsResponse } from '../types/index.ts';
import type { HomeSummary } from '../types/home.ts';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function getIdToken(): string | null {
  try {
    const config = getConfig();
    if (!config.cognitoUserPoolId || !config.cognitoClientId) return null;
    const pool = new CognitoUserPool({
      UserPoolId: config.cognitoUserPoolId,
      ClientId: config.cognitoClientId,
    });
    const user = pool.getCurrentUser();
    if (!user) return null;
    let token: string | null = null;
    user.getSession((err: Error | null, session: { getIdToken: () => { getJwtToken: () => string } } | null) => {
      if (!err && session) token = session.getIdToken().getJwtToken();
    });
    return token;
  } catch {
    return null;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const config = getConfig();
  const url = `${config.apiGatewayUrl.replace(/\/$/, '')}${path}`;
  const token = getIdToken();

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': token } : {}),
      ...options?.headers,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new ApiError(data.error || data.message || 'Request failed', response.status);
  }

  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  deleteWithBody: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'DELETE', body: body ? JSON.stringify(body) : undefined }),
};

/** Upcoming Campus plan sessions with their Apple Watch `.workout` payloads. */
export function getPlanWorkouts(): Promise<PlanWorkoutsResponse> {
  return api.get<PlanWorkoutsResponse>('/plan/workouts');
}

/**
 * Athlete home dashboard: morning brief, race, Campus plan, this week, health,
 * predictions and Enduraw trend. Owner-only (403 otherwise), `Cache-Control:
 * no-store`. Shape documented in CONTRACT.md; every field can be null.
 */
export function getHomeSummary(): Promise<HomeSummary> {
  return api.get<HomeSummary>('/home/summary');
}

/** Post-session input window of one activity (plan docs/design/rpe-athlete-input.md §6). */
export type ActivityFeedbackState = 'awaiting' | 'submitted' | 'closed' | 'none';

export interface ActivityFeedbackStatus {
  state: ActivityFeedbackState;
  /** ISO 8601 UTC, present only while the window is open. */
  deadline_at?: string;
}

export interface ActivityFeedbackBody {
  /** Rating of perceived exertion, integer 1-10. */
  rpe: number;
  /** Free text, at most 2000 characters. Omitted when empty. */
  summary?: string;
}

/**
 * `GET /activities/{id}/feedback`. Owner-only (403 otherwise). The form is only
 * shown for `awaiting`; a stale window is already reported `closed` server-side.
 */
export function getActivityFeedback(activityId: string): Promise<ActivityFeedbackStatus> {
  return api.get<ActivityFeedbackStatus>(`/activities/${encodeURIComponent(activityId)}/feedback`);
}

/**
 * `POST /activities/{id}/feedback` -> 202 accepted, 400 invalid body, 403 not
 * the owner, 409 window already closed or input already sent. Errors surface as
 * `ApiError` with the HTTP status.
 */
export function submitActivityFeedback(
  activityId: string,
  body: ActivityFeedbackBody,
): Promise<unknown> {
  return api.post<unknown>(`/activities/${encodeURIComponent(activityId)}/feedback`, body);
}
