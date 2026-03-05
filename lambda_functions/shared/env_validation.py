import os
import logging
from typing import List

logger = logging.getLogger(__name__)


def validate_env_vars(required: List[str], context: str = "Lambda") -> None:
    missing = [var for var in required if not os.environ.get(var)]
    if missing:
        msg = f"{context}: missing required environment variables: {', '.join(missing)}"
        logger.error(msg)
        raise EnvironmentError(msg)
