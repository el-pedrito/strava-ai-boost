import { forwardRef } from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';
import { cn } from '@/lib/cn';

export interface ToggleProps {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
  className?: string;
  id?: string;
  'aria-label'?: string;
}

export const Toggle = forwardRef<HTMLButtonElement, ToggleProps>(
  ({ checked, onCheckedChange, disabled, label, className, id, ...props }, ref) => {
    const switchEl = (
      <SwitchPrimitive.Root
        ref={ref}
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className={cn(
          'peer inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
          'disabled:cursor-not-allowed disabled:opacity-50',
          'data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted-foreground/30',
          className
        )}
        {...props}
      >
        <SwitchPrimitive.Thumb
          className={cn(
            'pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform',
            'data-[state=checked]:translate-x-[18px] data-[state=unchecked]:translate-x-0.5'
          )}
        />
      </SwitchPrimitive.Root>
    );
    if (!label) return switchEl;
    return (
      <label className="inline-flex items-center gap-2 cursor-pointer select-none">
        {switchEl}
        <span className="text-sm text-foreground">{label}</span>
      </label>
    );
  }
);
Toggle.displayName = 'Toggle';
