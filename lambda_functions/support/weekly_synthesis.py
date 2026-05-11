"""Weekly Synthesis Lambda - Generates a weekly training summary every Sunday."""

import json
import os
import boto3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict
from shared.logger import get_logger

logger = get_logger("weekly-synthesis")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Generate weekly training synthesis."""
    try:
        user_id = DEFAULT_USER_ID
        if not user_id:
            return {"statusCode": 400, "error": "No DEFAULT_USER_ID configured"}

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
            return {"statusCode": 200, "message": "No activities this week"}

        # Compute week stats
        total_km = sum(float(a.get("distance", 0)) for a in activities) / 1000
        total_sessions = len(activities)
        total_time_min = sum(float(a.get("moving_time", 0)) for a in activities) / 60
        run_activities = [a for a in activities if a.get("activity_type") == "Run"]
        avg_hr = 0
        if run_activities:
            hrs = [float(a.get("average_heartrate", 0)) for a in run_activities if a.get("average_heartrate")]
            avg_hr = round(sum(hrs) / len(hrs)) if hrs else 0

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
- FC moyenne (runs): {avg_hr} bpm
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
            inferenceConfig={"maxTokens": 500, "temperature": 0.7},
        )

        output = response.get("output", {}).get("message", {}).get("content", [])
        response_text = "".join(block.get("text", "") for block in output)

        # Parse JSON response
        import re
        cleaned = re.sub(r"```json\s*", "", response_text)
        cleaned = re.sub(r"```\s*", "", cleaned)
        synthesis = json.loads(cleaned)

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
        return {"statusCode": 200, "synthesis": synthesis}

    except Exception as e:
        logger.error(f"Weekly synthesis error: {e}")
        return {"statusCode": 500, "error": str(e)}
