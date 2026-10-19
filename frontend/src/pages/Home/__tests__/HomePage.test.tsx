import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { HomePage } from '../HomePage';
import { ApiError } from '@/api/client';
import type { HealthSeriesPoint, HomeSummary } from '@/types/home';

const getHomeSummaryMock = vi.hoisted(() => vi.fn<() => Promise<HomeSummary>>());
const downloadWorkoutMock = vi.hoisted(() => vi.fn<(b64: string, filename: string) => void>());

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return {
    ...actual,
    getHomeSummary: () => getHomeSummaryMock(),
  };
});

vi.mock('@/lib/downloadWorkout', () => ({
  downloadWorkout: (b64: string, filename: string) => downloadWorkoutMock(b64, filename),
}));

// ResizeObserver is used by recharts' ResponsiveContainer; jsdom lacks it.
beforeEach(() => {
  getHomeSummaryMock.mockReset();
  downloadWorkoutMock.mockReset();
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

/** `days` consecutive daily points from `start`, built by `make(i)`. */
function dailySeries(start: string, days: number, make: (i: number) => Partial<HealthSeriesPoint>): HealthSeriesPoint[] {
  const t0 = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: days }, (_, i) => ({
    date: new Date(t0 + i * 86_400_000).toISOString().slice(0, 10),
    resting_hr: 50,
    hrv: 60,
    hrv_kind: 'sdnn',
    sleep_s: 27000,
    ctl: 20,
    atl: 20,
    form: 0,
    ...make(i),
  }));
}

/** Daily loads of a training week with single rest days. */
function trainingLoads(days: number): number[] {
  const week = [55, 0, 70, 45, 0, 90, 40];
  return Array.from({ length: days }, (_, i) => week[i % week.length]);
}

/** ATL per day as intervals.icu computes it (EWMA, k = e^(-1/7)), rounded to 0.1. */
function atlFromLoads(loads: number[], atl0: number): number[] {
  const k = Math.exp(-1 / 7);
  let atl = atl0;
  return loads.map((load) => {
    atl = k * atl + (1 - k) * load;
    return Math.round(atl * 10) / 10;
  });
}

function fullFixture(): HomeSummary {
  return {
    generated_at: '2026-10-17T08:00:00Z',
    modules: { intervals_icu: true, campus_coach: true },
    brief: {
      date: '2026-10-17',
      built_at: '2026-10-17T05:30:00Z',
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
      { order: 4, title: 'Course 10 km', training_type: 'low-priority-race', status: 'todo', duration_min: 50 },
    ],
    next_session: {
      order: 3,
      title: 'Allure 21km',
      training_type: 'Intensity',
      duration_min: 64,
      session_id: 'session-test-1',
      coach_advice: 'Reste **bien relâché** sur les blocs. Regarde https://example.com/video-gammes.',
      description: null,
      workout_b64: 'AAEC',
      filename: 'allure-21km.workout',
    },
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
      { date: '2026-10-11', activity_id: '123', raw_pace_s: 335, adjusted_pace_s: 326, heat_cost_s: 0, wind_cost_s: 4, elevation_cost_s: 3 },
      { date: '2026-10-16', activity_id: '124', raw_pace_s: 334, adjusted_pace_s: 328, heat_cost_s: 0, wind_cost_s: 4, elevation_cost_s: 2 },
    ],
  };
}

