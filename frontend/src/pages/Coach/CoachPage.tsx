import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Container from '@cloudscape-design/components/container';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';
import Alert from '@cloudscape-design/components/alert';
import Button from '@cloudscape-design/components/button';
import Spinner from '@cloudscape-design/components/spinner';
import Box from '@cloudscape-design/components/box';
import Link from '@cloudscape-design/components/link';
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
        {data?.trends && (
          <Container header={<Header variant="h2">Tendances (4 dernières semaines)</Header>}>
            <KeyValuePairs
              columns={3}
              items={[
                { label: 'Volume hebdo (km)', value: data.trends.weekly_volume_km.join(' → ') },
                { label: 'Séances / semaine', value: data.trends.sessions_per_week.join(' → ') },
                { label: 'Allure moyenne', value: data.trends.avg_pace_per_week.join(' → ') },
              ]}
            />
          </Container>
        )}
      </SpaceBetween>
    </ContentLayout>
  );
}
