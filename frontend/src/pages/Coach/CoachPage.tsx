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

interface CoachSummary {
  recent_feedback: CoachFeedbackItem[];
  trends: {
    weekly_volume_km: number[];
    sessions_per_week: number[];
    avg_pace_per_week: string[];
  };
  athlete_profile: string;
}

export function CoachPage() {
  const navigate = useNavigate();
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
      <ContentLayout header={<Header variant="h1">Coach</Header>}>
        <Box textAlign="center" padding="xxl"><Spinner size="large" /></Box>
      </ContentLayout>
    );
  }

  return (
    <ContentLayout header={<Header variant="h1">Coach IA</Header>}>
      <SpaceBetween size="l">
        {error && <Alert type="error">{error}</Alert>}

        {/* Athlete Profile */}
        <Container header={<Header variant="h2" actions={<Button onClick={() => navigate('/preferences')}>Modifier</Button>}>Profil Athlète</Header>}>
          {data?.athlete_profile ? (
            <Box variant="p">{data.athlete_profile}</Box>
          ) : (
            <StatusIndicator type="info">
              Aucun profil défini. <Link onFollow={() => navigate('/preferences')}>Configurer</Link>
            </StatusIndicator>
          )}
        </Container>

        {/* Recent Coach Feedback */}
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

        {/* Training Trends */}
        {data?.trends && (() => {
          const weeks = ['S-4', 'S-3', 'S-2', 'S-1'];
          const vol = data.trends.weekly_volume_km;
          const sess = data.trends.sessions_per_week;
          const paces = data.trends.avg_pace_per_week;
          // Convert pace string to seconds for chart (lower = faster)
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
                  yDomain={[0, Math.max(...vol, 10) * 1.2]}
                  xTitle="Semaine"
                  yTitle="km"
                  series={[
                    {
                      title: 'Volume (km)',
                      type: 'bar',
                      data: weeks.map((w, i) => ({ x: w, y: vol[i] })),
                    },
                    {
                      title: 'Séances',
                      type: 'line',
                      data: weeks.map((w, i) => ({ x: w, y: sess[i] * (Math.max(...vol) / Math.max(...sess, 1)) })),
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
                  yDomain={[Math.min(...paceSecs.filter(s => s > 0)) - 15, Math.max(...paceSecs.filter(s => s > 0)) + 15]}
                  xTitle="Semaine"
                  yTitle="Allure (sec/km)"
                  series={[
                    {
                      title: 'Allure moyenne',
                      type: 'line',
                      data: weeks.map((w, i) => ({ x: w, y: paceSecs[i] })).filter(d => d.y > 0),
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
                Volume: {vol.map(v => `${v}km`).join(' → ')} | Séances: {sess.join(' → ')} | Allure: {paces.join(' → ')}
              </Box>
            </Container>
          );
        })()}
      </SpaceBetween>
    </ContentLayout>
  );
}
