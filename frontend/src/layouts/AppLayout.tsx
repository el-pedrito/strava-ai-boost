import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import AppLayout from '@cloudscape-design/components/app-layout';
import SideNavigation from '@cloudscape-design/components/side-navigation';
import Flashbar from '@cloudscape-design/components/flashbar';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import { useFlashMessages } from '../hooks/useFlashMessages.ts';
import { createContext, useContext } from 'react';

type AddMessageFn = (type: 'success' | 'error' | 'warning' | 'info', content: string) => void;

const FlashContext = createContext<AddMessageFn>(() => {});

export function useFlash() {
  return useContext(FlashContext);
}

const NAV_ITEMS = [
  { type: 'link' as const, text: 'Dashboard', href: '/' },
  { type: 'link' as const, text: 'Configuration', href: '/config' },
  { type: 'link' as const, text: 'Preferences', href: '/preferences' },
];

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
      <AppLayout
        toolsHide
        navigationHide={false}
        navigation={
          <SideNavigation
            header={{ text: 'Strava AI Boost', href: '/' }}
            activeHref={location.pathname}
            items={NAV_ITEMS}
            onFollow={(e) => {
              e.preventDefault();
              navigate(e.detail.href);
            }}
          />
        }
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
