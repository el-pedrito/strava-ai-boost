/**
 * Strava sport types: which family an activity belongs to, its translated label
 * and its icon. Shared by the Activités list and the activity detail page, so the
 * raw Strava name ("WeightTraining") is never shown to the athlete.
 */
import type { ComponentType } from 'react';
import type { TFunction } from 'i18next';
import {
  Activity as ActivityIcon,
  Bike,
  Dumbbell,
  Flower2,
  Footprints,
  Mountain,
  Waves,
} from 'lucide-react';

export type LucideIcon = ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;

const RUN_TYPES = new Set(['Run', 'TrailRun', 'VirtualRun']);
const STRENGTH_TYPES = new Set(['WeightTraining']);

/** Types with a translated label in `activities.type.*`. */
const LABELLED_TYPES = new Set([
  'Run',
  'TrailRun',
  'VirtualRun',
  'WeightTraining',
  'Workout',
  'Crossfit',
  'Ride',
  'VirtualRide',
  'EBikeRide',
  'Swim',
  'Walk',
  'Hike',
  'Yoga',
]);

/** A run, on road, trail or treadmill: the only family with a pace per km. */
export function isRunType(type?: string | null): boolean {
  return !!type && RUN_TYPES.has(type);
}

/** Renfo / muscu (Strava `WeightTraining`). */
export function isStrengthType(type?: string | null): boolean {
  return !!type && STRENGTH_TYPES.has(type);
}

/** "Course", "Renfo / Muscu"... The raw Strava type only for a sport we do not know. */
export function activityTypeLabel(t: TFunction, type?: string | null): string | null {
  if (!type) return null;
  if (LABELLED_TYPES.has(type)) return t(`activities.type.${type}`);
  return type;
}

export function activityIcon(type?: string | null): LucideIcon {
  switch (type) {
    case 'Run':
    case 'TrailRun':
    case 'VirtualRun':
      return Footprints;
    case 'Ride':
    case 'VirtualRide':
    case 'EBikeRide':
      return Bike;
    case 'Swim':
      return Waves;
    case 'WeightTraining':
    case 'Workout':
    case 'Crossfit':
      return Dumbbell;
    case 'Hike':
    case 'Walk':
      return Mountain;
    case 'Yoga':
      return Flower2;
    default:
      return ActivityIcon;
  }
}
