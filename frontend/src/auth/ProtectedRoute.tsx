import { Navigate } from 'react-router';
import { useAuth } from './AuthContext';
import { LoginPage } from '../pages/LoginPage';

function isDevMockAuth(): boolean {
  if (!import.meta.env.DEV || typeof window === 'undefined') return false;
  return window.localStorage.getItem('sab-devmock') === '1';
}

function AuthLoading() {
  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background text-foreground">
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary"
        aria-label="Loading"
      />
    </div>
  );
}

/**
 * Public `/login` route (home-screen shortcut, stale bookmark). Shows the login form,
 * and sends an authenticated user to `/`, including right after a successful sign-in.
 */
export function LoginRoute() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isDevMockAuth() || isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (isLoading) {
    return <AuthLoading />;
  }

  return <LoginPage />;
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isDevMockAuth()) {
    return <>{children}</>;
  }

  if (isLoading) {
    return <AuthLoading />;
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
