import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { Home } from 'lucide-react';
import { EmptyState, buttonVariants } from '@/ui';

/** Catch-all route inside the Shell: an unknown or stale URL keeps the navigation and a way home. */
export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6">
      <EmptyState
        illustration="search"
        title={t('notFound.title')}
        description={t('notFound.description')}
        action={
          // A real link (not Button asChild: Button renders two children, which Slot rejects).
          <Link to="/" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
            <Home className="h-4 w-4" aria-hidden="true" />
            <span>{t('notFound.backHome')}</span>
          </Link>
        }
      />
    </div>
  );
}
