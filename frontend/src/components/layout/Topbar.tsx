import { useLocation, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, Sun, Moon, LogOut, ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@radix-ui/react-dropdown-menu';
import { useTheme } from '@/theme/ThemeProvider';
import { useAuth } from '@/auth/AuthContext';
import { cn } from '@/lib/cn';
import { NAV_ITEMS } from './navItems';

interface TopbarProps {
  onMenuClick: () => void;
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();
  const { user, signOut } = useAuth();

  const currentItem = NAV_ITEMS.find((item) =>
    item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to)
  );
  const breadcrumbLabel = currentItem ? t(currentItem.labelKey) : '';

  const userEmail = user?.getUsername() ?? '';
  const userInitial = userEmail.charAt(0).toUpperCase() || 'U';

  const nextLang = i18n.language === 'fr' ? 'en' : 'fr';
  const switchLanguage = () => {
    void i18n.changeLanguage(nextLang);
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open menu"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <nav
        aria-label="Breadcrumb"
        className="hidden min-w-0 flex-1 items-center gap-2 text-sm md:flex"
      >
        <Link
          to="/"
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          Strava AI Boost
        </Link>
        {breadcrumbLabel && location.pathname !== '/' && (
          <>
            <span className="text-muted-foreground/60" aria-hidden="true">
              /
            </span>
            <span className="truncate text-foreground">{breadcrumbLabel}</span>
          </>
        )}
      </nav>

      <div className="flex flex-1 items-center justify-end gap-1 md:flex-none">
        <button
          type="button"
          onClick={switchLanguage}
          aria-label={`Switch language to ${nextLang.toUpperCase()}`}
          className="inline-flex h-9 items-center justify-center rounded-md px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {i18n.language === 'fr' ? 'FR' : 'EN'}
        </button>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'inline-flex h-9 items-center gap-1.5 rounded-md px-1.5 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden'
            )}
            aria-label="User menu"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
              {userInitial}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
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
    </header>
  );
}
