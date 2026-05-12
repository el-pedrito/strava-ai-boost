import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/cn';
import { NAV_ITEMS } from './navItems';

export function BottomNav() {
  const { t } = useTranslation();

  return (
    <nav
      aria-label="Primary mobile navigation"
      className="fixed bottom-0 left-0 right-0 z-40 flex h-16 items-stretch justify-around border-t border-border bg-surface-elevated/95 backdrop-blur md:hidden"
    >
      {NAV_ITEMS.map((item) => {
        const Icon = item.Icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'flex flex-1 flex-col items-center justify-center gap-0.5 px-1 text-[10px] font-medium transition-colors',
                isActive
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              )
            }
          >
            <Icon className="h-5 w-5" strokeWidth={2} />
            <span className="truncate">{t(item.labelKey)}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
