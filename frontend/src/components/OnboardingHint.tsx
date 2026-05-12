import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Sparkles, X } from 'lucide-react';
import { Button, Card } from '@/ui';
import { api } from '../api/client.ts';
import { ONBOARDING_DONE_KEY } from '../pages/Onboarding/OnboardingPage.tsx';

interface Props {
  /** If provided, skips internal fetch. */
  oauthConnected?: boolean;
}

function readDone(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_DONE_KEY) === '1';
  } catch {
    return false;
  }
}

export function OnboardingHint({ oauthConnected }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [done, setDone] = useState<boolean>(() => readDone());
  const [connected, setConnected] = useState<boolean | undefined>(oauthConnected);

  useEffect(() => {
    if (oauthConnected !== undefined) {
      setConnected(oauthConnected);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<{ connected: boolean }>('/config/oauth');
        if (!cancelled) setConnected(res?.connected ?? false);
      } catch {
        if (!cancelled) setConnected(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [oauthConnected]);

  const dismiss = useCallback(() => {
    try {
      window.localStorage.setItem(ONBOARDING_DONE_KEY, '1');
    } catch {
      // ignore
    }
    setDone(true);
  }, []);

  if (done) return null;
  if (connected === undefined) return null;
  // Show only when something still needs setup. For now: not Strava-connected.
  if (connected) return null;

  return (
    <Card
      padding="md"
      variant="elevated"
      className="border-primary/30 bg-primary/5"
      role="region"
      aria-label={t('onboarding.hint.aria')}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-3">
          <span
            className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
            aria-hidden="true"
          >
            <Sparkles className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              {t('onboarding.hint.title')}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t('onboarding.hint.description')}
            </p>
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <Button size="sm" onClick={() => navigate('/onboarding')}>
            {t('onboarding.hint.cta')}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={dismiss}
            aria-label={t('onboarding.hint.dismissAria')}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
