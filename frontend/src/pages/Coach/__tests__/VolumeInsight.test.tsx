import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { CoachPage } from '../CoachPage';

const getMock = vi.hoisted(() => vi.fn());

vi.mock('../../../api/client.ts', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client');
  return {
    ...actual,
    api: { ...actual.api, get: (path: string) => getMock(path), post: () => Promise.resolve({}) },
  };
});

vi.mock('../CoachChat.tsx', () => ({ CoachChat: () => <div data-testid="coach-chat" /> }));

/** weekly_volume_km: 3 completed weeks then the week in progress (last bucket). */
function summary(weeklyKm: number[], completedChange: number | null) {
  return {
    schema_version: 1,
    athlete_profile: '',
    recent_feedback: [],
    current_week: { runs: 0, run_km: 0, other: 1, total: 1 },
    weekly_trends: [],
    volume_change_completed_weeks_pct: completedChange,
    trends: {
      weekly_volume_km: weeklyKm,
      sessions_per_week: [4, 5, 4, 1],
      avg_pace_per_week: ['5:50', '5:42', '5:55', '-'],
      interval_paces: [],
      ef_paces: [],
      ramp_rate: completedChange,
      compliance: null,
      recovery: null,
      health_anomalies: [],
    },
  };
}

async function renderTrends(body: unknown) {
  getMock.mockImplementation((path: string) => {
    if (path === '/coach/recaps') return Promise.resolve({ recaps: [] });
    if (path === '/coach/summary') return Promise.resolve(body);
    return Promise.resolve({});
  });
  const user = userEvent.setup();
  render(
    <ThemeProvider>
      <MemoryRouter>
        <CoachPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
  await waitFor(() => expect(getMock).toHaveBeenCalledWith('/coach/summary'));
  await user.click(await screen.findByRole('tab', { name: 'Trends' }));
}

beforeEach(() => {
  getMock.mockReset();
  window.localStorage.setItem('strava-ai-boost-theme', 'dark');
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (q: string) => ({
      matches: false, media: q, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    }),
  });
});

describe('weekly volume insight', () => {
  it('Monday: the empty week in progress is not read as a -100% recovery week', async () => {
    await renderTrends(summary([39.9, 45.6, 40.2, 0], -11.8));
    expect(await screen.findByText('Steady volume around 42 km/week.')).toBeInTheDocument();
    expect(screen.queryByText(/Recovery week: −100%/)).not.toBeInTheDocument();
  });

  it('a real drop between the last two completed weeks is a recovery week', async () => {
    await renderTrends(summary([40, 45, 30, 5], -33.3));
    expect(await screen.findByText('Recovery week: −33% volume vs previous week. Normal after a heavy week.')).toBeInTheDocument();
  });

  it('a real rise between the last two completed weeks is flagged', async () => {
    await renderTrends(summary([30, 30, 40, 2], 33.3));
    expect(await screen.findByText('Volume up 33% vs previous week. Watch fatigue indicators.')).toBeInTheDocument();
  });
});
