import { LayoutDashboard, Sparkles, Gauge, Settings2, User } from 'lucide-react';
import type { ComponentType } from 'react';

export interface NavItem {
  to: string;
  labelKey: string;
  Icon: ComponentType<{ className?: string; size?: number; strokeWidth?: number }>;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', Icon: LayoutDashboard },
  { to: '/coach', labelKey: 'nav.coach', Icon: Sparkles },
  { to: '/quality', labelKey: 'nav.quality', Icon: Gauge },
  { to: '/config', labelKey: 'nav.configuration', Icon: Settings2 },
  { to: '/preferences', labelKey: 'nav.preferences', Icon: User },
];
