import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import AppLayout from '@cloudscape-design/components/app-layout';
import TopNavigation from '@cloudscape-design/components/top-navigation';
import Flashbar from '@cloudscape-design/components/flashbar';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import { useFlashMessages } from '../hooks/useFlashMessages.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { createContext, useContext } from 'react';
import { useTranslation } from 'react-i18next';

type AddMessageFn = (type: 'success' | 'error' | 'warning' | 'info', content: string) => void;

const FlashContext = createContext<AddMessageFn>(() => {});

export function useFlash() {
  return useContext(FlashContext);
}

export function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { items, addMessage } = useFlashMessages();
  const { signOut } = useAuth();
  const { t, i18n } = useTranslation();

  const BREADCRUMB_MAP: Record<string, string> = {
    '/': t('nav.dashboard'),
    '/config': t('nav.configuration'),
    '/preferences': t('nav.preferences'),
    '/quality': t('nav.quality'),
    '/coach': t('nav.coach'),
  };

  const breadcrumbs = [
    { text: 'Strava AI Boost', href: '/' },
    ...(location.pathname !== '/'
      ? [{ text: BREADCRUMB_MAP[location.pathname] || '', href: location.pathname }]
      : []),
  ];

  return (
    <FlashContext.Provider value={addMessage}>
      <div id="top-nav">
        <TopNavigation
          identity={{
            href: '/',
            title: 'AI Boost for Strava',
            logo: {
              src: '/logo.png',
              alt: 'Strava AI Boost',
            },
          }}
          utilities={[
            { type: 'button', text: location.pathname === '/' ? `[ ${t('nav.dashboard')} ]` : t('nav.dashboard'), onClick: () => navigate('/') },
            { type: 'button', text: location.pathname === '/config' ? `[ ${t('nav.configuration')} ]` : t('nav.configuration'), onClick: () => navigate('/config') },
            { type: 'button', text: location.pathname === '/preferences' ? `[ ${t('nav.preferences')} ]` : t('nav.preferences'), onClick: () => navigate('/preferences') },
            { type: 'button', text: location.pathname === '/quality' ? `[ ${t('nav.quality')} ]` : t('nav.quality'), onClick: () => navigate('/quality') },
            { type: 'button', text: location.pathname === '/coach' ? `[ ${t('nav.coach')} ]` : t('nav.coach'), onClick: () => navigate('/coach') },
            { type: 'button', text: i18n.language === 'fr' ? '🇬🇧' : '🇫🇷', onClick: () => i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr') },
            { type: 'button', text: t('nav.signOut'), onClick: () => signOut() },
          ]}
          i18nStrings={{ overflowMenuTriggerText: 'More', overflowMenuTitleText: 'All' }}
        />
      </div>
      <AppLayout
        toolsHide
        navigationHide
        headerSelector="#top-nav"
        breadcrumbs={
          <BreadcrumbGroup
            items={breadcrumbs}
            onFollow={(e) => {
              e.preventDefault();
              navigate(e.detail.href);
            }}
          />
        }
        notifications={<Flashbar items={items} />}
        content={<Outlet />}
      />
    </FlashContext.Provider>
  );
}
