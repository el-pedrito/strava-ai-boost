import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import * as Dialog from '@radix-ui/react-dialog';
import { Calculator, Check, ChevronDown, ChevronRight, Plus, RotateCcw, Trash2, X } from 'lucide-react';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  InfoTooltip,
  Input,
  Label,
  Select,
  Textarea,
  type SelectOption,
} from '@/ui';
import { api } from '../../api/client.ts';
import { getConfig } from '../../config.ts';
import { useFlash } from '../../layouts/AppLayout.tsx';
import type { PaceZones } from '../../types/index.ts';

const AGE_OPTIONS: SelectOption[] = [
  { value: '18-25', label: '18-25' },
  { value: '26-35', label: '26-35' },
  { value: '36-45', label: '36-45' },
  { value: '46-55', label: '46-55' },
  { value: '55+', label: '55+' },
];

const SPORT_OPTIONS: SelectOption[] = [
  { value: 'health & wellness', label: 'Health & Wellness' },
  { value: 'performance & competition', label: 'Performance & Competition' },
  { value: 'social & fun', label: 'Social & Fun' },
  { value: 'personal challenge', label: 'Personal Challenge' },
  { value: 'stress relief', label: 'Stress Relief' },
  { value: 'weight management', label: 'Weight Management' },
];

const LENGTH_OPTIONS: SelectOption[] = [
  { value: 'short', label: 'Short', description: '~300 chars, key metrics only' },
  { value: 'medium', label: 'Medium', description: '~800 chars, balanced insights' },
  { value: 'detailed', label: 'Detailed', description: '~1500 chars, full analysis' },
  { value: 'adaptive', label: 'Adaptive', description: 'Varies by complexity' },
];

const TONE_OPTIONS: SelectOption[] = [
  { value: 'technical & analytical', label: 'Technical & Analytical' },
  { value: 'motivational & energetic', label: 'Motivational & Energetic' },
  { value: 'casual & friendly', label: 'Casual & Friendly' },
  { value: 'humorous & fun', label: 'Humorous & Fun' },
  { value: 'authentic & personal', label: 'Authentic & Personal' },
];

const EMOJI_OPTIONS: SelectOption[] = [
  { value: 'none', label: 'None' },
  { value: 'minimal', label: 'Minimal (1-2)' },
  { value: 'moderate', label: 'Moderate (3-5)' },
  { value: 'enthusiastic', label: 'Enthusiastic (5+)' },
];

const DETAIL_OPTIONS: SelectOption[] = [
  { value: 'basic', label: 'Basic', description: 'simple metrics' },
  { value: 'intermediate', label: 'Intermediate', description: 'zones, pace analysis' },
  { value: 'advanced', label: 'Advanced', description: 'streams, detailed analysis' },
];

const LANGUAGE_OPTIONS: SelectOption[] = [
  { value: 'french', label: 'Français' },
  { value: 'english', label: 'English' },
  { value: 'spanish', label: 'Español' },
  { value: 'german', label: 'Deutsch' },
  { value: 'italian', label: 'Italiano' },
];

const INTEREST_OPTIONS: SelectOption[] = [
  { value: 'technology', label: 'Technology' },
  { value: 'music', label: 'Music' },
  { value: 'travel', label: 'Travel' },
  { value: 'food', label: 'Food' },
  { value: 'nature', label: 'Nature' },
  { value: 'photography', label: 'Photography' },
  { value: 'family', label: 'Family' },
  { value: 'competition', label: 'Competition' },
];

const DEFAULT_PACE_ZONES: PaceZones = {
  recovery: { min: '6:30', max: '8:00' },
  ef: { min: '5:45', max: '7:30' },
  aerobic: { min: '5:15', max: '5:50' },
  tempo: { min: '5:00', max: '5:45' },
  sweet_spot: { min: '4:45', max: '5:15' },
  seuil_60: { min: '4:30', max: '5:00' },
  seuil_30: { min: '4:15', max: '4:45' },
  allure_marathon: { min: '4:40', max: '5:10' },
  allure_semi: { min: '4:20', max: '4:50' },
  interval: { min: '3:30', max: '4:20' },
};

