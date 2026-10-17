export interface DashboardStats {
  total_activities: number;
  success_rate: number;
  completed_activities: number;
  failed_activities: number;
}

export interface Activity {
  name: string;
  date: string;
  processing_time: string;
  status: 'completed' | 'processing' | 'error' | 'unknown';
  modules_used: string[];
  activity_type?: string;
  confidence?: number;
  description_modified?: boolean | null;
  similarity_score?: number;
  feedback_analyzed?: boolean;
  generated_at?: string;
  created_at_raw?: string;
  start_date_raw?: string;
  /** Raw Strava start time, as returned by GET /dashboard/activities. */
  start_date?: string;
  processing_time_seconds?: number;
  activity_id?: string;
  enhanced_title?: string;
  enhanced_description?: string;
  original_name?: string;
  distance?: number;
  moving_time?: number;
  elapsed_time?: number;
  total_elevation_gain?: number;
  average_heartrate?: number;
  max_heartrate?: number;
  average_speed?: number;
  max_speed?: number;
  kudos_count?: number;
  comment_count?: number;
  audio_debrief_url?: string;
  audio_debrief_duration_sec?: number;
  audio_debrief_generated_at?: string;
  audio_debrief_language?: string;
  map?: { summary_polyline?: string };
  calories?: number | string;
}

export interface AudioDebriefPayload {
  audio_url: string;
  duration_sec?: number;
  generated_at?: string;
  language?: string;
  voice?: string;
  expires_in_sec?: number;
}

export interface QualityStats {
  avg_confidence: number;
  edit_rate: number;
  avg_similarity: number;
  total_analyzed: number;
  total_feedback: number;
}

export interface OAuthStatus {
  connected: boolean;
  configured: boolean;
  obtained_at?: string;
  last_refreshed?: string;
  scopes?: string[];
  message?: string;
}

export interface StravaAppStatus {
  configured: boolean;
  client_id?: string;
  redirect_uri?: string;
  message?: string;
}

export interface ModuleConfig {
  enabled: boolean;
  configured: boolean;
  description?: string;
  status?: string;
  last_extraction?: string;
  wait_time?: string;
}

export interface ModulesMap {
  campus_coach: ModuleConfig;
  enduraw: ModuleConfig;
  intervals_icu: ModuleConfig;
}

export interface EnhancementStatus {
  enhancement_enabled: boolean;
  enhancement_paused_at: string | null;
  status: 'active' | 'paused';
}

export interface SystemStatus {
  strava_connected: boolean;
  agentcore_status: 'healthy' | 'not_configured' | 'error' | 'unknown';
  enhancement_enabled: boolean;
  enhancement_status: 'active' | 'paused';
}

export interface PaceZone {
  min: string; // mm:ss format, e.g. "5:45"
  max: string; // mm:ss format, e.g. "7:30"
}

export interface PaceZones {
  recovery: PaceZone;
  ef: PaceZone;
  aerobic: PaceZone;
  tempo: PaceZone;
  sweet_spot: PaceZone;
  seuil_60: PaceZone;
  seuil_30: PaceZone;
  allure_marathon: PaceZone;
  allure_semi: PaceZone;
  interval: PaceZone;
}

/** One pace zone as synced from Campus Coach (read-only, written by the sync). */
export interface CampusPaceZone extends PaceZone {
  slug: string;
  value_s: number;
  dvalue_s: number;
}

/** Where the effective pace zones come from (mirrors shared/pace_zones.effective_pace_zones). */
export type PaceZonesSource = 'campus' | 'campus_stale' | 'manual_legacy' | 'none';

export interface UserPreferences {
  age_range: string;
  sport_approach: string;
  content_length: string;
  content_tone: string;
  emoji_usage: string;
  technical_detail: string;
  content_language: string;
  interests: string[];
  pace_zones?: PaceZones;
}

export interface FlashMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  content: string;
  dismissible: boolean;
}

/**
 * Why a plan session cannot be exported as an Apple Watch `.workout`.
 * Mirrors the REASON_* constants of lambda_functions/shared/campus_workout.py.
 */
export type WorkoutReasonCode =
  | 'unsupported_sport'
  | 'no_intervals'
  | 'legacy_shape'
  | 'bad_repeat'
  | 'bad_shape'
  | 'too_many_steps'
  | 'too_large'
  | 'internal';

/**
 * One upcoming Campus plan session, as served by `GET /plan/workouts`.
 * Mirrors `api/plan_workouts.py::_item`: every field copied from a Campus row is
 * null when the row holds no usable value of that type.
 */
export interface PlanWorkoutItem {
  session_id: string | null;
  /** ISO week label, `YYYY-Www`. */
  week_iso: string | null;
  training_index: number | null;
  title: string | null;
  training_type: string | null;
  /** Campus sport code (`road`, `ppg`, ...). */
  sport: string | null;
  duration_min: number | null;
  /**
   * Campus instructions for the session, trimmed and capped at 2000 characters.
   * Raw text: may hold markdown bold (`**x**`) and URLs. Optional so an older API
   * response (before the field existed) still type-checks.
   */
  description?: string | null;
  /** Campus coach word for the session, same rules as `description`. */
  coach_advice?: string | null;
  /** Step summary, null whenever the session is not encodable. */
  summary: string | null;
  filename: string;
  encodable: boolean;
  /**
   * A `WorkoutReasonCode` when `encodable` is false. Typed as `string` so a code
   * added server-side later still renders (with the generic sentence).
   */
  reason_code: string | null;
  /** Base64 `.workout` bytes, present only when `encodable` is true. */
  workout_b64?: string;
}

export interface PlanWorkoutsResponse {
  workouts: PlanWorkoutItem[];
  count: number;
  /** True when the server dropped the furthest weeks to stay under its caps. */
  truncated: boolean;
  timestamp?: string;
}

/** Home dashboard (`GET /home/summary`) types. */
export * from './home.ts';
