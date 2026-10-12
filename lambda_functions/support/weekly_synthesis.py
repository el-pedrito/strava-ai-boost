"""Weekly Synthesis Lambda - Generates a weekly training summary every Sunday."""

import json
import os
import re
import boto3
from aws_lambda_powertools.metrics import single_metric
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple
from shared.logger import get_logger, MetricUnit, METRICS_NAMESPACE
from shared.llm_models import no_thinking, text_from_converse


def _activity_hr(item: Dict[str, Any]) -> Any:
    """Average HR of an activity item, from the top level or activity_data_json."""
    hr = item.get("average_heartrate")
    if not hr:
        try:
            hr = json.loads(item.get("activity_data_json") or "{}").get("average_heartrate")
        except (TypeError, ValueError):
            hr = None
    try:
        return float(hr) if hr else None
    except (TypeError, ValueError):
        return None

logger = get_logger("weekly-synthesis")

# Business metric "an artefact was produced" (reliability plan, lot 1).
#
# This handler used to answer {"statusCode": 500} on failure, which no alarm reads, and
# the synthesis silently stopped for days. Now every run records one
# WeeklySynthesisProduced datapoint and a failure RAISES, so Lambda Errors counts it:
#   ok     -- synthesis stored
#   empty  -- no activity in the last 7 days: nothing to summarise. Not raised, and
#             counted as "ran" by the missing alarm so a rest week stays quiet
#   failed -- any failure, including a model answer with no summary (raised)
SYNTHESIS_METRIC_NAME = "WeeklySynthesisProduced"


class GenerationFailed(RuntimeError):
    """The synthesis could not be produced."""


def _record_outcome(outcome: str) -> None:
    """Emit WeeklySynthesisProduced{outcome} as its own EMF blob (dimensions: outcome)."""
    try:
        with single_metric(
            name=SYNTHESIS_METRIC_NAME, unit=MetricUnit.Count, value=1,
            namespace=METRICS_NAMESPACE,
        ) as metric:
            metric.add_dimension(name="outcome", value=outcome)
    except Exception as exc:  # noqa: BLE001 - a metric must never mask the real error
        logger.warning(f"Could not emit {SYNTHESIS_METRIC_NAME}{{outcome={outcome}}}: {exc}")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")
from shared.llm_models import resolve_sonnet_model_id

BEDROCK_MODEL_ID = resolve_sonnet_model_id()

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Generate weekly training synthesis.

    Raises on failure (after emitting outcome=failed) so Lambda Errors and the
    async retry both see it.
    """
    try:
        result, outcome = _generate_synthesis()
    except Exception as e:
        logger.exception(f"Weekly synthesis not produced: {e}")
        _record_outcome("failed")
        raise
    _record_outcome(outcome)
    return result


def _generate_synthesis() -> Tuple[Dict[str, Any], str]:
    """Build and store the synthesis. Returns (response payload, metric outcome)."""
    user_id = DEFAULT_USER_ID
    if not user_id:
        raise GenerationFailed("No DEFAULT_USER_ID configured")

    # Get this week's activities (last 7 days)
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).isoformat()

    table = dynamodb.Table(ACTIVITIES_TABLE)
    resp = table.query(
        IndexName="UserActivitiesIndex",
        KeyConditionExpression="user_id = :uid AND created_at >= :since",
        ExpressionAttributeValues={":uid": user_id, ":since": week_start},
    )
    activities = resp.get("Items", [])

    if not activities:
        logger.info("No activities this week, skipping synthesis")
        return {"statusCode": 200, "message": "No activities this week"}, "empty"

    # Compute week stats
    total_km = sum(float(a.get("distance", 0)) for a in activities) / 1000
    total_sessions = len(activities)
    total_time_min = sum(float(a.get("moving_time", 0)) for a in activities) / 60
    run_activities = [a for a in activities if a.get("activity_type") == "Run"]
    # average_heartrate is not a top-level attribute of the activity item: it
    # lives in activity_data_json. Reading only the top level always gave 0,
    # and the synthesis told the athlete his HR strap was broken (2026-10-12).
    hrs = [hr for hr in (_activity_hr(a) for a in run_activities) if hr]
    avg_hr = round(sum(hrs) / len(hrs)) if hrs else None

    # Get user profile for context
    config_table = dynamodb.Table(USER_CONFIG_TABLE)
    config_resp = config_table.get_item(Key={"user_id": user_id})
    user_config = config_resp.get("Item", {})
    prefs = user_config.get("user_preferences", {})
    athlete_profile = prefs.get("athlete_profile", "")
    personal_records = prefs.get("personal_records", [])

    # Build prompt for weekly synthesis
    records_str = ", ".join(f"{r['distance']} en {r['time']}" for r in personal_records) if personal_records else "Non renseignés"

    prompt = f"""Génère un résumé hebdomadaire d'entraînement pour cet athlète.

Profil: {athlete_profile or 'Non renseigné'}
Records: {records_str}

Semaine écoulée:
- {total_sessions} séances, {total_km:.1f} km, {total_time_min:.0f} min total
- FC moyenne (runs): {f"{avg_hr} bpm" if avg_hr else "non disponible (ne pas commenter)"}
- Types: {', '.join(set(a.get('activity_type', 'Unknown') for a in activities))}

Réponds en JSON:
{{
  "summary": "3-4 phrases résumant la semaine (volume, intensité, points forts)",
  "next_week_plan": "2-3 phrases de recommandation pour la semaine prochaine",
  "highlight": "1 phrase: le fait marquant de la semaine"
}}"""

    # Call Bedrock
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system=[{"text": "Tu es un coach running expert. Réponds uniquement en JSON valide."}],
        # No temperature: Claude 5.5 models reject it ("deprecated for this model").
        # 1500, not 500: the 2026-10-11 synthesis was cut mid-string and the
        # json.loads failed. Thinking off, it is a short JSON, not a reasoning task.
        inferenceConfig={"maxTokens": 1500},
        additionalModelRequestFields=no_thinking(BEDROCK_MODEL_ID),
    )

    response_text = text_from_converse(response)

    # Parse JSON response
    cleaned = re.sub(r"```json\s*", "", response_text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    synthesis = json.loads(cleaned)
    if not isinstance(synthesis, dict) or not synthesis.get("summary"):
        raise GenerationFailed("Model returned a synthesis without a summary")

    # Store in user_config
    config_table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET weekly_synthesis = :ws, weekly_synthesis_date = :d",
        ExpressionAttributeValues={
            ":ws": synthesis,
            ":d": now.isoformat(),
        },
    )

    logger.info(f"Weekly synthesis generated: {total_sessions} sessions, {total_km:.1f}km")
    return {"statusCode": 200, "synthesis": synthesis}, "ok"
