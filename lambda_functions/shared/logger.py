"""
Shared structured logging using AWS Lambda Powertools.

Usage:
    from shared.logger import get_logger, metrics

    logger = get_logger(__name__)
    logger.info("Processing activity", extra={"activity_id": "123"})
"""

from typing import Any, Dict

from aws_lambda_powertools import Logger, Metrics
from aws_lambda_powertools.metrics import MetricUnit


METRICS_NAMESPACE = "StravaAIBoost"


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
