import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../api/client.ts';

type CallbackState =
  | { kind: 'loading' }
  | { kind: 'success' }
  | { kind: 'error'; message: string };

export function OAuthCallback() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const processed = useRef(false);
  const [state, setState] = useState<CallbackState>({ kind: 'loading' });

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const error = searchParams.get('error');
    if (error) {
      const desc = searchParams.get('error_description') || t('oauthCallback.errorUnknown');
      navigate(`/config?oauth=error&message=${encodeURIComponent(`${error} - ${desc}`)}`);
      return;
    }

    const code = searchParams.get('code');
    const oauthState = searchParams.get('state');

    if (!code) {
      navigate('/config?oauth=error&message=' + encodeURIComponent(t('oauthCallback.errorNoCode')));
      return;
    }

    // Validate state
    const storedState = sessionStorage.getItem('oauth_state');
    if (storedState && storedState !== oauthState) {
      navigate('/config?oauth=error&message=' + encodeURIComponent(t('oauthCallback.errorInvalidState')));
      return;
    }

    const codeVerifier = sessionStorage.getItem('oauth_code_verifier') || '';
    const clientId = sessionStorage.getItem('oauth_client_id') || '';

    // Clean up sessionStorage
    sessionStorage.removeItem('oauth_state');
    sessionStorage.removeItem('oauth_code_verifier');
    sessionStorage.removeItem('oauth_client_id');

    // Exchange code for token via API Gateway
    api.post('/config/oauth', {
      code,
      state: oauthState,
      code_verifier: codeVerifier,
      client_id: clientId,
      client_secret: '', // Lambda gets it from Secrets Manager
    })
      .then(() => {
        setState({ kind: 'success' });
        navigate('/config?oauth=success');
      })
      .catch(() => {
        const msg = t('oauthCallback.errorExchange');
        setState({ kind: 'error', message: msg });
        navigate('/config?oauth=error&message=' + encodeURIComponent(msg));
      });
  }, [searchParams, navigate, t]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-center">
        {state.kind === 'loading' && (
          <>
            <div
              className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary"
              aria-label={t('common.loading')}
            />
            <p className="text-sm text-muted-foreground">{t('oauthCallback.connecting')}</p>
          </>
        )}
        {state.kind === 'success' && (
          <>
            <CheckCircle2 className="h-10 w-10 text-success" aria-hidden="true" />
            <p className="text-base font-medium">{t('oauthCallback.success')}</p>
            <p className="text-sm text-muted-foreground">{t('oauthCallback.redirecting')}</p>
          </>
        )}
        {state.kind === 'error' && (
          <>
            <AlertCircle className="h-10 w-10 text-danger" aria-hidden="true" />
            <p className="text-base font-medium">{t('oauthCallback.failed')}</p>
            <p className="text-sm text-muted-foreground">{state.message}</p>
          </>
        )}
      </div>
    </div>
  );
}
