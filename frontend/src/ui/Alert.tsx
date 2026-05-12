import { forwardRef, type HTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { AlertCircle, CheckCircle2, Info, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/cn';

const alertVariants = cva(
  'relative w-full rounded-lg border px-4 py-3 flex gap-3 items-start',
  {
    variants: {
      variant: {
        info: 'bg-info/5 border-info/30 text-foreground',
        success: 'bg-success/5 border-success/30 text-foreground',
        warning: 'bg-warning/5 border-warning/30 text-foreground',
        error: 'bg-danger/5 border-danger/30 text-foreground',
      },
    },
    defaultVariants: {
      variant: 'info',
    },
  }
);

const iconMap = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
};

const iconColorMap = {
  info: 'text-info',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-danger',
};

export interface AlertProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  ({ className, variant = 'info', children, ...props }, ref) => {
    const Icon = iconMap[variant ?? 'info'];
    const iconColor = iconColorMap[variant ?? 'info'];
    return (
      <div ref={ref} role="alert" className={cn(alertVariants({ variant }), className)} {...props}>
        <Icon className={cn('h-5 w-5 mt-0.5 flex-shrink-0', iconColor)} aria-hidden="true" />
        <div className="flex-1 text-sm leading-relaxed">{children}</div>
      </div>
    );
  }
);
Alert.displayName = 'Alert';
