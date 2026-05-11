import { useState } from 'react';
import { Activity, Sparkles, LineChart, Sun, Moon } from 'lucide-react';
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
} from '@/ui';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from '../theme/ThemeProvider';

const valueProps = [
  {
    icon: Sparkles,
    title: 'Auto-enhanced descriptions',
    description: 'Each activity gets a personalized title and report in your style.',
  },
  {
    icon: Activity,
    title: 'Personal AI coach',
    description: 'Trends, ramp rate, pace zones. Like a real coaching session.',
  },
  {
    icon: LineChart,
    title: 'Built on Strava you trust',
    description: 'Read-only by default. Your data stays yours.',
  },
];

export function LoginPage() {
  const { signIn, completeNewPassword, error, isLoading } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);

  const handleSubmit = async (e: { preventDefault: () => void }) => {
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

  const showError = error && error !== 'NEW_PASSWORD_REQUIRED';

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex">
      {/* Left hero panel — hidden on mobile */}
      <aside
        className="hidden md:flex md:w-1/2 relative overflow-hidden bg-gradient-to-br from-background via-surface to-surface-elevated border-r border-border animate-fade-in-up"
      >
        <div className="relative flex flex-col justify-between p-12 lg:p-16 w-full">
          <div className="flex flex-col gap-10">
            <div>
              <h1 className="font-display text-3xl lg:text-4xl font-semibold tracking-tight">
                Strava AI Boost
              </h1>
              <p className="mt-3 text-base lg:text-lg text-muted-foreground max-w-md leading-relaxed">
                Your AI coach on Strava. Smarter analysis. Honest descriptions. Real progress.
              </p>
            </div>

            <ul className="flex flex-col gap-6 max-w-md">
              {valueProps.map(({ icon: Icon, title, description }) => (
                <li key={title} className="flex gap-4">
                  <div className="flex-shrink-0 mt-0.5 h-10 w-10 rounded-lg border border-border bg-surface flex items-center justify-center">
                    <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="font-medium text-sm text-foreground">{title}</span>
                    <span className="text-sm text-muted-foreground leading-relaxed">
                      {description}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-muted-foreground">
            Built with care. Powered by Bedrock + Strava.
          </p>
        </div>
      </aside>

      {/* Right form panel */}
      <main className="relative flex-1 flex items-center justify-center px-6 py-12 md:px-12">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="absolute top-4 right-4"
        >
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" aria-hidden="true" />
          ) : (
            <Moon className="h-5 w-5" aria-hidden="true" />
          )}
        </Button>

        <Card variant="elevated" padding="lg" className="w-full max-w-md animate-fade-in-up">
          <CardHeader>
            <CardTitle className="text-2xl">
              {needsNewPassword ? 'Set new password' : 'Sign in'}
            </CardTitle>
            <CardDescription>
              {needsNewPassword
                ? 'First sign-in. Choose a strong password.'
                : "Welcome back. Let's check your progress."}
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              {showError && <Alert variant="error">{error}</Alert>}

              {!needsNewPassword ? (
                <>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                  </div>
                </>
              ) : (
                <>
                  <Alert variant="info">First sign-in. Choose a strong password.</Alert>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="new-password">New password</Label>
                    <Input
                      id="new-password"
                      type="password"
                      autoComplete="new-password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                    />
                    <p className="text-xs text-muted-foreground">
                      Min 12 chars, upper + lower + digits + symbols.
                    </p>
                  </div>
                </>
              )}

              <Button type="submit" variant="primary" size="lg" loading={isLoading} className="w-full">
                {needsNewPassword ? 'Set new password' : 'Sign in'}
              </Button>

              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center" aria-hidden="true">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase tracking-wider">
                  <span className="bg-surface-elevated px-3 text-muted-foreground">Or</span>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <Button type="button" variant="outline" size="lg" disabled className="w-full">
                  Connect with Strava
                </Button>
                <p className="text-xs text-muted-foreground text-center">
                  Connect after signing in.
                </p>
              </div>
            </form>
          </CardContent>
        </Card>

        <p className="absolute bottom-6 left-0 right-0 text-center text-xs text-muted-foreground px-6">
          Need access? Contact your administrator.
        </p>
      </main>
    </div>
  );
}
