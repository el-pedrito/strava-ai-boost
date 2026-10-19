/**
 * "habituel 52 ms ↓ −4,0 ms": the usual value of a recovery signal and the
 * signed, toned difference to it. Shared by the Home Recovery card and the
 * Santé page. The arrow and the sign carry the direction, the colour only
 * repeats it.
 */
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowRight, ArrowUp } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { HealthMetric } from '@/types/home';
import { formatDiff, formatMetricText } from '../format';
import { TONE_TEXT } from './tones';

export type UsualKey = 'hrv' | 'resting_hr' | 'sleep_s' | 'form';

const DIFF_TONE = { good: 'success', bad: 'warning', neutral: 'muted' } as const;

/** Sleep compares to the last 7 nights, the other signals to 60 days. */
export function usualBaseline(key: UsualKey, metric: HealthMetric): number | null {
  return (key === 'sleep_s' ? metric.baseline_7d : metric.baseline_60d) ?? null;
}

/** The payload's delta, or value − baseline when only those two are present. */
export function usualDelta(key: UsualKey, metric: HealthMetric): number | null {
  const baseline = usualBaseline(key, metric);
  if (metric.delta != null) return metric.delta;
  return metric.value != null && baseline != null ? metric.value - baseline : null;
}

export function UsualLine({
  metricKey,
  metric,
  testIdPrefix = 'home',
}: {
  metricKey: UsualKey;
  metric: HealthMetric;
  testIdPrefix?: string;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const isSleep = metricKey === 'sleep_s';
  const usual = formatMetricText(metricKey, usualBaseline(metricKey, metric), lang);
  if (usual == null) return null;
  const diff = formatDiff(metricKey, usualDelta(metricKey, metric), lang);
  const windowText = t(isSleep ? 'home.recovery.window7' : 'home.recovery.window60');
  const Arrow = diff?.direction === 'up' ? ArrowUp : diff?.direction === 'down' ? ArrowDown : ArrowRight;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
      <span title={windowText}>
        {t('home.recovery.usual', { value: usual })}
        <span className="sr-only"> ({windowText})</span>
      </span>
      {diff && (
        <span
          className={cn('inline-flex items-center gap-0.5 font-numeric font-semibold', TONE_TEXT[DIFF_TONE[diff.tone]])}
          data-testid={`${testIdPrefix}-diff-${metricKey}`}
          data-tone={diff.tone}
        >
          <Arrow className="h-3 w-3" aria-hidden="true" />
          {diff.text}
        </span>
      )}
    </p>
  );
}
