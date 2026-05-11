import { NavLink } from 'react-router-dom';
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
import { NAV_ITEMS } from './navItems';

interface SidebarProps {
  collapsed?: boolean;
  onItemClick?: () => void;
}

export function Sidebar({ collapsed = false, onItemClick }: SidebarProps) {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();

  const userEmail = user?.getUsername() ?? '';
  const userInitial = userEmail.charAt(0).toUpperCase() || 'U';

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-surface',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      <div
        className={cn(
          'flex items-center gap-3 border-b border-border px-4',
          collapsed ? 'h-14 justify-center px-0' : 'h-14'
        )}
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 ring-1 ring-primary/30"
          aria-hidden="true"
        >
          <span className="block h-4 w-1 rounded-full bg-primary" />
        </div>
        {!collapsed && (
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="truncate text-sm font-semibold text-foreground">
              Strava AI Boost
            </span>
            <span className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
              Performance toolkit
            </span>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.Icon;
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/'}
                  onClick={onItemClick}
                  className={({ isActive }) =>
                    cn(
                      'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                      collapsed && 'justify-center px-0'
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span
                          aria-hidden="true"
                          className="absolute left-0 top-1 bottom-1 w-[2px] rounded-r bg-primary"
                        />
                      )}
                      <Icon className="h-4 w-4 shrink-0" strokeWidth={2} />
                      {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
                    </>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-2">
        <DropdownMenu>
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
          <DropdownMenuContent
            side="top"
            align="start"
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
      </div>
    </aside>
  );
}
