import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageSquareText } from 'lucide-react';
import { Alert, Card, CardDescription, CardHeader, CardTitle, Label, Toggle } from '@/ui';
import { api } from '@/api/client';
import { isPushEnabled } from '@/config';
import type { ModulesMap } from '@/types';

/**
 * "Ressenti après séance" toggle (plan docs/design/rpe-athlete-input.md §1).
 * Stored as the module `athlete_input` (`modules_config.athlete_input.enabled`,
 * default off) through the same `POST /config/modules` call as the Enduraw
 * toggle. The request reaches the athlete as a push notification, so the card
 * is only rendered when the deployment has push (`pushEnabled` in config.json),
 * like the Notifications card it sits next to. The device subscription itself
 * stays in that card.
 */
export function AthleteInputCard() {
  if (!isPushEnabled()) return null;
  return <AthleteInputCardInner />;
}

function AthleteInputCardInner() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  // Once the athlete taps, a late GET must not overwrite their choice.
  const touched = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ modules?: Partial<ModulesMap> }>('/config/modules')
      .then((res) => {
        if (!cancelled && !touched.current) setEnabled(res.modules?.athlete_input?.enabled === true);
      })
      .catch(() => {
        // Off by default: the toggle still works, it just starts unchecked.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onToggle = async (checked: boolean) => {
    if (saving) return;
    touched.current = true;
    setEnabled(checked);
    setSaving(true);
    setError(false);
    try {
      await api.post('/config/modules', { module_id: 'athlete_input', enabled: checked });
    } catch {
      setEnabled(!checked);
      setError(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-center gap-1.5">
          <MessageSquareText className="h-4 w-4 text-primary" aria-hidden="true" />
          <CardTitle>{t('preferences.athleteInput.title')}</CardTitle>
        </div>
        <CardDescription>{t('preferences.athleteInput.description')}</CardDescription>
      </CardHeader>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Label htmlFor="athlete-input-toggle" className="leading-snug">
            {t('preferences.athleteInput.toggle')}
          </Label>
          <Toggle
            id="athlete-input-toggle"
            checked={enabled}
            disabled={!loaded || saving}
            onCheckedChange={(checked) => void onToggle(checked)}
            aria-label={t('preferences.athleteInput.toggle')}
          />
        </div>
        {enabled && (
          <p className="text-xs text-muted-foreground">{t('preferences.athleteInput.needsPush')}</p>
        )}
        {error && <Alert variant="error">{t('preferences.athleteInput.error')}</Alert>}
      </div>
    </Card>
  );
}
