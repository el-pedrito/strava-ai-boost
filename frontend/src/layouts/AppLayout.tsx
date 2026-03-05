import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import AppLayout from '@cloudscape-design/components/app-layout';
import TopNavigation from '@cloudscape-design/components/top-navigation';
import Flashbar from '@cloudscape-design/components/flashbar';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import { useFlashMessages } from '../hooks/useFlashMessages.ts';
import { createContext, useContext } from 'react';

type AddMessageFn = (type: 'success' | 'error' | 'warning' | 'info', content: string) => void;

const FlashContext = createContext<AddMessageFn>(() => {});

export function useFlash() {
  return useContext(FlashContext);
}

const BREADCRUMB_MAP: Record<string, string> = {
  '/': 'Dashboard',
  '/config': 'Configuration',
  '/preferences': 'Preferences',
};

export function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { items, addMessage } = useFlashMessages();

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
            { type: 'button', text: location.pathname === '/' ? '[ Dashboard ]' : 'Dashboard', onClick: () => navigate('/') },
            { type: 'button', text: location.pathname === '/config' ? '[ Configuration ]' : 'Configuration', onClick: () => navigate('/config') },
            { type: 'button', text: location.pathname === '/preferences' ? '[ Preferences ]' : 'Preferences', onClick: () => navigate('/preferences') },
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
