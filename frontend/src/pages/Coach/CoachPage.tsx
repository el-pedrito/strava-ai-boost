import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Container from '@cloudscape-design/components/container';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Alert from '@cloudscape-design/components/alert';
import Button from '@cloudscape-design/components/button';
import Spinner from '@cloudscape-design/components/spinner';
import Box from '@cloudscape-design/components/box';
import Link from '@cloudscape-design/components/link';
import MixedLineBarChart from '@cloudscape-design/components/mixed-line-bar-chart';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import { api } from '../../api/client.ts';

interface CoachFeedbackItem {
  activity_id: string;
  date: string;
  title: string;
  coach_feedback: { detailed_analysis?: string; strava_block?: string } | null;
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
    avg_pace_per_week: string[];
    interval_paces?: PacePoint[];
    ef_paces?: PacePoint[];
  };
  athlete_profile: string;
}

export function CoachPage() {
  const navigate = useNavigate();
  const safeMin = (arr: number[], fallback = 0) => arr.length ? Math.min(...arr) : fallback;
  const safeMax = (arr: number[], fallback = 1) => arr.length ? Math.max(...arr) : fallback;
  const [data, setData] = useState<CoachSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<CoachSummary>('/coach/summary')
      .then(setData)
      .catch(() => setError('Impossible de charger les données coach'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <ContentLayout header={<Header variant="h1">Coach IA</Header>}>
        <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>
      </ContentLayout>
    );
  }

  const vol = data?.trends?.weekly_volume_km ?? [];
  const sess = data?.trends?.sessions_per_week ?? [];
  const totalKm = vol.reduce((a, b) => a + b, 0);
  const totalSessions = sess.reduce((a, b) => a + b, 0);
  const lastEfPace = data?.trends?.ef_paces?.length ? data.trends.ef_paces[data.trends.ef_paces.length - 1].pace : '-';
  const tendance = vol.length >= 4 ? (vol[3] >= vol[0] ? '↑' : '↓') : '-';

  return (
    <ContentLayout header={<Header variant="h1">Coach IA</Header>}>
      <SpaceBetween size="l">
        {error && <Alert type="error">{error}</Alert>}

        {/* KPI Summary */}
        <Container>
          <ColumnLayout columns={4}>
            <div>
              <Box variant="h1">{Math.round(totalKm)} km</Box>
              <Box variant="small">Volume total (4 sem.)</Box>
            </div>
            <div>
              <Box variant="h1">{totalSessions}</Box>
              <Box variant="small">Séances (4 sem.)</Box>
            </div>
            <div>
              <Box variant="h1">{lastEfPace}</Box>
              <Box variant="small">Allure EF actuelle</Box>
            </div>
            <div>
              <Box variant="h1">{tendance}</Box>
              <Box variant="small">Tendance volume</Box>
            </div>
          </ColumnLayout>
        </Container>

        {/* Tendances */}
        {data?.trends && (() => {
          const weeks = ['S-4', 'S-3', 'S-2', 'S-1'];
          const paces = data.trends.avg_pace_per_week;
          const paceToSec = (p: string) => {
            const m = p.match(/^(\d+):(\d{2})$/);
            return m ? parseInt(m[1]) * 60 + parseInt(m[2]) : 0;
          };
          const paceSecs = paces.map(paceToSec);

          return (
            <Container header={<Header variant="h2">Tendances (4 dernières semaines)</Header>}>
              <ColumnLayout columns={2}>
                <MixedLineBarChart
                  height={200}
                  xDomain={weeks}
                  yDomain={[0, safeMax(vol, 10) * 1.2]}
                  xTitle="Semaine"
                  yTitle="km"
                  series={[
                    {
                      title: 'Volume (km)',
                      type: 'bar',
                      data: weeks.map((w, i) => ({ x: w, y: vol[i] })),
                      valueFormatter: (v) => `${v} km`,
                    },
                  ]}
                  xScaleType="categorical"
                  hideFilter
                  hideLegend={false}
                  empty={<Box>Pas de données</Box>}
                />
                <MixedLineBarChart
                  height={200}
                  xDomain={weeks}
                  yDomain={[safeMin(paceSecs.filter(s => s > 0), 300) - 15, safeMax(paceSecs.filter(s => s > 0), 400) + 15]}
                  xTitle="Semaine"
                  yTitle="Allure (min/km)"
                  series={[
                    {
                      title: 'Allure moyenne',
                      type: 'line',
                      data: weeks.map((w, i) => ({ x: w, y: paceSecs[i] })).filter(d => d.y > 0),
                      valueFormatter: (v) => { const m = Math.floor(v / 60); const s = Math.round(v % 60); return `${m}:${s.toString().padStart(2, '0')}/km`; },
                    },
                  ]}
                  xScaleType="categorical"
                  hideFilter
                  hideLegend
                  yTickFormatter={(v) => {
                    const m = Math.floor(Number(v) / 60);
                    const s = Math.round(Number(v) % 60);
                    return `${m}:${s.toString().padStart(2, '0')}`;
                  }}
                  empty={<Box>Pas de données</Box>}
                />
              </ColumnLayout>
              <Box variant="small" textAlign="center" margin={{ top: 's' }} color="text-body-secondary">
                Volume : {vol.map(v => `${v}km`).join(' → ')} | Séances : {sess.join(' → ')} séances/sem
              </Box>
            </Container>
          );
        })()}

        {/* Progression des allures */}
        {data?.trends && (data.trends.interval_paces?.length || data.trends.ef_paces?.length) ? (
          <Container header={<Header variant="h2">Progression des allures</Header>}>
            <ColumnLayout columns={2}>
              {data.trends.interval_paces && data.trends.interval_paces.length > 0 && (
                <div>
                  <Box variant="h4" margin={{ bottom: 'xs' }}>🔥 Allure fractions (intervalles)</Box>
                  <MixedLineBarChart
                    height={200}
                    xDomain={data.trends.interval_paces.map(p => p.date)}
                    yDomain={[
                      safeMin(data.trends.interval_paces.map(p => p.pace_sec), 240) - 10,
                      safeMax(data.trends.interval_paces.map(p => p.pace_sec), 300) + 10
                    ]}
                    series={[{
                      title: 'Allure fractions',
                      type: 'line',
                      data: data.trends.interval_paces.map(p => ({ x: p.date, y: p.pace_sec })),
                      valueFormatter: (v) => { const m = Math.floor(v / 60); const s = Math.round(v % 60); return `${m}:${s.toString().padStart(2, '0')}/km`; },
                    }]}
                    xScaleType="categorical"
                    hideFilter
                    hideLegend
                    yTickFormatter={(v) => {
                      const m = Math.floor(Number(v) / 60);
                      const s = Math.round(Number(v) % 60);
                      return `${m}:${s.toString().padStart(2, '0')}/km`;
                    }}
                    empty={<Box>Pas de fractions détectées</Box>}
                  />
                  <Box variant="small" color="text-body-secondary" textAlign="center">
                    Plus bas = plus rapide
                  </Box>
                </div>
              )}
              {data.trends.ef_paces && data.trends.ef_paces.length > 0 && (() => {
                const avgHr = data.trends.ef_paces!.filter(p => p.hr).map(p => p.hr!);
                const hrAnnotation = avgHr.length ? Math.round(avgHr.reduce((a, b) => a + b, 0) / avgHr.length) : null;
                return (
                  <div>
                    <Box variant="h4" margin={{ bottom: 'xs' }}>🏃 Allure EF (endurance facile)</Box>
                    <MixedLineBarChart
                      height={200}
                      xDomain={data.trends.ef_paces!.map(p => p.date)}
                      yDomain={[
                        safeMin(data.trends.ef_paces!.map(p => p.pace_sec), 350) - 10,
                        safeMax(data.trends.ef_paces!.map(p => p.pace_sec), 420) + 10
                      ]}
                      series={[{
                        title: 'Allure EF',
                        type: 'line',
                        data: data.trends.ef_paces!.map(p => ({ x: p.date, y: p.pace_sec })),
                        valueFormatter: (v) => { const m = Math.floor(v / 60); const s = Math.round(v % 60); return `${m}:${s.toString().padStart(2, '0')}/km`; },
                      }]}
                      xScaleType="categorical"
                      hideFilter
                      hideLegend
                      yTickFormatter={(v) => {
                        const m = Math.floor(Number(v) / 60);
                        const s = Math.round(Number(v) % 60);
                        return `${m}:${s.toString().padStart(2, '0')}/km`;
                      }}
                      empty={<Box>Pas de sorties EF détectées</Box>}
                    />
                    <Box variant="small" color="text-body-secondary" textAlign="center">
                      Allure qui baisse + FC stable = progression aérobie
                      {hrAnnotation && ` · FC moyenne EF : ${hrAnnotation} bpm`}
                    </Box>
                  </div>
                );
              })()}
            </ColumnLayout>
          </Container>
        ) : null}

        {/* Derniers retours coach */}
        <Container header={<Header variant="h2">Derniers retours coach</Header>}>
          {!data?.recent_feedback?.length ? (
            <StatusIndicator type="info">Aucun feedback coach disponible pour le moment.</StatusIndicator>
          ) : (
            <SpaceBetween size="s">
              {data.recent_feedback.map((item) => (
                <ExpandableSection key={item.activity_id} headerText={`${item.date} — ${item.title}`}>
                  <Box variant="p" color="text-body-secondary">
                    {item.coach_feedback?.detailed_analysis || 'Pas d\'analyse détaillée.'}
                  </Box>
                </ExpandableSection>
              ))}
            </SpaceBetween>
          )}
        </Container>

        {/* Profil Athlète */}
        <Container header={<Header variant="h2" actions={<Button onClick={() => navigate('/preferences')}>Modifier</Button>}>Profil Athlète</Header>}>
          {data?.athlete_profile ? (
            <Box variant="p">{data.athlete_profile}</Box>
          ) : (
            <StatusIndicator type="info">
              Aucun profil défini. <Link onFollow={() => navigate('/preferences')}>Configurer</Link>
            </StatusIndicator>
          )}
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
