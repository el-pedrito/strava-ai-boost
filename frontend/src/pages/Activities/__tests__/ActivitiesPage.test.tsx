import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { ActivitiesPage } from '../ActivitiesPage';

const getMock = vi.hoisted(() => vi.fn());

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return { ...actual, api: { ...actual.api, get: (path: string) => getMock(path) } };
});

/** Invented activities, Wednesday 21 Oct 2026 as "now" (week 43). */
const NOW = new Date('2026-10-21T12:00:00Z');
const ACTIVITIES = [
  {
    activity_id: '9001',
    activity_type: 'Run',
    enhanced_title: 'Fractionné du mardi',
    start_date: '2026-10-20T15:50:00Z',
    distance: 7390,
    moving_time: 2467,
    processing_status: 'completed',
  },
  {
    activity_id: '9002',
    activity_type: 'WeightTraining',
    enhanced_title: 'Haut du corps',
    start_date: '2026-10-19T06:00:00Z',
    distance: 0,
    moving_time: 2879,
    processing_status: 'failed',
  },
  {
    activity_id: '9003',
    activity_type: 'Run',
    enhanced_title: 'Sortie longue',
    start_date: '2026-10-11T08:00:00Z',
    distance: 15000,
    moving_time: 5400,
    processing_status: 'completed',
  },
];

function LocationProbe() {
  const loc = useLocation();
  return <output data-testid="location">{loc.pathname + loc.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/activities" element={<ActivitiesPage />} />
        <Route path="/activities/:id" element={<p>detail page</p>} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  );
}

const plain = (s: string | null | undefined) => (s ?? '').replace(/[\u202f\u00a0]/g, ' ');

describe('ActivitiesPage', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    getMock.mockReset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads the list, summarises the window and groups rows by week', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES });
    renderAt('/activities');
    expect(screen.getByTestId('activities-skeleton')).toBeInTheDocument();
    expect(await screen.findByText('Fractionné du mardi')).toBeInTheDocument();
    expect(getMock).toHaveBeenCalledWith('/dashboard/activities?limit=100');
    expect(screen.getByTestId('activities-subtitle')).toHaveTextContent(
      '3 activities in 30 days · 2 runs, 1 strength session',
    );
    const weeks = screen.getAllByTestId('activity-week');
    expect(weeks).toHaveLength(2);
    expect(within(weeks[0]).getByRole('heading')).toHaveTextContent(/^This week · /);
    expect(within(weeks[1]).getByRole('heading')).toHaveTextContent(/^Week of /);
    expect(plain(within(weeks[0]).getByTestId('activity-week-totals').textContent)).toBe(
      '7.4 km run · 2 activities',
    );
  });

  it('shows distance, time and pace for a run, only the time for strength, and a failed badge', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES });
    renderAt('/activities');
    await screen.findByText('Fractionné du mardi');
    const [runRow, gymRow] = screen.getAllByTestId('activity-row');
    expect(plain(runRow.textContent)).toContain('7.39 km · 41:07 · 5:34 /km');
    expect(plain(gymRow.textContent)).toContain('47:59');
    expect(gymRow.textContent).not.toContain('km');
    expect(within(gymRow).getByText('Failed')).toBeInTheDocument();
    expect(within(runRow).queryByText('Failed')).toBeNull();
    expect(within(runRow).queryByText('Processing')).toBeNull();
  });

  it('makes the whole row a link to the activity detail', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES });
    renderAt('/activities');
    await screen.findByText('Fractionné du mardi');
    const link = screen.getByRole('link', { name: /Fractionné du mardi/ });
    expect(link).toHaveAttribute('href', '/activities/9001');
    await userEvent.click(link);
    expect(screen.getByText('detail page')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/activities/9001');
  });

  it('filters by type and keeps the choice in the URL', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES });
    renderAt('/activities');
    await screen.findByText('Fractionné du mardi');
    const group = screen.getByRole('radiogroup', { name: 'Activity type' });
    expect(within(group).getByRole('radio', { name: 'All' })).toHaveAttribute('aria-checked', 'true');

    await userEvent.click(within(group).getByRole('radio', { name: 'Strength' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/activities?type=strength');
    expect(screen.getAllByTestId('activity-row')).toHaveLength(1);
    expect(screen.getByText('Haut du corps')).toBeInTheDocument();
    expect(screen.queryByText('Sortie longue')).toBeNull();

    await userEvent.click(within(group).getByRole('radio', { name: 'All' }));
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/activities$/);
    expect(screen.getAllByTestId('activity-row')).toHaveLength(3);
  });

  it('reads the filter from ?type= on load', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES });
    renderAt('/activities?type=run');
    await screen.findByText('Fractionné du mardi');
    expect(screen.getByRole('radio', { name: 'Running' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getAllByTestId('activity-row')).toHaveLength(2);
    expect(screen.queryByText('Haut du corps')).toBeNull();
  });

  it('shows the empty state when nothing happened in 30 days', async () => {
    getMock.mockResolvedValue({ activities: [] });
    renderAt('/activities');
    expect(await screen.findByText('No activity in the last 30 days')).toBeInTheDocument();
    expect(screen.queryByTestId('activity-row')).toBeNull();
  });

  it('offers to show all when the filter empties the list', async () => {
    getMock.mockResolvedValue({ activities: ACTIVITIES.filter((a) => a.activity_type === 'Run') });
    renderAt('/activities?type=strength');
    expect(await screen.findByText('No activity of this type in the last 30 days')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all' }));
    expect(screen.getAllByTestId('activity-row')).toHaveLength(2);
  });

  it('shows an error with a retry', async () => {
    getMock.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce({ activities: ACTIVITIES });
    renderAt('/activities');
    expect(await screen.findByText('Could not load your activities.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Fractionné du mardi')).toBeInTheDocument();
  });
});
