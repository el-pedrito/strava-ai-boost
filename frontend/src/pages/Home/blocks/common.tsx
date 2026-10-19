/**
 * Small presentational pieces shared by the Home cards. Status colours use the
 * AA `*-text` tokens (or `text-danger` / `text-info`, which already pass AA on
 * both themes); a status is never conveyed by colour alone.
 */
import { type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Card } from '@/ui';
import { PRIMARY_TEXT, type Tone } from './tones';

const TONE_PILL: Record<Tone, string> = {
  success: 'bg-success/10 text-success-text',
  warning: 'bg-warning/15 text-warning-text',
  danger: 'bg-danger/10 text-danger',
  primary: `bg-primary/10 ring-1 ring-inset ring-primary/40 ${PRIMARY_TEXT}`,
  muted: 'bg-muted text-muted-foreground',
  info: 'bg-info/10 text-info',
};

/** 12 px rounded label with an optional status dot. */
export function Pill({
  tone = 'muted',
  dot = false,
  className,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold leading-none',
        TONE_PILL[tone],
        className
      )}
    >
      {dot && <span className="h-2 w-2 shrink-0 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
}

/** A Home card: surface, 16/20 px padding, never stretched by the grid. */
export function HomeCard({
  labelledBy,
  className,
  children,
}: {
  labelledBy: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card
      variant="elevated"
      padding="none"
      aria-labelledby={labelledBy}
      className={cn('min-w-0 p-4 md:p-5', className)}
      role="region"
    >
      {children}
    </Card>
  );
}

/** Card header row: optional icon, h2 title, and trailing content. */
export function CardHead({
  id,
  icon,
  title,
  children,
  className,
}: {
  id: string;
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1', className)}>
      {icon}
      <h2 id={id} className="text-lg font-semibold tracking-tight text-foreground">
        {title}
      </h2>
      {children}
    </div>
  );
}

/** Number with its unit in smaller muted type, separated by a narrow space. */
export function ValueUnit({ value, unit, className }: { value: string; unit?: string; className?: string }) {
  return (
    <span className={cn('font-numeric', className)}>
      {value}
      {unit ? (
        <span className="ml-0.5 text-xs font-medium text-muted-foreground">{`\u202F${unit}`}</span>
      ) : null}
    </span>
  );
}
