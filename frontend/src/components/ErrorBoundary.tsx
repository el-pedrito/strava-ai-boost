import { Component, type ReactNode, type ErrorInfo } from 'react';
import { Box, Button, Alert } from '@cloudscape-design/components';

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
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

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <Box padding="xl">
          <Alert
            type="error"
            header={this.props.fallbackMessage ?? 'Something went wrong'}
          >
            <Box padding={{ top: 's' }}>
              <p>An unexpected error occurred. Please try again.</p>
              <Button onClick={this.handleRetry}>Retry</Button>
            </Box>
          </Alert>
        </Box>
      );
    }

    return this.props.children;
  }
}
