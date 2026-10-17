import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '@/theme/ThemeProvider';
import { CoachPage } from '../CoachPage';

// api.get is used for /coach/summary and /coach/recaps.
const getMock = vi.hoisted(() => vi.fn());

vi.mock('../../../api/client.ts', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>(
    '../../../api/client',
  );
  return {
    ...actual,
    api: {
      ...actual.api,
      get: (path: string) => getMock(path),
      post: () => Promise.resolve({}),
    },
  };
});

// CoachChat pulls streaming machinery we don't exercise here.
vi.mock('../CoachChat.tsx', () => ({ CoachChat: () => <div data-testid="coach-chat" /> }));

type AnySummary = Record<string, unknown>;

function emptyRunningTrends() {
  return {
    weekly_volume_km: [10, 12, 11, 13],
    sessions_per_week: [3, 3, 4, 3],
    avg_pace_per_week: ['5:00', '5:01', '4:59', '5:02'],
    interval_paces: [],
    ef_paces: [],
    ramp_rate: null,
    compliance: null,
    recovery: null,
    health_anomalies: [],
  };
}

function points(field: 'top_weight_kg' | 'volume_kg' | 'e1rm_kg', values: number[]) {
  return values.map((v, i) => {
    const p: Record<string, unknown> = {
      date: `2026-10-${(i + 1).toString().padStart(2, '0')}`,
      top_weight_kg: null,
      volume_kg: null,
      e1rm_kg: null,
    };
    p[field] = v;
    return p;
  });
}

function fullInsights() {
  const seg = (logged: number, campus = 0) => ({ logged, campus_plan: campus });
  const groups = () => ({
    pectoraux: seg(3), dos: seg(2), epaules: seg(1.5), biceps: seg(1), triceps: seg(1.5),
    quadriceps: seg(2), ischios: seg(1), fessiers: seg(1), mollets: seg(0), abdos: seg(1),
  });
  const weeks = Array.from({ length: 8 }, (_, i) => ({
    week: `2026-W${35 + i}`,
    partial: i === 7,
    groups: groups(),
    explosivite: seg(0),
    autre: seg(i === 7 ? 1 : 0),
  }));
  return {
    counting_rule: 'coach.strength.insights.countingRule',
    weeks,
    push_pull: [
      { week: '2026-W39', push: 3, pull: 2, ratio: 1.5 },
      { week: '2026-W40', push: 4, pull: 2, ratio: 2 },
      { week: '2026-W41', push: 3, pull: 0, ratio: null },
      { week: '2026-W42', push: 3, pull: 2, ratio: 1.5 },
    ],
    records: [
      {
        exercise: 'Squat', kind: 'loaded', last_date: '2026-10-13', notation_mixed: false,
        load_label: 'total_noted', top_weight_kg: 110, top_weight_date: '2026-10-13',
        e1rm_kg: 120, e1rm_date: '2026-10-13', best_volume_kg: 1500, best_volume_date: '2026-10-13',
        best_reps_bw: null, best_weighted_bw: null,
      },
      {
        exercise: 'Tractions', kind: 'bodyweight', last_date: '2026-10-10', notation_mixed: false,
        load_label: null, top_weight_kg: null, top_weight_date: null, e1rm_kg: null, e1rm_date: null,
        best_volume_kg: null, best_volume_date: null,
        best_reps_bw: { reps: 10, date: '2026-10-10' },
        best_weighted_bw: { reps: 6, added_weight_kg: 20, date: '2026-10-10' },
      },
    ],
    unmapped_exercises: [{ exercise: 'Flexion de genou', reason: 'to_confirm' }],
    mixed_exercises: [{ exercise: 'Développé machine', note_key: 'mixed_chest_shoulder_machine' }],
  };
}

function summaryWith(trendsExtra: AnySummary): AnySummary {
  return {
    schema_version: 1,
    athlete_profile: '',
    recent_feedback: [],
    current_week: { runs: 3, run_km: 30, other: 1, total: 4 },
    weekly_trends: [],
    volume_change_completed_weeks_pct: null,
    trends: { ...emptyRunningTrends(), ...trendsExtra },
  };
}

function renderCoach() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <CoachPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

async function openTrends(user: ReturnType<typeof userEvent.setup>) {
  // The strength blocks live in the "Trends" tab (default tab is "Now").
  await waitFor(() => expect(getMock).toHaveBeenCalledWith('/coach/summary'));
  const tab = await screen.findByRole('tab', { name: 'Trends' });
  await user.click(tab);
}

