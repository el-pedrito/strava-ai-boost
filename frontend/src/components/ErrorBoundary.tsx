import { Component, type ReactNode, type ErrorInfo } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertOctagon } from 'lucide-react';
import { Button } from '@/ui';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
  /**
   * A custom node rendered instead of the full-page fallback when a child
   * throws. Used to wrap individual dashboard blocks in a compact "block
   * unavailable" card so one failing block never blanks the whole page.
   */
  fallback?: ReactNode;
  /**
   * When this value changes between renders, the boundary resets and retries
   * its children. Pass a STABLE reference (e.g. the fetched summary object or a
   * fetch generation), never an inline `?? []`, which would reset on every
   * parent render and loop on a persistently throwing child.
   */
  resetKey?: unknown;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface FallbackProps {
  error: Error | null;
  heading?: string;
  onRetry: () => void;
  onGoHome: () => void;
}

function ErrorFallback({ error, heading, onRetry, onGoHome }: FallbackProps): ReactNode {
  const { t } = useTranslation();
  const isDev = import.meta.env.DEV;
  const title = heading ?? t('errorBoundary.heading');

  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-foreground p-6">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card text-card-foreground p-8 shadow-sm">
        <div className="flex flex-col items-center text-center gap-4">
          <AlertOctagon className="h-10 w-10 text-danger" aria-hidden="true" />
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="text-sm text-muted-foreground">{t('errorBoundary.description')}</p>
          {isDev && error?.message ? (
            <pre className="w-full font-mono text-xs bg-muted p-3 rounded-md overflow-x-auto whitespace-pre-wrap line-clamp-[8] text-left">
              {error.message}
            </pre>
          ) : null}
          <div className="flex gap-2 pt-2">
            <Button variant="primary" onClick={onRetry}>
              {t('errorBoundary.retry')}
            </Button>
            <Button variant="ghost" onClick={onGoHome}>
              {t('errorBoundary.goHome')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  componentDidUpdate(prevProps: Props): void {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  private handleGoHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // A custom (compact) fallback takes precedence over the full-page one.
      if (this.props.fallback !== undefined) {
        return this.props.fallback;
      }
      return (
        <ErrorFallback
          error={this.state.error}
          heading={this.props.fallbackMessage}
          onRetry={this.handleRetry}
          onGoHome={this.handleGoHome}
        />
      );
    }
    return this.props.children;
  }
}
