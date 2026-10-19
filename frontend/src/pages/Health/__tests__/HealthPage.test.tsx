import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { HealthPage } from '../HealthPage';
import { HeroCard } from '../../Home/blocks/HeroCard';
import type { HealthSeriesPoint, HomeSummary } from '@/types/home';

const getHomeSummaryMock = vi.hoisted(() => vi.fn<() => Promise<HomeSummary>>());

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return { ...actual, getHomeSummary: () => getHomeSummaryMock() };
});

// The shared line charts are replaced by a probe exposing the exact rows they
// receive, so a gap can be checked as a null (not a zero) without SVG layout.
vi.mock('../../Home/blocks/charts', () => ({
  MetricLineChart: ({ data, metric }: { data: Array<Record<string, unknown>>; metric: string }) => (
    <div
      data-testid={`probe-${metric}`}
      data-rows={data.length}
      data-values={JSON.stringify(data.map((d) => d[metric] ?? null))}
    />
  ),
  LoadLineChart: ({ data, gaps }: { data: Array<Record<string, unknown>>; gaps: Array<{ start: string; end: string }> }) => (
    <div
      data-testid="probe-load"
      data-rows={data.length}
      data-atl={JSON.stringify(data.map((d) => d.atl ?? null))}
      data-shaded={gaps.map((g) => `${g.start}..${g.end}`).join(',')}
    />
  ),
}));

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

const DAY_MS = 86_400_000;
const iso = (t: number) => new Date(t).toISOString().slice(0, 10);

/** Invented 91-day series shaped like the real outage: no load from 12 Aug to 7 Oct. */
function realLikeSeries(): HealthSeriesPoint[] {
  const start = Date.parse('2026-07-21T00:00:00Z');
  const week = [55, 0, 70, 45, 0, 90, 40];
  const k = Math.exp(-1 / 7);
  let atl = 17;
  let ctl = 15;
  return Array.from({ length: 91 }, (_, i) => {
    const date = iso(start + i * DAY_MS);
    const outage = date >= '2026-08-12' && date <= '2026-10-07';
    const load = outage ? 0 : week[i % 7];
    atl = k * atl + (1 - k) * load;
    ctl = Math.exp(-1 / 42) * ctl + (1 - Math.exp(-1 / 42)) * load;
    const last = date === '2026-10-19';
    return {
      date,
      // 10 Oct: no HRV measured that night; 18-19 Oct: no wellness sync yet.
      hrv: date === '2026-10-10' || date >= '2026-10-18' ? null : 62 + (i % 5),
      hrv_kind: date === '2026-10-10' || date >= '2026-10-18' ? null : 'sdnn',
      resting_hr: date >= '2026-10-18' ? null : 50 + (i % 3),
      sleep_s: date >= '2026-10-18' ? null : 27000 + (i % 4) * 600,
      atl: Math.round(atl * 10) / 10,
      ctl: Math.round(ctl * 10) / 10,
      form: last ? -14.3 : Math.round((ctl - atl) * 10) / 10,
    };
  });
}

