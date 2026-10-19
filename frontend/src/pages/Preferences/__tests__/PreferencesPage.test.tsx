import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { PreferencesPage } from '../PreferencesPage';

const getMock = vi.hoisted(() => vi.fn<(path: string) => Promise<unknown>>());
const postMock = vi.hoisted(() => vi.fn<(path: string, body?: unknown) => Promise<unknown>>());

vi.mock('@/api/client', () => ({
  api: {
    get: (path: string) => getMock(path),
    post: (path: string, body?: unknown) => postMock(path, body),
  },
}));

vi.mock('@/config', () => ({
  getConfig: () => ({ defaultUserId: 'u1' }),
  isPushEnabled: () => false,
}));

vi.mock('@/layouts/AppLayout', () => ({
  useFlash: () => () => {},
}));

const SYNCED_AT = '2026-10-17T06:05:00Z';

function campusZone(min: string, max: string, slug: string) {
  return { min, max, slug, value_s: 349, dvalue_s: 13 };
}

const CAMPUS_ZONES = {
  recovery: campusZone('6:40', '7:20', 'slow'),
  ef: campusZone('5:36', '6:02', 'ef'),
  aerobic: campusZone('5:10', '5:30', 'aerobie'),
  tempo: campusZone('4:55', '5:10', 'tempo'),
  sweet_spot: campusZone('4:45', '4:55', 'sweet-spot'),
  seuil_60: campusZone('4:35', '4:45', 'seuil60'),
  seuil_30: campusZone('4:25', '4:35', 'seuil30'),
  allure_marathon: campusZone('4:40', '4:50', 'marathon'),
  allure_semi: campusZone('4:25', '4:32', 'half-marathon'),
  interval: campusZone('3:50', '4:05', 'vma'),
};

function respond(preferences: Record<string, unknown>) {
  getMock.mockResolvedValue({ success: true, preferences: { athlete_profile: 'Runner', ...preferences } });
}

function localHhMm(iso: string): string {
  const d = new Date(iso);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

describe('PreferencesPage pace zones', () => {
  beforeEach(() => {
    getMock.mockReset();
    postMock.mockReset();
    postMock.mockResolvedValue({ success: true });
  });

  it('shows the Campus zones with the source week and sync time', async () => {
    respond({
      campus_pace_zones: CAMPUS_ZONES,
      campus_pace_zones_week: '2026-W43',
      campus_pace_zones_synced_at: SYNCED_AT,
      pace_zones_source: 'campus',
      pace_zones: { ef: { min: '9:00', max: '9:30' } },
    });
    render(<PreferencesPage />);

    const header = await screen.findByTestId('pace-zones-source');
    expect(header).toHaveTextContent(`Campus · week 43 · synced ${localHhMm(SYNCED_AT)}`);
    expect(within(screen.getByTestId('pace-zone-ef')).getByText('5:36 - 6:02 /km')).toBeInTheDocument();
    expect(within(screen.getByTestId('pace-zone-interval')).getByText('3:50 - 4:05 /km')).toBeInTheDocument();
    expect(screen.queryByText('9:00 - 9:30 /km')).not.toBeInTheDocument();
    expect(screen.queryByText('Out of date')).not.toBeInTheDocument();
  });

  it('shows a single-value Campus zone as one pace', async () => {
    respond({
      campus_pace_zones: { ...CAMPUS_ZONES, tempo: { min: '5:15', max: '5:15' } },
      campus_pace_zones_week: '2026-W43',
      campus_pace_zones_synced_at: SYNCED_AT,
      pace_zones_source: 'campus',
    });
    render(<PreferencesPage />);

    const tempo = await screen.findByTestId('pace-zone-tempo');
    expect(within(tempo).getByText('5:15 /km')).toBeInTheDocument();
    expect(within(tempo).queryByText('5:15 - 5:15 /km')).not.toBeInTheDocument();
  });

  it('shows a stale badge when the Campus week is out of date', async () => {
    respond({
      campus_pace_zones: CAMPUS_ZONES,
      campus_pace_zones_week: '2026-W40',
      campus_pace_zones_synced_at: SYNCED_AT,
      pace_zones_source: 'campus_stale',
    });
    render(<PreferencesPage />);

    expect(await screen.findByTestId('pace-zones-source')).toHaveTextContent('week 40');
    expect(screen.getByText('Out of date')).toBeInTheDocument();
    expect(within(screen.getByTestId('pace-zone-ef')).getByText('5:36 - 6:02 /km')).toBeInTheDocument();
  });

  it('falls back to the legacy manual zones, read-only, while awaiting the Campus sync', async () => {
    respond({
      pace_zones: { ef: { min: '5:45', max: '7:30' }, tempo: { min: '5:00', max: '5:45' } },
      pace_zones_source: 'manual_legacy',
    });
    render(<PreferencesPage />);

    expect(await screen.findByText(/Waiting for the Campus sync/)).toBeInTheDocument();
    expect(within(screen.getByTestId('pace-zone-ef')).getByText('5:45 - 7:30 /km')).toBeInTheDocument();
    expect(within(screen.getByTestId('pace-zone-recovery')).getByText('-')).toBeInTheDocument();
    expect(screen.queryByTestId('pace-zones-source')).not.toBeInTheDocument();
  });

  it('infers the legacy source when an older API omits pace_zones_source', async () => {
    respond({ pace_zones: { ef: { min: '5:45', max: '7:30' } } });
    render(<PreferencesPage />);

    expect(await screen.findByText(/Waiting for the Campus sync/)).toBeInTheDocument();
    expect(within(screen.getByTestId('pace-zone-ef')).getByText('5:45 - 7:30 /km')).toBeInTheDocument();
  });

  it('says there are no zones when neither Campus nor manual zones exist', async () => {
    respond({ pace_zones_source: 'none' });
    render(<PreferencesPage />);

    expect(await screen.findByText(/No pace zones yet/)).toBeInTheDocument();
    expect(screen.queryByTestId('pace-zone-ef')).not.toBeInTheDocument();
  });

  it('renders no pace input of any kind', async () => {
    respond({
      campus_pace_zones: CAMPUS_ZONES,
      campus_pace_zones_week: '2026-W43',
      pace_zones_source: 'campus',
    });
    const { container } = render(<PreferencesPage />);

    await screen.findByTestId('pace-zones-source');
    expect(container.querySelector('[id$="-min"], [id$="-max"]')).toBeNull();
    expect(screen.queryByRole('button', { name: /Reset to defaults/ })).not.toBeInTheDocument();
    const zone = screen.getByTestId('pace-zone-ef');
    expect(within(zone).queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('never sends pace_zones in the save payload', async () => {
    respond({
      campus_pace_zones: CAMPUS_ZONES,
      pace_zones_source: 'campus',
      pace_zones: { ef: { min: '5:45', max: '7:30' } },
    });
    render(<PreferencesPage />);

    const profile = await screen.findByLabelText('Your athlete profile');
    fireEvent.change(profile, { target: { value: 'Runner, sub-1h30 half' } });
    fireEvent.click(screen.getByRole('button', { name: /Save preferences/ }));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    const [path, body] = postMock.mock.calls[0];
    expect(path).toBe('/preferences');
    expect(body).toMatchObject({ user_id: 'u1', athlete_profile: 'Runner, sub-1h30 half' });
    expect(body).not.toHaveProperty('pace_zones');
    expect(body).not.toHaveProperty('campus_pace_zones');
  });
});
