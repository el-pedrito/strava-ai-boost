import { Fragment } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/cn';

export type StepStatus = 'done' | 'current' | 'todo';

export interface StepperStep {
  label: string;
  status: StepStatus;
}

export interface StepperProps {
  steps: StepperStep[];
  current: number;
  className?: string;
  ariaLabel?: string;
}

function statusClasses(status: StepStatus): {
  circle: string;
  label: string;
  line: string;
} {
  switch (status) {
    case 'done':
      return {
        circle: 'bg-success text-success-foreground border-success',
        label: 'text-foreground',
        line: 'bg-success',
      };
    case 'current':
      return {
        circle:
          'bg-primary/10 text-primary border-primary ring-4 ring-primary/15',
        label: 'text-foreground font-medium',
        line: 'bg-border',
      };
    case 'todo':
    default:
      return {
        circle: 'bg-transparent text-muted-foreground border-border',
        label: 'text-muted-foreground',
        line: 'bg-border',
      };
  }
}

export function Stepper({ steps, current, className, ariaLabel }: StepperProps) {
  return (
    <ol
      aria-label={ariaLabel}
      className={cn(
        'flex w-full flex-col gap-4 md:flex-row md:items-start md:gap-0',
        className,
      )}
    >
      {steps.map((step, idx) => {
        const c = statusClasses(step.status);
        const isLast = idx === steps.length - 1;
        const isCurrent = idx === current;
        const stepNumber = idx + 1;
        return (
          <Fragment key={`${step.label}-${idx}`}>
            {/* Mobile vertical row + desktop horizontal item */}
            <li
              aria-current={isCurrent ? 'step' : undefined}
              className={cn(
                'flex items-center gap-3 md:flex-col md:items-center md:gap-2 md:flex-1 md:min-w-0',
              )}
            >
              <div className="flex items-start gap-3 md:flex-col md:items-center md:gap-2">
                <span
                  className={cn(
                    'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border-2 text-sm font-semibold transition-all duration-200',
                    c.circle,
                  )}
                  aria-hidden="true"
                >
                  {step.status === 'done' ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <span>{stepNumber}</span>
                  )}
                </span>
              </div>
              <span
                className={cn(
                  'text-sm transition-colors duration-200 md:mt-1 md:text-center md:text-xs',
                  c.label,
                )}
              >
                {step.label}
              </span>
            </li>

            {/* Connector line */}
            {!isLast ? (
              <>
                {/* Vertical for mobile */}
                <li
                  aria-hidden="true"
                  className="flex md:hidden ml-4 h-6 w-0.5 -my-2"
                >
                  <span className={cn('h-full w-full transition-colors', c.line)} />
                </li>
                {/* Horizontal for desktop */}
                <li
                  aria-hidden="true"
                  className="hidden md:flex md:flex-1 md:items-center md:px-2 md:pt-4"
                >
                  <span
                    className={cn(
                      'h-0.5 w-full rounded-full transition-colors duration-200',
                      c.line,
                    )}
                  />
                </li>
              </>
            ) : null}
          </Fragment>
        );
      })}
    </ol>
  );
}
