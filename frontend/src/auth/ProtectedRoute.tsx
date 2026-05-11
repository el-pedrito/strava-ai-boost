import { useAuth } from './AuthContext';
import { LoginPage } from '../pages/LoginPage';

function isDevMockAuth(): boolean {
  if (!import.meta.env.DEV || typeof window === 'undefined') return false;
  return window.localStorage.getItem('sab-devmock') === '1';
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isDevMockAuth()) {
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background text-foreground">
        <div
          className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
