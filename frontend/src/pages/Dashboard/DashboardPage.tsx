import { useState, useEffect, useCallback } from 'react';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Alert from '@cloudscape-design/components/alert';
import Button from '@cloudscape-design/components/button';
import { SystemOverview } from './SystemOverview.tsx';
import { ConnectionStatus } from './ConnectionStatus.tsx';
import { RecentActivities } from './RecentActivities.tsx';
import { useAutoRefresh } from '../../hooks/useAutoRefresh.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import { formatDateTime, computeProcessingTime } from '../../utils/formatDate.ts';
import type { DashboardStats, SystemStatus, Activity } from '../../types/index.ts';

interface RawActivity {
  enhanced_title?: string;
  original_name?: string;
  created_at?: string;
  updated_at?: string;
  processing_status?: string;
  modules_used?: string[];
  activity_type?: string;
  confidence?: number;
  description_modified?: boolean | null;
  similarity_score?: number;
  feedback_analyzed?: boolean;
  generated_at?: string;
}

function transformActivities(raw: RawActivity[]): Activity[] {
  return raw.slice(0, 10).map((act) => ({
    name: act.enhanced_title || act.original_name || 'Unknown',
    date: act.created_at ? formatDateTime(act.created_at) : 'N/A',
    processing_time: computeProcessingTime(act.created_at, act.updated_at),
    status: (act.processing_status as Activity['status']) || 'unknown',
    modules_used: act.modules_used || [],
    activity_type: act.activity_type,
    confidence: act.confidence,
    description_modified: act.description_modified,
    similarity_score: act.similarity_score,
    feedback_analyzed: act.feedback_analyzed,
    generated_at: act.generated_at,
  }));
}

function computeAvgProcessingTime(activities: Activity[]): string {
  const times = activities
    .map((a) => parseInt(a.processing_time, 10))
    .filter((t) => !isNaN(t));
  if (times.length === 0) return 'N/A';
  const avg = Math.round(times.reduce((sum, t) => sum + t, 0) / times.length);
  return `${avg}s`;
}

function computeStatsFromActivities(raw: RawActivity[]): DashboardStats {
  const now = new Date();
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

  const recent = raw.filter((a) => {
    if (!a.created_at) return false;
    try { return new Date(a.created_at) >= thirtyDaysAgo; } catch { return false; }
  });

  const completed = recent.filter((a) => a.processing_status === 'completed').length;
  const failed = recent.filter((a) => a.processing_status === 'failed').length;
  const total = recent.length;
  const successRate = total > 0 ? (completed / total) * 100 : 0;

  return {
    total_activities: total,
    success_rate: Math.round(successRate * 10) / 10,
    completed_activities: completed,
    failed_activities: failed,
  };
}

export function DashboardPage() {
  const flash = useFlash();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      setError(null);
      const [actRes, enhRes] = await Promise.all([
        api.get<{ activities: RawActivity[] }>('/dashboard/activities?limit=100').catch(() => null),
        api.get<{ enhancement_enabled: boolean; status: string }>('/config/enhancement').catch(() => null),
      ]);

      if (actRes?.activities) {
        setStats(computeStatsFromActivities(actRes.activities));
        setActivities(transformActivities(actRes.activities));
      } else if (!stats) {
        setError('Failed to load dashboard data');
      }

      setStatus((prev) => ({
        strava_connected: prev?.strava_connected ?? false,
        agentcore_status: prev?.agentcore_status ?? 'unknown',
        enhancement_enabled: enhRes?.enhancement_enabled ?? true,
        enhancement_status: (enhRes?.status as 'active' | 'paused') ?? 'active',
      }));
    } catch {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchConnectionStatus = useCallback(async () => {
    try {
      const [oauthRes, agentRes] = await Promise.all([
        api.get<{ connected: boolean }>('/config/oauth').catch(() => ({ connected: false })),
        api.get<{ overall_status: string }>('/health/agentcore').catch(() => null),
      ]);

      setStatus((prev) => ({
        strava_connected: oauthRes?.connected ?? false,
        agentcore_status: (agentRes?.overall_status as SystemStatus['agentcore_status']) ?? 'unknown',
        enhancement_enabled: prev?.enhancement_enabled ?? true,
        enhancement_status: prev?.enhancement_status ?? 'active',
      }));
    } catch {
      // Silently handle
    }
  }, []);

  useEffect(() => {
    fetchAll();
    fetchConnectionStatus();
  }, [fetchAll, fetchConnectionStatus]);

  useAutoRefresh(() => {
    fetchAll();
    fetchConnectionStatus();
  }, 60000);

  const handleToggleEnhancement = async () => {
    const action = status?.enhancement_enabled ? 'pause' : 'resume';
    try {
      await api.post('/config/enhancement', { action });
      flash(
        action === 'pause' ? 'info' : 'success',
        action === 'pause'
          ? 'Enhancement has been paused. New activities will not be processed.'
          : 'Enhancement has been resumed. New activities will be processed automatically.'
      );
      fetchAll();
    } catch {
      flash('error', 'Failed to toggle enhancement. Please try again.');
    }
  };

  const avgProcessingTime = computeAvgProcessingTime(activities);

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Monitor your activity processing and system performance">
          Dashboard
        </Header>
      }
    >
      <SpaceBetween size="l">
        {error && (
          <Alert type="error" action={<Button onClick={fetchAll}>Retry</Button>}>
            {error}
          </Alert>
        )}
        <SystemOverview stats={stats} loading={loading} avgProcessingTime={avgProcessingTime} />
        <ConnectionStatus
          status={status}
          loading={loading}
          onToggleEnhancement={handleToggleEnhancement}
        />
        <RecentActivities activities={activities} loading={loading} onRefresh={fetchAll} />
      </SpaceBetween>
    </ContentLayout>
  );
}