function fixture(overrides: Partial<HomeSummary> = {}): HomeSummary {
  return {
    generated_at: '2026-10-19T06:00:00Z',
    modules: { intervals_icu: true, campus_coach: false },
    // Invented brief shaped like a real morning: the wellness sync is two days
    // old, so the brief skips HRV, resting HR and sleep as too old ("missing"
    // with a value) and only rates freshness, which turns the light red.
    brief: {
      date: '2026-10-19',
      built_at: '2026-10-19T05:30:00Z',
      light: 'red',
      signals: [
        { key: 'hrv', value: 55, baseline: 64, status: 'missing', as_of: '2026-10-17' },
        { key: 'resting_hr', value: 49, baseline: 51, status: 'missing', as_of: '2026-10-17' },
        { key: 'sleep', value: 28800, baseline: 27600, status: 'missing', as_of: '2026-10-17' },
        { key: 'form', value: -26.4, baseline: -8.2, status: 'bad', as_of: '2026-10-19' },
      ],
      missing: ['hrv', 'resting_hr', 'sleep'],
      next_session: null,
      weather: null,
      weather_attribution: null,
    },
    race: null,
    plan: null,
    week_sessions: null,
    next_session: null,
    predictions: null,
    predictions_history: null,
    enduraw_trend: null,
    health: {
      hrv: { value: 55, as_of: '2026-10-17', stale: true, baseline_60d: 64, delta: -9, kind: 'sdnn' },
      resting_hr: { value: 49, as_of: '2026-10-17', stale: true, baseline_60d: 51, delta: -2 },
      sleep_s: { value: 28800, as_of: '2026-10-17', stale: true, baseline_7d: 27600, delta: 1200 },
      sleep_score: null,
      ctl: { value: 14.2, as_of: '2026-10-19', stale: false },
      atl: { value: 28.5, as_of: '2026-10-19', stale: false },
      form: { value: -26.4, as_of: '2026-10-19', stale: false },
      vo2max: { value: 55.4, as_of: '2026-10-17', stale: true },
      weight: null,
    },
    health_series: realLikeSeries(),
    ...overrides,
  };
}

function renderHealth() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <HealthPage />
      </MemoryRouter>
    </ThemeProvider>
  );
}

const values = (el: HTMLElement, attr: string) => JSON.parse(el.getAttribute(attr) ?? '[]') as Array<number | null>;

