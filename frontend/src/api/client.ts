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
