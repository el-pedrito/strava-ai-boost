import { lazy, Suspense, useState, useEffect, useMemo, type ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useLocation, useParams } from 'react-router';
import {
  Activity as ActivityIcon,
  Bike,
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  Clock,
  Dumbbell,
  Flame,
  Flower2,
  Footprints,
  Headphones,
  Heart,
  Loader2,
  Map as MapIcon,
  Mountain,
  Ruler,
  Sparkles,
  TrendingUp,
  Waves,
  Zap,
} from 'lucide-react';
import { AudioPlayer, Badge, Button, Card, EmptyState } from '../../ui';
import { api, ApiError } from '../../api/client.ts';
import { cn } from '../../lib/cn.ts';
import { formatDateTime } from '../../utils/formatDate.ts';
import type { Activity, AudioDebriefPayload } from '../../types/index.ts';

const ActivityMap = lazy(() =>
  import('./ActivityMap').then((m) => ({ default: m.ActivityMap })),
);

type LucideIcon = ComponentType<{ className?: string }>;
type BadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'outline';

interface CoachFeedbackBlock {
  detailed_analysis?: string;
  strava_block?: string;
  recommendation_next?: string;
}

interface CoachFeedbackItem {
  activity_id: string;
  date: string;
  title: string;
  coach_feedback: CoachFeedbackBlock | null;
}

interface CoachSummaryShape {
  recent_feedback: CoachFeedbackItem[];
}

function activityIcon(type?: string): LucideIcon {
  switch (type) {
    case 'Run':
    case 'TrailRun':
    case 'VirtualRun':
      return Footprints;
    case 'Ride':
    case 'VirtualRide':
    case 'EBikeRide':
      return Bike;
    case 'Swim':
      return Waves;
    case 'WeightTraining':
    case 'Workout':
    case 'Crossfit':
      return Dumbbell;
    case 'Hike':
    case 'Walk':
      return Mountain;
    case 'Yoga':
      return Flower2;
    default:
      return ActivityIcon;
  }
}

function moduleBadge(name: string): { label: string; variant: BadgeVariant } {
  const lower = name.toLowerCase();
  if (name === 'campus_coach' || lower.includes('campus')) {
    return { label: 'Campus Coach', variant: 'success' };
  }
  if (name === 'enduraw' || lower.includes('enduraw')) {
    return { label: 'Enduraw', variant: 'info' };
  }
  if (name === 'intervals_icu' || lower.includes('intervals')) {
    return { label: 'Intervals.icu', variant: 'primary' };
  }
  return { label: name, variant: 'default' };
}

function formatDistanceKm(meters?: number): string | null {
  if (meters === undefined || meters === null || Number.isNaN(meters)) return null;
  if (meters <= 0) return null;
  return `${(meters / 1000).toFixed(2)} km`;
}

function formatDurationSec(seconds?: number): string | null {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds) || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  if (h > 0) return `${h}h ${m.toString().padStart(2, '0')}m`;
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function formatPace(distanceMeters?: number, movingTimeSec?: number): string | null {
  if (!distanceMeters || !movingTimeSec || distanceMeters <= 0 || movingTimeSec <= 0) return null;
  const km = distanceMeters / 1000;
  const secPerKm = movingTimeSec / km;
  if (!Number.isFinite(secPerKm)) return null;
  const m = Math.floor(secPerKm / 60);
  const s = Math.round(secPerKm % 60);
  return `${m}:${s.toString().padStart(2, '0')}/km`;
}

function formatHr(value?: number): string | null {
  if (value === undefined || value === null || Number.isNaN(value) || value <= 0) return null;
  return `${Math.round(value)} bpm`;
}

function formatElevation(meters?: number): string | null {
  if (meters === undefined || meters === null || Number.isNaN(meters)) return null;
  return `${Math.round(meters)} m`;
}

interface StatTileProps {
  icon: LucideIcon;
  label: string;
  value: string;
}