describe('HomePage', () => {
  it('shows a loading status while the request is pending', () => {
    getHomeSummaryMock.mockReturnValue(new Promise(() => {}));
    renderHome();
    expect(screen.getByRole('status')).toHaveTextContent('Loading home');
  });

  it('renders the hero with verdict, session, weather chips and signal words', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    const hero = await screen.findByRole('region', { name: 'This morning' });
    expect(within(hero).getByText('Green light')).toBeInTheDocument();
    expect(within(hero).getByText('Normal recovery: do your session as planned.')).toBeInTheDocument();
    expect(within(hero).getByText("Today's session")).toBeInTheDocument();
    expect(within(hero).getByText('Allure 21km')).toBeInTheDocument();
    expect(within(hero).getByText('64 min')).toBeInTheDocument();
    // Weather chips: dry slot in words, rain with its unit.
    expect(within(hero).getByText('07:00')).toBeInTheDocument();
    expect(within(hero).getByText('6 °C · wind 20 km/h · dry')).toBeInTheDocument();
    expect(within(hero).getByText('11 °C · wind 12 km/h · rain 0.4 mm')).toBeInTheDocument();
    // Signals: dot + word, never colour alone, and no raw value in the hero.
    const signals = within(hero).getByRole('list', { name: 'Signals' });
    expect(within(signals).getByText('Watch')).toBeInTheDocument();
    expect(within(signals).getByText('Normal')).toBeInTheDocument();
    expect(within(hero).queryByText(/baseline|52\.1/)).not.toBeInTheDocument();
    // Missing signal translated, timestamp on the Paris clock (05:30Z = 07:30).
    expect(within(hero).getByText('Missing signals: Sleep')).toBeInTheDocument();
    expect(within(hero).getByText('Updated at 07:30')).toBeInTheDocument();
    expect(within(hero).getByText('Weather data by Open-Meteo.com (CC BY 4.0)')).toBeInTheDocument();
  });

  it('renders the coach word through CoachText: bold, link labels, no HTML injection', async () => {
    const fx = fullFixture();
    fx.next_session!.coach_advice =
      'Reste **bien relâché**. <img src=x onerror="alert(1)"> Vois https://www.youtube.com/watch?v=gammes1 et https://example.com/fiche.';
    getHomeSummaryMock.mockResolvedValue(fx);
    const { container } = renderHome();

    const advice = await screen.findByTestId('home-coach-advice');
    // The shared renderer, the same as on the Plan page.
    expect(within(advice).getByTestId('coach-text')).toBeInTheDocument();
    expect(within(advice).getByText('bien relâché').tagName).toBe('STRONG');
    // Same labels as Plan: a video host is "the video", any other URL "the link".
    expect(within(advice).getByRole('link', { name: 'the link' })).toHaveAttribute('href', 'https://example.com/fiche');
    const link = within(advice).getByRole('link', { name: 'the video' });
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=gammes1');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    // The markup stays text: no <img> element is created.
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(advice).toHaveTextContent('<img src=x onerror="alert(1)">');
  });

  it('downloads the Watch workout synchronously and links to the plan', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    const hero = await screen.findByRole('region', { name: 'This morning' });
    fireEvent.click(within(hero).getByRole('button', { name: 'Add to Watch' }));
    expect(downloadWorkoutMock).toHaveBeenCalledWith('AAEC', 'allure-21km.workout');
    expect(within(hero).getByRole('link', { name: 'See the plan' })).toHaveAttribute('href', '/plan');
  });

  it('hides the Watch button without workout_b64 but keeps the plan link', async () => {
    const fx = fullFixture();
    fx.next_session!.workout_b64 = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const hero = await screen.findByRole('region', { name: 'This morning' });
    expect(within(hero).queryByRole('button', { name: 'Add to Watch' })).not.toBeInTheDocument();
    expect(within(hero).getByRole('link', { name: 'See the plan' })).toBeInTheDocument();
  });

  it('shows an error when the Watch file cannot be built', async () => {
    downloadWorkoutMock.mockImplementation(() => {
      throw new Error('bad base64');
    });
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const hero = await screen.findByRole('region', { name: 'This morning' });
    fireEvent.click(within(hero).getByRole('button', { name: 'Add to Watch' }));
    expect(within(hero).getByText('Could not prepare the Watch file.')).toBeInTheDocument();
  });

  it('maps an "amber" light to the orange verdict', async () => {
    const fx = fullFixture();
    fx.brief!.light = 'amber';
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    expect(await screen.findByText('Amber light')).toBeInTheDocument();
    expect(screen.getByText('Mixed signals: keep the session, but ease off if you feel tired.')).toBeInTheDocument();
  });

  it('renders the race card with pace, gap and range, and drops the half from predictions', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    const race = await screen.findByRole('region', { name: 'Semi-marathon' });
    expect(within(race).getByText('29 days left')).toBeInTheDocument();
    expect(within(race).getByText('1:35:59')).toBeInTheDocument();
    expect(within(race).getByText('4:33/km')).toBeInTheDocument();
    expect(within(race).getByText('1:37:37')).toBeInTheDocument();
    expect(within(race).getByTestId('home-race-gap')).toHaveTextContent('+1:38 vs target');
    expect(within(race).getByRole('img', { name: /Predicted range 1:35:14 – 1:40:01/ })).toBeInTheDocument();

    const pred = screen.getByRole('region', { name: /Predictions/ });
    expect(within(pred).getByText('20:28')).toBeInTheDocument(); // 5 km
    expect(within(pred).getByText('Marathon')).toBeInTheDocument();
    expect(within(pred).queryByText('Half')).not.toBeInTheDocument();
    expect(within(pred).getByText('Half-marathon trend')).toBeInTheDocument();
    expect(within(pred).getByText('Campus only keeps a few weeks of history.')).toBeInTheDocument();
  });

  it('merges plan and sessions into one week card with words, not codes', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    const week = await screen.findByRole('region', { name: /This week/ });
    expect(within(week).getByText('Week 11/15')).toBeInTheDocument();
    expect(within(week).getByText('Strength block')).toBeInTheDocument();
    expect(within(week).queryByText('Force_A21')).not.toBeInTheDocument();
    expect(within(week).getByText('13.2 / 39.2 km')).toBeInTheDocument();
    // The contradicting volume range is gone: one km target only.
    expect(within(week).queryByText(/26/)).not.toBeInTheDocument();
    expect(within(week).getByTestId('home-week-remaining')).toHaveTextContent('2 sessions left');

    const sessions = within(week).getAllByTestId('home-week-session');
    expect(sessions).toHaveLength(4);
    // No order number is rendered in a row.
    expect(sessions[0]).not.toHaveTextContent(/^1/);
    const next = sessions.find((el) => el.dataset.next === 'true');
    expect(within(next!).getByText('Allure 21km')).toBeInTheDocument();
    expect(within(next!).getByText('Next')).toBeInTheDocument();
    // The tune-up race is named as such, with a single badge.
    expect(within(sessions[3]).getByText('Tune-up race')).toBeInTheDocument();
    expect(within(sessions[0]).getByText('Done')).toBeInTheDocument();
  });

  it('links the week card footer to the full activities list', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const week = await screen.findByRole('region', { name: /This week/ });
    expect(within(week).getByRole('link', { name: 'All activities' })).toHaveAttribute('href', '/activities');
  });

  it('hides unknown cycle codes rather than showing them', async () => {
    const fx = fullFixture();
    fx.plan!.cycle_theme = 'XQ_17';
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const week = await screen.findByRole('region', { name: /This week/ });
    expect(within(week).queryByText('XQ_17')).not.toBeInTheDocument();
    expect(within(week).queryByText('Cycle')).not.toBeInTheDocument();
  });

  it('shows the real km without a bar when the expected km is null', async () => {
    const fx = fullFixture();
    fx.plan!.week_km_expected = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const week = await screen.findByRole('region', { name: /This week/ });
    expect(within(week).getByText("This week's volume").parentElement).toHaveTextContent('13.2 km');
    expect(within(week).queryByRole('progressbar', { name: /km run/ })).not.toBeInTheDocument();
  });

  it('shows recovery values with their usual value and coloured difference', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();

    const rec = await screen.findByRole('region', { name: /Recovery/ });
    expect(within(rec).getByTestId('home-recovery-hrv')).toHaveTextContent('48 ms');
    expect(within(rec).getByTestId('home-recovery-hrv')).toHaveTextContent('usual 52 ms');
    expect(within(rec).getByTestId('home-diff-hrv')).toHaveTextContent('−4.1 ms');
    expect(within(rec).getByTestId('home-diff-hrv')).toHaveAttribute('data-tone', 'bad');
    // Resting HR going down is good news.
    expect(within(rec).getByTestId('home-recovery-resting_hr')).toHaveTextContent('45 bpm');
    expect(within(rec).getByTestId('home-diff-resting_hr')).toHaveAttribute('data-tone', 'good');
    // Sleep as a duration, never seconds.
    expect(within(rec).getByTestId('home-recovery-sleep_s')).toHaveTextContent('7 h 30');
    expect(within(rec).getByTestId('home-recovery-sleep_s')).toHaveTextContent('usual 7 h 48');
    expect(within(rec).getByTestId('home-diff-sleep_s')).toHaveTextContent('−18 min');
    expect(rec).not.toHaveTextContent('27000');
    // Freshness (TSB), renamed, with a zone in words.
    expect(within(rec).getByTestId('home-recovery-form')).toHaveTextContent('Freshness');
    expect(within(rec).getByTestId('home-recovery-form')).toHaveTextContent('−17.8');
    expect(within(rec).getByTestId('home-recovery-form')).toHaveTextContent('normal training fatigue');
    // The window lives in a tooltip (and for screen readers).
    expect(within(rec).getAllByTitle('Your 60-day average')).toHaveLength(2); // HRV + resting HR
    expect(within(rec).getByTitle('Your average over the last 7 nights')).toBeInTheDocument();
  });

  it('switches the recovery chart between metrics', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const rec = await screen.findByRole('region', { name: /Recovery/ });
    const picker = within(rec).getByRole('group', { name: 'Metric shown' });
    const hrv = within(picker).getByRole('button', { name: 'HRV' });
    const sleep = within(picker).getByRole('button', { name: 'Sleep' });
    expect(hrv).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(sleep);
    expect(sleep).toHaveAttribute('aria-pressed', 'true');
    expect(within(rec).getByRole('img', { name: /Sleep over 90 days: 2 measurements, latest 7\sh\s30/ })).toBeInTheDocument();
  });

  it('keeps load details collapsed until asked, with stale badges inside', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const toggle = await screen.findByRole('button', { name: 'Load and details' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const ctl = screen.getByTestId('home-load-ctl');
    expect(ctl).not.toBeVisible();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(ctl).toBeVisible();
    expect(ctl).toHaveTextContent('10.5');
    expect(screen.getByTestId('home-load-vo2max')).toHaveTextContent('56.3');
    expect(screen.getByTestId('home-load-weight')).toHaveTextContent('92.0 kg');
    // vo2max and weight are stale; CTL is not.
    expect(screen.getAllByText('stale')).toHaveLength(2);
    expect(within(ctl).queryByText('stale')).not.toBeInTheDocument();
    // No data-trust warning on a healthy series.
    expect(screen.queryByTestId('home-load-gap-warning')).not.toBeInTheDocument();
  });

  it('warns, conditionally, when no load was recorded for weeks (realistic ATL decay)', async () => {
    const fx = fullFixture();
    // EWMA like intervals.icu (k = e^(-1/7)) from ATL 35: training through 31 Aug,
    // nothing recorded 1 Sep..7 Oct, training again from 8 Oct.
    const atl = atlFromLoads([...trainingLoads(31), ...Array<number>(37).fill(0), ...trainingLoads(10)], 35);
    fx.health_series = dailySeries('2026-08-01', atl.length, (i) => ({ atl: atl[i] }));
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const warning = await screen.findByTestId('home-load-gap-warning');
    expect(warning).toHaveTextContent(
      'No load recorded from 1 Sept to 7 Oct: if you ran, Intervals.icu did not receive your runs, and fitness and freshness are then underestimated.'
    );
    // Visible without expanding the card.
    expect(warning).toBeVisible();
    // Today's freshness is flagged instead of being read as a zone.
    const form = screen.getByTestId('home-recovery-form');
    expect(form).toHaveTextContent('underestimated, see Load');
    expect(form).not.toHaveTextContent('normal training fatigue');
  });

  it('drops the warning once the gap no longer weighs on the latest CTL (42 days)', async () => {
    const fx = fullFixture();
    // Same outage (1 Jul..6 Aug), then 42 days of training: it ended too long ago.
    const atl = atlFromLoads([...trainingLoads(14), ...Array<number>(37).fill(0), ...trainingLoads(42)], 35);
    fx.health_series = dailySeries('2026-06-17', atl.length, (i) => ({ atl: atl[i] }));
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByTestId('home-recovery-form');
    expect(screen.queryByTestId('home-load-gap-warning')).not.toBeInTheDocument();
    expect(screen.getByTestId('home-recovery-form')).not.toHaveTextContent('underestimated, see Load');
  });

  it('keeps a still-relevant gap when a newer sleep-only row has no load', async () => {
    const fx = fullFixture();
    // Outage 1 Sep..7 Oct, training to 15 Nov (latest load: 39 days after the gap,
    // inside the 42-day window), then sleep-only rows to 30 Nov (54 days after).
    const atl = atlFromLoads([...trainingLoads(31), ...Array<number>(37).fill(0), ...trainingLoads(39)], 35);
    const loadRows = dailySeries('2026-08-01', atl.length, (i) => ({ atl: atl[i] }));
    const sleepOnly = dailySeries('2026-11-16', 15, () => ({ atl: null, ctl: null, form: null }));
    fx.health_series = [...loadRows, ...sleepOnly];
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    expect(await screen.findByTestId('home-load-gap-warning')).toHaveTextContent('No load recorded from 1 Sept to 7 Oct:');
  });

  it('does not revive a stale gap because of a sleep-only tail', async () => {
    const fx = fullFixture();
    // Outage 1 Sep..7 Oct, training to 19 Nov (43 days after: stale), then sleep-only rows.
    const atl = atlFromLoads([...trainingLoads(31), ...Array<number>(37).fill(0), ...trainingLoads(43)], 35);
    const loadRows = dailySeries('2026-08-01', atl.length, (i) => ({ atl: atl[i] }));
    const sleepOnly = dailySeries('2026-11-20', 5, () => ({ atl: null, ctl: null, form: null }));
    fx.health_series = [...loadRows, ...sleepOnly];
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByTestId('home-recovery-form');
    expect(screen.queryByTestId('home-load-gap-warning')).not.toBeInTheDocument();
  });

  it('words a genuine 3-week break conditionally, not as an ingestion failure', async () => {
    const fx = fullFixture();
    const atl = atlFromLoads([...trainingLoads(31), ...Array<number>(21).fill(0), ...trainingLoads(10)], 35);
    fx.health_series = dailySeries('2026-08-01', atl.length, (i) => ({ atl: atl[i] }));
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const warning = await screen.findByTestId('home-load-gap-warning');
    expect(warning).toHaveTextContent('No load recorded from 1 Sept to 21 Sept: if you ran,');
  });

  it('says "Race day" at 0 and uses the singular at 1', async () => {
    const fx = fullFixture();
    fx.race!.days_left = 0;
    getHomeSummaryMock.mockResolvedValue(fx);
    const { unmount } = renderHome();
    const race = await screen.findByRole('region', { name: 'Semi-marathon' });
    expect(within(race).getByText('Race day')).toBeInTheDocument();
    unmount();

    const fx1 = fullFixture();
    fx1.race!.days_left = 1;
    getHomeSummaryMock.mockResolvedValue(fx1);
    renderHome();
    const race1 = await screen.findByRole('region', { name: 'Semi-marathon' });
    expect(within(race1).getByText('1 day left')).toBeInTheDocument();
  });

  it('draws the target as a ring and the prediction as a filled dot, in the bar and the legend', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const race = await screen.findByRole('region', { name: 'Semi-marathon' });
    for (const id of ['home-race-marker-target', 'home-race-legend-target']) {
      const el = within(race).getByTestId(id);
      expect(el.className).toMatch(/border-success-text/);
      expect(el.className).toMatch(/bg-surface/);
    }
    for (const id of ['home-race-marker-predicted', 'home-race-legend-predicted']) {
      const el = within(race).getByTestId(id);
      expect(el.className).toMatch(/bg-info/);
      expect(el.className).not.toMatch(/border-\[?\d|border-2|border-\[3px\]/);
    }
  });

  it('renders the Enduraw card with a summary and the pace note', async () => {
    getHomeSummaryMock.mockResolvedValue(fullFixture());
    renderHome();
    const endu = await screen.findByRole('region', { name: /Enduraw/ });
    expect(within(endu).getByText('2 runs')).toBeInTheDocument();
    expect(within(endu).getByTestId('home-enduraw-summary')).toHaveTextContent(
      'With wind and elevation removed, your 16 Oct pace is 5:28/km instead of 5:34/km.'
    );
    // The Y axis is reversed (faster is up): the note must say so, not "lower is faster".
    expect(within(endu).getByText('Pace in min/km, reversed axis: higher is faster.')).toBeInTheDocument();
  });

  it('hides the race card when the race is inactive', async () => {
    const fx = fullFixture();
    fx.race!.active = false;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('region', { name: 'This morning' });
    expect(screen.queryByRole('region', { name: 'Semi-marathon' })).not.toBeInTheDocument();
    expect(screen.queryByText('29 days left')).not.toBeInTheDocument();
    // Without a race card the half goes back to the predictions.
    expect(within(screen.getByRole('region', { name: /Predictions/ })).getByText('Half')).toBeInTheDocument();
  });

  it('hides the race card when days_left is negative (race passed)', async () => {
    const fx = fullFixture();
    fx.race!.days_left = -3;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('region', { name: 'This morning' });
    expect(screen.queryByRole('region', { name: 'Semi-marathon' })).not.toBeInTheDocument();
  });

  it('never shows the brief\'s frozen session when the live next session is null', async () => {
    const fx = fullFixture();
    // The brief was built at 07:30 naming "Allure 21km"; the athlete has done it since.
    fx.next_session = null;
    expect(fx.brief!.next_session?.title).toBe('Allure 21km');
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();

    const hero = await screen.findByRole('region', { name: 'This morning' });
    // The morning verdict and weather stay; nothing about a session.
    expect(within(hero).getByText('Green light')).toBeInTheDocument();
    expect(within(hero).getByText('07:00')).toBeInTheDocument();
    expect(within(hero).queryByText("Today's session")).not.toBeInTheDocument();
    expect(within(hero).queryByText('Allure 21km')).not.toBeInTheDocument();
    expect(within(hero).queryByText('64 min')).not.toBeInTheDocument();
    expect(within(hero).queryByRole('button', { name: 'Add to Watch' })).not.toBeInTheDocument();
    expect(within(hero).queryByRole('link', { name: /plan/i })).not.toBeInTheDocument();
    expect(within(hero).queryByTestId('home-coach-advice')).not.toBeInTheDocument();
  });

  it('hides the hero, enduraw and race when they are null', async () => {
    const fx = fullFixture();
    fx.brief = null;
    fx.next_session = null;
    fx.race = null;
    fx.enduraw_trend = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    // The week card still renders, proving the page loaded.
    await screen.findByRole('region', { name: /This week/ });
    expect(screen.queryByRole('region', { name: 'This morning' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Enduraw/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Semi-marathon' })).not.toBeInTheDocument();
  });

  it('tolerates null fields inside a health metric', async () => {
    const fx = fullFixture();
    fx.health!.hrv = { value: null, kind: 'sdnn', as_of: null, stale: false };
    fx.health!.weight = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const rec = await screen.findByRole('region', { name: /Recovery/ });
    expect(within(rec).getByTestId('home-recovery-hrv')).toHaveTextContent('N/A');
    expect(screen.queryByTestId('home-load-weight')).not.toBeInTheDocument();
  });

  it('shows empty states when both modules are off', async () => {
    const fx = fullFixture();
    fx.modules = { intervals_icu: false, campus_coach: false };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByText('Campus Coach not connected');
    expect(screen.getByText('intervals.icu not connected')).toBeInTheDocument();
    // Campus- and intervals-gated cards are hidden.
    expect(screen.queryByRole('region', { name: /This week/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Recovery/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load and details' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Predictions/ })).not.toBeInTheDocument();
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
    expect(await screen.findByRole('region', { name: /This week/ })).toBeInTheDocument();
    expect(getHomeSummaryMock).toHaveBeenCalledTimes(2);
  });

  it('shows "no prediction this week" when predictions is null', async () => {
    const fx = fullFixture();
    fx.predictions = null;
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const pred = await screen.findByRole('region', { name: /Predictions/ });
    expect(within(pred).getByText('No prediction this week')).toBeInTheDocument();
  });

  it('shows "no prediction this week" when predictions items are empty', async () => {
    const fx = fullFixture();
    fx.predictions = { week: '2026-W42', items: [] };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    const pred = await screen.findByRole('region', { name: /Predictions/ });
    expect(within(pred).getByText('No prediction this week')).toBeInTheDocument();
  });

  it('hides the health cards when only sleep_score (not rendered) has a value', async () => {
    const fx = fullFixture();
    fx.health = {
      resting_hr: null, hrv: null, sleep_s: null, sleep_score: { value: 82, as_of: '2026-10-17', stale: false },
      ctl: null, atl: null, form: null, vo2max: null, weight: null,
    };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('region', { name: /This week/ });
    expect(screen.queryByRole('region', { name: /Recovery/ })).not.toBeInTheDocument();
  });

  it('hides the health cards when intervals is on but there are no values', async () => {
    const fx = fullFixture();
    fx.health = {
      resting_hr: null, hrv: null, sleep_s: null, sleep_score: null,
      ctl: null, atl: null, form: null, vo2max: null, weight: null,
    };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHome();
    await screen.findByRole('region', { name: /This week/ });
    expect(screen.queryByRole('region', { name: /Recovery/ })).not.toBeInTheDocument();
    // The intervals empty-state is NOT shown either (the module is on).
    expect(screen.queryByText('intervals.icu not connected')).not.toBeInTheDocument();
  });
});
