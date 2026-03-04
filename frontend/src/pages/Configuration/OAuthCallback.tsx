import { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import { api } from '../../api/client.ts';

export function OAuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const error = searchParams.get('error');
    if (error) {
      const desc = searchParams.get('error_description') || 'Unknown error';
      navigate(`/config?oauth=error&message=${encodeURIComponent(`${error} - ${desc}`)}`);
      return;
    }

    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code) {
      navigate('/config?oauth=error&message=' + encodeURIComponent('No authorization code received'));
      return;
    }

    // Validate state
    const storedState = sessionStorage.getItem('oauth_state');
    if (storedState && storedState !== state) {
      navigate('/config?oauth=error&message=' + encodeURIComponent('Invalid state - possible security issue'));
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
      state,
      code_verifier: codeVerifier,
      client_id: clientId,
      client_secret: '', // Lambda gets it from Secrets Manager
    })
      .then(() => {
        navigate('/config?oauth=success');
      })
      .catch(() => {
        navigate('/config?oauth=error&message=' + encodeURIComponent('Failed to exchange OAuth code'));
      });
  }, [searchParams, navigate]);

  return (
    <Box textAlign="center" padding="xxl">
      <StatusIndicator type="loading">Connecting to Strava...</StatusIndicator>
    </Box>
  );
}