function StatTile({ icon: Icon, label, value }: StatTileProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-surface p-4">
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-1 font-numeric text-base font-semibold text-foreground">{value}</p>
      </div>
    </div>
  );
}

function QualityBar({ label, value, suffix }: { label: string; value: number; suffix?: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-numeric font-medium text-foreground">
          {pct.toFixed(0)}
          {suffix ?? '%'}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function NotFoundState() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6">
      <EmptyState
        illustration="search"
        title={t('activity.notFound')}
        description={t('activity.notFoundHint')}
        action={
          <Button variant="outline" size="sm" onClick={() => navigate('/')}>
            <ChevronLeft className="h-4 w-4" />
            <span>{t('activity.backToDashboard')}</span>
          </Button>
        }
      />
    </div>
  );
}

export function ActivityDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { id: routeId } = useParams<{ id: string }>();

  const stateActivity = (location.state as { activity?: Activity } | null)?.activity ?? null;
  const [activity, setActivity] = useState<Activity | null>(stateActivity);
  const [coachFeedback, setCoachFeedback] = useState<CoachFeedbackItem | null>(null);
  const [feedbackExpanded, setFeedbackExpanded] = useState(false);
  const [audioDebrief, setAudioDebrief] = useState<AudioDebriefPayload | null>(null);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioStatus, setAudioStatus] = useState<'unknown' | 'pending' | 'unavailable'>('unknown');

  const activityId = activity?.activity_id ?? routeId ?? null;

  // Fetch activity from API to enrich with fields not in location.state (map, calories, etc.)
  useEffect(() => {
    if (!activityId) return;
    let cancelled = false;
    async function fetchActivity() {
      try {
        const data = await api.get<{ activities: Activity[] }>(`/dashboard/activities?activity_id=${activityId}`);
        if (cancelled) return;
        const match = data?.activities?.[0];
        if (match) setActivity((prev) => prev ? { ...prev, ...match } : match);
      } catch {
        // Silently ignore
      }
    }
    fetchActivity();
    return () => { cancelled = true; };
  }, [activityId]);

  useEffect(() => {
    let cancelled = false;
    async function loadCoach() {
      if (!activityId) return;
      try {
        const summary = await api.get<CoachSummaryShape>('/coach/summary');
        if (cancelled) return;
        const match = summary?.recent_feedback?.find(
          (f) => f.activity_id === activityId,
        );
        if (match) setCoachFeedback(match);
      } catch {
        // Silently ignore — coach feedback is optional
      }
    }
    loadCoach();
    return () => {
      cancelled = true;
    };
  }, [activityId]);

  useEffect(() => {
    let cancelled = false;
    async function loadAudio() {
      if (!activityId) return;
      setAudioLoading(true);
      try {
        const payload = await api.get<AudioDebriefPayload>(
          `/activities/${encodeURIComponent(activityId)}/audio-url`,
        );
        if (cancelled) return;
        if (payload?.audio_url) {
          setAudioDebrief(payload);
          setAudioStatus('unknown');
        } else {
          setAudioStatus('unavailable');
        }
      } catch (err) {
        if (cancelled) return;
        // 404 means the debrief is not (yet) available — treat as pending if recent
        if (err instanceof ApiError && err.status === 404) {
          const generatedAt = activity?.generated_at || activity?.created_at_raw;
          const ageMs = generatedAt ? Date.now() - new Date(generatedAt).getTime() : Number.NaN;
          setAudioStatus(
            Number.isFinite(ageMs) && ageMs >= 0 && ageMs < 5 * 60 * 1000
              ? 'pending'
              : 'unavailable',
          );
        } else {
          setAudioStatus('unavailable');
        }
      } finally {
        if (!cancelled) setAudioLoading(false);
      }
    }
    loadAudio();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activityId]);

  const stats = useMemo(() => {
    if (!activity) return [] as StatTileProps[];
    const items: StatTileProps[] = [];
    const distance = formatDistanceKm(activity.distance);
    const duration = formatDurationSec(activity.moving_time);
    const pace = formatPace(activity.distance, activity.moving_time);
    const avgHr = formatHr(activity.average_heartrate);
    const maxHr = formatHr(activity.max_heartrate);
    const elev = formatElevation(activity.total_elevation_gain);

    if (distance) items.push({ icon: Ruler, label: t('activity.stats.distance'), value: distance });
    if (duration) items.push({ icon: Clock, label: t('activity.stats.duration'), value: duration });
    if (pace) items.push({ icon: Zap, label: t('activity.stats.pace'), value: pace });
    if (avgHr) items.push({ icon: Heart, label: t('activity.stats.avgHr'), value: avgHr });
    if (maxHr) items.push({ icon: TrendingUp, label: t('activity.stats.maxHr'), value: maxHr });
    if (elev) items.push({ icon: Mountain, label: t('activity.stats.elevGain'), value: elev });
    const cal = activity.calories ? Math.round(Number(activity.calories)) : 0;
    if (cal > 0) items.push({ icon: Flame, label: t('activity.stats.calories'), value: `${cal} kcal` });
    return items;
  }, [activity, t]);

  if (!activity) {
    return <NotFoundState />;
  }

  const Icon = activityIcon(activity.activity_type);
  const title = activity.enhanced_title || activity.name || activity.original_name || t('activity.untitled');
  const subtitle = activity.created_at_raw
    ? formatDateTime(activity.created_at_raw)
    : activity.date || '';

  const description = activity.enhanced_description?.trim() ?? '';
  const descriptionLines = description.split(/\n+/).filter((l) => l.trim().length > 0);

  const confidencePct =
    activity.confidence !== undefined && activity.confidence !== null
      ? activity.confidence <= 1
        ? activity.confidence * 100
        : activity.confidence
      : null;
  const similarityPct =
    activity.similarity_score !== undefined && activity.similarity_score !== null
      ? activity.similarity_score <= 1
        ? activity.similarity_score * 100
        : activity.similarity_score
      : null;

  const hasQuality = confidencePct !== null || similarityPct !== null;

  return (
    <div className="flex flex-col gap-6 md:gap-8 pb-10">
      <header className="flex flex-col gap-4">
        <div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            aria-label={t('activity.back')}
          >
            <ChevronLeft className="h-4 w-4" />
            <span>{t('activity.back')}</span>
          </Button>
        </div>

        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          {/* eslint-disable-next-line react-hooks/static-components -- Icon is a reference to a module-level Lucide component picked by activityIcon(), not a component created during render. */}
            <Icon className="h-6 w-6" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
                {title}
              </h1>
              {activity.activity_type ? (
                <Badge variant="outline" size="sm">
                  {activity.activity_type}
                </Badge>
              ) : null}
            </div>
            {subtitle ? (
              <p className="mt-1 font-numeric text-sm text-muted-foreground">{subtitle}</p>
            ) : null}
          </div>
        </div>
      </header>

      {activity.map?.summary_polyline ? (
        <Suspense
          fallback={
            <div className="h-[300px] w-full animate-pulse rounded-xl bg-muted" />
          }
        >
          <ActivityMap polyline={activity.map.summary_polyline} />
        </Suspense>
      ) : (
        <Card padding="md" className="flex flex-col items-center justify-center gap-2 py-10 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <MapIcon className="h-6 w-6" />
          </div>
          <p className="text-sm font-medium text-foreground">{t('activity.map.title')}</p>
          <p className="text-xs text-muted-foreground">{t('activity.map.placeholder')}</p>
        </Card>
      )}

      {stats.length > 0 ? (
        <section aria-label={t('activity.stats.aria')} className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {t('activity.stats.title')}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {stats.map((s) => (
              <StatTile key={s.label} icon={s.icon} label={s.label} value={s.value} />
            ))}
          </div>
        </section>
      ) : null}

      {description ? (
        <section aria-label={t('activity.aiDescription')} className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {t('activity.aiDescription')}
            </h2>
          </div>
          <Card padding="md">
            {activity.enhanced_title && activity.enhanced_title !== title ? (
              <h3 className="mb-3 text-base font-semibold text-foreground">
                {activity.enhanced_title}
              </h3>
            ) : null}
            <div className="space-y-2 text-sm leading-relaxed text-foreground">
              {descriptionLines.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          </Card>
        </section>
      ) : null}

      <section aria-label={t('activity.audio.title')} className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Headphones className="h-4 w-4 text-primary" />
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {t('activity.audio.title')}
          </h2>
        </div>
        {audioDebrief?.audio_url ? (
          <AudioPlayer
            src={audioDebrief.audio_url}
            duration={audioDebrief.duration_sec ?? activity.audio_debrief_duration_sec}
          />
        ) : audioLoading ? (
          <Card padding="md" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t('activity.audio.generating')}</span>
          </Card>
        ) : audioStatus === 'pending' ? (
          <Card padding="md" className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>{t('activity.audio.generating')}</span>
          </Card>
        ) : (
          <Card padding="md" className="text-sm text-muted-foreground">
            {t('activity.audio.unavailable')}
          </Card>
        )}
      </section>

      {activity.modules_used && activity.modules_used.length > 0 ? (
        <section aria-label={t('activity.modulesUsed')} className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {t('activity.modulesUsed')}
          </h2>
          <div className="flex flex-wrap gap-2">
            {activity.modules_used.map((m) => {
              const mb = moduleBadge(m);
              return (
                <Badge key={m} variant={mb.variant} size="sm">
                  {mb.label}
                </Badge>
              );
            })}
          </div>
        </section>
      ) : null}

      {coachFeedback?.coach_feedback ? (
        <section aria-label={t('activity.coachFeedback')} className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {t('activity.coachFeedback')}
          </h2>
          <Card padding="md" className="flex flex-col gap-3">
            {coachFeedback.coach_feedback.strava_block ? (
              <div className="space-y-2 text-sm leading-relaxed text-foreground">
                {coachFeedback.coach_feedback.strava_block
                  .split(/\n+/)
                  .filter((l) => l.trim().length > 0)
                  .map((line, i) => (
                    <p key={i}>{line}</p>
                  ))}
              </div>
            ) : null}
            {coachFeedback.coach_feedback.detailed_analysis ? (
              <>
                <button
                  type="button"
                  onClick={() => setFeedbackExpanded((v) => !v)}
                  className={cn(
                    'inline-flex items-center gap-1.5 self-start text-xs font-medium text-primary hover:underline',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded',
                  )}
                  aria-expanded={feedbackExpanded}
                >
                  {feedbackExpanded ? (
                    <ChevronUp className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" />
                  )}
                  <span>
                    {feedbackExpanded
                      ? t('activity.coach.hideDetail')
                      : t('activity.coach.showDetail')}
                  </span>
                </button>
                {feedbackExpanded ? (
                  <div className="space-y-2 border-t border-border pt-3 text-sm leading-relaxed text-muted-foreground">
                    {coachFeedback.coach_feedback.detailed_analysis
                      .split(/\n+/)
                      .filter((l) => l.trim().length > 0)
                      .map((line, i) => (
                        <p key={i}>{line}</p>
                      ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </Card>
        </section>
      ) : null}

      {hasQuality ? (
        <section aria-label={t('activity.quality')} className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold tracking-tight text-foreground">
            {t('activity.quality')}
          </h2>
          <Card padding="md" className="flex flex-col gap-4">
            {confidencePct !== null ? (
              <QualityBar label={t('activity.qualityLabels.confidence')} value={confidencePct} />
            ) : null}
            {similarityPct !== null ? (
              <QualityBar label={t('activity.qualityLabels.similarity')} value={similarityPct} />
            ) : null}
          </Card>
        </section>
      ) : null}
    </div>
  );
}
