export function statusType(s: string): 'success' | 'in-progress' | 'error' | 'info' {
  if (s === 'completed') return 'success';
  if (s === 'processing') return 'in-progress';
  if (s === 'error') return 'error';
  return 'info';
}

export function agentcoreType(s: string): 'success' | 'warning' | 'error' {
  if (s === 'healthy') return 'success';
  if (s === 'not_configured') return 'warning';
  return 'error';
}

export function agentcoreLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatModuleName(name: string): { label: string; className: string } {
  if (name === 'campus_coach' || name.toLowerCase().includes('campus')) {
    return { label: 'Campus Coach', className: 'badge-campus' };
  }
  if (name === 'enduraw' || name.toLowerCase().includes('enduraw')) {
    return { label: 'Enduraw', className: 'badge-enduraw' };
  }
  return { label: name, className: '' };
}

export const MODULE_DISPLAY_NAMES: Record<string, string> = {
  campus_coach: 'Campus Coach',
  enduraw: 'Enduraw',
  intervals_icu: 'Intervals.icu',
};

export const ACTIVITY_TYPE_ICONS: Record<string, string> = {
  Run: '\u{1F3C3}',
  Ride: '\u{1F6B4}',
  Swim: '\u{1F3CA}',
  Walk: '\u{1F6B6}',
  Hike: '\u26F0\uFE0F',
  WeightTraining: '\u{1F3CB}\uFE0F',
  Workout: '\u{1F4AA}',
  Yoga: '\u{1F9D8}',
  VirtualRide: '\u{1F6B4}',
  VirtualRun: '\u{1F3C3}',
  TrailRun: '\u26F0\uFE0F',
};

export function getActivityIcon(type?: string): string {
  if (!type) return '';
  return ACTIVITY_TYPE_ICONS[type] || '';
}
