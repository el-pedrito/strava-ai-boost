import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { HomePage, filterHrvByLatestKind } from '../HomePage';
import { ApiError } from '@/api/client';
import type { HomeSummary } from '@/types/home';

const getHomeSummaryMock = vi.hoisted(() => vi.fn<() => Promise<HomeSummary>>());

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return {
    ...actual,
    getHomeSummary: () => getHomeSummaryMock(),
  };
});

// ResizeObserver is used by recharts' ResponsiveContainer; jsdom lacks it.
beforeEach(() => {
  getHomeSummaryMock.mockReset();
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() {
        return false;
      },
    })) as unknown as typeof window.matchMedia;
  }
});

function renderHome() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>
  );
}

function fullFixture(): HomeSummary {
  return {
    generated_at: '2026-10-17T08:00:00Z',
    modules: { intervals_icu: true, campus_coach: true },
    brief: {
      date: '2026-10-17',
      built_at: '2026-10-17T07:30:00Z',
      light: 'green',
      signals: [
        { key: 'hrv', value: 48.0, baseline: 52.1, status: 'warn', as_of: '2026-10-16' },
        { key: 'resting_hr', value: 45, baseline: 47.2, status: 'ok', as_of: '2026-10-16' },
      ],
      missing: ['sleep'],
      next_session: { title: 'Allure 21km', training_type: 'Intensity', duration_min: 64 },
      weather: [
        { slot: '07:00', temp_c: 6.0, wind_kmh: 20.0, precip_mm: 0.0 },
        { slot: '18:00', temp_c: 11.0, wind_kmh: 12.0, precip_mm: 0.4 },
      ],
      weather_attribution: 'Weather data by Open-Meteo.com (CC BY 4.0)',
    },
    race: {
      active: true,
      name: 'SEMI-MARATHON',
      type: 'half-marathon',
      date: '2026-11-15',
      days_left: 29,
      target_time_s: 5759,
      target_pace_s: 273,
      predicted_time_s: 5857,
      predicted_range_s: [5714, 6001],
      prediction_week: '2026-W42',
    },
    plan: {
      week_index: 11,
      weeks_total: 15,
      cycle_theme: 'Force_A21',
      trainings_done: 48,
      trainings_total: 81,
      week_km_expected: 39.2,
      week_km_real: 13.2,
      weekly_volume_low: 26,
      weekly_volume_high: 38,
      sessions_per_week: 4,
    },
    week_sessions: [
      { order: 1, title: 'Footing EF', training_type: 'Endurance', status: 'done', duration_min: 45 },
      { order: 2, title: 'PPG', training_type: 'Strength', status: 'done', duration_min: 30 },
      { order: 3, title: 'Allure 21km', training_type: 'Intensity', status: 'todo', duration_min: 64 },
      { order: 4, title: 'Sortie longue', training_type: 'Endurance', status: 'todo', duration_min: 90 },
    ],
    next_session: { order: 3, title: 'Allure 21km', training_type: 'Intensity', duration_min: 64 },
    health: {
      resting_hr: { value: 45, as_of: '2026-10-16', stale: false, baseline_60d: 47.2, delta: -2.2 },
      hrv: { value: 48.0, kind: 'sdnn', as_of: '2026-10-16', stale: false, baseline_60d: 52.1, delta: -4.1 },
      sleep_s: { value: 27000, as_of: '2026-10-17', stale: false, baseline_7d: 28100, delta: -1100 },
      sleep_score: { value: 82, as_of: '2026-10-17', stale: false },
      ctl: { value: 10.5, as_of: '2026-10-17', stale: false },
      atl: { value: 28.3, as_of: '2026-10-17', stale: false },
      form: { value: -17.8, as_of: '2026-10-17', stale: false },
      vo2max: { value: 56.3, as_of: '2026-10-15', stale: true },
      weight: { value: 92.0, as_of: '2026-10-10', stale: true },
    },
    health_series: [
      { date: '2026-07-20', resting_hr: 46, hrv: 50.0, hrv_kind: 'sdnn', sleep_s: 27500, ctl: 18.0, atl: 20.1, form: -2.1 },
      { date: '2026-10-15', resting_hr: 45, hrv: 48.0, hrv_kind: 'sdnn', sleep_s: 27000, ctl: 10.5, atl: 28.3, form: -17.8 },
    ],
    predictions: {
      week: '2026-W42',
      items: [
        { distance: '5km', time_s: 1228, range_s: [1196, 1261], pace_s: 245.7 },
        { distance: '10km', time_s: 2560, range_s: [2500, 2620], pace_s: 256.0 },
        { distance: 'half-marathon', time_s: 5857, range_s: [5714, 6001], pace_s: 277.5 },
        { distance: 'marathon', time_s: 12600, range_s: [12300, 12900], pace_s: 298.5 },
      ],
    },
    predictions_history: [
      { week: '2026-W37', half_marathon_time_s: 5950 },
      { week: '2026-W42', half_marathon_time_s: 5857 },
    ],
    enduraw_trend: [
      { date: '2026-10-11', activity_id: '123', raw_pace_s: 280, adjusted_pace_s: 271, heat_cost_s: 0, wind_cost_s: 4, elevation_cost_s: 3 },
      { date: '2026-10-14', activity_id: '124', raw_pace_s: 300, adjusted_pace_s: 288, heat_cost_s: 1, wind_cost_s: 6, elevation_cost_s: 2 },
    ],
  };
}

