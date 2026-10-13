"""Shared API Gateway stage logging (cdk-nag APIG1 access logs, APIG6 execution logs)."""

from typing import Any, Dict

from aws_cdk import RemovalPolicy, aws_apigateway as apigateway, aws_logs as logs
from constructs import Construct


def api_stage_logging_options(scope: Construct, log_group_id: str) -> Dict[str, Any]:
    """StageOptions kwargs enabling access logs and ERROR-level execution logs.

    - Access logs: one JSON line per request (status, latency, caller IP), 1 month.
    - Execution logs at ERROR for every method (*/*), never INFO, and data trace OFF:
      request/response bodies carry Strava payloads and Cognito JWTs.

    Relies on the account-level API Gateway CloudWatch role, which the webhook
    RestApi (cloudWatchRole) already sets for the account.
    """
    access_logs = logs.LogGroup(
        scope,
        log_group_id,
        retention=logs.RetentionDays.ONE_MONTH,
        removal_policy=RemovalPolicy.DESTROY,
    )
    return {
        "access_log_destination": apigateway.LogGroupLogDestination(access_logs),
        "access_log_format": apigateway.AccessLogFormat.json_with_standard_fields(
            caller=False,
            http_method=True,
            ip=True,
            protocol=True,
            request_time=True,
            resource_path=True,
            response_length=True,
            status=True,
            user=False,
        ),
        "logging_level": apigateway.MethodLoggingLevel.ERROR,
        "data_trace_enabled": False,
    }
