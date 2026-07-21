import { useTranslation } from 'react-i18next';
import { LogOut, ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@radix-ui/react-dropdown-menu';
import { useAuth } from '@/auth/AuthContext';
import { cn } from '@/lib/cn';

interface UserMenuProps {
  /**
   * Placement variant:
   * - `sidebar`: full-width trigger with email, dropdown opens upward.
   * - `topbar`: compact avatar-only trigger (mobile), dropdown opens downward.
   */
  variant: 'sidebar' | 'topbar';
  /** Sidebar only: hides the email/chevron when the sidebar is collapsed. */
  collapsed?: boolean;
}

/**
 * Shared user menu (avatar, email header, Sign Out) used by Sidebar and Topbar.
 * Single source of truth for the email/initial derivation and menu items.
 */
export function UserMenu({ variant, collapsed = false }: UserMenuProps) {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();

  const userEmail = user?.getUsername() ?? '';
  const userInitial = userEmail.charAt(0).toUpperCase() || 'U';

  return (
    <DropdownMenu>
      {variant === 'sidebar' ? (
        <DropdownMenuTrigger
          className={cn(
            'flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            collapsed && 'justify-center px-0'
          )}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
            {userInitial}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1 truncate text-foreground">
                {userEmail || 'Account'}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </>
          )}
        </DropdownMenuTrigger>
      ) : (
        <DropdownMenuTrigger
          className="inline-flex h-9 items-center gap-1.5 rounded-md px-1.5 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
          aria-label={t('common.userMenu')}
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
            {userInitial}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </DropdownMenuTrigger>
      )}
      <DropdownMenuContent
        side={variant === 'sidebar' ? 'top' : undefined}
        align={variant === 'sidebar' ? 'start' : 'end'}
        sideOffset={8}
        className="z-50 min-w-[14rem] rounded-md border border-border bg-surface-elevated p-1 shadow-lg"
      >
        <div className="px-2 py-1.5 text-xs text-muted-foreground">
          <div className="truncate">{userEmail}</div>
        </div>
        <DropdownMenuItem
          onSelect={() => signOut()}
          className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-foreground outline-none hover:bg-muted focus:bg-muted"
        >
          <LogOut className="h-4 w-4" />
          <span>{t('nav.signOut')}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
