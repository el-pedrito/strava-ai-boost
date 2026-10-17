import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AthleteInputCard } from '../AthleteInputCard';

const getMock = vi.hoisted(() => vi.fn<(path: string) => Promise<unknown>>());
const postMock = vi.hoisted(() => vi.fn<(path: string, body?: unknown) => Promise<unknown>>());

vi.mock('@/api/client', () => ({
  api: {
    get: (path: string) => getMock(path),
    post: (path: string, body?: unknown) => postMock(path, body),
  },
}));

const pushFlag = vi.hoisted(() => ({ enabled: true }));
vi.mock('@/config', () => ({ isPushEnabled: () => pushFlag.enabled }));

function modules(athleteInput?: { enabled: boolean }) {
  return {
    modules: {
      campus_coach: { enabled: false, configured: false },
      enduraw: { enabled: true, configured: true },
      intervals_icu: { enabled: false, configured: false },
      ...(athleteInput ? { athlete_input: { ...athleteInput, configured: true } } : {}),
    },
  };
}

async function toggle() {
  const el = await screen.findByRole('switch', { name: 'Ask for my feedback after each session' });
  await waitFor(() => expect(el).toBeEnabled());
  return el;
}

describe('AthleteInputCard', () => {
  beforeEach(() => {
    pushFlag.enabled = true;
    getMock.mockReset();
    postMock.mockReset();
  });

  it('is not rendered when the deployment has no push', () => {
    pushFlag.enabled = false;
    const { container } = render(<AthleteInputCard />);
    expect(container).toBeEmptyDOMElement();
    expect(getMock).not.toHaveBeenCalled();
  });

  it('starts off when the module is absent', async () => {
    getMock.mockResolvedValue(modules());
    render(<AthleteInputCard />);
    expect(screen.getByText('Post-session feedback')).toBeInTheDocument();
    expect(await toggle()).toHaveAttribute('aria-checked', 'false');
    expect(getMock).toHaveBeenCalledWith('/config/modules');
  });

  it('reflects a stored enabled flag', async () => {
    getMock.mockResolvedValue(modules({ enabled: true }));
    render(<AthleteInputCard />);
    await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'true'));
  });

  it('saves through the module configuration call, like Enduraw', async () => {
    getMock.mockResolvedValue(modules({ enabled: false }));
    postMock.mockResolvedValue({ success: true });
    render(<AthleteInputCard />);
    await userEvent.click(await toggle());
    expect(postMock).toHaveBeenCalledWith('/config/modules', { module_id: 'athlete_input', enabled: true });
    await waitFor(async () => expect(await toggle()).toHaveAttribute('aria-checked', 'true'));
  });

  it('turns it off with enabled false', async () => {
    getMock.mockResolvedValue(modules({ enabled: true }));
    postMock.mockResolvedValue({ success: true });
    render(<AthleteInputCard />);
    const el = await toggle();
    await waitFor(() => expect(el).toHaveAttribute('aria-checked', 'true'));
    await userEvent.click(el);
    expect(postMock).toHaveBeenCalledWith('/config/modules', { module_id: 'athlete_input', enabled: false });
  });

  it('rolls back and shows an error when saving fails', async () => {
    getMock.mockResolvedValue(modules({ enabled: false }));
    postMock.mockRejectedValue(new Error('boom'));
    render(<AthleteInputCard />);
    await userEvent.click(await toggle());
    expect(await screen.findByText('Could not save this setting. Please try again.')).toBeInTheDocument();
    expect(await toggle()).toHaveAttribute('aria-checked', 'false');
  });

  it('still works off when the modules GET fails', async () => {
    getMock.mockRejectedValue(new Error('down'));
    render(<AthleteInputCard />);
    expect(await toggle()).toHaveAttribute('aria-checked', 'false');
  });
});
