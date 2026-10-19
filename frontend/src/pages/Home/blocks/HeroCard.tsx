/**
 * "Ce matin": the morning verdict (brief light in words), today's Campus
 * session with the coach's own words, the Watch download, weather chips and
 * the brief signals as dot + word. Signal VALUES live in the Récupération card,
 * so nothing is shown twice.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ChevronRight, Clock, Info, MessageCircle, Watch } from 'lucide-react';
import { Alert, Button, buttonVariants } from '@/ui';
import { cn } from '@/lib/cn';
import { downloadWorkout } from '@/lib/downloadWorkout';
import type { HomeBrief, HomeNextSession } from '@/types/home';
import { fmtNumber, formatClock, formatWeekdayDate } from '../format';
import { CoachText } from '@/components/CoachText';
import { HomeCard, Pill } from './common';
import { TONE_TEXT } from './tones';
import { LIGHT_TONE, STATUS_TONE, signalStatus, statusLabelKey, toLight } from '../brief';

/** The Campus coach word, through the shared renderer (same parsing as the Plan page). */
function CoachWords({ text }: { text: string | null | undefined }) {
  const { t } = useTranslation();
  if (!text || !text.trim()) return null;
  return (
    <figure className="min-w-0 rounded-lg bg-info/10 px-3 py-2.5" data-testid="home-coach-advice">
      <figcaption className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-info">
        <MessageCircle className="h-4 w-4" aria-hidden="true" />
        {t('home.brief.coachAdvice')}
      </figcaption>
      <blockquote className="[overflow-wrap:anywhere]">
        <CoachText text={text.trim()} clampLines={4} />
      </blockquote>
    </figure>
  );
}

export function HeroCard({ brief, next }: { brief: HomeBrief | null; next: HomeNextSession | null }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [watchError, setWatchError] = useState(false);

  const light = toLight(brief?.light);
  // Only the live top-level `next_session`. `brief.next_session` was frozen when the
  // morning brief was built and can name a session completed since.
  const title = next?.title ?? null;
  const duration = next?.duration_min ?? null;
  const workoutB64 = typeof next?.workout_b64 === 'string' && next.workout_b64.length > 0 ? next.workout_b64 : null;
  const day = formatWeekdayDate(brief?.date, lang);
  const builtAt = formatClock(brief?.built_at);
  const signals = brief?.signals ?? [];
  const missing = brief?.missing ?? [];
  const weather = brief?.weather ?? [];

  // Synchronous on purpose: iOS only hands the file to the Workout app when the
  // download starts inside the click (see lib/downloadWorkout).
  const addToWatch = () => {
    if (!workoutB64) return;
    try {
      downloadWorkout(workoutB64, next?.filename || `${title ?? 'workout'}.workout`);
      setWatchError(false);
    } catch {
      setWatchError(true);
    }
  };

  const signalLabel = (key: string) => t(`home.brief.signal.${key}`, { defaultValue: key });

  return (
    <HomeCard labelledBy="home-brief-title" className="flex flex-col gap-4 md:p-6">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h2 id="home-brief-title" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {t('home.brief.title')}
        </h2>
        {day && <span className="text-xs text-muted-foreground">{day}</span>}
        {brief && (
          <Pill tone={LIGHT_TONE[light]} dot className="ml-auto">
            {t(`home.brief.light.${light}`)}
          </Pill>
        )}
      </div>

      {brief && (
        <p className={cn('text-base font-medium leading-snug', light === 'unknown' ? 'text-muted-foreground' : 'text-foreground')}>
          {t(`home.brief.verdict.${light}`)}
        </p>
      )}

      {title && (
        <div>
          <p className="text-sm text-muted-foreground">{t('home.brief.nextSession')}</p>
          <p className="text-2xl font-bold leading-tight tracking-tight text-foreground [overflow-wrap:anywhere] lg:text-[28px]">
            {title}
          </p>
          {duration != null && (
            <p className="mt-1 flex items-center gap-1.5 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" aria-hidden="true" />
              {t('home.minutes', { value: duration })}
            </p>
          )}
        </div>
      )}

      <CoachWords text={next?.coach_advice} />

      {title && (
        <div className="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
          {workoutB64 && (
            <Button size="lg" onClick={addToWatch} className="min-h-11 w-full md:w-auto">
              <Watch className="h-5 w-5" aria-hidden="true" />
              {t('home.brief.addToWatch')}
            </Button>
          )}
          {/* A real link styled as a button (Button asChild renders two children, which Slot rejects). */}
          <Link to="/plan" className={cn(buttonVariants({ variant: 'outline', size: 'md' }), 'min-h-11 w-full md:w-auto')}>
            {t('home.brief.seePlan')}
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      )}
      {watchError && <Alert variant="error">{t('home.brief.watchError')}</Alert>}

      {weather.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs text-muted-foreground">{t('home.brief.weather')}</p>
          <ul className="flex flex-wrap gap-1.5">
            {weather.map((w) => {
              const temp = fmtNumber(w.temp_c, 0, lang);
              const wind = fmtNumber(w.wind_kmh, 0, lang);
              const rain =
                w.precip_mm == null
                  ? null
                  : Math.round(w.precip_mm * 10) === 0
                    ? t('home.brief.dry')
                    : t('home.brief.precip', { value: fmtNumber(w.precip_mm, 1, lang) });
              const parts = [
                temp != null ? t('home.brief.temp', { value: temp }) : null,
                wind != null ? t('home.brief.wind', { value: wind }) : null,
                rain,
              ].filter((p): p is string => p != null);
              return (
                <li
                  key={w.slot}
                  className="inline-flex min-h-8 items-center gap-1.5 whitespace-nowrap rounded-full border border-border bg-surface-muted px-2.5 text-[13px]"
                >
                  <span className="font-numeric font-semibold">{w.slot}</span>
                  <span className="text-foreground">{parts.length > 0 ? parts.join(' · ') : t('home.na')}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {signals.length > 0 && (
        <ul aria-label={t('home.brief.signalsAria')} className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-3">
          {signals.map((s) => {
            const status = signalStatus(s);
            return (
              <li key={s.key} className="flex items-center gap-1.5 text-sm" data-status={status}>
                <span className="text-muted-foreground">{signalLabel(s.key)}</span>
                <span className={cn('inline-flex items-center gap-1 text-xs font-semibold', TONE_TEXT[STATUS_TONE[status]])}>
                  <span className="h-2.5 w-2.5 rounded-full bg-current" aria-hidden="true" />
                  {/* A known value the brief skipped as too old reads "ancien", like the Recovery tile, never "Indisponible". */}
                  {t(statusLabelKey(status))}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {missing.length > 0 && (
        <p className="flex items-start gap-2 text-[13px] text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{t('home.brief.missing', { list: missing.map(signalLabel).join(', ') })}</span>
        </p>
      )}

      {(builtAt || (brief?.weather_attribution && weather.length > 0)) && (
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          {builtAt && <span>{t('home.brief.builtAt', { time: builtAt })}</span>}
          {brief?.weather_attribution && weather.length > 0 && <span>{brief.weather_attribution}</span>}
        </p>
      )}
    </HomeCard>
  );
}
