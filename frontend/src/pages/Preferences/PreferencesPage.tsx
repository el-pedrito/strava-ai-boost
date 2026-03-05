import { useState, useEffect } from 'react';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Form from '@cloudscape-design/components/form';
import FormField from '@cloudscape-design/components/form-field';
import Select from '@cloudscape-design/components/select';
import Multiselect from '@cloudscape-design/components/multiselect';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Box from '@cloudscape-design/components/box';
import Alert from '@cloudscape-design/components/alert';
import type { SelectProps } from '@cloudscape-design/components/select';
import type { MultiselectProps } from '@cloudscape-design/components/multiselect';
import { api } from '../../api/client.ts';
import { getConfig } from '../../config.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import type { PaceZones } from '../../types/index.ts';

const AGE_OPTIONS: SelectProps.Option[] = [
  { value: '18-25', label: '18-25' },
  { value: '26-35', label: '26-35' },
  { value: '36-45', label: '36-45' },
  { value: '46-55', label: '46-55' },
  { value: '55+', label: '55+' },
];

const SPORT_OPTIONS: SelectProps.Option[] = [
  { value: 'health & wellness', label: 'Health & Wellness' },
  { value: 'performance & competition', label: 'Performance & Competition' },
  { value: 'social & fun', label: 'Social & Fun' },
  { value: 'personal challenge', label: 'Personal Challenge' },
  { value: 'stress relief', label: 'Stress Relief' },
  { value: 'weight management', label: 'Weight Management' },
];

const LENGTH_OPTIONS: SelectProps.Option[] = [
  { value: 'short', label: 'Short', description: '~300 characters - concise, key metrics only' },
  { value: 'medium', label: 'Medium', description: '~800 characters - balanced insights' },
  { value: 'detailed', label: 'Detailed', description: '~1500 characters - comprehensive analysis' },
  { value: 'adaptive', label: 'Adaptive', description: 'Varies by activity complexity' },
];

const TONE_OPTIONS: SelectProps.Option[] = [
  { value: 'technical & analytical', label: 'Technical & Analytical' },
  { value: 'motivational & energetic', label: 'Motivational & Energetic' },
  { value: 'casual & friendly', label: 'Casual & Friendly' },
  { value: 'humorous & fun', label: 'Humorous & Fun' },
  { value: 'authentic & personal', label: 'Authentic & Personal' },
];

const EMOJI_OPTIONS: SelectProps.Option[] = [
  { value: 'none', label: 'None' },
  { value: 'minimal', label: 'Minimal (1-2 emojis)' },
  { value: 'moderate', label: 'Moderate (3-5 emojis)' },
  { value: 'enthusiastic', label: 'Enthusiastic (5+ emojis)' },
];

const DETAIL_OPTIONS: SelectProps.Option[] = [
  { value: 'basic', label: 'Basic (simple metrics)' },
  { value: 'intermediate', label: 'Intermediate (zones, pace analysis)' },
  { value: 'advanced', label: 'Advanced (streams, detailed analysis)' },
];

const LANGUAGE_OPTIONS: SelectProps.Option[] = [
  { value: 'french', label: 'Fran\u00e7ais' },
  { value: 'english', label: 'English' },
  { value: 'spanish', label: 'Espa\u00f1ol' },
  { value: 'german', label: 'Deutsch' },
  { value: 'italian', label: 'Italiano' },
];

const INTEREST_OPTIONS: MultiselectProps.Option[] = [
  { value: 'technology', label: 'Technology' },
  { value: 'music', label: 'Music' },
  { value: 'travel', label: 'Travel' },
  { value: 'food', label: 'Food' },
  { value: 'nature', label: 'Nature' },
  { value: 'photography', label: 'Photography' },
  { value: 'family', label: 'Family' },
  { value: 'competition', label: 'Competition' },
];

function findOption(options: SelectProps.Option[], value: string) {
  return options.find((o) => o.value === value) ?? null;
}

const DEFAULT_PACE_ZONES: PaceZones = {
  recovery:        { min: '6:30', max: '8:00' },
  ef:              { min: '5:45', max: '7:30' },
  tempo:           { min: '5:00', max: '5:45' },
  sweet_spot:      { min: '4:45', max: '5:15' },
  seuil_60:        { min: '4:30', max: '5:00' },
  seuil_30:        { min: '4:15', max: '4:45' },
  allure_marathon:  { min: '4:40', max: '5:10' },
  allure_semi:     { min: '4:20', max: '4:50' },
  interval:        { min: '3:30', max: '4:20' },
};

