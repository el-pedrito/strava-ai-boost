import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Cog,
  ExternalLink,
  LineChart,
  Link2,
  Sparkles,
  User,
} from 'lucide-react';
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Stepper,
  type StepStatus,
} from '@/ui';
import { useFlash } from '../../layouts/AppLayout.tsx';
import { api } from '../../api/client.ts';
import type { OAuthStatus } from '../../types/index.ts';

export const ONBOARDING_DONE_KEY = 'sab.onboarding.done';

type OnboardingStep = 0 | 1 | 2 | 3;

function stepStatusFor(stepIndex: number, current: number): StepStatus {
  if (stepIndex < current) return 'done';
  if (stepIndex === current) return 'current';
  return 'todo';
}

export function OnboardingPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const flash = useFlash();
  const [current, setCurrent] = useState<OnboardingStep>(0);
  const [oauth, setOauth] = useState<OAuthStatus | null>(null);
  const [autoAdvancing, setAutoAdvancing] = useState(false);

  const fetchOauth = useCallback(async () => {
    try {
      const res = await api.get<OAuthStatus>('/config/oauth');
      setOauth(res);
      return res;
    } catch {
      setOauth({ connected: false, configured: false });
      return null;
    }
  }, []);

  useEffect(() => {
    void fetchOauth();
  }, [fetchOauth]);

  // While on step 2 (Connect Strava), poll OAuth status.
  useEffect(() => {
    if (current !== 1) return;
    const id = window.setInterval(() => {
      void fetchOauth();
    }, 4000);
    return () => window.clearInterval(id);
  }, [current, fetchOauth]);

  // Auto-advance from step 2 once connected.
  useEffect(() => {
    if (current !== 1) return;
    if (!oauth?.connected) return;
    if (autoAdvancing) return;
    setAutoAdvancing(true);
    const timer = window.setTimeout(() => {
      setCurrent(2);
      setAutoAdvancing(false);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [current, oauth?.connected, autoAdvancing]);

  const finish = useCallback(() => {
    try {
      window.localStorage.setItem(ONBOARDING_DONE_KEY, '1');
    } catch {
      // ignore
    }
    flash('success', t('onboarding.finish.flash'));
    navigate('/');
  }, [flash, navigate, t]);

  const skip = useCallback(() => {
    try {
      window.localStorage.setItem(ONBOARDING_DONE_KEY, '1');
    } catch {
      // ignore
    }
    navigate('/');
  }, [navigate]);

  const stepLabels = useMemo(
    () => [
      t('onboarding.steps.welcome'),
      t('onboarding.steps.connect'),
      t('onboarding.steps.modules'),
      t('onboarding.steps.preferences'),
    ],
    [t],
  );

  const steps = stepLabels.map((label, idx) => ({
    label,
    status: stepStatusFor(idx, current),
  }));

  const goNext = () => setCurrent((c) => (Math.min(3, c + 1) as OnboardingStep));
  const goBack = () => setCurrent((c) => (Math.max(0, c - 1) as OnboardingStep));

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 md:py-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
          {t('onboarding.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('onboarding.subtitle')}</p>
      </header>

      <Card padding="md" variant="elevated">
        <Stepper
          steps={steps}
          current={current}
          ariaLabel={t('onboarding.stepperAria')}
        />
      </Card>

      {current === 0 ? (
        <StepWelcome onNext={goNext} onSkip={skip} />
      ) : current === 1 ? (
        <StepConnect
          connected={oauth?.connected ?? false}
          onNext={goNext}
          onBack={goBack}
          onSkip={skip}
        />
      ) : current === 2 ? (
        <StepModules onNext={goNext} onBack={goBack} onSkip={skip} />
      ) : (
        <StepPreferences onBack={goBack} onFinish={finish} />
      )}
    </div>
  );
}

function StepWelcome({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  const { t } = useTranslation();
  const bullets = [
    {
      icon: Sparkles,
      title: t('onboarding.welcome.b1.title'),
      desc: t('onboarding.welcome.b1.desc'),
    },
    {
      icon: Activity,
      title: t('onboarding.welcome.b2.title'),
      desc: t('onboarding.welcome.b2.desc'),
    },
    {
      icon: LineChart,
      title: t('onboarding.welcome.b3.title'),
      desc: t('onboarding.welcome.b3.desc'),
    },
  ];

  return (
    <Card padding="lg">
      <CardHeader>
        <CardTitle className="text-2xl">{t('onboarding.welcome.title')}</CardTitle>
        <CardDescription>{t('onboarding.welcome.subtitle')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ul className="flex flex-col gap-3">
          {bullets.map((b) => {
            const Icon = b.icon;
            return (
              <li key={b.title} className="flex items-start gap-3 rounded-lg border border-border bg-surface-muted/40 p-3">
                <span
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
                  aria-hidden="true"
                >
                  <Icon className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{b.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{b.desc}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" onClick={onSkip}>
          {t('onboarding.skip')}
        </Button>
        <Button onClick={onNext}>
          {t('onboarding.welcome.cta')}
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </Card>
  );
}

function StepConnect({
  connected,
  onNext,
  onBack,
  onSkip,
}: {
  connected: boolean;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            aria-hidden="true"
          >
            <Link2 className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <CardTitle>{t('onboarding.connect.title')}</CardTitle>
            <CardDescription>{t('onboarding.connect.subtitle')}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {connected ? (
          <div className="flex items-start gap-3 rounded-lg border border-success/30 bg-success/5 p-4">
            <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-success" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                {t('onboarding.connect.connected')}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {t('onboarding.connect.connectedHint')}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-muted/40 p-4">
            <p className="text-sm text-foreground">{t('onboarding.connect.body')}</p>
            <ul className="ml-4 list-disc text-xs text-muted-foreground">
              <li>{t('onboarding.connect.bullet1')}</li>
              <li>{t('onboarding.connect.bullet2')}</li>
              <li>{t('onboarding.connect.bullet3')}</li>
            </ul>
          </div>
        )}
      </CardContent>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t('onboarding.back')}
        </Button>
        <div className="flex flex-wrap gap-2">
          {connected ? (
            <Button onClick={onNext}>
              {t('onboarding.next')}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={onSkip}>
                {t('onboarding.skip')}
              </Button>
              <Button onClick={() => navigate('/config')}>
                {t('onboarding.connect.openConfig')}
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
              </Button>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

function StepModules({
  onNext,
  onBack,
  onSkip,
}: {
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const modules = [
    {
      key: 'campus',
      title: t('onboarding.modules.campus.title'),
      desc: t('onboarding.modules.campus.desc'),
    },
    {
      key: 'enduraw',
      title: t('onboarding.modules.enduraw.title'),
      desc: t('onboarding.modules.enduraw.desc'),
    },
    {
      key: 'intervals',
      title: t('onboarding.modules.intervals.title'),
      desc: t('onboarding.modules.intervals.desc'),
    },
  ];

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            aria-hidden="true"
          >
            <Cog className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <CardTitle>{t('onboarding.modules.title')}</CardTitle>
            <CardDescription>{t('onboarding.modules.subtitle')}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {modules.map((m) => (
          <Card key={m.key} padding="md" variant="flat" className="flex flex-col gap-3">
            <div>
              <p className="text-sm font-semibold text-foreground">{m.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{m.desc}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/config#modules')}
            >
              {t('onboarding.modules.configure')}
            </Button>
          </Card>
        ))}
      </CardContent>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t('onboarding.back')}
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onSkip}>
            {t('onboarding.modules.skipAll')}
          </Button>
          <Button onClick={onNext}>
            {t('onboarding.modules.done')}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </Card>
  );
}

function StepPreferences({
  onBack,
  onFinish,
}: {
  onBack: () => void;
  onFinish: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Card padding="lg">
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            aria-hidden="true"
          >
            <User className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <CardTitle>{t('onboarding.preferences.title')}</CardTitle>
            <CardDescription>{t('onboarding.preferences.subtitle')}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{t('onboarding.preferences.body')}</p>
      </CardContent>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          {t('onboarding.back')}
        </Button>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={onFinish}>
            {t('onboarding.preferences.finish')}
          </Button>
          <Button onClick={() => navigate('/preferences')}>
            {t('onboarding.preferences.set')}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
