import { useLocation, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, Sun, Moon } from 'lucide-react';
import { useTheme } from '@/theme/ThemeProvider';
import { NAV_ITEMS } from './navItems';
import { UserMenu } from './UserMenu';

interface TopbarProps {
  onMenuClick: () => void;
}

export function Topbar({ onMenuClick }: TopbarProps) {
  const location = useLocation();
  const { t, i18n } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const currentItem = NAV_ITEMS.find((item) =>
    item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to)
  );
  const breadcrumbLabel = currentItem ? t(currentItem.labelKey) : '';

  const nextLang = i18n.language === 'fr' ? 'en' : 'fr';
  const switchLanguage = () => {
    void i18n.changeLanguage(nextLang);
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        aria-label={t('common.openMenu')}
        className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <nav
        aria-label={t('common.breadcrumb')}
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
          aria-label={t('common.switchLanguage', { lang: nextLang.toUpperCase() })}
          className="inline-flex h-9 items-center justify-center rounded-md px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {i18n.language === 'fr' ? 'FR' : 'EN'}
        </button>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? t('login.themeLight') : t('login.themeDark')}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {theme === 'dark' ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>

        <UserMenu variant="topbar" />
      </div>
    </header>
  );
}
