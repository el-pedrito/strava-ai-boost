import { useState, type FormEvent } from 'react';
import {
  Box,
  Button,
  Container,
  Form,
  FormField,
  Header,
  Input,
  SpaceBetween,
  Alert,
} from '@cloudscape-design/components';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { signIn, completeNewPassword, error, isLoading } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (needsNewPassword) {
      await completeNewPassword(newPassword);
    } else {
      await signIn(email, password);
    }
  };

  // Detect new password challenge from error state
  if (error === 'NEW_PASSWORD_REQUIRED' && !needsNewPassword) {
    setNeedsNewPassword(true);
  }

  return (
    <Box padding="xxxl">
      <div style={{ maxWidth: '400px', margin: '0 auto' }}>
        <Container header={<Header variant="h1">Strava AI Boost</Header>}>
          <form onSubmit={handleSubmit}>
            <Form
              actions={
                <Button variant="primary" loading={isLoading} formAction="submit">
                  {needsNewPassword ? 'Set new password' : 'Sign in'}
                </Button>
              }
            >
              <SpaceBetween size="l">
                {error && error !== 'NEW_PASSWORD_REQUIRED' && (
                  <Alert type="error">{error}</Alert>
                )}

                {!needsNewPassword ? (
                  <>
                    <FormField label="Email">
                      <Input
                        type="email"
                        value={email}
                        onChange={({ detail }) => setEmail(detail.value)}
                        placeholder="you@example.com"
                      />
                    </FormField>
                    <FormField label="Password">
                      <Input
                        type="password"
                        value={password}
                        onChange={({ detail }) => setPassword(detail.value)}
                      />
                    </FormField>
                  </>
                ) : (
                  <>
                    <Alert type="info">Please set a new password for your account.</Alert>
                    <FormField label="New password" constraintText="Min 12 chars, upper + lower + digits + symbols">
                      <Input
                        type="password"
                        value={newPassword}
                        onChange={({ detail }) => setNewPassword(detail.value)}
                      />
                    </FormField>
                  </>
                )}
              </SpaceBetween>
            </Form>
          </form>
        </Container>
      </div>
    </Box>
  );
}
