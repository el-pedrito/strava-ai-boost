/**
 * Types for `GET /home/summary`. Mirrors `/tmp/home-review/CONTRACT.md` strictly.
 *
 * Conventions from the contract:
 * - Durations in seconds, paces in s/km.
 * - Dates `YYYY-MM-DD` (Europe/Paris), timestamps ISO UTC.
 * - EVERY field can be `null` when the datum is missing. Never an old value
 *   without its date. The whole top-level objects (`brief`, `race`, ...) can be
 *   `null` too, so the UI hides the block rather than inventing content.
 */

export type BriefLight = 'green' | 'orange' | 'red' | 'unknown';
export type SignalKey = 'hrv' | 'resting_hr' | 'sleep' | 'form';
export type SignalStatus = 'ok' | 'warn' | 'bad' | 'missing';
export type HrvKind = 'sdnn' | 'rmssd';
export type PredictionDistance = '5km' | '10km' | 'half-marathon' | 'marathon';
export type SessionStatus = 'done' | 'todo' | 'missed';

export interface BriefSignal {
  key: SignalKey | string;
  value: number | null;
  baseline: number | null;
  status: SignalStatus | string;
  as_of: string | null;
}

export interface BriefSession {
  title: string | null;
  training_type: string | null;
  duration_min: number | null;
}

export interface BriefWeatherSlot {
  slot: string;
  temp_c: number | null;
  wind_kmh: number | null;
  precip_mm: number | null;
}

export interface HomeBrief {
  date: string | null;
  built_at: string | null;
  light: BriefLight | string;
  signals: BriefSignal[] | null;
  missing: string[] | null;
  next_session: BriefSession | null;
  weather: BriefWeatherSlot[] | null;
  weather_attribution: string | null;
}

export interface HomeRace {
  active: boolean;
  name: string | null;
  type: string | null;
  date: string | null;
  days_left: number | null;
  target_time_s: number | null;
  target_pace_s: number | null;
  predicted_time_s: number | null;
  /** `[low, high]` seconds. */
  predicted_range_s: [number, number] | null;
  prediction_week: string | null;
}

export interface HomePlan {
  week_index: number | null;
  weeks_total: number | null;
  cycle_theme: string | null;
  trainings_done: number | null;
  trainings_total: number | null;
  week_km_expected: number | null;
  week_km_real: number | null;
  weekly_volume_low: number | null;
  weekly_volume_high: number | null;
  sessions_per_week: number | null;
}

export interface HomeWeekSession {
  order: number;
  title: string | null;
  training_type: string | null;
  status: SessionStatus | string;
  duration_min: number | null;
}

export interface HomeNextSession {
  order: number | null;
  title: string | null;
  training_type: string | null;
  duration_min: number | null;
  /** Campus session id (same as `PlanWorkoutItem.session_id`). */
  session_id?: string | null;
  /** Campus coach word, trimmed, capped at 2000 chars; may hold `**bold**` and URLs. */
  coach_advice?: string | null;
  /** Campus instructions, same rules as `coach_advice`. */
  description?: string | null;
  /** Base64 Apple `.workout` bytes (same mapper as `/plan/workouts`); null if not encodable. */
  workout_b64?: string | null;
  /** `.workout` filename; null whenever `workout_b64` is null. */
  filename?: string | null;
}

/** A single dated health signal. `kind` only present on HRV. */
export interface HealthMetric {
  value: number | null;
  as_of: string | null;
  stale: boolean;
  kind?: HrvKind | string | null;
  baseline_60d?: number | null;
  baseline_7d?: number | null;
  delta?: number | null;
}

export interface HomeHealth {
  resting_hr: HealthMetric | null;
  hrv: HealthMetric | null;
  sleep_s: HealthMetric | null;
  sleep_score: HealthMetric | null;
  ctl: HealthMetric | null;
  atl: HealthMetric | null;
  form: HealthMetric | null;
  vo2max: HealthMetric | null;
  weight: HealthMetric | null;
}

export interface HealthSeriesPoint {
  date: string;
  resting_hr: number | null;
  hrv: number | null;
  hrv_kind?: HrvKind | string | null;
  sleep_s: number | null;
  ctl: number | null;
  atl: number | null;
  form: number | null;
}

export interface PredictionItem {
  distance: PredictionDistance | string;
  time_s: number | null;
  /** `[low, high]` seconds. */
  range_s: [number, number] | null;
  pace_s: number | null;
}

export interface HomePredictions {
  week: string | null;
  items: PredictionItem[] | null;
}

export interface PredictionsHistoryPoint {
  week: string;
  half_marathon_time_s: number | null;
}

export interface EndurawTrendPoint {
  date: string;
  activity_id: string | null;
  raw_pace_s: number | null;
  adjusted_pace_s: number | null;
  heat_cost_s: number | null;
  wind_cost_s: number | null;
  elevation_cost_s: number | null;
}

export interface HomeModules {
  intervals_icu: boolean;
  campus_coach: boolean;
}

export interface HomeSummary {
  generated_at: string | null;
  modules: HomeModules;
  brief: HomeBrief | null;
  race: HomeRace | null;
  plan: HomePlan | null;
  week_sessions: HomeWeekSession[] | null;
  next_session: HomeNextSession | null;
  health: HomeHealth | null;
  health_series: HealthSeriesPoint[] | null;
  predictions: HomePredictions | null;
  predictions_history: PredictionsHistoryPoint[] | null;
  enduraw_trend: EndurawTrendPoint[] | null;
}
