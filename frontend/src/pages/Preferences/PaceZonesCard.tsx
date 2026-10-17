import { useTranslation } from 'react-i18next';
import { Alert, Badge, Card, CardDescription, CardHeader, CardTitle, InfoTooltip } from '@/ui';
import type { PaceZone, PaceZones, PaceZonesSource } from '../../types/index.ts';

const ZONE_LABELS: Record<keyof PaceZones, { number: string; label: string; description: string }> = {
  recovery: { number: 'Z1', label: 'Recovery', description: 'Very easy pace' },
  ef: { number: 'Z2', label: 'EF (Endurance Fond.)', description: 'Easy, conversational' },
  aerobic: { number: 'Z3', label: 'Aerobic', description: 'Active endurance' },
  tempo: { number: 'Z4', label: 'Tempo', description: 'Comfortably hard' },
  sweet_spot: { number: 'Z5', label: 'Sweet Spot', description: 'Tempo to threshold' },
  seuil_60: { number: 'Z6', label: 'Threshold 60', description: 'Lactate threshold, 60min effort' },
  seuil_30: { number: 'Z7', label: 'Threshold 30', description: 'Critical, 30min effort' },
  allure_marathon: { number: 'Z8', label: 'Marathon Pace', description: 'Target marathon pace' },
  allure_semi: { number: 'Z9', label: 'Half-Marathon Pace', description: 'Target half pace' },
  interval: { number: 'Z10', label: 'Intervals / VO2max', description: 'Fast intervals' },
};

export type ZoneMap = Partial<Record<keyof PaceZones, PaceZone>>;

export interface PaceZonesCardProps {
  source: PaceZonesSource;
  /** Zones to display: Campus zones for campus/campus_stale, legacy manual zones otherwise. */
  zones: ZoneMap | null;
  /** ISO week label of the Campus source week, e.g. '2026-W43'. */
  week: string | null;
  /** ISO timestamp of the last Campus sync that wrote the zones. */
  syncedAt: string | null;
}

/** '2026-W43' -> '43'. Anything else is shown as received rather than guessed. */
function weekNumber(label: string): string {
  const m = /^\d{4}-W(\d{1,2})$/.exec(label);
  return m ? String(parseInt(m[1], 10)) : label;
}

/** Local HH:MM of an ISO timestamp, or null when it does not parse. */
function syncTime(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

/**
 * Read-only pace zones. Campus Coach is the single source of the zones: the
 * page never edits them and the save never sends them.
 */
export function PaceZonesCard({ source, zones, week, syncedAt }: PaceZonesCardProps) {
  const { t } = useTranslation();
  const fromCampus = source === 'campus' || source === 'campus_stale';
  const hasZones = !!zones && Object.keys(zones).length > 0;

  const headerParts = ['Campus'];
  if (week) headerParts.push(t('preferences.zones.week', { week: weekNumber(week) }));
  const time = syncedAt ? syncTime(syncedAt) : null;
  if (time) headerParts.push(t('preferences.zones.synced', { time }));

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <CardTitle>{t('preferences.zones.title')}</CardTitle>
            <InfoTooltip i18nKey="preferences.zones.help" align="start" />
          </div>
          <CardDescription>{t('preferences.zones.description')}</CardDescription>
        </div>
      </CardHeader>

      {fromCampus && (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span data-testid="pace-zones-source">{headerParts.join(' · ')}</span>
          {source === 'campus_stale' && (
            <Badge variant="warning" size="sm">
              {t('preferences.zones.stale')}
            </Badge>
          )}
        </div>
      )}

      {!fromCampus && (
        <Alert variant="info" className="mb-4">
          {hasZones ? t('preferences.zones.awaitingSync') : t('preferences.zones.none')}
        </Alert>
      )}

      {hasZones && (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {(Object.keys(ZONE_LABELS) as Array<keyof PaceZones>).map((zoneKey) => {
            const zone = zones?.[zoneKey];
            const meta = ZONE_LABELS[zoneKey];
            return (
              <li
                key={zoneKey}
                data-testid={`pace-zone-${zoneKey}`}
                className="flex flex-col gap-2 rounded-lg border border-border bg-surface-muted p-3"
              >
                <div className="flex items-baseline gap-2">
                  <Badge variant="primary" size="sm">
                    {meta.number}
                  </Badge>
                  <span className="font-medium text-sm text-foreground">{meta.label}</span>
                </div>
                <p className="text-xs text-muted-foreground">{meta.description}</p>
                <p className="font-numeric tabular-nums text-sm text-foreground">
                  {zone?.min && zone?.max ? `${zone.min} - ${zone.max} /km` : '-'}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