const ZONE_LABELS: Record<keyof PaceZones, { number: string; label: string; description: string }> = {
  recovery: { number: 'Z1', label: 'Recovery', description: 'Very easy pace' },
  ef: { number: 'Z2', label: 'EF (Endurance Fond.)', description: 'Easy, conversational' },
  aerobic: { number: 'Z3', label: 'Aerobic', description: 'Active endurance' },
  tempo: { number: 'Z4', label: 'Tempo', description: 'Comfortably hard' },
  sweet_spot: { number: 'Z5', label: 'Sweet Spot', description: 'Tempo to threshold' },
  seuil_60: { number: 'Z6', label: 'Threshold 60', description: 'Lactate threshold, 60min effort' },
  seuil_30: { number: 'Z7', label: 'Threshold 30', description: 'Critical, 30min effort' },
  allure_marathon: { number: 'Z8', label: 'Marathon Pace', description: 'Target marathon pace' },
  allure_semi: { number: 'Z9', label: 'Half-Marathon Pace', description: 'Target half pace' },
  interval: { number: 'Z10', label: 'Intervals / VO2max', description: 'Fast intervals' },
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

const formatTime = (secs: number): string => {
  if (secs >= 3600) {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${Math.floor(secs / 60)}:${(secs % 60).toString().padStart(2, '0')}`;
};

interface StrengthExercise {
  name: string;
  sets: string;
  load: string;
  rest: string;
}

interface StrengthSession {
  id: string;
  name: string;
  frequency: string;
  exercises: StrengthExercise[];
}

interface PersonalRecord {
  id: string;
  distance: string;
  time: string;
  date: string;
  event: string;
}

interface AutoPr {
  elapsed_time: number;
  date: string;
}

interface PreferencesState {
  ageRange: string;
  sportApproach: string;
  contentLength: string;
  contentTone: string;
  emojiUsage: string;
  technicalDetail: string;
  contentLanguage: string;
  interests: string[];
  paceZones: PaceZones;
  athleteProfile: string;
  personalRecords: PersonalRecord[];
  maxHr: string;
  strengthProgram: StrengthSession[];
}

const initialState: PreferencesState = {
  ageRange: DEFAULTS.age_range,
  sportApproach: DEFAULTS.sport_approach,
  contentLength: DEFAULTS.content_length,
  contentTone: DEFAULTS.content_tone,
  emojiUsage: DEFAULTS.emoji_usage,
  technicalDetail: DEFAULTS.technical_detail,
  contentLanguage: DEFAULTS.content_language,
  interests: [],
  paceZones: { ...DEFAULT_PACE_ZONES },
  athleteProfile: '',
  personalRecords: [],
  maxHr: '',
  strengthProgram: [],
};

function statesEqual(a: PreferencesState, b: PreferencesState): boolean {
  if (
    a.ageRange !== b.ageRange ||
    a.sportApproach !== b.sportApproach ||
    a.contentLength !== b.contentLength ||
    a.contentTone !== b.contentTone ||
    a.emojiUsage !== b.emojiUsage ||
    a.technicalDetail !== b.technicalDetail ||
    a.contentLanguage !== b.contentLanguage ||
    a.athleteProfile !== b.athleteProfile ||
    a.maxHr !== b.maxHr
  )
    return false;
  if (a.interests.length !== b.interests.length) return false;
  if (![...a.interests].sort().every((v, i) => v === [...b.interests].sort()[i])) return false;
  const zoneKeys = Object.keys(DEFAULT_PACE_ZONES) as Array<keyof PaceZones>;
  for (const k of zoneKeys) {
    if (a.paceZones[k].min !== b.paceZones[k].min) return false;
    if (a.paceZones[k].max !== b.paceZones[k].max) return false;
  }
  if (a.personalRecords.length !== b.personalRecords.length) return false;
  for (let i = 0; i < a.personalRecords.length; i++) {
    const ra = a.personalRecords[i];
    const rb = b.personalRecords[i];
    if (ra.distance !== rb.distance || ra.time !== rb.time || ra.date !== rb.date || ra.event !== rb.event) return false;
  }
  if (JSON.stringify(a.strengthProgram) !== JSON.stringify(b.strengthProgram)) return false;
  return true;
}

export function PreferencesPage() {
  const { t } = useTranslation();
  const flash = useFlash();
  const [state, setState] = useState<PreferencesState>(initialState);
  const lastLoadedRef = useRef<PreferencesState>(initialState);
  const [autoPrs, setAutoPrs] = useState<Record<string, AutoPr>>({});
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [showAddRecord, setShowAddRecord] = useState(false);

  const loadPreferences = async () => {
    try {
      const userId = getConfig().defaultUserId;
      const data = await api.get<{ success: boolean; preferences: Record<string, unknown> }>(
        `/preferences?user_id=${userId}`
      );
      if (data.success && data.preferences) {
        const p = data.preferences;
        const next: PreferencesState = {
          ageRange: (p.age_range as string) || DEFAULTS.age_range,
          sportApproach: (p.sport_approach as string) || DEFAULTS.sport_approach,
          contentLength: (p.content_length as string) || DEFAULTS.content_length,
          contentTone: (p.content_tone as string) || DEFAULTS.content_tone,
          emojiUsage: (p.emoji_usage as string) || DEFAULTS.emoji_usage,
          technicalDetail: (p.technical_detail as string) || DEFAULTS.technical_detail,
          contentLanguage: (p.content_language as string) || DEFAULTS.content_language,
          interests: Array.isArray(p.interests) ? (p.interests as string[]) : [],
          paceZones:
            p.pace_zones && typeof p.pace_zones === 'object'
              ? { ...DEFAULT_PACE_ZONES, ...(p.pace_zones as PaceZones) }
              : { ...DEFAULT_PACE_ZONES },
          athleteProfile: (p.athlete_profile as string) || '',
          personalRecords: Array.isArray(p.personal_records)
            ? (p.personal_records as Array<{ distance: string; time: string; date: string; event: string }>).map(
                (r) => ({ ...r, id: crypto.randomUUID() })
              )
            : [],
          maxHr: p.max_hr ? String(p.max_hr) : '',
          strengthProgram: Array.isArray((p.strength_program as { sessions?: unknown[] })?.sessions)
            ? ((p.strength_program as { sessions: Array<{ id?: string; name: string; frequency: string; exercises: StrengthExercise[] }> }).sessions).map(
                (s) => ({ ...s, id: s.id || crypto.randomUUID() })
              )
            : [],
        };
        setState(next);
        lastLoadedRef.current = next;
        if (p.best_efforts_prs && typeof p.best_efforts_prs === 'object') {
          setAutoPrs(p.best_efforts_prs as Record<string, AutoPr>);
        }
      }
    } catch {
      // Use defaults
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    void loadPreferences();
  }, []);

  const dirty = useMemo(() => loaded && !statesEqual(state, lastLoadedRef.current), [state, loaded]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const userId = getConfig().defaultUserId;
      await api.post('/preferences', {
        user_id: userId,
        age_range: state.ageRange,
        sport_approach: state.sportApproach,
        content_length: state.contentLength,
        content_tone: state.contentTone,
        emoji_usage: state.emojiUsage,
        technical_detail: state.technicalDetail,
        content_language: state.contentLanguage,
        interests: state.interests,
        pace_zones: state.paceZones,
        athlete_profile: state.athleteProfile,
        personal_records: state.personalRecords
          .filter((r) => r.distance && r.time)
          .map((r) => ({ distance: r.distance, time: r.time, date: r.date, event: r.event })),
        ...(state.maxHr ? { max_hr: parseInt(state.maxHr, 10) } : {}),
        strength_program: {
          sessions: state.strengthProgram.map((s) => ({
            id: s.id,
            name: s.name,
            frequency: s.frequency,
            exercises: s.exercises,
          })),
        },
      });
      flash('success', 'Preferences saved. Future activities will use these settings.');
      lastLoadedRef.current = state;
      // trigger memo recompute
      setState((prev) => ({ ...prev }));
    } catch (err) {
      flash('error', `Failed to save preferences: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setState(lastLoadedRef.current);
  };

  const computeMaxHrFromAge = () => {
    const ageOption = state.ageRange;
    if (!ageOption) return;
    const parts = ageOption.split('-');
    const start = parseInt(parts[0], 10);
    const isPlus = ageOption.includes('+');
    const end = isPlus ? start : parseInt(parts[1], 10);
    const midAge = isPlus ? start + 5 : start + Math.floor((end - start) / 2);
    const theoretical = Math.round(208 - 0.7 * midAge);
    setState((prev) => ({ ...prev, maxHr: String(theoretical) }));
  };

  if (!loaded) return null;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6 pb-32 md:py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">{t('preferences.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('preferences.description')}</p>
      </header>

      {/* Athlete profile */}
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>{t('preferences.profile.title')}</CardTitle>
            <InfoTooltip i18nKey="preferences.profile.help" align="start" />
          </div>
          <CardDescription>{t('preferences.profile.description')}</CardDescription>
        </CardHeader>
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Label htmlFor="athlete-profile">{t('preferences.profile.fieldLabel')}</Label>
                <InfoTooltip i18nKey="preferences.profile.field.help" align="start" />
              </div>
              <span
                className={
                  state.athleteProfile.length > 2000
                    ? 'text-xs text-danger'
                    : 'text-xs text-muted-foreground'
                }
              >
                {state.athleteProfile.length}/2000
              </span>
            </div>
            <Textarea
              id="athlete-profile"
              value={state.athleteProfile}
              rows={6}
              onChange={(e) => {
                const value = e.target.value;
                if (value.length <= 2000) setState((prev) => ({ ...prev, athleteProfile: value }));
              }}
              placeholder="Describe yourself: goals, training history, experience, injuries, what you want to improve..."
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5">
              <Label htmlFor="max-hr">{t('preferences.profile.fcMax')}</Label>
              <InfoTooltip i18nKey="preferences.maxHr.help" align="start" />
            </div>
            <p className="text-xs text-muted-foreground">{t('preferences.profile.fcMaxDescription')}</p>
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-32">
                <Input
                  id="max-hr"
                  value={state.maxHr}
                  onChange={(e) => setState((prev) => ({ ...prev, maxHr: e.target.value.replace(/\D/g, '') }))}
                  placeholder="192"
                  type="number"
                  inputMode="numeric"
                />
              </div>
              <Button variant="outline" size="md" onClick={computeMaxHrFromAge}>
                <Calculator className="h-4 w-4" aria-hidden="true" />
                {t('preferences.profile.calculateTanaka')}
              </Button>
              {state.maxHr && state.ageRange && (
                <span className="text-xs text-info">{t('preferences.profile.tanakaFormula')}</span>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Strength Program */}
      <StrengthProgramSection
        sessions={state.strengthProgram}
        onChange={(sessions) => setState((prev) => ({ ...prev, strengthProgram: sessions }))}
      />

      {/* Personal Records */}
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <CardTitle>Personal records</CardTitle>
                <InfoTooltip i18nKey="preferences.records.help" align="start" />
              </div>
              <CardDescription>
                Your benchmark times. The coach uses them to contextualize your progress.
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowAddRecord(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add record
            </Button>
          </div>
        </CardHeader>
        <RecordsList
          records={state.personalRecords}
          onRemove={(id) =>
            setState((prev) => ({ ...prev, personalRecords: prev.personalRecords.filter((r) => r.id !== id) }))
          }
        />
        <AddRecordDialog
          open={showAddRecord}
          onOpenChange={setShowAddRecord}
          onAdd={(record) =>
            setState((prev) => ({ ...prev, personalRecords: [...prev.personalRecords, record] }))
          }
        />
      </Card>

      {/* Auto-detected PRs */}
      {Object.keys(autoPrs).length > 0 && (
        <Card padding="lg">
          <CardHeader>
            <CardTitle>Auto-detected PRs (Strava)</CardTitle>
            <CardDescription>Detected automatically from your Strava activities.</CardDescription>
          </CardHeader>
          <ul className="flex flex-col divide-y divide-border">
            {Object.entries(autoPrs).map(([name, pr]) => (
              <li key={name} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="font-medium text-foreground">{name}</span>
                <span className="font-numeric tabular-nums text-foreground">{formatTime(pr.elapsed_time)}</span>
                <span className="text-xs text-muted-foreground">{pr.date}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Pace zones */}
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5">
                <CardTitle>{t('preferences.zones.title')}</CardTitle>
                <InfoTooltip i18nKey="preferences.zones.help" align="start" />
              </div>
              <CardDescription>{t('preferences.zones.description')}</CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setState((prev) => ({ ...prev, paceZones: { ...DEFAULT_PACE_ZONES } }))}
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Reset to defaults
            </Button>
          </div>
        </CardHeader>
        <Alert variant="info" className="mb-4">
          Enter your paces in <strong>mm:ss /km</strong>. Start = fastest pace in zone, End = slowest.
        </Alert>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {(Object.keys(ZONE_LABELS) as Array<keyof PaceZones>).map((zoneKey) => {
            const zone = state.paceZones[zoneKey] ?? DEFAULT_PACE_ZONES[zoneKey];
            const meta = ZONE_LABELS[zoneKey];
            return (
              <div
                key={zoneKey}
                className="flex flex-col gap-2 rounded-lg border border-border bg-surface-muted p-3"
              >
                <div className="flex items-baseline gap-2">
                  <Badge variant="primary" size="sm">
                    {meta.number}
                  </Badge>
                  <span className="font-medium text-sm text-foreground">{meta.label}</span>
                </div>
                <p className="text-xs text-muted-foreground">{meta.description}</p>
                <div className="grid grid-cols-2 gap-2">
                  <div className="flex flex-col gap-1">
                    <Label htmlFor={`${zoneKey}-min`} className="text-xs text-muted-foreground">
                      Start
                    </Label>
                    <Input
                      id={`${zoneKey}-min`}
                      value={zone.min}
                      placeholder="5:00"
                      onChange={(e) =>
                        setState((prev) => ({
                          ...prev,
                          paceZones: { ...prev.paceZones, [zoneKey]: { ...prev.paceZones[zoneKey], min: e.target.value } },
                        }))
                      }
                      className="font-numeric"
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <Label htmlFor={`${zoneKey}-max`} className="text-xs text-muted-foreground">
                      End
                    </Label>
                    <Input
                      id={`${zoneKey}-max`}
                      value={zone.max}
                      placeholder="6:00"
                      onChange={(e) =>
                        setState((prev) => ({
                          ...prev,
                          paceZones: { ...prev.paceZones, [zoneKey]: { ...prev.paceZones[zoneKey], max: e.target.value } },
                        }))
                      }
                      className="font-numeric"
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Content style */}
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>{t('preferences.style.title')}</CardTitle>
            <InfoTooltip i18nKey="preferences.style.help" align="start" />
          </div>
          <CardDescription>{t('preferences.style.description')}</CardDescription>
        </CardHeader>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field
            label={t('preferences.style.length')}
            hint="Preferred length for activity descriptions"
            helpKey="preferences.style.length.help"
          >
            <Select
              options={LENGTH_OPTIONS}
              value={state.contentLength}
              onChange={(v) => setState((prev) => ({ ...prev, contentLength: v }))}
            />
          </Field>
          <Field
            label={t('preferences.style.tone')}
            hint="Communication style for descriptions"
            helpKey="preferences.style.tone.help"
          >
            <Select
              options={TONE_OPTIONS}
              value={state.contentTone}
              onChange={(v) => setState((prev) => ({ ...prev, contentTone: v }))}
            />
          </Field>
          <Field
            label={t('preferences.style.emoji')}
            hint="How many emojis to include in generated text"
            helpKey="preferences.style.emoji.help"
          >
            <Select
              options={EMOJI_OPTIONS}
              value={state.emojiUsage}
              onChange={(v) => setState((prev) => ({ ...prev, emojiUsage: v }))}
            />
          </Field>
          <Field
            label={t('preferences.style.technical')}
            hint="Level of technical detail"
            helpKey="preferences.style.technical.help"
          >
            <Select
              options={DETAIL_OPTIONS}
              value={state.technicalDetail}
              onChange={(v) => setState((prev) => ({ ...prev, technicalDetail: v }))}
            />
          </Field>
          <Field
            label={t('preferences.style.language')}
            hint="Language for titles and descriptions"
            helpKey="preferences.style.language.help"
          >
            <Select
              options={LANGUAGE_OPTIONS}
              value={state.contentLanguage}
              onChange={(v) => setState((prev) => ({ ...prev, contentLanguage: v }))}
            />
          </Field>
        </div>
      </Card>

      {/* Demographics */}
      <Card padding="lg">
        <CardHeader>
          <div className="flex items-center gap-1.5">
            <CardTitle>Demographics</CardTitle>
            <InfoTooltip i18nKey="preferences.demographics.help" align="start" />
          </div>
          <CardDescription>Demographic info to adapt content to your profile.</CardDescription>
        </CardHeader>
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field
              label={t('preferences.demographics.age')}
              hint="Helps adapt references and tone"
              helpKey="preferences.demographics.age.help"
            >
              <Select
                options={AGE_OPTIONS}
                value={state.ageRange}
                onChange={(v) => setState((prev) => ({ ...prev, ageRange: v }))}
              />
            </Field>
            <Field
              label="Sport approach"
              hint="Your main motivation for training"
              helpKey="preferences.demographics.sportApproach.help"
            >
              <Select
                options={SPORT_OPTIONS}
                value={state.sportApproach}
                onChange={(v) => setState((prev) => ({ ...prev, sportApproach: v }))}
              />
            </Field>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5">
              <Label>Interests</Label>
              <InfoTooltip i18nKey="preferences.demographics.interests.help" align="start" />
            </div>
            <p className="text-xs text-muted-foreground">
              The AI uses these to add relevant references in generated content.
            </p>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {INTEREST_OPTIONS.map((opt) => {
                const checked = state.interests.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() =>
                      setState((prev) => ({
                        ...prev,
                        interests: checked
                          ? prev.interests.filter((i) => i !== opt.value)
                          : [...prev.interests, opt.value],
                      }))
                    }
                    aria-pressed={checked}
                    className={
                      'flex items-center justify-center rounded-lg border px-3 py-2 text-sm font-medium transition-colors ' +
                      (checked
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-surface text-foreground hover:bg-muted')
                    }
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </Card>

      {/* Sticky save bar */}
      {dirty && (
        <div className="fixed bottom-20 left-4 right-4 z-30 md:bottom-4 md:left-auto md:right-8 md:w-auto animate-fade-in-up">
          <Card
            padding="sm"
            variant="elevated"
            className="flex items-center justify-between gap-3 border-primary/30 shadow-lg md:gap-6"
          >
            <span className="text-sm font-medium text-foreground">Unsaved changes</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleReset} disabled={saving}>
                Reset
              </Button>
              <Button size="sm" onClick={handleSave} loading={saving}>
                <Check className="h-4 w-4" aria-hidden="true" />
                Save preferences
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

interface FieldProps {
  label: string;
  hint?: string;
  helpKey?: string;
  children: React.ReactNode;
}

function Field({ label, hint, helpKey, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {helpKey ? (
        <div className="flex items-center gap-1.5">
          <Label>{label}</Label>
          <InfoTooltip i18nKey={helpKey} align="start" />
        </div>
      ) : (
        <Label>{label}</Label>
      )}
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

interface RecordsListProps {
  records: PersonalRecord[];
  onRemove: (id: string) => void;
}

const KNOWN_DISTANCES: Record<string, number> = {
  '5K': 5,
  '10K': 10,
  Semi: 21.097,
  Marathon: 42.195,
  '5k': 5,
  '10k': 10,
  semi: 21.097,
  marathon: 42.195,
  'Semi-marathon': 21.097,
  'semi-marathon': 21.097,
  '21K': 21.097,
  '21k': 21.097,
  '42K': 42.195,
  '42k': 42.195,
};

function computePace(distance: string, time: string): { pace: string; speed: string } {
  const distRaw = distance.replace(/\s*(km|K)\s*$/i, '').trim();
  const distKm = KNOWN_DISTANCES[distance] || KNOWN_DISTANCES[distRaw] || parseFloat(distRaw) || 0;

  let totalSec = 0;
  const timeStr = time.trim();
  const hOnly = timeStr.match(/^(\d+)h(\d{1,2})(?::(\d{2}))?$/i);
  if (hOnly) {
    totalSec = parseInt(hOnly[1], 10) * 3600 + parseInt(hOnly[2], 10) * 60 + (hOnly[3] ? parseInt(hOnly[3], 10) : 0);
  } else {
    const cleaned = timeStr.replace(/['"]/g, ':').replace(/:+/g, ':').replace(/:$/, '');
    const hms = cleaned.match(/^(\d+):(\d{1,2}):(\d{2})$/);
    const ms = cleaned.match(/^(\d+):(\d{2})$/);
    if (hms) totalSec = parseInt(hms[1], 10) * 3600 + parseInt(hms[2], 10) * 60 + parseInt(hms[3], 10);
    else if (ms) totalSec = parseInt(ms[1], 10) * 60 + parseInt(ms[2], 10);
  }

  if (distKm > 0 && totalSec > 0) {
    const paceSec = totalSec / distKm;
    const pM = Math.floor(paceSec / 60);
    const pS = Math.round(paceSec % 60);
    return {
      pace: `${pM}:${pS.toString().padStart(2, '0')}/km`,
      speed: `${(distKm / (totalSec / 3600)).toFixed(1)} km/h`,
    };
  }
  return { pace: '', speed: '' };
}

function RecordsList({ records, onRemove }: RecordsListProps) {
  const { t } = useTranslation();
  if (records.length === 0) {
    return (
      <EmptyState
        illustration="records"
        title={t('empty.records.title')}
        description={t('preferences.records.empty')}
      />
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-border">
      {records.map((record) => {
        const { pace, speed } = computePace(record.distance, record.time);
        return (
          <li key={record.id} className="flex items-center justify-between gap-3 py-3">
            <div className="flex flex-1 flex-col gap-0.5 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-foreground">{record.distance || '—'}</span>
                <span className="font-numeric tabular-nums text-sm text-foreground">{record.time || '—'}</span>
                {pace && (
                  <span className="text-xs text-info">
                    {pace} · {speed}
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground truncate">
                {[record.event, record.date].filter(Boolean).join(' · ') || '—'}
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onRemove(record.id)}
              aria-label="Remove record"
              className="text-muted-foreground hover:text-danger"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

const DISTANCE_OPTIONS: SelectOption[] = [
  { value: '5K', label: '5K' },
  { value: '10K', label: '10K' },
  { value: 'Semi', label: 'Half-marathon' },
  { value: 'Marathon', label: 'Marathon' },
  { value: 'custom', label: 'Other...' },
];

interface AddRecordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdd: (record: PersonalRecord) => void;
}

function AddRecordDialog({ open, onOpenChange, onAdd }: AddRecordDialogProps) {
  const [distanceChoice, setDistanceChoice] = useState('5K');
  const [customDistance, setCustomDistance] = useState('');
  const [time, setTime] = useState('');
  const [date, setDate] = useState('');
  const [event, setEvent] = useState('');

  const reset = () => {
    setDistanceChoice('5K');
    setCustomDistance('');
    setTime('');
    setDate('');
    setEvent('');
  };

  const handleSubmit = () => {
    const distance = distanceChoice === 'custom' ? customDistance.trim() : distanceChoice;
    if (!distance || !time.trim()) return;
    onAdd({
      id: crypto.randomUUID(),
      distance,
      time: time.trim(),
      date: date.trim(),
      event: event.trim(),
    });
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[92vw] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-lg animate-fade-in-up">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title className="text-lg font-semibold text-foreground">Add personal record</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                Enter your benchmark time. Pace is computed automatically.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <form
            className="mt-4 flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
          >
            <Field label="Distance">
              <Select
                options={DISTANCE_OPTIONS}
                value={distanceChoice}
                onChange={setDistanceChoice}
                placeholder="Choose..."
              />
            </Field>
            {distanceChoice === 'custom' && (
              <Field label="Custom distance">
                <Input
                  value={customDistance}
                  onChange={(e) => setCustomDistance(e.target.value)}
                  placeholder="e.g. 15K, 8.5"
                />
              </Field>
            )}
            <Field label="Time" hint="Format: 22:15 or 1:42:00">
              <Input value={time} onChange={(e) => setTime(e.target.value)} placeholder="22:15" />
            </Field>
            <Field label="Date" hint="Optional, ISO format">
              <Input
                value={date}
                onChange={(e) => setDate(e.target.value)}
                placeholder="2026-03-15"
                type="date"
              />
            </Field>
            <Field label="Event" hint="Optional">
              <Input value={event} onChange={(e) => setEvent(e.target.value)} placeholder="Parkrun, Paris half..." />
            </Field>

            <div className="mt-2 flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button type="submit" disabled={!time.trim() || (distanceChoice === 'custom' && !customDistance.trim())}>
                Add record
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function StrengthProgramSection({
  sessions,
  onChange,
}: {
  sessions: StrengthSession[];
  onChange: (sessions: StrengthSession[]) => void;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggleCollapse = (id: string) =>
    setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }));

  const addSession = () =>
    onChange([...sessions, { id: crypto.randomUUID(), name: '', frequency: '', exercises: [] }]);

  const removeSession = (id: string) => onChange(sessions.filter((s) => s.id !== id));

  const updateSession = (id: string, field: 'name' | 'frequency', value: string) =>
    onChange(sessions.map((s) => (s.id === id ? { ...s, [field]: value } : s)));

  const addExercise = (sessionId: string) =>
    onChange(
      sessions.map((s) =>
        s.id === sessionId ? { ...s, exercises: [...s.exercises, { name: '', sets: '', load: '', rest: '' }] } : s
      )
    );

  const removeExercise = (sessionId: string, idx: number) =>
    onChange(
      sessions.map((s) =>
        s.id === sessionId ? { ...s, exercises: s.exercises.filter((_, i) => i !== idx) } : s
      )
    );

  const updateExercise = (sessionId: string, idx: number, field: keyof StrengthExercise, value: string) =>
    onChange(
      sessions.map((s) =>
        s.id === sessionId
          ? { ...s, exercises: s.exercises.map((e, i) => (i === idx ? { ...e, [field]: value } : e)) }
          : s
      )
    );

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle>Programme Musculation</CardTitle>
        <CardDescription>
          Ton programme de référence. Le coach compare tes séances réelles avec ce plan pour tracker les progressions.
        </CardDescription>
      </CardHeader>
      <div className="flex flex-col gap-4">
        {sessions.map((session) => {
          const isCollapsed = collapsed[session.id];
          return (
            <div key={session.id} className="rounded-lg border border-border p-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleCollapse(session.id)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                <Input
                  value={session.name}
                  onChange={(e) => updateSession(session.id, 'name', e.target.value)}
                  placeholder="Nom de la séance"
                  className="flex-1"
                />
                <Input
                  value={session.frequency}
                  onChange={(e) => updateSession(session.id, 'frequency', e.target.value)}
                  placeholder="Fréquence (ex: 2x/sem)"
                  className="w-36"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => removeSession(session.id)}
                  className="text-muted-foreground hover:text-danger"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              {!isCollapsed && (
                <div className="mt-3 flex flex-col gap-2">
                  {session.exercises.length > 0 && (
                    <div className="hidden text-xs font-medium text-muted-foreground md:grid md:grid-cols-[1fr_80px_80px_80px_32px] md:gap-2">
                      <span>Exercice</span>
                      <span>Séries</span>
                      <span>Charge</span>
                      <span>Repos</span>
                      <span />
                    </div>
                  )}
                  {session.exercises.map((ex, idx) => (
                    <div
                      key={idx}
                      className="grid grid-cols-2 gap-2 md:grid-cols-[1fr_80px_80px_80px_32px]"
                    >
                      <Input
                        value={ex.name}
                        onChange={(e) => updateExercise(session.id, idx, 'name', e.target.value)}
                        placeholder="Exercice"
                        className="col-span-2 md:col-span-1"
                      />
                      <Input
                        value={ex.sets}
                        onChange={(e) => updateExercise(session.id, idx, 'sets', e.target.value)}
                        placeholder="4x8"
                      />
                      <Input
                        value={ex.load}
                        onChange={(e) => updateExercise(session.id, idx, 'load', e.target.value)}
                        placeholder="60kg"
                      />
                      <Input
                        value={ex.rest}
                        onChange={(e) => updateExercise(session.id, idx, 'rest', e.target.value)}
                        placeholder="90s"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => removeExercise(session.id, idx)}
                        className="text-muted-foreground hover:text-danger"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  <Button variant="outline" size="sm" onClick={() => addExercise(session.id)} className="self-start">
                    <Plus className="h-4 w-4" />
                    Ajouter exercice
                  </Button>
                </div>
              )}
            </div>
          );
        })}
        <Button variant="outline" size="sm" onClick={addSession} className="self-start">
          <Plus className="h-4 w-4" />
          Ajouter une séance
        </Button>
      </div>
    </Card>
  );
}
