import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Calendar,
  ChevronDown,
  ChevronUp,
  Flame,
  Footprints,
  Pencil,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  KPI,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/ui';
import { ChartTooltip, useChartTheme } from '@/ui/Chart';
import { cn } from '@/lib/cn';
import { api } from '../../api/client.ts';
import { CoachChat } from './CoachChat.tsx';

interface CoachFeedbackItem {
  activity_id: string;
  date: string;
  title: string;
  coach_feedback: {
    detailed_analysis?: string;
    strava_block?: string;
    recommendation_next?: string;
  } | null;
}

interface PacePoint {
  date: string;
  pace: string;
  pace_sec: number;
  hr?: number;
}

interface CoachSummary {
  recent_feedback: CoachFeedbackItem[];
  trends: {
    weekly_volume_km: number[];
    sessions_per_week: number[];
    run_sessions_per_week?: number[];
    other_sessions_per_week?: number[];
    avg_pace_per_week: string[];
    interval_paces?: PacePoint[];
    ef_paces?: PacePoint[];
    ramp_rate?: number | null;
    compliance?: { planned: number; completed: number; percentage: number } | null;
  };
  athlete_profile: string;
}

const WEEK_LABELS: string[] = ['4 wks ago', '3 wks', '2 wks', '1 wk'];

function paceToSec(pace: string): number {
  const m = pace.match(/^(\d+):(\d{2})$/);
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : 0;
}

function formatPace(secs: number): string {
  if (!Number.isFinite(secs) || secs <= 0) return '-';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function KPISkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="h-28 rounded-xl border border-border bg-surface animate-pulse"
        />
      ))}
    </div>
  );
}

interface FeedbackCardProps {
  item: CoachFeedbackItem;
}

