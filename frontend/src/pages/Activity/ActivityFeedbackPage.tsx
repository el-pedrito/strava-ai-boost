import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { Alert, Button, Card, CardDescription, CardHeader, CardTitle, Label, Textarea } from '../../ui';
import { ApiError, getActivityFeedback, submitActivityFeedback } from '../../api/client.ts';
import { cn } from '../../lib/cn.ts';
import { formatLocalTime } from '../../utils/formatDate.ts';

/** Same bound as the API (plan §6): longer text is rejected with a 400. */
export const SUMMARY_MAX_LENGTH = 2000;

const RPE_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

type View = 'loading' | 'form' | 'done' | 'sent' | 'unavailable';

/**
 * Post-session input screen, opened from the "how did it feel" push
 * notification (`/activities/<id>/feedback`). Mobile first.
 *
 * Reads the window state first and only shows the form while it is
 * `awaiting`; anything else, and a 409 on submit, reads "already processed".
 * The athlete gives an RPE (1-10, required) and an optional summary (the
 * textarea accepts iOS dictation). The input goes to the agents, never as is
 * to Strava (D1).
 */
export function ActivityFeedbackPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id = '' } = useParams<{ id: string }>();
  const validId = /^\d+$/.test(id);

  const [view, setView] = useState<View>(validId ? 'loading' : 'unavailable');
  const [rpe, setRpe] = useState<number | null>(null);
  const [summary, setSummary] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deadline, setDeadline] = useState<string | null>(null);
  const rpeRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!validId) return;
    let cancelled = false;
    getActivityFeedback(id)
      .then((res) => {
        if (cancelled) return;
        setDeadline(formatLocalTime(res.deadline_at));
        setView(res.state === 'awaiting' ? 'form' : 'done');
      })
      .catch(() => {
        if (!cancelled) setView('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [id, validId]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (rpe === null || submitting) return;
    setSubmitting(true);
    setError(null);
    const text = summary.trim();
    try {
      await submitActivityFeedback(id, text ? { rpe, summary: text } : { rpe });
      setView('sent');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setView('done');
      } else if (err instanceof ApiError && err.status === 400) {
        setError(t('activityFeedback.error.invalid'));
      } else if (err instanceof ApiError && err.status === 403) {
        setError(t('activityFeedback.error.forbidden'));
      } else {
        setError(t('activityFeedback.error.generic'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Radio-group keyboard model: arrows move and select, like native radios.
  const onRpeKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      next = (index + 1) % RPE_VALUES.length;
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      next = (index - 1 + RPE_VALUES.length) % RPE_VALUES.length;
    } else {
      return;
    }
    event.preventDefault();
    setRpe(RPE_VALUES[next]);
    rpeRefs.current[next]?.focus();
  };

  const backToActivity = (
    <Button variant="outline" onClick={() => navigate(`/activities/${id}`)}>
      {t('activityFeedback.viewActivity')}
    </Button>
  );

  let body;
  if (view === 'loading') {
    body = (
      <div className="flex justify-center py-12" role="status" aria-live="polite">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">{t('common.loading')}</span>
      </div>
    );
  } else if (view === 'unavailable') {
    body = (
      <div className="flex flex-col gap-4">
        <Alert variant="warning">{t('activityFeedback.unavailable')}</Alert>
        <Button variant="outline" onClick={() => navigate('/')}>
          {t('activity.backToDashboard')}
        </Button>
      </div>
    );
  } else if (view === 'done') {
    body = (
      <div className="flex flex-col gap-4" role="status">
        <Alert variant="info">{t('activityFeedback.alreadyProcessed')}</Alert>
        {validId && backToActivity}
      </div>
    );
  } else if (view === 'sent') {
    body = (
      <div className="flex flex-col items-center gap-4 py-4 text-center" role="status">
        <CheckCircle2 className="h-10 w-10 text-success" aria-hidden="true" />
        <p className="text-base font-medium text-foreground">{t('activityFeedback.sent')}</p>
        <p className="text-sm text-muted-foreground">{t('activityFeedback.sentHint')}</p>
        {backToActivity}
      </div>
    );
  } else {
    body = (
      <form className="flex flex-col gap-6" onSubmit={onSubmit} noValidate>
        {deadline && (
          <p className="text-sm text-muted-foreground">{t('activityFeedback.deadline', { time: deadline })}</p>
        )}
        <fieldset className="flex flex-col gap-3" aria-describedby="rpe-hint">
          <legend className="mb-1 text-sm font-medium text-foreground">
            {t('activityFeedback.rpe.label')}
          </legend>
          <p id="rpe-hint" className="text-xs text-muted-foreground">
            {t('activityFeedback.rpe.hint')}
          </p>
          <div
            className="grid grid-cols-5 gap-2"
            role="radiogroup"
            aria-label={t('activityFeedback.rpe.label')}
            aria-required="true"
          >
            {RPE_VALUES.map((value, index) => {
              const selected = rpe === value;
              // Roving tabindex: one stop in the tab order, on the choice or the first value.
              const tabbable = rpe === null ? index === 0 : selected;
              return (
                <button
                  key={value}
                  ref={(el) => {
                    rpeRefs.current[index] = el;
                  }}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  tabIndex={tabbable ? 0 : -1}
                  onKeyDown={(e) => onRpeKeyDown(e, index)}
                  aria-label={t('activityFeedback.rpe.valueAria', { value })}
                  onClick={() => setRpe(value)}
                  className={cn(
                    'h-12 rounded-lg border text-base font-semibold transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
                    selected
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-surface text-foreground hover:bg-muted',
                  )}
                >
                  {value}
                </button>
              );
            })}
          </div>
          <div className="flex justify-between text-xs text-muted-foreground" aria-hidden="true">
            <span>{t('activityFeedback.rpe.easy')}</span>
            <span>{t('activityFeedback.rpe.max')}</span>
          </div>
        </fieldset>

        <div className="flex flex-col gap-2">
          <Label htmlFor="feedback-summary">{t('activityFeedback.summary.label')}</Label>
          <Textarea
            id="feedback-summary"
            rows={5}
            maxLength={SUMMARY_MAX_LENGTH}
            value={summary}
            onChange={(e) => setSummary(e.target.value.slice(0, SUMMARY_MAX_LENGTH))}
            placeholder={t('activityFeedback.summary.placeholder')}
            aria-describedby="feedback-summary-count"
            className="text-base"
          />
          <p id="feedback-summary-count" className="text-right text-xs text-muted-foreground">
            {t('activityFeedback.summary.count', { count: summary.length, max: SUMMARY_MAX_LENGTH })}
          </p>
        </div>

        {error && (
          <Alert variant="error" role="alert">
            {error}
          </Alert>
        )}

        <Button
          type="submit"
          size="lg"
          className="w-full"
          disabled={rpe === null || submitting}
          loading={submitting}
        >
          {t('activityFeedback.submit')}
        </Button>
        {rpe === null && (
          <p className="-mt-4 text-center text-xs text-muted-foreground">
            {t('activityFeedback.rpe.required')}
          </p>
        )}
      </form>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4 px-4 py-6">
      <Card padding="lg">
        <CardHeader>
          <CardTitle>{t('activityFeedback.title')}</CardTitle>
          <CardDescription>{t('activityFeedback.description')}</CardDescription>
        </CardHeader>
        {body}
      </Card>
    </div>
  );
}
