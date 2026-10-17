import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Suspense } from 'react';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { BottomNav } from '../BottomNav';
import { Sidebar } from '../Sidebar';
import { getNavItems, NAV_ITEMS } from '../navItems';
import { PlanGate } from '@/pages/Plan/PlanGate';
import { setLanguage } from '@/i18n';

const flag = vi.hoisted(() => ({ enabled: false }));

vi.mock('@/config', () => ({
  isWorkoutExportEnabled: () => flag.enabled,
  getConfig: () => ({ apiGatewayUrl: '', workoutExportEnabled: flag.enabled }),
}));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { getUsername: () => 'runner@example.com' },
    signOut: vi.fn(),
  }),
}));

vi.mock('@/api/client', () => ({
  getPlanWorkouts: () => Promise.resolve({ workouts: [], count: 0, truncated: false }),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Suspense fallback={<div>suspense</div>}>
        <Routes>
          <Route path="/" element={<div>dashboard home</div>} />
          <Route path="/plan" element={<PlanGate />} />
        </Routes>
      </Suspense>
    </MemoryRouter>
  );
}

describe('workoutExportEnabled flag', () => {
  beforeEach(() => {
    flag.enabled = false;
  });

  it('flag off: getNavItems returns the base items without /plan', () => {
    expect(getNavItems(false)).toBe(NAV_ITEMS);
    expect(getNavItems(false).some((item) => item.to === '/plan')).toBe(false);
  });

  it('flag on: getNavItems inserts /plan right after /coach', () => {
    const routes = getNavItems(true).map((item) => item.to);
    expect(routes).toEqual(['/', '/coach', '/plan', '/quality', '/monitoring', '/config', '/preferences']);
    // The shared base list is never mutated.
    expect(NAV_ITEMS.some((item) => item.to === '/plan')).toBe(false);
  });

  it('flag off: no Plan entry in the bottom nav nor the sidebar', () => {
    render(
      <MemoryRouter>
        <BottomNav />
        <Sidebar />
      </MemoryRouter>
    );
    expect(screen.queryByRole('link', { name: 'Plan' })).not.toBeInTheDocument();
  });

  it('flag on: Plan entry in the bottom nav and the sidebar, 7 bottom items', () => {
    flag.enabled = true;
    render(
      <MemoryRouter>
        <BottomNav />
        <Sidebar />
      </MemoryRouter>
    );
    const bottom = screen.getByRole('navigation', { name: 'Primary mobile navigation' });
    expect(within(bottom).getAllByRole('link')).toHaveLength(7);
    expect(within(bottom).getByRole('link', { name: 'Plan' })).toHaveAttribute('href', '/plan');
    expect(screen.getAllByRole('link', { name: 'Plan' })).toHaveLength(2);
  });

  it('Monitoring tab: in the sidebar and in the mobile bar (short label)', () => {
    flag.enabled = true;
    render(
      <MemoryRouter>
        <BottomNav />
        <Sidebar />
      </MemoryRouter>
    );
    const bottom = screen.getByRole('navigation', { name: 'Primary mobile navigation' });
    expect(within(bottom).getByRole('link', { name: 'Monit.' })).toHaveAttribute('href', '/monitoring');
    expect(screen.getByRole('link', { name: 'Monitoring' })).toHaveAttribute('href', '/monitoring');
  });

  // jsdom does no layout, so 375 px cannot be measured here. These tests pin what
  // makes the 7 slots fit instead: every slot is a shrinkable flex item (flex-1 +
  // min-w-0), every label is clamped to its slot (max-w-full + truncate), and the
  // long labels render in their short mobile form.
  it('flag on: every bottom slot shrinks and clamps its label', () => {
    flag.enabled = true;
    render(
      <MemoryRouter>
        <BottomNav />
      </MemoryRouter>
    );
    const bottom = screen.getByRole('navigation', { name: 'Primary mobile navigation' });
    const links = within(bottom).getAllByRole('link');
    expect(links).toHaveLength(7);
    for (const link of links) {
      expect(link).toHaveClass('flex-1', 'min-w-0');
      const label = link.querySelector('span');
      expect(label).not.toBeNull();
      expect(label).toHaveClass('max-w-full', 'truncate');
    }
  });

  it('flag on: the bottom nav uses the short labels, the sidebar the full ones', () => {
    flag.enabled = true;
    render(
      <MemoryRouter>
        <BottomNav />
        <Sidebar />
      </MemoryRouter>
    );
    const bottom = screen.getByRole('navigation', { name: 'Primary mobile navigation' });
    const bottomLabels = within(bottom).getAllByRole('link').map((link) => link.textContent);
    expect(bottomLabels).toEqual(['Dashboard', 'Coach', 'Plan', 'Quality', 'Monit.', 'Config', 'Prefs']);
    for (const label of bottomLabels) expect(label!.length).toBeLessThanOrEqual(10);
    expect(within(bottom).queryByText('Configuration')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Configuration' })).toHaveAttribute('href', '/config');
    expect(screen.getByRole('link', { name: 'Preferences' })).toHaveAttribute('href', '/preferences');
  });

  it('flag on: French short labels in the bottom nav stay within 10 characters', async () => {
    flag.enabled = true;
    await setLanguage('fr');
    let unmount: (() => void) | undefined;
    try {
      ({ unmount } = render(
        <MemoryRouter>
          <BottomNav />
        </MemoryRouter>
      ));
      const bottom = screen.getByRole('navigation', { name: 'Primary mobile navigation' });
      const labels = within(bottom).getAllByRole('link').map((link) => link.textContent);
      expect(labels).toEqual(['Dashboard', 'Coach', 'Plan', 'Qualité', 'Monit.', 'Config', 'Préf.']);
      for (const label of labels) expect(label!.length).toBeLessThanOrEqual(10);
    } finally {
      unmount?.();
      await setLanguage('en');
    }
  });

  it('flag off: /plan redirects to the dashboard', () => {
    renderAt('/plan');
    expect(screen.getByText('dashboard home')).toBeInTheDocument();
  });

  it('flag on: /plan renders the plan page', async () => {
    flag.enabled = true;
    renderAt('/plan');
    expect(await screen.findByRole('heading', { level: 1, name: 'Plan to Watch' })).toBeInTheDocument();
    expect(screen.queryByText('dashboard home')).not.toBeInTheDocument();
  });
});
