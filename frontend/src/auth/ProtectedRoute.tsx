import { Spinner, Box } from '@cloudscape-design/components';
import { useAuth } from '../auth/AuthContext';
import { LoginPage } from '../pages/LoginPage';

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <Box textAlign="center" padding="xxxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <>{children}</>;
}