function FeedbackCard({ item }: FeedbackCardProps) {
  const [expanded, setExpanded] = useState(false);
  const summary = item.coach_feedback?.strava_block ?? 'No summary available.';
  const detail = item.coach_feedback?.detailed_analysis;

  return (
    <Card variant="default" padding="md">
      <div className="flex flex-col gap-1 mb-2">
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
          {item.date}
        </span>
        <span className="text-base font-medium leading-tight">{item.title}</span>
      </div>
      <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
        {summary}
      </p>
      {detail ? (
        <div className="mt-3 pt-3 border-t border-border">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            <span>{expanded ? 'Hide details' : 'Detailed analysis'}</span>
          </button>
          {expanded ? (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {detail}
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

export function CoachPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const chartTheme = useChartTheme();

  const [data, setData] = useState<CoachSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<CoachSummary>('/coach/summary')
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setError(`Unable to load coach data: ${msg}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const trends = data?.trends;
  const vol = useMemo<number[]>(() => trends?.weekly_volume_km ?? [], [trends]);
  const totalKm = vol.reduce((a, b) => a + b, 0);
  const runSessions = (trends?.run_sessions_per_week ?? []).reduce(
    (a: number, b: number) => a + b,
    0
  );
  const otherSessions = (trends?.other_sessions_per_week ?? []).reduce(
    (a: number, b: number) => a + b,
    0
  );
  const thisWeekKm = vol.length > 0 ? vol[vol.length - 1] : 0;
  const rampRate = trends?.ramp_rate ?? null;

  const volumeChartData = useMemo(
    () =>
      WEEK_LABELS.map((week, i) => ({
        week,
        km: vol[i] ?? 0,
      })),
    [vol]
  );

  const paceChartData = useMemo(() => {
    const paces = trends?.avg_pace_per_week ?? [];
    return WEEK_LABELS.map((week, i) => {
      const sec = paces[i] ? paceToSec(paces[i]) : 0;
      return { week, paceSec: sec > 0 ? sec : null };
    });
  }, [trends]);

  const validPaceSecs = paceChartData
    .map((p) => p.paceSec)
    .filter((s): s is number => typeof s === 'number' && s > 0);
  const paceMin = validPaceSecs.length > 0 ? Math.min(...validPaceSecs) : 300;
  const paceMax = validPaceSecs.length > 0 ? Math.max(...validPaceSecs) : 400;

  const intervalPaces = trends?.interval_paces ?? [];
  const efPaces = trends?.ef_paces ?? [];
  const efAvgHr = (() => {
    const hrs = efPaces.filter((p) => p.hr).map((p) => p.hr as number);
    if (hrs.length === 0) return null;
    return Math.round(hrs.reduce((a, b) => a + b, 0) / hrs.length);
  })();

  const insights = useMemo<string[]>(() => {
    const out: string[] = [];
    if (vol.length >= 2) {
      const first = vol[0];
      const last = vol[vol.length - 1];
      const delta = last - first;
      const sign = delta > 0 ? '+' : '';
      out.push(
        `Volume: ${first}km → ${last}km (${sign}${delta.toFixed(1)}km)`
      );
    }
    const paces = trends?.avg_pace_per_week ?? [];
    if (paces.length >= 2) {
      const firstSec = paceToSec(paces[0]);
      const lastSec = paceToSec(paces[paces.length - 1]);
      if (firstSec > 0 && lastSec > 0 && lastSec < firstSec) {
        out.push(
          `Pace improvement: ${paces[0]} → ${paces[paces.length - 1]}`
        );
      }
    }
    if (rampRate !== null && rampRate > 10) {
      out.push('Load is climbing fast. Consider an easier week.');
    }
    return out;
  }, [vol, trends, rampRate]);

  const nextSession =
    data?.recent_feedback?.[0]?.coach_feedback?.recommendation_next ??
    'Plan your next session in your Campus Coach plan.';

  const compliance = trends?.compliance ?? null;

  let rampTone: 'success' | 'danger' | 'muted' = 'muted';
  let RampIcon = TrendingUp;
  if (rampRate !== null) {
    if (rampRate > 10) {
      rampTone = 'danger';
      RampIcon = TrendingUp;
    } else if (rampRate > 0) {
      rampTone = 'success';
      RampIcon = TrendingUp;
    } else if (rampRate < 0) {
      rampTone = 'muted';
      RampIcon = TrendingDown;
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6 flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Coach</h1>
        <p className="text-sm text-muted-foreground">
          Your training assistant. Trends, insights, conversation.
        </p>
      </header>

      {error ? (
        <div className="mb-4">
          <Alert variant="error">{error}</Alert>
        </div>
      ) : null}

      <Tabs defaultValue="now">
        <TabsList>
          <TabsTrigger value="now">Now</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
        </TabsList>

        {/* TAB: NOW */}
        <TabsContent value="now">
          <div className="flex flex-col gap-6">
            <Card variant="elevated" padding="md">
              <div className="flex items-start gap-3">
                <div className="rounded-lg bg-primary/10 p-2 text-primary">
                  <Calendar className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="flex-1">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-1">
                    Next session
                  </div>
                  <p className="text-sm leading-relaxed">{nextSession}</p>
                </div>
              </div>
            </Card>

            {loading ? (
              <KPISkeleton />
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <KPI
                  label="Volume (4 weeks)"
                  value={Math.round(totalKm)}
                  unit="km"
                />
                <KPI
                  label="Sessions (4 weeks)"
                  value={
                    <span className="text-2xl">
                      {runSessions}
                      <span className="text-muted-foreground"> runs</span>
                      <span className="text-muted-foreground"> · </span>
                      {otherSessions}
                      <span className="text-muted-foreground"> other</span>
                    </span>
                  }
                />
                <KPI label="This week" value={thisWeekKm} unit="km" />
                <KPI
                  label="Ramp rate"
                  value={
                    rampRate !== null ? (
                      <span
                        className={cn(
                          rampTone === 'danger' && 'text-danger',
                          rampTone === 'success' && 'text-success'
                        )}
                      >
                        {rampRate > 0 ? '+' : ''}
                        {rampRate}%
                      </span>
                    ) : (
                      '-'
                    )
                  }
                  icon={
                    rampRate !== null ? (
                      <RampIcon
                        className={cn(
                          'h-4 w-4',
                          rampTone === 'danger' && 'text-danger',
                          rampTone === 'success' && 'text-success'
                        )}
                        aria-hidden="true"
                      />
                    ) : undefined
                  }
                />
              </div>
            )}

            {rampRate !== null && rampRate > 10 ? (
              <Alert variant="warning">
                Load is climbing fast (+{rampRate}%). Consider an easier week.
              </Alert>
            ) : null}

            {compliance ? (
              <Card variant="default" padding="md">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">Plan compliance</span>
                  <span
                    className={cn(
                      'text-sm font-numeric font-semibold',
                      compliance.percentage >= 80 && 'text-success',
                      compliance.percentage >= 50 &&
                        compliance.percentage < 80 &&
                        'text-warning',
                      compliance.percentage < 50 && 'text-danger'
                    )}
                  >
                    {compliance.percentage}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn(
                      'h-full transition-all',
                      compliance.percentage >= 80 && 'bg-success',
                      compliance.percentage >= 50 &&
                        compliance.percentage < 80 &&
                        'bg-warning',
                      compliance.percentage < 50 && 'bg-danger'
                    )}
                    style={{
                      width: `${Math.min(100, Math.max(0, compliance.percentage))}%`,
                    }}
                  />
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {compliance.completed}/{compliance.planned} sessions completed
                </div>
              </Card>
            ) : null}

            <section className="flex flex-col gap-3">
              <h2 className="text-lg font-semibold tracking-tight">
                Latest feedback
              </h2>
              {!data?.recent_feedback?.length ? (
                <Card variant="flat" padding="md">
                  <p className="text-sm text-muted-foreground">
                    No coach feedback available yet.
                  </p>
                </Card>
              ) : (
                <div className="flex flex-col gap-3">
                  {data.recent_feedback.slice(0, 2).map((item) => (
                    <FeedbackCard key={item.activity_id} item={item} />
                  ))}
                </div>
              )}
            </section>

            <Card variant="default" padding="md">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold tracking-tight">Profile</h2>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate('/preferences')}
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Edit</span>
                </Button>
              </div>
              {data?.athlete_profile ? (
                <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
                  {data.athlete_profile}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No profile defined.{' '}
                  <button
                    type="button"
                    onClick={() => navigate('/preferences')}
                    className="text-primary hover:underline font-medium"
                  >
                    Configure
                  </button>
                </p>
              )}
            </Card>
          </div>
        </TabsContent>

        {/* TAB: TRENDS */}
        <TabsContent value="trends">
          <div className="flex flex-col gap-6">
            {loading ? (
              <Card variant="default" padding="lg">
                <p className="text-sm text-muted-foreground">Loading trends...</p>
              </Card>
            ) : !trends ? (
              <Card variant="flat" padding="md">
                <p className="text-sm text-muted-foreground">No trends available.</p>
              </Card>
            ) : (
              <>
                <Card variant="default" padding="lg">
                  <div className="mb-4 flex flex-col gap-0.5">
                    <h2 className="text-lg font-semibold tracking-tight">
                      Weekly volume
                    </h2>
                    <span className="text-xs text-muted-foreground">
                      Last 4 weeks
                    </span>
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={volumeChartData}
                      margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
                    >
                      <CartesianGrid
                        horizontal
                        vertical={false}
                        strokeDasharray="3 3"
                        stroke={chartTheme.gridColor}
                      />
                      <XAxis
                        dataKey="week"
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={{ stroke: chartTheme.gridColor }}
                      />
                      <YAxis
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: number) => `${v}`}
                      />
                      <Tooltip
                        cursor={{ fill: chartTheme.gridColor, opacity: 0.3 }}
                        content={
                          <ChartTooltip
                            valueFormatter={(v) => `${v} km`}
                          />
                        }
                      />
                      <Bar
                        dataKey="km"
                        name="Volume"
                        fill={chartTheme.primaryColor}
                        radius={[8, 8, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </Card>

                <Card variant="default" padding="lg">
                  <div className="mb-4 flex flex-col gap-0.5">
                    <h2 className="text-lg font-semibold tracking-tight">
                      Average pace
                    </h2>
                    <span className="text-xs text-muted-foreground">
                      Lower = faster
                    </span>
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart
                      data={paceChartData}
                      margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
                    >
                      <CartesianGrid
                        horizontal
                        vertical={false}
                        strokeDasharray="3 3"
                        stroke={chartTheme.gridColor}
                      />
                      <XAxis
                        dataKey="week"
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={{ stroke: chartTheme.gridColor }}
                      />
                      <YAxis
                        reversed
                        domain={[Math.max(0, paceMin - 15), paceMax + 15]}
                        tick={{
                          fill: chartTheme.axisColor,
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                        }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v: number) => formatPace(v)}
                      />
                      <Tooltip
                        cursor={{ stroke: chartTheme.gridColor }}
                        content={
                          <ChartTooltip
                            valueFormatter={(v) =>
                              typeof v === 'number'
                                ? `${formatPace(v)}/km`
                                : String(v)
                            }
                          />
                        }
                      />
                      <Line
                        type="monotone"
                        dataKey="paceSec"
                        name="Pace"
                        stroke={chartTheme.successColor}
                        strokeWidth={2.5}
                        dot={{
                          r: 4,
                          fill: chartTheme.primaryColor,
                          stroke: chartTheme.primaryColor,
                        }}
                        activeDot={{ r: 6, fill: chartTheme.primaryColor }}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Card>

                {(intervalPaces.length > 0 || efPaces.length > 0) ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {intervalPaces.length > 0 ? (
                      <Card variant="default" padding="md">
                        <div className="mb-3 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Flame
                              className="h-4 w-4 text-primary"
                              aria-hidden="true"
                            />
                            <h3 className="text-sm font-semibold">
                              Interval pace
                            </h3>
                          </div>
                        </div>
                        <ResponsiveContainer width="100%" height={160}>
                          <LineChart
                            data={intervalPaces.map((p) => ({
                              date: p.date,
                              paceSec: p.pace_sec,
                            }))}
                            margin={{ top: 4, right: 4, bottom: 0, left: -16 }}
                          >
                            <CartesianGrid
                              horizontal
                              vertical={false}
                              strokeDasharray="3 3"
                              stroke={chartTheme.gridColor}
                            />
                            <XAxis
                              dataKey="date"
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                            />
                            <YAxis
                              reversed
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: number) => formatPace(v)}
                              width={40}
                            />
                            <Tooltip
                              content={
                                <ChartTooltip
                                  valueFormatter={(v) =>
                                    typeof v === 'number'
                                      ? `${formatPace(v)}/km`
                                      : String(v)
                                  }
                                />
                              }
                            />
                            <Line
                              type="monotone"
                              dataKey="paceSec"
                              name="Interval"
                              stroke={chartTheme.primaryColor}
                              strokeWidth={2}
                              dot={{ r: 3, fill: chartTheme.primaryColor }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Lower = faster
                        </p>
                      </Card>
                    ) : null}

                    {efPaces.length > 0 ? (
                      <Card variant="default" padding="md">
                        <div className="mb-3 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Footprints
                              className="h-4 w-4 text-success"
                              aria-hidden="true"
                            />
                            <h3 className="text-sm font-semibold">Easy pace</h3>
                          </div>
                          {efAvgHr !== null ? (
                            <Badge variant="outline" size="sm">
                              Avg HR: {efAvgHr} bpm
                            </Badge>
                          ) : null}
                        </div>
                        <ResponsiveContainer width="100%" height={160}>
                          <LineChart
                            data={efPaces.map((p) => ({
                              date: p.date,
                              paceSec: p.pace_sec,
                            }))}
                            margin={{ top: 4, right: 4, bottom: 0, left: -16 }}
                          >
                            <CartesianGrid
                              horizontal
                              vertical={false}
                              strokeDasharray="3 3"
                              stroke={chartTheme.gridColor}
                            />
                            <XAxis
                              dataKey="date"
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                            />
                            <YAxis
                              reversed
                              tick={{
                                fill: chartTheme.axisColor,
                                fontSize: 10,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={false}
                              tickFormatter={(v: number) => formatPace(v)}
                              width={40}
                            />
                            <Tooltip
                              content={
                                <ChartTooltip
                                  valueFormatter={(v) =>
                                    typeof v === 'number'
                                      ? `${formatPace(v)}/km`
                                      : String(v)
                                  }
                                />
                              }
                            />
                            <Line
                              type="monotone"
                              dataKey="paceSec"
                              name="EF"
                              stroke={chartTheme.successColor}
                              strokeWidth={2}
                              dot={{ r: 3, fill: chartTheme.successColor }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                        <p className="mt-2 text-xs text-muted-foreground">
                          Pace down + HR stable = aerobic progress
                        </p>
                      </Card>
                    ) : null}
                  </div>
                ) : null}

                {insights.length > 0 ? (
                  <Card variant="flat" padding="md">
                    <div className="flex items-start gap-3">
                      <Sparkles
                        className="h-4 w-4 text-primary mt-0.5 flex-shrink-0"
                        aria-hidden="true"
                      />
                      <ul className="flex flex-col gap-1.5 text-sm">
                        {insights.map((line, i) => (
                          <li key={i} className="leading-relaxed">
                            {line}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </Card>
                ) : null}
              </>
            )}
          </div>
        </TabsContent>

        {/* TAB: CHAT */}
        <TabsContent value="chat">
          <CoachChat />
        </TabsContent>
      </Tabs>

      {/* Suppress unused i18n warning */}
      <span className="hidden">{t('coach.title')}</span>
    </div>
  );
}
