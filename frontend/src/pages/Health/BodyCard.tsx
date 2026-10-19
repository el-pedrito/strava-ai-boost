/**
 * VO2max and Poids tiles. A tile whose value is null is not rendered; the
 * card is skipped by the page when both are null (`bodyTilesVisible`).
 */
import { useTranslation } from 'react-i18next';
import type { HomeHealth } from '@/types/home';
import { formatMetric } from '../Home/format';
import { CardHead, HomeCard, ValueUnit } from '../Home/blocks/common';
import { AsOfLine } from './ReadinessCard';
import { BODY_TILES as TILES, visibleBodyTiles } from './body';

export function BodyCard({ health }: { health: HomeHealth }) {
  const { t, i18n } = useTranslation();
  const visible = new Set(visibleBodyTiles(health));
  return (
    <HomeCard labelledBy="health-body-title" className="flex flex-col gap-3">
      <CardHead id="health-body-title" title={t('health.body.title')} />
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {TILES.filter((tile) => visible.has(tile.key)).map((tile) => {
          const metric = health[tile.key];
          const formatted = formatMetric(tile.key, metric?.value, i18n.language);
          const unit = formatted?.unit || (tile.unit ? t(tile.unit) : '');
          return (
            <li key={tile.key} className="min-w-0 rounded-lg bg-surface-muted px-3 py-3" data-testid={`health-body-${tile.key}`}>
              <span className="text-sm font-medium text-foreground">{t(tile.label)}</span>
              <p className="mt-1 text-2xl font-semibold leading-tight text-foreground">
                {formatted && <ValueUnit value={formatted.value} unit={unit} />}
              </p>
              <AsOfLine metric={metric} testId={`health-asof-${tile.key}`} />
            </li>
          );
        })}
      </ul>
    </HomeCard>
  );
}
