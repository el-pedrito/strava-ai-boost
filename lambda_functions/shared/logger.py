"""
Shared structured logging using AWS Lambda Powertools.

Usage:
    from shared.logger import get_logger, metrics

    logger = get_logger(__name__)
    logger.info("Processing activity", extra={"activity_id": "123"})
"""

from typing import Any, Dict
import warnings

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit


METRICS_NAMESPACE = "StravaAIBoost"

# Every metric in this project is ANOMALY-ONLY: CoachClaimMismatch,
# WebhookRejectedForeignOrigin, StrengthHistoryWriteFailed and friends are recorded
# only when the thing they name actually happens. An invocation that records nothing is
# therefore the expected, healthy case -- but @log_metrics warns on every such flush.
# Python's warning registry dedupes it to once per process rather than once per
# invocation, so the cost is one spurious stderr line per cold container, not per call.
# Suppressed anyway, and deliberately NOT by inventing a dummy metric to keep the set
# non-empty: the warning is reporting a state we already know about and chose.
warnings.filterwarnings(
    "ignore",
    message="No application metrics to publish",
    category=UserWarning,
)


def get_logger(service: str = "strava-ai-boost") -> Logger:
    return Logger(service=service, log_uncaught_exceptions=True)


def inject_correlation_id(logger: Logger, event: Dict[str, Any]) -> None:
    """Extract API Gateway requestId and set it as correlation ID on the logger."""
    request_id = (event.get("requestContext") or {}).get("requestId")
    if request_id:
        logger.set_correlation_id(request_id)


def get_metrics(service: str = "strava-ai-boost") -> Metrics:
    return Metrics(namespace=METRICS_NAMESPACE, service=service)


# Pre-configured metrics instance for business metrics
metrics = get_metrics()

# Re-export for convenience
__all__ = ["get_logger", "get_metrics", "inject_correlation_id", "metrics", "MetricUnit", "METRICS_NAMESPACE"]
