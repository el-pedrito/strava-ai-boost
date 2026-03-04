import { useState, useEffect, useCallback } from 'react';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import { SystemOverview } from './SystemOverview.tsx';
import { ConnectionStatus } from './ConnectionStatus.tsx';
import { ModuleStatus } from './ModuleStatus.tsx';
import { RecentActivities } from './RecentActivities.tsx';
import { useAutoRefresh } from '../../hooks/useAutoRefresh.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import type { DashboardStats, SystemStatus, Activity, ModulesMap } from '../../types/index.ts';

interface RawActivity {
  enhanced_title?: string;
  original_name?: string;
  created_at?: string;
  updated_at?: string;
  processing_status?: string;
  modules_used?: string[];
}

function transformActivities(raw: RawActivity[]): Activity[] {
  return raw.slice(0, 10).map((act) => {
    let processingTime = 'N/A';
    if (act.created_at && act.updated_at) {
      try {
        const created = new Date(act.created_at);
        const updated = new Date(act.updated_at);
        processingTime = `${Math.round((updated.getTime() - created.getTime()) / 1000)}s`;
      } catch { /* ignore */ }
    }

    let dateStr = 'N/A';
    if (act.created_at) {
      try {
        const dt = new Date(act.created_at);
        dateStr = dt.toISOString().slice(0, 16).replace('T', ' ');
      } catch { /* ignore */ }
    }

    return {
      name: act.enhanced_title || act.original_name || 'Unknown',
      date: dateStr,
      processing_time: processingTime,
      status: (act.processing_status as Activity['status']) || 'unknown',
      modules_used: act.modules_used || [],
    };
  });
}

export function DashboardPage() {
  const flash = useFlash();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [modules, setModules] = useState<ModulesMap | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [sysRes, actRes, enhRes, modRes] = await Promise.all([
        api.get<{ total_activities: number; success_rate: number; recent_activities_24h: number }>(
          '/dashboard/system'
        ).catch(() => null),
        api.get<{ activities: RawActivity[] }>('/dashboard/activities').catch(() => null),
        api.get<{ enhancement_enabled: boolean; status: string }>('/config/enhancement').catch(() => null),
        api.get<{ modules: ModulesMap }>('/config/modules').catch(() => null),
      ]);

      if (sysRes) {
        setStats({
          total_activities: sysRes.total_activities ?? 0,
          success_rate_24h: sysRes.success_rate ?? 0,
          recent_activities_24h: sysRes.recent_activities_24h ?? 0,
        });
      }

      if (actRes?.activities) {
        setActivities(transformActivities(actRes.activities));
      }

      setStatus((prev) => ({
        strava_connected: prev?.strava_connected ?? false,
        agentcore_status: prev?.agentcore_status ?? 'unknown',
        enhancement_enabled: enhRes?.enhancement_enabled ?? true,
        enhancement_status: (enhRes?.status as 'active' | 'paused') ?? 'active',
      }));

      if (modRes?.modules) setModules(modRes.modules);
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

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Monitor your activity processing and system performance">
          Dashboard
        </Header>
      }
    >
      <SpaceBetween size="l">
        <SystemOverview stats={stats} loading={loading} />
        <ConnectionStatus
          status={status}
          loading={loading}
          onToggleEnhancement={handleToggleEnhancement}
        />
        <ModuleStatus modules={modules} loading={loading} />
        <RecentActivities activities={activities} loading={loading} onRefresh={fetchAll} />
      </SpaceBetween>
    </ContentLayout>
  );
}