const ZONE_LABELS: Record<string, { label: string; description: string }> = {
  recovery:        { label: 'Recup (Recovery)', description: 'Allure de recuperation, tres facile' },
  ef:              { label: 'EF (Endurance Fondamentale)', description: 'Allure facile, conversation possible' },
  tempo:           { label: 'Tempo', description: 'Allure confortablement dure' },
  sweet_spot:      { label: 'Sweet Spot', description: 'Entre tempo et seuil' },
  seuil_60:        { label: 'Seuil 60 (Threshold)', description: 'Seuil lactique, effort 60min' },
  seuil_30:        { label: 'Seuil 30 (Critical)', description: 'Seuil critique, effort 30min' },
  allure_marathon:  { label: 'Allure Marathon', description: 'Pace cible marathon' },
  allure_semi:     { label: 'Allure Semi', description: 'Pace cible semi-marathon' },
  interval:        { label: 'Intervalles / VMA', description: 'Fractions rapides, recup entre' },
};

const DEFAULTS = {
  age_range: '26-35',
  sport_approach: 'health & wellness',
  content_length: 'medium',
  content_tone: 'motivational & energetic',
  emoji_usage: 'moderate',
  technical_detail: 'intermediate',
  content_language: 'french',
  interests: [] as string[],
};

export function PreferencesPage() {
  const flash = useFlash();
  const [ageRange, setAgeRange] = useState<SelectProps.Option | null>(findOption(AGE_OPTIONS, DEFAULTS.age_range));
  const [sportApproach, setSportApproach] = useState<SelectProps.Option | null>(findOption(SPORT_OPTIONS, DEFAULTS.sport_approach));
  const [contentLength, setContentLength] = useState<SelectProps.Option | null>(findOption(LENGTH_OPTIONS, DEFAULTS.content_length));
  const [contentTone, setContentTone] = useState<SelectProps.Option | null>(findOption(TONE_OPTIONS, DEFAULTS.content_tone));
  const [emojiUsage, setEmojiUsage] = useState<SelectProps.Option | null>(findOption(EMOJI_OPTIONS, DEFAULTS.emoji_usage));
  const [technicalDetail, setTechnicalDetail] = useState<SelectProps.Option | null>(findOption(DETAIL_OPTIONS, DEFAULTS.technical_detail));
  const [contentLanguage, setContentLanguage] = useState<SelectProps.Option | null>(findOption(LANGUAGE_OPTIONS, DEFAULTS.content_language));
  const [interests, setInterests] = useState<MultiselectProps.Option[]>([]);
  const [paceZones, setPaceZones] = useState<PaceZones>({ ...DEFAULT_PACE_ZONES });
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const loadPreferences = async () => {
    try {
      const userId = getConfig().defaultUserId;
      const data = await api.get<{ success: boolean; preferences: Record<string, unknown> }>(`/preferences?user_id=${userId}`);
      if (data.success && data.preferences) {
        const p = data.preferences;
        setAgeRange(findOption(AGE_OPTIONS, (p.age_range as string) || DEFAULTS.age_range));
        setSportApproach(findOption(SPORT_OPTIONS, (p.sport_approach as string) || DEFAULTS.sport_approach));
        setContentLength(findOption(LENGTH_OPTIONS, (p.content_length as string) || DEFAULTS.content_length));
        setContentTone(findOption(TONE_OPTIONS, (p.content_tone as string) || DEFAULTS.content_tone));
        setEmojiUsage(findOption(EMOJI_OPTIONS, (p.emoji_usage as string) || DEFAULTS.emoji_usage));
        setTechnicalDetail(findOption(DETAIL_OPTIONS, (p.technical_detail as string) || DEFAULTS.technical_detail));
        setContentLanguage(findOption(LANGUAGE_OPTIONS, (p.content_language as string) || DEFAULTS.content_language));
        const userInterests = (p.interests as string[]) || [];
        setInterests(INTEREST_OPTIONS.filter((o) => userInterests.includes(o.value!)));
        if (p.pace_zones && typeof p.pace_zones === 'object') {
          setPaceZones({ ...DEFAULT_PACE_ZONES, ...(p.pace_zones as PaceZones) });
        }
      }
    } catch {
      // Use defaults
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    loadPreferences();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const userId = getConfig().defaultUserId;
      await api.post('/preferences', {
        user_id: userId,
        age_range: ageRange?.value,
        sport_approach: sportApproach?.value,
        content_length: contentLength?.value,
        content_tone: contentTone?.value,
        emoji_usage: emojiUsage?.value,
        technical_detail: technicalDetail?.value,
        content_language: contentLanguage?.value,
        interests: interests.map((i) => i.value),
        pace_zones: paceZones,
      });
      flash('success', 'Preferences saved successfully! Future activities will use these settings.');
    } catch (err) {
      flash('error', `Failed to save preferences: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) return null;

  return (
    <ContentLayout
      header={
        <Header variant="h1" description="Personalize how AI generates your activity titles and descriptions. These preferences shape the tone, detail level, and style of every enhanced activity.">
          Content Personalization Preferences
        </Header>
      }
    >
      <SpaceBetween size="l">
        <Container
          header={
            <Header variant="h2" description="Tell the AI about yourself so it can tailor content to your profile">
              Personal Profile
            </Header>
          }
        >
          <SpaceBetween size="l">
            <FormField label="Age Range" description="Helps adapt references and tone to your generation">
              <Select
                selectedOption={ageRange}
                onChange={({ detail }) => setAgeRange(detail.selectedOption)}
                options={AGE_OPTIONS}
              />
            </FormField>

            <FormField label="Sport Approach" description="Your main motivation for training">
              <Select
                selectedOption={sportApproach}
                onChange={({ detail }) => setSportApproach(detail.selectedOption)}
                options={SPORT_OPTIONS}
              />
            </FormField>

            <FormField label="Interests (Optional)" description="AI will use these to add relevant references in content">
              <Multiselect
                selectedOptions={interests}
                onChange={({ detail }) => setInterests([...detail.selectedOptions])}
                options={INTEREST_OPTIONS}
                placeholder="Select your interests"
              />
            </FormField>
          </SpaceBetween>
        </Container>

        <Container
          header={
            <Header variant="h2" description="Control the output format, tone, and language of generated descriptions">
              Content Style
            </Header>
          }
        >
          <Form
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button onClick={loadPreferences}>Reset to Current</Button>
                <Button variant="primary" onClick={handleSave} loading={saving}>Save Preferences</Button>
              </SpaceBetween>
            }
          >
            <SpaceBetween size="l">
              <FormField label="Description Length" description="Preferred length for activity descriptions">
                <Select
                  selectedOption={contentLength}
                  onChange={({ detail }) => setContentLength(detail.selectedOption)}
                  options={LENGTH_OPTIONS}
                />
              </FormField>

              <FormField label="Content Tone" description="Communication style for descriptions">
                <Select
                  selectedOption={contentTone}
                  onChange={({ detail }) => setContentTone(detail.selectedOption)}
                  options={TONE_OPTIONS}
                />
              </FormField>

              <FormField label="Emoji Usage" description="How many emojis to include">
                <Select
                  selectedOption={emojiUsage}
                  onChange={({ detail }) => setEmojiUsage(detail.selectedOption)}
                  options={EMOJI_OPTIONS}
                />
              </FormField>

              <FormField label="Technical Detail Level" description="Level of technical detail in descriptions">
                <Select
                  selectedOption={technicalDetail}
                  onChange={({ detail }) => setTechnicalDetail(detail.selectedOption)}
                  options={DETAIL_OPTIONS}
                />
              </FormField>

              <FormField label="Content Language" description="Language for titles and descriptions">
                <Select
                  selectedOption={contentLanguage}
                  onChange={({ detail }) => setContentLanguage(detail.selectedOption)}
                  options={LANGUAGE_OPTIONS}
                />
              </FormField>
            </SpaceBetween>
          </Form>
        </Container>
        <Container
          header={
            <Header variant="h2" description="Define your personal pace zones so the AI correctly classifies your workouts (EF, Tempo, Seuil, etc.)">
              Pace Zones Configuration
            </Header>
          }
        >
          <SpaceBetween size="l">
            <Alert type="info">
              Entrez vos allures en <strong>mm:ss min/km</strong> (ex: 05:45 = 5min45s par km).
              Debut = allure la plus rapide de la zone, Fin = allure la plus lente.
              Ces zones permettent a l'IA de classer correctement vos seances (EF, Tempo, Seuil, etc.).
            </Alert>
            <ColumnLayout columns={2}>
              {(Object.keys(ZONE_LABELS) as Array<keyof PaceZones>).map((zoneKey) => {
                const zone = paceZones[zoneKey] ?? DEFAULT_PACE_ZONES[zoneKey];
                const meta = ZONE_LABELS[zoneKey];
                return (
                  <FormField
                    key={zoneKey}
                    label={meta.label}
                    description={meta.description}
                  >
                    <SpaceBetween direction="horizontal" size="xs">
                      <Box>
                        <Box color="text-body-secondary" fontSize="body-s">Debut (min/km)</Box>
                        <Input
                          value={zone.min}
                          placeholder="05:00"
                          onChange={({ detail }) =>
                            setPaceZones((prev) => ({
                              ...prev,
                              [zoneKey]: { ...prev[zoneKey], min: detail.value },
                            }))
                          }
                        />
                      </Box>
                      <Box>
                        <Box color="text-body-secondary" fontSize="body-s">Fin (min/km)</Box>
                        <Input
                          value={zone.max}
                          placeholder="06:00"
                          onChange={({ detail }) =>
                            setPaceZones((prev) => ({
                              ...prev,
                              [zoneKey]: { ...prev[zoneKey], max: detail.value },
                            }))
                          }
                        />
                      </Box>
                    </SpaceBetween>
                  </FormField>
                );
              })}
            </ColumnLayout>
            <Button
              variant="link"
              onClick={() => setPaceZones({ ...DEFAULT_PACE_ZONES })}
            >
              Reset to defaults
            </Button>
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    </ContentLayout>
  );
}
