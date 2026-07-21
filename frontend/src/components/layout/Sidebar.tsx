import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { cn } from '@/lib/cn';
import { NAV_ITEMS } from './navItems';
import { UserMenu } from './UserMenu';

interface SidebarProps {
  collapsed?: boolean;
  width?: number;
  onItemClick?: () => void;
  onToggleCollapse?: () => void;
}

export function Sidebar({ collapsed = false, width, onItemClick, onToggleCollapse }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-surface',
        // when width prop is provided, w-* classes are ignored (inline style wins)
        !width && (collapsed ? 'w-16' : 'w-64')
      )}
      style={width ? { width: `${width}px` } : undefined}
    >
      <div
        className={cn(
          'flex items-center gap-3 border-b border-border',
          collapsed ? 'h-14 justify-center px-0' : 'h-14 px-4'
        )}
      >
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 ring-1 ring-primary/30"
          aria-hidden="true"
        >
          <span className="block h-4 w-1 rounded-full bg-primary" />
        </div>
        {!collapsed && (
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate text-sm font-semibold text-foreground">
              Strava AI Boost
            </span>
            <span className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
              Performance toolkit
            </span>
          </div>
        )}
        {onToggleCollapse && (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
            className={cn(
              'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              collapsed && 'absolute right-1 top-3'
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
            ) : (
              <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
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
        <UserMenu variant="sidebar" collapsed={collapsed} />
      </div>
    </aside>
  );
}