describe('HealthPage', () => {
  it('titles the page with the newest as_of date', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    expect(await screen.findByRole('heading', { level: 1, name: 'Health' })).toBeInTheDocument();
    expect(await screen.findByTestId('health-subtitle')).toHaveTextContent('Intervals.icu · data as of 19 Oct');
  });

  it('shows the brief verdict and each brief status, never a second set of thresholds', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    const verdict = await screen.findByTestId('health-verdict');
    expect(verdict).toHaveAttribute('data-light', 'red');
    expect(verdict).toHaveTextContent('Red light');
    expect(verdict).toHaveTextContent('Poor recovery: rest or keep it very easy today.');

    // 55 vs 64 ms is a 14 % drop, but the brief skipped it as too old: "stale", not a client verdict.
    const hrv = screen.getByTestId('health-ready-hrv');
    expect(hrv).toHaveAttribute('data-status', 'stale');
    expect(hrv).toHaveTextContent('stale');
    expect(hrv).toHaveTextContent('55 ms');
    expect(hrv).toHaveTextContent('usual 64 ms');
    expect(within(hrv).getByTestId('health-diff-hrv')).toBeInTheDocument();

    const rhr = screen.getByTestId('health-ready-resting_hr');
    expect(rhr).toHaveAttribute('data-status', 'stale');
    expect(rhr).toHaveTextContent('49 bpm');

    const sleep = screen.getByTestId('health-ready-sleep_s');
    expect(sleep).toHaveAttribute('data-status', 'stale');
    expect(sleep).toHaveTextContent('8 h 00');

    const form = screen.getByTestId('health-ready-form');
    expect(form).toHaveAttribute('data-status', 'bad');
    expect(form).toHaveTextContent('Alert');
    expect(form).toHaveTextContent('unreliable: load incomplete, see below');
    // −26,4 would be "normal training fatigue": computed on biased load, and it
    // contradicts the Alert dot, so no zone word at all.
    expect(within(form).queryByTestId('health-form-zone')).not.toBeInTheDocument();
    expect(form).not.toHaveTextContent('normal training fatigue');
  });

  it('shows the zone word when the load is complete and it agrees with the dot', async () => {
    const fx = fixture({
      health_series: realLikeSeries().map((p) => ({ ...p, atl: 30, ctl: 20 })),
    });
    fx.brief = { ...fx.brief!, signals: [{ key: 'form', value: -18, baseline: -8.2, status: 'warn', as_of: '2026-10-19' }] };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHealth();
    const form = await screen.findByTestId('health-ready-form');
    expect(form).toHaveTextContent('Watch');
    expect(within(form).getByTestId('health-form-zone')).toHaveTextContent('normal training fatigue');
    expect(form).not.toHaveTextContent('unreliable');
  });

  it('uses the Home words for fresh brief statuses', async () => {
    const fx = fixture();
    fx.brief = {
      ...fx.brief!,
      light: 'orange',
      signals: [
        { key: 'hrv', value: 55, baseline: 64, status: 'warn', as_of: '2026-10-19' },
        { key: 'resting_hr', value: 49, baseline: 51, status: 'ok', as_of: '2026-10-19' },
        { key: 'form', value: -12, baseline: -8.2, status: 'ok', as_of: '2026-10-19' },
      ],
    };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHealth();
    expect(await screen.findByTestId('health-verdict')).toHaveTextContent('Mixed signals');
    expect(screen.getByTestId('health-ready-hrv')).toHaveTextContent('Watch');
    expect(screen.getByTestId('health-ready-resting_hr')).toHaveTextContent('Normal');
    // Sleep is absent from the brief: "Unavailable", even though a value is known.
    const sleep = screen.getByTestId('health-ready-sleep_s');
    expect(sleep).toHaveAttribute('data-status', 'missing');
    expect(sleep).toHaveTextContent('Unavailable');
  });

  it('gives the same verdict and status words as the Home hero for one payload', async () => {
    const fx = fixture();
    getHomeSummaryMock.mockResolvedValue(fx);
    const { unmount } = renderHealth();
    await screen.findByTestId('health-verdict');
    const santeWords = ['hrv', 'resting_hr', 'sleep_s', 'form'].map(
      (k) => screen.getByTestId(`health-status-${k}`).textContent
    );
    const santeVerdict = screen.getByTestId('health-verdict').textContent;
    unmount();

    render(
      <MemoryRouter>
        <HeroCard brief={fx.brief} next={null} />
      </MemoryRouter>
    );
    const homeWords = within(screen.getByRole('list', { name: 'Signals' }))
      .getAllByRole('listitem')
      .map((li) => li.querySelector('span.font-semibold')?.textContent);
    expect(santeWords).toEqual(homeWords);
    expect(santeWords).toEqual(['stale', 'stale', 'stale', 'Alert']);
    expect(santeVerdict).toContain('Red light');
    expect(screen.getByText('Red light')).toBeInTheDocument();
    expect(screen.getByText('Poor recovery: rest or keep it very easy today.')).toBeInTheDocument();
  });

  it('reads every signal as unavailable and shows no verdict without a brief', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture({ brief: null }));
    renderHealth();
    const hrv = await screen.findByTestId('health-ready-hrv');
    expect(hrv).toHaveAttribute('data-status', 'missing');
    expect(hrv).toHaveTextContent('Unavailable');
    expect(screen.queryByTestId('health-verdict')).not.toBeInTheDocument();
  });

  it('words a stale value as "stale · on <date>" and a fresh one as "on <date>"', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    expect(await screen.findByTestId('health-asof-hrv')).toHaveTextContent(/^stale · on 17 Oct$/);
    expect(screen.getByTestId('health-asof-form')).toHaveTextContent(/^on 19 Oct$/);
  });

  it('filters every chart series with the 30 / 90-day toggle', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    const probe = await screen.findByTestId('probe-hrv');
    expect(probe).toHaveAttribute('data-rows', '90');
    expect(screen.getByTestId('probe-load')).toHaveAttribute('data-rows', '90');

    const toggle = screen.getByRole('group', { name: 'Chart period' });
    const btn30 = within(toggle).getByRole('button', { name: 'Last 30 days' });
    expect(btn30).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(btn30);
    expect(btn30).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('probe-hrv')).toHaveAttribute('data-rows', '30');
    expect(screen.getByTestId('probe-resting_hr')).toHaveAttribute('data-rows', '30');
    expect(screen.getByTestId('probe-sleep_s')).toHaveAttribute('data-rows', '30');
    expect(screen.getByTestId('probe-load')).toHaveAttribute('data-rows', '30');
    expect(screen.getByRole('heading', { name: 'Last 30 days' })).toBeInTheDocument();
  });

  it('keeps null days as gaps, never zeros, including days missing from the payload', async () => {
    const fx = fixture();
    // Drop 5 Oct from the payload entirely: the page must still give it a row.
    fx.health_series = fx.health_series!.filter((p) => p.date !== '2026-10-05');
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHealth();
    fireEvent.click(await screen.findByRole('button', { name: 'Last 30 days' }));
    const hrv = values(screen.getByTestId('probe-hrv'), 'data-values');
    expect(hrv).toHaveLength(30);
    // Window 20 Sep..19 Oct: 5 Oct is index 15, 10 Oct index 20, 18-19 Oct the tail.
    expect(hrv[15]).toBeNull();
    expect(hrv[20]).toBeNull();
    expect(hrv.slice(-2)).toEqual([null, null]);
    expect(hrv).not.toContain(0);
    expect(values(screen.getByTestId('probe-load'), 'data-atl')[15]).toBeNull();
    // The screen-reader summary counts measurements, not rows.
    expect(screen.getByTestId('health-chart-hrv')).toHaveAttribute('data-points', '26');
  });

  it('shades the load-gap period on both load charts under the warning', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    const load = await screen.findByTestId('health-chart-load');
    expect(screen.getByTestId('probe-load')).toHaveAttribute('data-shaded', '2026-08-12..2026-10-07');
    expect(load).toHaveAttribute('data-gaps', '2026-08-12..2026-10-07');
    expect(screen.getByTestId('health-chart-form')).toHaveAttribute('data-gaps', '2026-08-12..2026-10-07');
    expect(screen.getByTestId('home-load-gap-warning')).toHaveTextContent('No load recorded from 12 Aug to 7 Oct');
    expect(load).toHaveAttribute('aria-label', expect.stringContaining('Shaded area from 12 Aug to 7 Oct'));

    // On 30 days the shading is trimmed to the window, the wording keeps the true start.
    fireEvent.click(screen.getByRole('button', { name: 'Last 30 days' }));
    expect(screen.getByTestId('probe-load')).toHaveAttribute('data-shaded', '2026-09-20..2026-10-07');
    expect(screen.getByTestId('home-load-gap-warning')).toHaveTextContent('from 12 Aug to 7 Oct');
  });

  it('gives each chart a one-line summary for screen readers', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    const hrv = await screen.findByTestId('health-chart-hrv');
    expect(hrv).toHaveAttribute('role', 'img');
    expect(hrv.getAttribute('aria-label')).toMatch(/^HRV over 90 days: \d+ measurements, from .+ to .+, latest .+ on 17 Oct\.$/);
    expect(screen.getByTestId('health-chart-form').getAttribute('aria-label')).toMatch(/^Freshness \(TSB\) over 90 days:/);
  });

  it('shows the VO2max tile and hides the weight tile whose value is null', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture());
    renderHealth();
    const vo2 = await screen.findByTestId('health-body-vo2max');
    expect(vo2).toHaveTextContent('55.4');
    expect(vo2).toHaveTextContent('ml/kg/min');
    expect(screen.queryByTestId('health-body-weight')).not.toBeInTheDocument();
  });

  it('drops the body card when both tiles are null', async () => {
    const fx = fixture();
    fx.health = { ...fx.health!, vo2max: null };
    getHomeSummaryMock.mockResolvedValue(fx);
    renderHealth();
    await screen.findByTestId('health-ready-hrv');
    expect(screen.queryByRole('region', { name: 'VO2max and weight' })).not.toBeInTheDocument();
  });

  it('asks to connect Intervals.icu when the module is off', async () => {
    getHomeSummaryMock.mockResolvedValue(fixture({ modules: { intervals_icu: false, campus_coach: false } }));
    renderHealth();
    expect(await screen.findByText(/Intervals\.icu/, { selector: 'h2,h3,p' })).toBeInTheDocument();
    expect(screen.queryByTestId('health-ready-hrv')).not.toBeInTheDocument();
  });
});