beforeEach(() => {
  getMock.mockReset();
  getMock.mockImplementation((path: string) => {
    if (path === '/coach/recaps') return Promise.resolve({ recaps: [] });
    return Promise.resolve({});
  });
  // recharts' ResponsiveContainer needs ResizeObserver; jsdom lacks it.
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  // ThemeProvider reads matchMedia during render; jsdom lacks it.
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {}, dispatchEvent() { return false; },
  })) as unknown as typeof window.matchMedia;
});

function mockSummary(trendsExtra: AnySummary) {
  getMock.mockImplementation((path: string) => {
    if (path === '/coach/recaps') return Promise.resolve({ recaps: [] });
    if (path === '/coach/summary') return Promise.resolve(summaryWith(trendsExtra));
    return Promise.resolve({});
  });
}

describe('Strength insights blocks', () => {
  it('renders the weekly groups, records and push/pull blocks', async () => {
    const user = userEvent.setup();
    mockSummary({
      strength_insights: fullInsights(),
      strength_progression: [
        {
          exercise: 'Squat', sessions: 4, e1rm_eligible: true, mixed: false,
          notation_mixed: false, load_label: 'total_noted',
          points: points('top_weight_kg', [100, 102, 105, 110]),
        },
      ],
      strength_sessions: [],
      strength_history: [],
    });
    renderCoach();
    await openTrends(user);

    expect(await screen.findByText('Logged sets per muscle group (8 weeks)')).toBeInTheDocument();
    expect(screen.getByText('Records')).toBeInTheDocument();
    expect(screen.getByText('Push / pull balance')).toBeInTheDocument();
    // Squat appears both as a progression chip and a records row; Tractions in records.
    expect(screen.getAllByText('Squat').length).toBeGreaterThan(0);
    expect(screen.getByText('Tractions')).toBeInTheDocument();
  });

  it('renders nothing strength-related when the payload is missing', async () => {
    const user = userEvent.setup();
    mockSummary({});
    renderCoach();
    await openTrends(user);
    expect(screen.queryByText('Logged sets per muscle group (8 weeks)')).not.toBeInTheDocument();
    expect(screen.queryByText('Records')).not.toBeInTheDocument();
    expect(screen.queryByText('Push / pull balance')).not.toBeInTheDocument();
  });

  it('hides the weekly and push/pull blocks when every value is zero', async () => {
    const user = userEvent.setup();
    const insights = fullInsights();
    const zero = { logged: 0, campus_plan: 0 };
    insights.weeks = insights.weeks.map((wk) => ({
      ...wk,
      groups: Object.fromEntries(Object.keys(wk.groups).map((g) => [g, zero])) as typeof wk.groups,
      explosivite: zero,
      autre: zero,
    }));
    insights.push_pull = insights.push_pull.map((p) => ({ ...p, push: 0, pull: 0, ratio: null }));
    mockSummary({ strength_insights: insights, strength_progression: [], strength_sessions: [], strength_history: [] });
    renderCoach();
    await openTrends(user);
    expect(await screen.findByText('Records')).toBeInTheDocument();
    expect(screen.queryByText('Logged sets per muscle group (8 weeks)')).not.toBeInTheDocument();
    expect(screen.queryByText('Push / pull balance')).not.toBeInTheDocument();
  });

  it('shows a local fallback for a malformed block while siblings still render', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const user = userEvent.setup();
    const insights = fullInsights();
    // A null push_pull entry makes StrengthPushPull throw during render; its
    // local ErrorBoundary must catch it while the other blocks render.
    (insights as AnySummary).push_pull = [null];
    mockSummary({ strength_insights: insights, strength_progression: [], strength_sessions: [], strength_history: [] });
    renderCoach();
    await openTrends(user);

    // Siblings render.
    expect(await screen.findByText('Logged sets per muscle group (8 weeks)')).toBeInTheDocument();
    expect(screen.getByText('Records')).toBeInTheDocument();
    // The push/pull block shows its compact fallback instead of crashing the page.
    expect(screen.getByText('Block unavailable')).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it('e1RM toggle appears only for an eligible exercise and resets on a non-eligible one', async () => {
    const user = userEvent.setup();
    mockSummary({
      strength_insights: fullInsights(),
      strength_progression: [
        {
          exercise: 'Squat', sessions: 4, e1rm_eligible: true, mixed: false,
          notation_mixed: false, load_label: 'total_noted',
          points: [
            { date: '2026-10-01', top_weight_kg: 100, volume_kg: 1000, e1rm_kg: 116 },
            { date: '2026-10-05', top_weight_kg: 105, volume_kg: 1100, e1rm_kg: 120 },
            { date: '2026-10-09', top_weight_kg: 110, volume_kg: 1200, e1rm_kg: 125 },
          ],
        },
        {
          exercise: 'Curl barre', sessions: 3, e1rm_eligible: false, mixed: false,
          notation_mixed: false, load_label: 'total_noted',
          points: [
            { date: '2026-10-01', top_weight_kg: 30, volume_kg: 300, e1rm_kg: null },
            { date: '2026-10-05', top_weight_kg: 32, volume_kg: 320, e1rm_kg: null },
            { date: '2026-10-09', top_weight_kg: 34, volume_kg: 340, e1rm_kg: null },
          ],
        },
      ],
      strength_sessions: [],
      strength_history: [],
    });
    renderCoach();
    await openTrends(user);

    // Squat is active first and is eligible -> e1RM toggle present.
    expect(await screen.findByText('Strength progression')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'e1RM' }).length).toBeGreaterThan(0);

    // Select e1RM, then switch to the non-eligible exercise: the toggle
    // disappears AND the stored metric becomes weight (Weight is aria-pressed).
    await user.click(screen.getAllByRole('button', { name: 'e1RM' })[0]);
    await user.click(screen.getByRole('button', { name: 'Curl barre' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'e1RM' })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Max load' })).toHaveAttribute('aria-pressed', 'true');

    // Reselect the eligible exercise: the metric stays weight (not silently e1RM).
    await user.click(screen.getByRole('button', { name: 'Squat' }));
    expect(await screen.findByRole('button', { name: 'e1RM' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Max load' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'e1RM' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows a metric empty state instead of hiding when a metric has <3 points', async () => {
    const user = userEvent.setup();
    mockSummary({
      strength_insights: fullInsights(),
      strength_progression: [
        {
          exercise: 'Squat', sessions: 4, e1rm_eligible: true, mixed: false,
          notation_mixed: false, load_label: 'total_noted',
          // weight has 4 points (chartable), volume only 1.
          points: [
            { date: '2026-10-01', top_weight_kg: 100, volume_kg: 1000, e1rm_kg: null },
            { date: '2026-10-05', top_weight_kg: 105, volume_kg: null, e1rm_kg: null },
            { date: '2026-10-09', top_weight_kg: 110, volume_kg: null, e1rm_kg: null },
            { date: '2026-10-12', top_weight_kg: 112, volume_kg: null, e1rm_kg: null },
          ],
        },
      ],
      strength_sessions: [],
      strength_history: [],
    });
    renderCoach();
    await openTrends(user);

    expect(await screen.findByText('Strength progression')).toBeInTheDocument();
    // Switch to the Volume metric (only 1 point) -> metric empty state, block stays.
    await user.click(screen.getByRole('button', { name: 'Volume' }));
    expect(await screen.findByText(/Not enough points for this metric/i)).toBeInTheDocument();
    expect(screen.getByText('Strength progression')).toBeInTheDocument();
  });

  it('shows the mixed-exercise note on the progression chart', async () => {
    const user = userEvent.setup();
    mockSummary({
      strength_insights: fullInsights(),
      strength_progression: [
        {
          exercise: 'Développé machine', sessions: 4, e1rm_eligible: false, mixed: true,
          notation_mixed: false, load_label: 'total_noted',
          points: points('top_weight_kg', [55, 57, 60, 62]),
        },
      ],
      strength_sessions: [],
      strength_history: [],
    });
    renderCoach();
    await openTrends(user);
    expect(await screen.findByText(/Mixes two machine presses/i)).toBeInTheDocument();
  });

  it('push/pull block shows a null ratio as a dash', async () => {
    const user = userEvent.setup();
    mockSummary({ strength_insights: fullInsights(), strength_progression: [], strength_sessions: [], strength_history: [] });
    renderCoach();
    await openTrends(user);
    const header = await screen.findByText('Push / pull balance');
    const card = header.closest('div');
    expect(card).toBeTruthy();
    // W41 has pull=0 -> ratio is null -> rendered as an em dash in its span.
    const w41 = within(card as HTMLElement).getByText(/W41/);
    expect(w41.textContent).toMatch(/—/);
  });
});
