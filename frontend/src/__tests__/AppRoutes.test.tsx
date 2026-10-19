import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Suspense } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AppRoutes } from '../App';

const auth = vi.hoisted(() => ({ isAuthenticated: false, isLoading: false }));

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: auth.isAuthenticated,
    isLoading: auth.isLoading,
    error: null,
    user: { getUsername: () => 'runner@example.com' },
    signIn: vi.fn(),
    signOut: vi.fn(),
    completeNewPassword: vi.fn(),
  }),
}));

vi.mock('@/config', () => ({
  isWorkoutExportEnabled: () => false,
  getConfig: () => ({ apiGatewayUrl: '', workoutExportEnabled: false }),
}));

vi.mock('@/theme/ThemeProvider', () => ({
  useTheme: () => ({ theme: 'light', setTheme: vi.fn(), toggleTheme: vi.fn() }),
}));

// The home page fetches data; the routing tests only need to know it was reached.
vi.mock('@/pages/Home/HomePage', () => ({ HomePage: () => <div>home page stub</div> }));
vi.mock('@/pages/Health/HealthPage', () => ({ HealthPage: () => <div>health page stub</div> }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Suspense fallback={<div>suspense</div>}>
        <AppRoutes />
      </Suspense>
    </MemoryRouter>,
  );
}

describe('/login route', () => {
  beforeEach(() => {
    auth.isAuthenticated = false;
    auth.isLoading = false;
  });

  it('shows the login form when signed out', () => {
    renderAt('/login');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('redirects to / when already authenticated', async () => {
    auth.isAuthenticated = true;
    renderAt('/login');
    expect(await screen.findByText('home page stub')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();
  });
});

describe('catch-all route', () => {
  beforeEach(() => {
    auth.isAuthenticated = true;
    auth.isLoading = false;
  });

  it('renders the NotFound page inside the Shell for an unknown URL', async () => {
    renderAt('/this/does/not/exist');
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    // Inside the Shell: the top bar is still there.
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/');
  });

  it('asks a signed-out visitor to log in first', () => {
    auth.isAuthenticated = false;
    renderAt('/this/does/not/exist');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});

describe('/health route', () => {
  beforeEach(() => {
    auth.isAuthenticated = true;
    auth.isLoading = false;
  });

  it('renders the Health page inside the Shell', async () => {
    renderAt('/health');
    expect(await screen.findByText('health page stub')).toBeInTheDocument();
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });
});
