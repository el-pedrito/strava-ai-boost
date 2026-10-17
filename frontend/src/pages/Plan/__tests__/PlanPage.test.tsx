import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { PlanPage } from '../PlanPage';
import { setLanguage } from '@/i18n';
import type { PlanWorkoutItem, PlanWorkoutsResponse } from '@/types/index';

const getPlanWorkoutsMock = vi.hoisted(() => vi.fn<() => Promise<PlanWorkoutsResponse>>());
const downloadWorkoutMock = vi.hoisted(() => vi.fn<(b64: string, filename: string) => void>());

vi.mock('@/api/client', () => ({
  getPlanWorkouts: () => getPlanWorkoutsMock(),
}));

vi.mock('@/lib/downloadWorkout', () => ({
  downloadWorkout: (b64: string, filename: string) => downloadWorkoutMock(b64, filename),
}));

function item(overrides: Partial<PlanWorkoutItem>): PlanWorkoutItem {
  return {
    session_id: 's1',
    week_iso: '2026-W43',
    training_index: 1,
    title: 'Intensité semi',
    training_type: 'intensity',
    sport: 'road',
    duration_min: 62,
    summary: "WU 15' · 4x(9' Semi 4:28 + 2') · CD 5'",
    filename: '2026-W43-1-intensite-semi.workout',
    encodable: true,
    reason_code: null,
    workout_b64: 'AAEC',
    ...overrides,
  };
}

function respond(workouts: PlanWorkoutItem[], truncated = false) {
  getPlanWorkoutsMock.mockResolvedValue({ workouts, count: workouts.length, truncated });
}

