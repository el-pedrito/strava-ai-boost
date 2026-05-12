import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Card } from './Card';
import {
  ActivityIllustration,
  CelebrateIllustration,
  ConnectIllustration,
  FeedbackIllustration,
  RecordsIllustration,
  SearchIllustration,
} from './illustrations';

export type EmptyStateIllustration =
  | 'activity'
  | 'feedback'
  | 'records'
  | 'search'
  | 'connect'
  | 'celebrate';

export interface EmptyStateProps {
  illustration: EmptyStateIllustration;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

const ILLUSTRATIONS = {
  activity: ActivityIllustration,
  feedback: FeedbackIllustration,
  records: RecordsIllustration,
  search: SearchIllustration,
  connect: ConnectIllustration,
  celebrate: CelebrateIllustration,
} as const;

/**
 * Standardised empty state with a custom inline SVG illustration,
 * title, optional description and optional action slot.
 *
 * Wrapped in a `Card variant="flat"` and animated with `animate-fade-in-up`.
 */
export function EmptyState({
  illustration,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  const Illustration = ILLUSTRATIONS[illustration];

  return (
    <Card
      variant="flat"
      padding="lg"
      className={cn('animate-fade-in-up', className)}
    >
      <div className="flex flex-col items-center text-center gap-4">
        <Illustration className="w-full max-w-[200px] h-auto text-muted-foreground" />
        <div className="flex flex-col items-center gap-1.5">
          <h3 className="text-lg font-semibold text-foreground tracking-tight">
            {title}
          </h3>
          {description ? (
            <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
              {description}
            </p>
          ) : null}
        </div>
        {action ? <div className="mt-2">{action}</div> : null}
      </div>
    </Card>
  );
}
