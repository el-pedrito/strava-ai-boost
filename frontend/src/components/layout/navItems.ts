import { LayoutDashboard, Sparkles, Gauge, Settings2, User, Watch } from 'lucide-react';
import type { ComponentType } from 'react';
import { isWorkoutExportEnabled } from '@/config';

export interface NavItem {
  to: string;
  labelKey: string;
  /** Shorter label for the 6-slot mobile bottom bar, when the full one is too long. */
  shortLabelKey?: string;
  Icon: ComponentType<{ className?: string; size?: number; strokeWidth?: number }>;
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', Icon: LayoutDashboard },
  { to: '/coach', labelKey: 'nav.coach', Icon: Sparkles },
  { to: '/quality', labelKey: 'nav.quality', Icon: Gauge },
  { to: '/config', labelKey: 'nav.configuration', shortLabelKey: 'nav.configurationShort', Icon: Settings2 },
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
