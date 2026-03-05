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
