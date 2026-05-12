import { CircleCheck, CircleAlert, TriangleAlert, Info, X } from 'lucide-react';
import type { ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { cn } from '@/lib/cn';
import type { FlashItem, FlashType } from './flash';

interface FlashToastsProps {
  items: FlashItem[];
}

const ICON_MAP: Record<FlashType, ComponentType<{ className?: string }>> = {
  success: CircleCheck,
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

const TONE_MAP: Record<FlashType, string> = {
  success: 'border-success/40 text-success',
  error: 'border-danger/40 text-danger',
  warning: 'border-warning/40 text-warning',
  info: 'border-info/40 text-info',
};

export function FlashToasts({ items }: FlashToastsProps) {
  const { t } = useTranslation();
  const reduceMotion = useReducedMotion();

  // Always render the live region so screen readers can announce changes,
  // even when the visible list is empty.
  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed right-4 top-16 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {items.map((item) => {
          const Icon = ICON_MAP[item.type];
          return (
            <motion.div
              key={item.id}
              role="status"
              layout
              initial={reduceMotion ? { opacity: 0 } : { x: 20, opacity: 0 }}
              animate={reduceMotion ? { opacity: 1 } : { x: 0, opacity: 1 }}
              exit={reduceMotion ? { opacity: 0 } : { x: 20, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className={cn(
                'pointer-events-auto flex items-start gap-3 rounded-lg border bg-surface-elevated p-3 shadow-lg',
                TONE_MAP[item.type]
              )}
            >
              <Icon className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="flex-1 text-sm leading-snug text-foreground">
                {item.content}
              </p>
              <button
                type="button"
                onClick={item.onDismiss}
                aria-label={t('common.dismiss')}
                className="-m-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
