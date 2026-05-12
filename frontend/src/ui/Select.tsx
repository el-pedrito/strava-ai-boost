import { forwardRef, type SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/cn';

export interface SelectOption {
  value: string;
  label: string;
  description?: string;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'value'> {
  options: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, options, value, onChange, placeholder, disabled, ...props }, ref) => (
    <div className="relative w-full">
      <select
        ref={ref}
        value={value ?? ''}
        onChange={(e) => onChange?.(e.target.value)}
        disabled={disabled}
        className={cn(
          'flex h-11 w-full appearance-none rounded-lg border border-border bg-surface pl-3 pr-9 py-2 text-sm text-foreground transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:border-transparent',
          'disabled:cursor-not-allowed disabled:opacity-50',
          !value && 'text-muted-foreground',
          className
        )}
        {...props}
      >
        {placeholder ? (
          <option value="" disabled hidden>
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.description ? `${option.label} — ${option.description}` : option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  )
);
Select.displayName = 'Select';
