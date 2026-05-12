import { forwardRef, useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { animate, useMotionValue, useReducedMotion } from 'framer-motion';
import { cn } from '@/lib/cn';

export interface KPIProps extends HTMLAttributes<HTMLDivElement> {
  label: string;
  value: ReactNode;
  unit?: string;
  delta?: { value: number; label?: string; positiveIsGood?: boolean };
  icon?: ReactNode;
  loading?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const ANIMATION_DURATION_MS = 600;
const DEBOUNCE_MS = 300;

function isFiniteNumeric(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function tryParseNumber(value: ReactNode): number | null {
  if (isFiniteNumeric(value)) return value;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed === '') return null;
    // Avoid matching strings with units or mixed content (e.g., "12 km", "5m30s")
    if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return null;
    const n = Number(trimmed);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatNumber(value: number, isInteger: boolean): string {
  if (isInteger) return String(Math.round(value));
  return value.toFixed(1);
}

interface AnimatedNumberProps {
  value: number;
  ariaLabel?: string;
}

function AnimatedNumber({ value, ariaLabel }: AnimatedNumberProps) {
  const reduceMotion = useReducedMotion();
  const motionValue = useMotionValue(0);
  const [display, setDisplay] = useState<string>(() =>
    formatNumber(reduceMotion ? value : 0, Number.isInteger(value))
  );
  const debounceRef = useRef<number | null>(null);
  const isInteger = Number.isInteger(value);

  useEffect(() => {
    if (reduceMotion) {
      motionValue.set(value);
      setDisplay(formatNumber(value, isInteger));
      return;
    }

    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(() => {
      const controls = animate(motionValue, value, {
        duration: ANIMATION_DURATION_MS / 1000,
        ease: [0.215, 0.61, 0.355, 1], // easeOutCubic
        onUpdate: (latest) => {
          setDisplay(formatNumber(latest, isInteger));
        },
      });
      return () => controls.stop();
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [value, isInteger, motionValue, reduceMotion]);

  return (
    <span aria-live="polite" aria-label={ariaLabel ?? formatNumber(value, isInteger)}>
      {display}
    </span>
  );
}

export const KPI = forwardRef<HTMLDivElement, KPIProps>(
  (
    { className, label, value, unit, delta, icon, loading, size = 'md', ...props },
    ref
  ) => {
    const valueSize = size === 'lg' ? 'text-5xl' : size === 'sm' ? 'text-2xl' : 'text-4xl';
    const labelSize = size === 'sm' ? 'text-[11px]' : 'text-xs';

    let deltaTone: 'success' | 'danger' | 'muted' = 'muted';
    let DeltaIcon = Minus;
    if (delta && delta.value !== 0) {
      const positive = delta.value > 0;
      const positiveIsGood = delta.positiveIsGood ?? true;
      const isGood = positive === positiveIsGood;
      deltaTone = isGood ? 'success' : 'danger';
      DeltaIcon = positive ? ArrowUpRight : ArrowDownRight;
    }

    const numericValue = tryParseNumber(value);

    return (
      <div
        ref={ref}
        className={cn(
          'flex flex-col gap-2 rounded-xl border border-border bg-surface p-5 transition-all hover:border-border-strong',
          className
        )}
        {...props}
      >
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              'uppercase tracking-wider font-medium text-muted-foreground',
              labelSize
            )}
          >
            {label}
          </span>
          {icon ? <span className="text-muted-foreground">{icon}</span> : null}
        </div>
        <div className="flex items-baseline gap-2">
          {loading ? (
            <div className={cn('h-10 w-24 bg-muted animate-pulse rounded')} />
          ) : (
            <>
              <span className={cn('font-numeric font-semibold leading-none text-foreground', valueSize)}>
                {numericValue !== null ? (
                  <AnimatedNumber value={numericValue} />
                ) : (
                  value
                )}
              </span>
              {unit ? (
                <span className="text-sm font-medium text-muted-foreground">{unit}</span>
              ) : null}
            </>
          )}
        </div>
        {delta ? (
          <div
            className={cn(
              'inline-flex items-center gap-1 text-xs font-medium',
              deltaTone === 'success' && 'text-success',
              deltaTone === 'danger' && 'text-danger',
              deltaTone === 'muted' && 'text-muted-foreground'
            )}
          >
            <DeltaIcon className="h-3 w-3" />
            <span>
              {delta.value > 0 ? '+' : ''}
              {delta.value}
              {typeof delta.value === 'number' && !Number.isInteger(delta.value) ? '' : '%'}
            </span>
            {delta.label ? <span className="text-muted-foreground"> {delta.label}</span> : null}
          </div>
        ) : null}
      </div>
    );
  }
);
KPI.displayName = 'KPI';
