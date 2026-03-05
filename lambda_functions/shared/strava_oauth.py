import logging
from datetime import datetime, UTC
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http_session: requests.Session | None = None,
) -> Optional[Dict[str, Any]]:
    token_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }

    session = http_session or requests
    response = session.post(STRAVA_TOKEN_URL, data=token_data, timeout=30)

    if response.status_code != 200:
        logger.error(f"Token refresh failed: {response.status_code}")
        return None

    new_tokens = response.json()
    if 'access_token' not in new_tokens:
        logger.error("Invalid token refresh response")
        return None

    new_tokens['obtained_at'] = datetime.now(UTC).isoformat()
    new_tokens['last_refreshed'] = datetime.now(UTC).isoformat()
    logger.info("Successfully refreshed access token")
    return new_tokens
