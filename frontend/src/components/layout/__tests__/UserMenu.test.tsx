import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserMenu } from '../UserMenu';

const signOutMock = vi.fn();

vi.mock('@/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { getUsername: () => 'runner@example.com' },
    signOut: signOutMock,
  }),
}));

describe('UserMenu', () => {
  beforeEach(() => {
    signOutMock.mockClear();
  });

  it('sidebar variant shows initial and email in the trigger', () => {
    render(<UserMenu variant="sidebar" />);
    expect(screen.getByText('R')).toBeInTheDocument();
    expect(screen.getByText('runner@example.com')).toBeInTheDocument();
  });

  it('sidebar variant hides the email when collapsed', () => {
    render(<UserMenu variant="sidebar" collapsed />);
    expect(screen.getByText('R')).toBeInTheDocument();
    expect(screen.queryByText('runner@example.com')).not.toBeInTheDocument();
  });

  it('topbar variant shows only the initial with an accessible label', () => {
    render(<UserMenu variant="topbar" />);
    expect(screen.getByText('R')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAccessibleName();
    expect(screen.queryByText('runner@example.com')).not.toBeInTheDocument();
  });

  it('opens the menu and calls signOut', async () => {
    const user = userEvent.setup();
    render(<UserMenu variant="topbar" />);

    await user.click(screen.getByRole('button'));
    // Email header appears inside the opened dropdown
    expect(await screen.findByText('runner@example.com')).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: /sign out/i }));
    expect(signOutMock).toHaveBeenCalledTimes(1);
  });
});
