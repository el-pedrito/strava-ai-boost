import { type ReactNode } from 'react';
import * as Popover from '@radix-ui/react-popover';
import { HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/cn';

export interface InfoTooltipProps {
  /** i18n key prefix, e.g. 'metrics.ctl' — expects {prefix}.title and {prefix}.definition (and optional {prefix}.calculation). */
  i18nKey: string;
  className?: string;
  align?: 'start' | 'center' | 'end';
  side?: 'top' | 'right' | 'bottom' | 'left';
  /** Optional ReactNode to render instead of building from i18n. Useful for free-form content. */
  content?: ReactNode;
}

export function InfoTooltip({
  i18nKey,
  className,
  align = 'end',
  side = 'bottom',
  content,
}: InfoTooltipProps) {
  const { t } = useTranslation();

  const title = t(`${i18nKey}.title`, { defaultValue: '' });
  const definition = t(`${i18nKey}.definition`, { defaultValue: '' });
  const calculation = t(`${i18nKey}.calculation`, { defaultValue: '' });
  const ariaLabel = t('common.metricInfo', { defaultValue: 'About this metric' });

  return (
    <Popover.Root>
      <Popover.Trigger
        type="button"
        aria-label={ariaLabel}
        className={cn(
          'inline-flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground/60 transition-colors',
          'hover:text-muted-foreground hover:bg-muted',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          className,
        )}
      >
        <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side={side}
          align={align}
          sideOffset={6}
          className={cn(
            'z-50 max-w-xs rounded-lg border border-border bg-surface-elevated p-3 shadow-lg',
            'data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'text-foreground'
          )}
        >
          {content ? (
            content
          ) : (
            <div className="flex flex-col gap-1.5">
              {title && <h4 className="text-sm font-semibold leading-tight">{title}</h4>}
              {definition && (
                <p className="text-xs leading-relaxed text-muted-foreground">{definition}</p>
              )}
              {calculation && (
                <p className="text-[11px] leading-relaxed text-muted-foreground/80 mt-1 pt-1 border-t border-border">
                  {calculation}
                </p>
              )}
            </div>
          )}
          <Popover.Arrow className="fill-surface-elevated" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
