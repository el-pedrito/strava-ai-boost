import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBoundary } from '../ErrorBoundary';

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Test error');
  return <div>Content rendered</div>;
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders error UI when child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/unexpected error/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('uses custom fallback message', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary fallbackMessage="Custom error message">
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Custom error message')).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('recovers on retry click', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const user = userEvent.setup();

    let shouldThrow = true;

    function ConditionalChild() {
      if (shouldThrow) throw new Error('Test error');
      return <div>Recovered</div>;
    }

    const { rerender } = render(
      <ErrorBoundary>
        <ConditionalChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    shouldThrow = false;
    await user.click(screen.getByRole('button', { name: /retry/i }));

    rerender(
      <ErrorBoundary>
        <ConditionalChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Recovered')).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('renders a custom compact fallback instead of the full-page one', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary fallback={<div>Block unavailable</div>}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Block unavailable')).toBeInTheDocument();
    // The full-page fallback heading must not appear when a custom fallback is set.
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('isolates a throwing child so a sibling boundary still renders', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <div>
        <ErrorBoundary fallback={<div>Block A unavailable</div>}>
          <ThrowingChild shouldThrow={true} />
        </ErrorBoundary>
        <ErrorBoundary fallback={<div>Block B unavailable</div>}>
          <div>Sibling content</div>
        </ErrorBoundary>
      </div>,
    );

    expect(screen.getByText('Block A unavailable')).toBeInTheDocument();
    expect(screen.getByText('Sibling content')).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('recovers when resetKey changes', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    let shouldThrow = true;

    function Child() {
      if (shouldThrow) throw new Error('boom');
      return <div>Recovered via resetKey</div>;
    }

    const { rerender } = render(
      <ErrorBoundary fallback={<div>Block unavailable</div>} resetKey={1}>
        <Child />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Block unavailable')).toBeInTheDocument();

    // Fix the child and bump the resetKey: the boundary resets and re-renders.
    shouldThrow = false;
    rerender(
      <ErrorBoundary fallback={<div>Block unavailable</div>} resetKey={2}>
        <Child />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Recovered via resetKey')).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it('does not reset while resetKey is unchanged', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    let shouldThrow = true;

    function Child() {
      if (shouldThrow) throw new Error('boom');
      return <div>Should not recover</div>;
    }

    const { rerender } = render(
      <ErrorBoundary fallback={<div>Block unavailable</div>} resetKey={1}>
        <Child />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Block unavailable')).toBeInTheDocument();

    // Child fixed but resetKey unchanged: the boundary stays in its fallback.
    shouldThrow = false;
    rerender(
      <ErrorBoundary fallback={<div>Block unavailable</div>} resetKey={1}>
        <Child />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Block unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Should not recover')).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
