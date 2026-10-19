/**
 * "Prêt pour aujourd'hui ?": VFC, FC repos, Sommeil and Fraîcheur, each with a
 * status dot plus a word, its value, the usual value and the difference, and
 * the date of the measurement ("ancien · au 17 oct." when it is not today's).
 */
import { useTranslation } from 'react-i18next';
import { InfoTooltip } from '@/ui';
import type { HealthMetric, HomeHealth } from '@/types/home';
import { formatMetric, formatShortDate } from '../Home/format';
import { CardHead, HomeCard, Pill, ValueUnit } from '../Home/blocks/common';
import { INFO_HIT, type Tone } from '../Home/blocks/tones';
import { UsualLine } from '../Home/blocks/UsualLine';
import { readinessItems, type ReadinessItem, type ReadinessKey, type ReadinessStatus } from './readiness';

const LABEL: Record<ReadinessKey, string> = {
  hrv: 'home.health.hrv',
  resting_hr: 'home.health.restingHr',
  sleep_s: 'home.health.sleep',
  form: 'health.ready.formLabel',
};

const INFO: Record<ReadinessKey, string> = {
  hrv: 'metrics.hrv',
  resting_hr: 'metrics.restinghr',
  sleep_s: 'metrics.sleep',
  form: 'metrics.tsb',
};

const STATUS_TONE: Record<ReadinessStatus, Tone> = {
  good: 'success',
  watch: 'warning',
  bad: 'danger',
  uncertain: 'muted',
  missing: 'muted',
};

/** "au 19 oct." or, for a value that is not today's, "ancien · au 17 oct.". */
export function AsOfLine({ metric, testId }: { metric: HealthMetric | null | undefined; testId?: string }) {
  const { t, i18n } = useTranslation();
  const date = formatShortDate(metric?.as_of, i18n.language);
  if (metric?.value == null || date == null) return null;
  return (
    <p
      className={metric.stale ? 'mt-1 text-xs font-semibold text-warning-text' : 'mt-1 text-xs text-muted-foreground'}
      data-testid={testId}
    >
      {t(metric.stale ? 'health.staleAsOf' : 'health.asOf', { date })}
    </p>
  );
}

function ReadinessTile({ item, metric, formIncomplete }: { item: ReadinessItem; metric: HealthMetric | null; formIncomplete: boolean }) {
  const { t, i18n } = useTranslation();
  const value = formatMetric(item.key, metric?.value, i18n.language);
  return (
    <li
      className="min-w-0 rounded-lg bg-surface-muted px-3 py-3"
      data-testid={`health-ready-${item.key}`}
      data-status={item.status}
    >
      <div className="flex min-h-6 flex-wrap items-center gap-x-1 gap-y-1">
        <span className="text-sm font-medium text-foreground">{t(LABEL[item.key])}</span>
        <InfoTooltip i18nKey={INFO[item.key]} className={INFO_HIT} />
        <Pill tone={STATUS_TONE[item.status]} dot className="ml-auto">
          {t(`health.ready.status.${item.status}`)}
        </Pill>
      </div>
      <p className="mt-1 text-2xl font-semibold leading-tight text-foreground">
        {value ? <ValueUnit value={value.value} unit={value.unit} /> : <span className="text-muted-foreground">{t('home.na')}</span>}
      </p>
      {metric && item.key !== 'form' && <UsualLine metricKey={item.key} metric={metric} testIdPrefix="health" />}
      {item.key === 'form' && item.zone && (
        <p className="mt-1 text-xs text-muted-foreground">{t(`home.recovery.formZone.${item.zone}`)}</p>
      )}
      {item.key === 'form' && formIncomplete && value && (
        <p className="mt-1 text-xs font-semibold text-warning-text">{t('health.ready.formUnreliable')}</p>
      )}
      <AsOfLine metric={metric} testId={`health-asof-${item.key}`} />
    </li>
  );
}

export function ReadinessCard({ health, formIncomplete }: { health: HomeHealth; formIncomplete: boolean }) {
  const { t } = useTranslation();
  const items = readinessItems(health, { formIncomplete });
  return (
    <HomeCard labelledBy="health-ready-title" className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <CardHead id="health-ready-title" title={t('health.ready.title')} />
        <p className="text-sm text-muted-foreground">{t('health.ready.intro')}</p>
      </div>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <ReadinessTile key={item.key} item={item} metric={health[item.key]} formIncomplete={formIncomplete} />
        ))}
      </ul>
    </HomeCard>
  );
}
