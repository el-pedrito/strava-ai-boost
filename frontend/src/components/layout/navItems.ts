import { LayoutDashboard, ListChecks, HeartPulse, Sparkles, Gauge, Activity, Settings2, User, Watch } from 'lucide-react';
import type { ComponentType } from 'react';
import { isWorkoutExportEnabled } from '@/config';

export interface NavItem {
  to: string;
  labelKey: string;
  /** Shorter label for the 6-slot mobile bottom bar, when the full one is too long. */
  shortLabelKey?: string;
  Icon: ComponentType<{ className?: string; size?: number; strokeWidth?: number }>;
  /** false = sidebar only, hidden from the mobile bottom bar. */
  mobile?: boolean;
}

/**
 * Mobile bar keeps the daily pages (6 slots max with the plan flag on). The
 * admin pages (Quality, Monitoring, Config) stay one tap away in the drawer.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', Icon: LayoutDashboard },
  { to: '/activities', labelKey: 'nav.activities', Icon: ListChecks },
  { to: '/health', labelKey: 'nav.health', Icon: HeartPulse },
  { to: '/coach', labelKey: 'nav.coach', Icon: Sparkles },
  { to: '/quality', labelKey: 'nav.quality', Icon: Gauge, mobile: false },
  { to: '/monitoring', labelKey: 'nav.monitoring', shortLabelKey: 'nav.monitoringShort', Icon: Activity, mobile: false },
  { to: '/config', labelKey: 'nav.configuration', shortLabelKey: 'nav.configurationShort', Icon: Settings2, mobile: false },
  { to: '/preferences', labelKey: 'nav.preferences', shortLabelKey: 'nav.preferencesShort', Icon: User },
];

/** Apple Watch export of the Campus plan, shown only behind `workoutExportEnabled`. */
export const PLAN_NAV_ITEM: NavItem = { to: '/plan', labelKey: 'nav.plan', Icon: Watch };

/**
 * Navigation entries to render. The plan entry sits right after Coach, its
 * closest neighbour, and only when the runtime flag is on.
 */
export function getNavItems(workoutExportEnabled: boolean = isWorkoutExportEnabled()): NavItem[] {
  if (!workoutExportEnabled) return NAV_ITEMS;
  const items = [...NAV_ITEMS];
  const coachIndex = items.findIndex((item) => item.to === '/coach');
  items.splice(coachIndex + 1, 0, PLAN_NAV_ITEM);
  return items;
}
