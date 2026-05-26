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