describe('PlanPage', () => {
  beforeEach(() => {
    getPlanWorkoutsMock.mockReset();
    downloadWorkoutMock.mockReset();
    // Only Date is faked (promises and timers stay real). Default "today" is in
    // 2026-W41, so the W43/W44 fixtures keep their plain "Week N" headers.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-07T10:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a loading status while the request is pending', () => {
    getPlanWorkoutsMock.mockReturnValue(new Promise(() => {}));
    render(<PlanPage />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading sessions');
  });

  it('shows the empty state when no session is upcoming', async () => {
    respond([]);
    render(<PlanPage />);
    expect(await screen.findByText('No upcoming sessions')).toBeInTheDocument();
    expect(screen.queryByTestId('plan-session')).not.toBeInTheDocument();
  });

  it('shows an error with a retry that reloads the sessions', async () => {
    getPlanWorkoutsMock.mockRejectedValueOnce(new Error('boom'));
    render(<PlanPage />);
    expect(await screen.findByText('Could not load the upcoming sessions.')).toBeInTheDocument();
    expect(screen.queryByText('No upcoming sessions')).not.toBeInTheDocument();

    respond([item({})]);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: 'Intensité semi' })).toBeInTheDocument();
    expect(screen.queryByText('Could not load the upcoming sessions.')).not.toBeInTheDocument();
    expect(getPlanWorkoutsMock).toHaveBeenCalledTimes(2);
  });

  it('groups sessions by ISO week, weeks in chronological order', async () => {
    respond([
      item({ session_id: 'a', week_iso: '2026-W44', title: 'Sortie longue' }),
      item({ session_id: 'b', week_iso: '2026-W43', title: 'Intensité semi' }),
      item({ session_id: 'c', week_iso: '2026-W44', title: 'Footing' }),
    ]);
    render(<PlanPage />);

    const week43 = await screen.findByRole('region', { name: 'Week 43' });
    const week44 = screen.getByRole('region', { name: 'Week 44' });
    expect(within(week43).getAllByTestId('plan-session')).toHaveLength(1);
    expect(within(week43).getByText('Intensité semi')).toBeInTheDocument();
    const week44Titles = within(week44)
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(week44Titles).toEqual(['Sortie longue', 'Footing']);

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(['Week 43', 'Week 44']);
  });

  it('renders title, duration, summary and sport label of a session', async () => {
    respond([item({})]);
    render(<PlanPage />);
    const card = await screen.findByTestId('plan-session');
    expect(within(card).getByText('Intensité semi')).toBeInTheDocument();
    expect(within(card).getByText('62 min')).toBeInTheDocument();
    expect(within(card).getByText("WU 15' · 4x(9' Semi 4:28 + 2') · CD 5'")).toBeInTheDocument();
    expect(within(card).getByText('Run')).toBeInTheDocument();
  });

  it('calls downloadWorkout synchronously with the exact b64 and filename', async () => {
    respond([
      item({ session_id: 'a', workout_b64: 'Zmlyc3Q=', filename: 'first.workout', title: 'First' }),
      item({ session_id: 'b', workout_b64: 'c2Vjb25k', filename: 'second.workout', title: 'Second' }),
    ]);
    render(<PlanPage />);
    const button = await screen.findByRole('button', { name: 'Add to Watch: Second' });

    // fireEvent is synchronous: the call must already be recorded on return,
    // which proves nothing is awaited before the download (iOS user gesture).
    fireEvent.click(button);
    expect(downloadWorkoutMock).toHaveBeenCalledTimes(1);
    expect(downloadWorkoutMock).toHaveBeenCalledWith('c2Vjb25k', 'second.workout');
  });

  it('shows an inline error when the payload cannot be downloaded', async () => {
    downloadWorkoutMock.mockImplementation(() => {
      throw new Error('bad base64');
    });
    respond([item({})]);
    render(<PlanPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Add to Watch: Intensité semi' }));
    expect(screen.getByRole('alert')).toHaveTextContent('unreadable');
  });

  it('greys a non-encodable session with its reason and no download button', async () => {
    respond([
      item({
        session_id: 'legacy',
        title: 'Vieille séance',
        encodable: false,
        reason_code: 'legacy_shape',
        workout_b64: undefined,
      }),
      item({
        session_id: 'big',
        title: 'Trop longue',
        encodable: false,
        reason_code: 'too_many_steps',
        workout_b64: undefined,
      }),
    ]);
    render(<PlanPage />);

    const cards = await screen.findAllByTestId('plan-session');
    expect(cards).toHaveLength(2);
    for (const card of cards) {
      expect(card).toHaveAttribute('data-encodable', 'false');
      expect(within(card).queryByRole('button')).not.toBeInTheDocument();
      expect(within(card).getByText('Not available on the Watch')).toBeInTheDocument();
    }
    expect(within(cards[0]).getByText(/Plan needs a resync\./)).toBeInTheDocument();
    expect(within(cards[1]).getByText(/Too many steps for the Watch\./)).toBeInTheDocument();
  });

  it('treats an unknown reason or an encodable item without bytes as not exportable', async () => {
    respond([
      item({ session_id: 'x', encodable: false, reason_code: 'brand_new_code', workout_b64: undefined }),
      item({ session_id: 'y', encodable: true, workout_b64: undefined }),
    ]);
    render(<PlanPage />);
    const cards = await screen.findAllByTestId('plan-session');
    for (const card of cards) {
      expect(card).toHaveAttribute('data-encodable', 'false');
      expect(within(card).getByText(/This session could not be exported\./)).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: /Add to Watch/ })).not.toBeInTheDocument();
  });

  it('shows the truncated notice only when the server truncated the list', async () => {
    respond([item({})], true);
    const { unmount } = render(<PlanPage />);
    expect(await screen.findByText(/only the nearest weeks are shown/)).toBeInTheDocument();
    unmount();

    respond([item({})], false);
    render(<PlanPage />);
    await screen.findByTestId('plan-session');
    expect(screen.queryByText(/only the nearest weeks are shown/)).not.toBeInTheDocument();
  });

  it('includes the iPhone import help', async () => {
    respond([]);
    render(<PlanPage />);
    expect(await screen.findByText('How to add it on iPhone?')).toBeInTheDocument();
    expect(screen.getByText(/open the Files app/)).toBeInTheDocument();
    expect(screen.getByText(/delete the old one on the Watch/)).toBeInTheDocument();
  });

  it('groups sessions without a week label under a trailing "Unknown week" header', async () => {
    respond([
      item({ session_id: 'n', week_iso: null, title: 'Sans semaine' }),
      item({ session_id: 'k', week_iso: '2026-W44', title: 'Footing' }),
    ]);
    render(<PlanPage />);
    const unknown = await screen.findByRole('region', { name: 'Unknown week' });
    expect(within(unknown).getByText('Sans semaine')).toBeInTheDocument();
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(['Week 44', 'Unknown week']);
  });

  it('falls back to "Session" when the title is null, in text and aria-label', async () => {
    respond([item({ title: null })]);
    render(<PlanPage />);
    const card = await screen.findByTestId('plan-session');
    expect(within(card).getByRole('heading', { level: 3, name: 'Session' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Add to Watch: Session' })).toBeInTheDocument();
  });

  it('ties the download error to its own card when a session id repeats across weeks', async () => {
    downloadWorkoutMock.mockImplementation(() => {
      throw new Error('bad base64');
    });
    respond([
      item({ session_id: 'same', week_iso: '2026-W43', title: 'First' }),
      item({ session_id: 'same', week_iso: '2026-W44', title: 'Second' }),
    ]);
    render(<PlanPage />);
    const second = await screen.findByRole('button', { name: 'Add to Watch: Second' });
    fireEvent.click(second);
    const alert = screen.getByRole('alert');
    // The id comes from the week + session key, so it cannot collide with W43's card.
    expect(alert.id).toContain('2026-W44');
    expect(second).toHaveAttribute('aria-describedby', alert.id);
    expect(screen.getByRole('button', { name: 'Add to Watch: First' })).not.toHaveAttribute('aria-describedby');
  });

  it('a retry clears the load error and keeps the buttons disabled while loading', async () => {
    getPlanWorkoutsMock.mockRejectedValueOnce(new Error('boom'));
    render(<PlanPage />);
    expect(await screen.findByText('Could not load the upcoming sessions.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled();

    getPlanWorkoutsMock.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    // No stale error (and so no clickable Retry) while the new request runs.
    expect(screen.queryByText('Could not load the upcoming sessions.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Loading sessions');
  });

  it('a refresh clears a previous download error', async () => {
    downloadWorkoutMock.mockImplementation(() => {
      throw new Error('bad base64');
    });
    respond([item({})]);
    render(<PlanPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Add to Watch: Intensité semi' }));
    expect(screen.getByRole('alert')).toHaveTextContent('unreadable');

    getPlanWorkoutsMock.mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  });

  it('renders French labels: week header and legacy reason', async () => {
    await setLanguage('fr');
    let unmount: (() => void) | undefined;
    try {
      respond([
        item({ session_id: 'ok' }),
        item({ session_id: 'old', encodable: false, reason_code: 'legacy_shape', workout_b64: undefined }),
      ]);
      ({ unmount } = render(<PlanPage />));
      expect(await screen.findByRole('heading', { level: 2, name: 'Semaine 43' })).toBeInTheDocument();
      expect(screen.getByText(/Plan à resynchroniser\./)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Ajouter à la Watch : Intensité semi' })).toBeInTheDocument();
      unmount();
      respond([item({ session_id: 'n', week_iso: null, title: null })]);
      ({ unmount } = render(<PlanPage />));
      expect(await screen.findByRole('heading', { level: 2, name: 'Semaine inconnue' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 3, name: 'Séance' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Ajouter à la Watch : Séance' })).toBeInTheDocument();
    } finally {
      // Unmount before switching back, otherwise the language change re-renders
      // the mounted page outside act().
      unmount?.();
      await setLanguage('en');
    }
  });

  describe('hierarchy, coach words and race', () => {
    // Wednesday of 2026-W43 in Paris.
    const WED_W43 = new Date('2026-10-21T10:00:00Z');

    it('labels this week and next week, with their date range and short week number', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({ session_id: 'a', week_iso: '2026-W43', title: 'Footing' }),
        item({ session_id: 'b', week_iso: '2026-W44', title: 'Allure 21 km' }),
        item({ session_id: 'c', week_iso: '2026-W45', title: 'Sortie longue' }),
      ]);
      render(<PlanPage />);
      const thisWeek = await screen.findByRole('region', { name: 'This week' });
      expect(within(thisWeek).getByTestId('plan-week-range')).toHaveTextContent('Mon 19 – Sun 25 Oct · W43');
      const nextWeek = screen.getByRole('region', { name: 'Next week' });
      expect(within(nextWeek).getByTestId('plan-week-range')).toHaveTextContent('Mon 26 Oct – Sun 1 Nov · W44');
      expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
        'This week',
        'Next week',
        'Week 45',
      ]);
    });

    it('gives only the next session a filled Watch button, the others an icon button with an aria-label', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({ session_id: 'a', week_iso: '2026-W43', title: 'Footing' }),
        item({ session_id: 'b', week_iso: '2026-W43', title: 'Allure 21 km' }),
        item({ session_id: 'c', week_iso: '2026-W44', title: 'Sortie longue' }),
      ]);
      render(<PlanPage />);
      const buttons = await screen.findAllByRole('button', { name: /^Add to Watch: / });
      expect(buttons).toHaveLength(3);
      // Visible label only on the next one; the icon buttons rely on aria-label.
      expect(buttons.filter((b) => b.textContent === 'Add to Watch')).toEqual([
        screen.getByRole('button', { name: 'Add to Watch: Footing' }),
      ]);
      expect(screen.getByRole('button', { name: 'Add to Watch: Allure 21 km' })).toHaveTextContent('');
      const cards = screen.getAllByTestId('plan-session');
      expect(cards.map((c) => c.getAttribute('data-role'))).toEqual(['next', 'normal', 'normal']);
      expect(within(cards[0]).getByText('Next')).toBeInTheDocument();
      expect(within(cards[0]).getByText('Campus sets no day: to do by Sun 25 Oct.')).toBeInTheDocument();
    });

    it('takes the first session of next week as next when this week has none left', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({ session_id: 'b', week_iso: '2026-W44', title: 'Allure 21 km' }),
        item({ session_id: 'c', week_iso: '2026-W44', title: 'Sortie longue' }),
      ]);
      render(<PlanPage />);
      const cards = await screen.findAllByTestId('plan-session');
      expect(cards.map((c) => c.getAttribute('data-role'))).toEqual(['next', 'normal']);
    });

    it('shows the next session coach word open and its instructions collapsed', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({
          session_id: 'a',
          title: 'Footing',
          coach_advice: 'Reste facile, **vraiment** facile.',
          description: 'Footing en endurance fondamentale.',
        }),
        item({ session_id: 'b', title: 'Allure', coach_advice: 'Arrive reposé.', description: 'Quatre fois neuf minutes.' }),
      ]);
      render(<PlanPage />);
      const [next, other] = await screen.findAllByTestId('plan-session');

      const box = within(next).getByTestId('plan-coach-box');
      expect(within(box).getByText("Campus coach's word")).toBeInTheDocument();
      expect(within(box).getByText('vraiment').tagName).toBe('STRONG');
      // Coach word not inside a <details>; instructions inside a closed one.
      expect(within(box).getByText(/Reste facile/).closest('details')).toBeNull();
      const consigne = within(box).getByText('Footing en endurance fondamentale.').closest('details');
      expect(consigne).not.toBeNull();
      expect(consigne).not.toHaveAttribute('open');
      expect(within(consigne as HTMLElement).getByText('Session instructions')).toBeInTheDocument();

      // Other sessions: one collapsed "Coach's word" holding both texts.
      const disclosure = within(other).getByText("Coach's word").closest('details');
      expect(disclosure).not.toHaveAttribute('open');
      expect(within(disclosure as HTMLElement).getByText('Arrive reposé.')).toBeInTheDocument();
      expect(within(disclosure as HTMLElement).getByText('Quatre fois neuf minutes.')).toBeInTheDocument();
    });

    it('renders no coach block when the session has neither text', async () => {
      vi.setSystemTime(WED_W43);
      respond([item({ session_id: 'a' }), item({ session_id: 'b', coach_advice: '  ', description: null })]);
      render(<PlanPage />);
      await screen.findAllByTestId('plan-session');
      expect(screen.queryByTestId('plan-coach-box')).not.toBeInTheDocument();
      expect(screen.queryByText("Coach's word")).not.toBeInTheDocument();
    });

    it('renders the race as a race card with its countdown, coach word open, and a header strip', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({ session_id: 'a', week_iso: '2026-W43', title: 'Footing' }),
        item({
          session_id: 'r',
          week_iso: '2026-W46',
          title: 'SEMI-MARATHON',
          training_type: 'Competition',
          coach_advice: 'Bon courage pour ta compétition !',
          description: 'Pars prudemment.',
        }),
      ]);
      render(<PlanPage />);
      const raceWeek = await screen.findByRole('region', { name: 'Race week' });
      const race = within(raceWeek).getByTestId('plan-session');
      expect(race).toHaveAttribute('data-role', 'race');
      expect(within(race).getByText('Race day')).toBeInTheDocument();
      // Sunday of W46 (15 Nov) minus Wednesday 21 Oct = 25 days.
      expect(within(race).getByRole('img', { name: 'in 25 days' })).toHaveTextContent('D-25');
      expect(within(race).getByText('Estimated date: end of week, Sun 15 Nov')).toBeInTheDocument();
      expect(within(race).getByText('Bon courage pour ta compétition !').closest('details')).toBeNull();
      // Not the next session: icon button only.
      expect(within(race).getByRole('button', { name: 'Add to Watch: SEMI-MARATHON' })).toHaveTextContent('');

      const strip = screen.getByTestId('plan-race-strip');
      expect(strip).toHaveTextContent('SEMI-MARATHON · Sun 15 Nov');
      expect(strip).toHaveTextContent('D-25');
    });

    it('detects the race from a MARATHON title alone, not from an intermediate race', async () => {
      vi.setSystemTime(WED_W43);
      respond([
        item({ session_id: 'i', title: 'Course intermédiaire', training_type: 'low-priority-race' }),
        item({ session_id: 'm', week_iso: '2026-W46', title: 'Semi-marathon', training_type: null }),
      ]);
      render(<PlanPage />);
      const cards = await screen.findAllByTestId('plan-session');
      expect(cards.map((c) => c.getAttribute('data-role'))).toEqual(['next', 'race']);
    });

    it('shows no race strip when the plan has no race', async () => {
      vi.setSystemTime(WED_W43);
      respond([item({})]);
      render(<PlanPage />);
      await screen.findByTestId('plan-session');
      expect(screen.queryByTestId('plan-race-strip')).not.toBeInTheDocument();
    });

    it('renders the French hierarchy: Cette semaine, dates, Prochaine and J-x', async () => {
      vi.setSystemTime(WED_W43);
      await setLanguage('fr');
      let unmount: (() => void) | undefined;
      try {
        respond([
          item({ session_id: 'a', week_iso: '2026-W43', title: 'Footing', coach_advice: 'Écoute ton corps.' }),
          item({ session_id: 'r', week_iso: '2026-W46', title: 'SEMI-MARATHON', training_type: 'Competition' }),
        ]);
        ({ unmount } = render(<PlanPage />));
        const thisWeek = await screen.findByRole('region', { name: 'Cette semaine' });
        expect(within(thisWeek).getByTestId('plan-week-range')).toHaveTextContent('lun. 19 – dim. 25 oct. · S43');
        expect(within(thisWeek).getByText('Prochaine')).toBeInTheDocument();
        expect(within(thisWeek).getByText('Mot du coach Campus')).toBeInTheDocument();
        expect(screen.getByRole('region', { name: 'Semaine de course' })).toBeInTheDocument();
        expect(screen.getAllByRole('img', { name: 'dans 25 jours' })[0]).toHaveTextContent('J-25');
      } finally {
        unmount?.();
        await setLanguage('en');
      }
    });
  });
});
