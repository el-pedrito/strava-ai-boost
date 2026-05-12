import { Component, type ReactNode, type ErrorInfo } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertOctagon } from 'lucide-react';
import { Button } from '@/ui';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface FallbackProps {
  error: Error | null;
  heading?: string;
  onReload: () => void;
  onGoHome: () => void;
}

function ErrorFallback({ error, heading, onReload, onGoHome }: FallbackProps): ReactNode {
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
            <Button variant="primary" onClick={onReload}>
              {t('errorBoundary.reload')}
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

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleGoHome = (): void => {
    window.location.href = '/';
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <ErrorFallback
          error={this.state.error}
          heading={this.props.fallbackMessage}
          onReload={this.handleReload}
          onGoHome={this.handleGoHome}
        />
      );
    }
    return this.props.children;
  }
}
