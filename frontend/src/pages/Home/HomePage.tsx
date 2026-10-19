/**
 * Accueil: the morning view. Phone: one column (hero, race, week, recovery,
 * load, predictions, Enduraw). From 1024 px: two columns, the hero spanning
 * the race and week rows like the mockup; cards are never stretched.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { Alert, Button, EmptyState } from '@/ui';
import { ApiError, getHomeSummary } from '@/api/client';
import type { HomeHealth, HomeSummary } from '@/types/home';
import { detectLoadGaps, loadGapAffectsLatest } from './insights';
import { HeroCard } from './blocks/HeroCard';
import { RaceCard } from './blocks/RaceCard';
import { WeekCard } from './blocks/WeekCard';
import { RecoveryCard } from './blocks/RecoveryCard';
import { LoadCard } from './blocks/LoadCard';
import { PredictionsCard } from './blocks/PredictionsCard';
import { EndurawCard } from './blocks/EndurawCard';

/** True when at least one health signal carries a value (an all-null health
 * object means intervals.icu is on but has nothing yet -> hide the cards). */
function healthHasValues(health: HomeHealth): boolean {
  return Object.values(health).some((m) => m != null && m.value != null);
}

/* ----------------------------------------------------------------- page */

export function HomePage() {
  const { t } = useTranslation();
  const [data, setData] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'forbidden' | 'generic' | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getHomeSummary()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError && e.status === 403 ? 'forbidden' : 'generic');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  const reload = () => {
    setError(null);
    setLoading(true);
    setReloadToken((n) => n + 1);
  };

  const modules = data?.modules;
  const intervalsOn = modules?.intervals_icu ?? false;
  const campusOn = modules?.campus_coach ?? false;

  const raceVisible =
    !!data?.race && data.race.active && (data.race.days_left == null || data.race.days_left >= 0);

  const series = data?.health_series ?? null;
  const loadGaps = useMemo(() => detectLoadGaps(series), [series]);
  const latestDate = series && series.length > 0 ? series.reduce((m, p) => (p.date > m ? p.date : m), series[0].date) : null;
  const formIncomplete = loadGapAffectsLatest(loadGaps, latestDate);
  const healthVisible = intervalsOn && !!data?.health && healthHasValues(data.health);
  const heroVisible = !!data?.brief || !!data?.next_session?.title;
  const weekSessions = data?.week_sessions ?? [];

  return (
    <div className="flex flex-col gap-5 md:gap-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{t('home.title')}</h1>
          <p className="text-sm text-muted-foreground">{t('home.subtitle')}</p>
        </div>
        <Button variant="outline" size="md" onClick={reload} disabled={loading} className="min-h-11 shrink-0">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('home.refresh')}
        </Button>
      </div>

      {loading && !data && (
        <div role="status" className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-primary" aria-hidden="true" />
          {t('home.loading')}
        </div>
      )}

      {error === 'forbidden' && <Alert variant="error">{t('home.error.forbidden')}</Alert>}

      {error === 'generic' && (
        <Alert variant="error">
          <div className="flex items-center justify-between gap-3">
            <span>{t('home.error.load')}</span>
            <Button variant="outline" size="sm" onClick={reload} disabled={loading} className="min-h-11">
              {t('common.retry')}
            </Button>
          </div>
        </Alert>
      )}

      {data && !error && (
        <div
          className="grid grid-cols-1 items-start gap-3 md:gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]"
          data-testid="home-grid"
        >
          {heroVisible && <HeroCard brief={data.brief} next={data.next_session} />}

          <div className="flex min-w-0 flex-col gap-3 md:gap-4">
            {raceVisible && data.race && <RaceCard race={data.race} />}
            {campusOn ? (
              (data.plan || weekSessions.length > 0) && (
                <WeekCard plan={data.plan} sessions={weekSessions} nextOrder={data.next_session?.order ?? null} />
              )
            ) : (
              <EmptyState
                illustration="connect"
                title={t('home.empty.campus.title')}
                description={t('home.empty.campus.description')}
              />
            )}
          </div>

          {healthVisible && data.health && (
            <>
              <RecoveryCard health={data.health} series={series} formIncomplete={formIncomplete} />
              <LoadCard health={data.health} series={series} gaps={loadGaps} />
            </>
          )}
          {!intervalsOn && (
            <EmptyState
              illustration="connect"
              title={t('home.empty.intervals.title')}
              description={t('home.empty.intervals.description')}
            />
          )}

          {campusOn && (
            <PredictionsCard
              predictions={data.predictions}
              history={data.predictions_history ?? null}
              excludeDistance={raceVisible ? (data.race?.type ?? null) : null}
            />
          )}

          {data.enduraw_trend && data.enduraw_trend.length > 0 && <EndurawCard trend={data.enduraw_trend} />}
        </div>
      )}
    </div>
  );
}
