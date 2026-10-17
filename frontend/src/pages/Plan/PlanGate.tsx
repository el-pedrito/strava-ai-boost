import { lazy } from 'react';
import { Navigate } from 'react-router';
import { isWorkoutExportEnabled } from '@/config';

const PlanPage = lazy(() => import('./PlanPage.tsx').then((m) => ({ default: m.PlanPage })));

/**
 * `/plan` route element. Behind `workoutExportEnabled`: when the flag is off the
 * page chunk is never fetched and the route sends the user back to the dashboard.
 */
export function PlanGate() {
  if (!isWorkoutExportEnabled()) return <Navigate to="/" replace />;
  return <PlanPage />;
}
