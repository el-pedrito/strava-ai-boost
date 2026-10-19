import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ActivityDetailPage } from '../ActivityDetailPage';

const getMock = vi.hoisted(() => vi.fn());

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return { ...actual, api: { ...actual.api, get: (path: string) => getMock(path) } };
});

const LONG_TEXT = Array.from({ length: 10 }, (_, i) => `Paragraphe ${i + 1} de la séance inventée.`).join('\n\n');

/** Invented strength session, no heart rate. */
const GYM = {
  activity_id: '777',
  activity_type: 'WeightTraining',
  enhanced_title: 'Séance haut du corps',
  enhanced_description: LONG_TEXT,
  start_date: '2026-10-16T15:50:00Z',
  distance: 0,
  moving_time: 2879,
  processing_status: 'completed',
  modules_used: ['intervals_icu'],
};

function renderDetail(detail: Record<string, unknown>) {
  getMock.mockImplementation((path: string) =>
    path.startsWith('/dashboard/activities') ? Promise.resolve({ activities: [detail] }) : Promise.reject(new Error('n/a')),
  );
  return render(
    <MemoryRouter initialEntries={[`/activities/${detail.activity_id}`]}>
      <Routes>
        <Route path="/activities/:id" element={<ActivityDetailPage />} />
        <Route path="/activities" element={<p>activities list</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ActivityDetailPage', () => {
  beforeEach(() => {
    getMock.mockReset();
  });

  it('translates the sport type instead of the raw Strava name', async () => {
    renderDetail(GYM);
    const badge = await screen.findByTestId('activity-type');
    expect(badge).toHaveTextContent('Strength');
    expect(screen.queryByText('WeightTraining')).toBeNull();
  });

  it('labels a run as Run', async () => {
    renderDetail({ ...GYM, activity_id: '778', activity_type: 'Run', distance: 7390 });
    expect(await screen.findByTestId('activity-type')).toHaveTextContent('Run');
  });

  it('goes back to the activities list', async () => {
    renderDetail(GYM);
    await screen.findByTestId('activity-type');
    const back = await screen.findByRole('link', { name: 'All activities' });
    expect(back).toHaveAttribute('href', '/activities');
    await userEvent.click(back);
    expect(screen.getByText('activities list')).toBeInTheDocument();
  });

  it('shows heart rate only when the payload has it', async () => {
    const { unmount } = renderDetail(GYM);
    await screen.findByTestId('activity-type');
    expect(screen.queryByText(/bpm/)).toBeNull();
    unmount();
    renderDetail({ ...GYM, activity_id: '779', average_heartrate: 132.4, max_heartrate: 168 });
    expect(await screen.findByText('132 bpm')).toBeInTheDocument();
    expect(screen.getByText('168 bpm')).toBeInTheDocument();
  });

  it('collapses a long AI description with a Read all toggle', async () => {
    renderDetail(GYM);
    const text = await screen.findByTestId('activity-description');
    expect(text).toHaveAttribute('data-expanded', 'false');
    expect(text.className).toContain('line-clamp-6');
    const toggle = screen.getByRole('button', { name: 'Read all' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(text).toHaveAttribute('data-expanded', 'true');
    expect(text.className).not.toContain('line-clamp-6');
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
  });
});