describe('HomePage', () => {
  it('shows a loading status while the request is pending', () => {
    getHomeSummaryMock.mockReturnValue(new Promise(() => {}));
    renderHome();
    expect(screen.getByRole('status')).toHaveTextContent('Loading home');
  });

  it('renders every block from a full fixture', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    // Brief
    expect(await screen.findByRole('heading', { name: "Today's brief" })).toBeInTheDocument();
    expect(screen.getByText('Green light')).toBeInTheDocument();
    expect(screen.getByText('Weather data by Open-Meteo.com (CC BY 4.0)')).toBeInTheDocument();
    expect(screen.getByText('07:00')).toBeInTheDocument();
    expect(screen.getByText('18:00')).toBeInTheDocument();
    expect(screen.getByText(/^Built at \d{2}:\d{2}$/)).toBeInTheDocument();
    expect(screen.getByText('Missing signals: sleep')).toBeInTheDocument();

    // Race: 1:35:59 target, predicted + range as estimate
    expect(screen.getByRole('heading', { name: 'SEMI-MARATHON' })).toBeInTheDocument();
    expect(screen.getByText('29 days left')).toBeInTheDocument();
    expect(screen.getByText('1:35:59')).toBeInTheDocument();
    expect(screen.getAllByText('1:37:37').length).toBeGreaterThanOrEqual(1);
    // Both the race card and the predictions block label their range an estimate.
    expect(screen.getAllByText(/estimate:/).length).toBeGreaterThanOrEqual(1);

    // Plan
    expect(screen.getByRole('heading', { name: 'Campus plan' })).toBeInTheDocument();
    expect(screen.getByText('Week 11/15')).toBeInTheDocument();
    expect(screen.getByText('13.2 / 39.2 km')).toBeInTheDocument();
    expect(screen.getByText('Target weekly volume: 26\u201338 km')).toBeInTheDocument();

    // This week: 4 sessions, next highlighted at order 3
    expect(screen.getByRole('heading', { name: 'This week' })).toBeInTheDocument();
    const sessions = screen.getAllByTestId('home-week-session');
    expect(sessions).toHaveLength(4);
    const next = sessions.find((el) => el.dataset.next === 'true');
    expect(next).toBeDefined();
    expect(within(next!).getByText('Allure 21km')).toBeInTheDocument();
    expect(within(next!).getByText('Next')).toBeInTheDocument();

    // Health
    expect(screen.getByRole('heading', { name: 'Health' })).toBeInTheDocument();
    expect(screen.getByText('45 bpm')).toBeInTheDocument();
    expect(screen.getByText('48 (SDNN)')).toBeInTheDocument(); // HRV with kind
    expect(screen.getByText('7:30')).toBeInTheDocument(); // sleep h:mm
    expect(screen.getByText('92.0 kg')).toBeInTheDocument();
    expect(screen.getByText('Last 90 days')).toBeInTheDocument();

    // Predictions
    expect(screen.getByRole('heading', { name: 'Predictions' })).toBeInTheDocument();
    expect(screen.getByText('20:28')).toBeInTheDocument(); // 5k = 1228 s
    expect(screen.getByText('Half-marathon trend')).toBeInTheDocument();
    expect(screen.getByText('Campus only keeps a few weeks of history.')).toBeInTheDocument();

    // Enduraw
    expect(screen.getByRole('heading', { name: 'Enduraw' })).toBeInTheDocument();
  });

  it('shows a stale badge on stale health metrics only', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    await screen.findByRole('heading', { name: 'Health' });

    // vo2max and weight are stale → 2 stale badges, resting HR (fresh) has none.
    const staleBadges = screen.getAllByText('stale');
    expect(staleBadges).toHaveLength(2);
  });

  it('hides the race card when the race is inactive', async () => {
    const fx = fullFixture();
    fx.race!.active = false;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: "Today's brief" });
    expect(screen.queryByRole('heading', { name: 'SEMI-MARATHON' })).not.toBeInTheDocument();
    expect(screen.queryByText('29 days left')).not.toBeInTheDocument();
  });

  it('hides the race card when days_left is negative (race passed)', async () => {
    const fx = fullFixture();
    fx.race!.days_left = -3;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: "Today's brief" });
    expect(screen.queryByRole('heading', { name: 'SEMI-MARATHON' })).not.toBeInTheDocument();
  });

  it('hides the brief, enduraw and race when they are null', async () => {
    const fx = fullFixture();
    fx.brief = null;
    fx.race = null;
    fx.enduraw_trend = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    // Plan still renders, proving the page loaded.
    await screen.findByRole('heading', { name: 'Campus plan' });
    expect(screen.queryByRole('heading', { name: "Today's brief" })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Enduraw' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'SEMI-MARATHON' })).not.toBeInTheDocument();
  });

  it('tolerates null fields inside a health metric', async () => {
    const fx = fullFixture();
    fx.health!.hrv = { value: null, kind: 'sdnn', as_of: null, stale: false };
    fx.health!.weight = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: 'Health' });
    // The HRV cell renders its N/A placeholder rather than crashing.
    expect(screen.getByText('Health')).toBeInTheDocument();
    expect(screen.getAllByText('Resting HR').length).toBeGreaterThanOrEqual(1);
  });

  it('shows empty states when both modules are off', async () => {
    const fx = fullFixture();
    fx.modules = { intervals_icu: false, campus_coach: false };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByText('Campus Coach not connected');
    expect(screen.getByText('intervals.icu not connected')).toBeInTheDocument();
    // Campus-gated blocks are hidden.
    expect(screen.queryByRole('heading', { name: 'Campus plan' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'This week' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Health' })).not.toBeInTheDocument();
  });

  it('shows a dedicated forbidden message on a 403', async () => {
    getHomeSummaryMock.mockRejectedValue(new ApiError('Forbidden', 403));
    renderHome();
    expect(
      await screen.findByText('Access denied: this data belongs to another account.')
    ).toBeInTheDocument();
    // No generic retry button on a 403.
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('shows a retry on a generic error and reloads on click', async () => {
    getHomeSummaryMock.mockRejectedValueOnce(new ApiError('boom', 500));
    renderHome();
    expect(await screen.findByText('Could not load the home dashboard.')).toBeInTheDocument();

    getHomeSummaryMock.mockResolvedValueOnce(fullFixture());
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: 'Campus plan' })).toBeInTheDocument();
    expect(getHomeSummaryMock).toHaveBeenCalledTimes(2);
  });

  it('shows "n/a" and hides the week bar when week km are null', async () => {
    const fx = fullFixture();
    fx.plan!.week_km_expected = null;
    fx.plan!.week_km_real = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    const { container } = renderHome();
    await screen.findByRole('heading', { name: 'Campus plan' });
    expect(screen.getByText('n/a')).toBeInTheDocument();
    // The progress bar track (role=presentation) is not rendered.
    expect(container.querySelector('[role="presentation"]')).toBeNull();
  });

  it('shows "no prediction this week" when predictions is null', async () => {
    const fx = fullFixture();
    fx.predictions = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: 'Predictions' });
    expect(screen.getByText('No prediction this week')).toBeInTheDocument();
  });

  it('shows "no prediction this week" when predictions items are empty', async () => {
    const fx = fullFixture();
    fx.predictions = { week: '2026-W42', items: [] };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: 'Predictions' });
    expect(screen.getByText('No prediction this week')).toBeInTheDocument();
  });

  it('hides the Health card when intervals is on but there are no values', async () => {
    const fx = fullFixture();
    // Every signal null -> the card is hidden even though the module is on.
    fx.health = {
      resting_hr: null, hrv: null, sleep_s: null, sleep_score: null,
      ctl: null, atl: null, form: null, vo2max: null, weight: null,
    };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('heading', { name: 'Campus plan' });
    expect(screen.queryByRole('heading', { name: 'Health' })).not.toBeInTheDocument();
    // The intervals empty-state is NOT shown either (the module is on).
    expect(screen.queryByText('intervals.icu not connected')).not.toBeInTheDocument();
  });

  it('filters the HRV series to the latest hrv_kind (pure helper)', () => {
    // Latest point is rmssd: the earlier sdnn value must be nulled on the line.
    const out = filterHrvByLatestKind([
      { hrv: 60.0, hrv_kind: 'sdnn' },
      { hrv: 42.0, hrv_kind: 'rmssd' },
    ]);
    expect(out[0].hrv).toBeNull();   // sdnn point dropped from the line
    expect(out[1].hrv).toBe(42.0);   // latest kind kept
  });

  it('keeps all HRV points when every kind matches the latest', () => {
    const out = filterHrvByLatestKind([
      { hrv: 50.0, hrv_kind: 'sdnn' },
      { hrv: 48.0, hrv_kind: 'sdnn' },
    ]);
    expect(out.map((p) => p.hrv)).toEqual([50.0, 48.0]);
  });

});
