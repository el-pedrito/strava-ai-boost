import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiError, api, getActivityFeedback, submitActivityFeedback } from '../client';

vi.mock('../../config.ts', () => ({
  getConfig: () => ({
    apiGatewayUrl: 'https://api.example.com',
    defaultUserId: 'user-123',
  }),
}));

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe('ApiError', () => {
  it('stores status code', () => {
    const error = new ApiError('Not found', 404);
    expect(error.message).toBe('Not found');
    expect(error.status).toBe(404);
    expect(error).toBeInstanceOf(Error);
  });
});

describe('api.get', () => {
  it('sends GET with correct headers', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: 'test' }),
    });

    const result = await api.get('/dashboard/stats');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/dashboard/stats',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    );
    expect(result).toEqual({ data: 'test' });
  });

  it('strips trailing slash from base URL', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await api.get('/test');
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/test',
      expect.anything(),
    );
  });

  it('throws ApiError on non-ok response', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ error: 'Server error' }),
    });

    await expect(api.get('/fail')).rejects.toThrow(ApiError);
    await expect(api.get('/fail')).rejects.toMatchObject({ status: 500 });
  });

  it('uses error message from response body', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ message: 'Bad request' }),
    });

    await expect(api.get('/bad')).rejects.toThrow('Bad request');
  });

  it('falls back to generic message', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: () => Promise.resolve({}),
    });

    await expect(api.get('/bad')).rejects.toThrow('Request failed');
  });
});

describe('api.post', () => {
  it('sends POST with JSON body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 1 }),
    });

    await api.post('/items', { name: 'test' });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/items',
      expect.objectContaining({
        method: 'POST',
        body: '{"name":"test"}',
      }),
    );
  });

  it('sends POST without body', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await api.post('/action');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/action',
      expect.objectContaining({
        method: 'POST',
        body: undefined,
      }),
    );
  });
});

describe('api.delete', () => {
  it('sends DELETE request', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ deleted: true }),
    });

    const result = await api.delete('/items/1');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/items/1',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(result).toEqual({ deleted: true });
  });
});

describe('activity feedback', () => {
  it('GETs the feedback window of an activity', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ state: 'awaiting', deadline_at: '2026-10-17T19:00:00Z' }),
    });

    const result = await getActivityFeedback('123');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/activities/123/feedback',
      expect.not.objectContaining({ method: 'POST' }),
    );
    expect(result).toEqual({ state: 'awaiting', deadline_at: '2026-10-17T19:00:00Z' });
  });

  it('POSTs the RPE and summary as JSON', async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 202, json: () => Promise.resolve({}) });

    await submitActivityFeedback('123', { rpe: 7, summary: 'ok' });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/activities/123/feedback',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ rpe: 7, summary: 'ok' }) }),
    );
  });

  it('surfaces a 409 as ApiError with its status', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ error: 'closed' }),
    });

    await expect(submitActivityFeedback('123', { rpe: 7 })).rejects.toMatchObject({ status: 409 });
  });

  it('encodes the activity id in the path', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ state: 'none' }) });

    await getActivityFeedback('1/../x');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/activities/1%2F..%2Fx/feedback',
      expect.anything(),
    );
  });
});
