"""Coach Ask API - Conversational endpoint for asking questions to the coach."""

import json
import os
import boto3
from typing import Any, Dict
from shared.logger import get_logger, inject_correlation_id
from shared.responses import CORS_HEADERS_READ as CORS_HEADERS, create_success_response, create_error_response

logger = get_logger("coach-ask-api")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
COACH_AGENT_ARN = os.environ.get("COACH_AGENT_ARN", "")
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /coach/ask - conversational coach endpoint."""
    inject_correlation_id(logger, event)
    
    try:
        body = json.loads(event.get("body", "{}"))
        question = body.get("question", "").strip()
        user_id = body.get("user_id", os.environ.get("DEFAULT_USER_ID", ""))
        
        if not question:
            return create_error_response(400, "Missing 'question' field", cors_headers=CORS_HEADERS)
        if len(question) > 500:
            return create_error_response(400, "Question too long (max 500 chars)", cors_headers=CORS_HEADERS)
        
        # Build context for the coach
        context_parts = []
        
        # Get user preferences
        try:
            table = dynamodb.Table(USER_CONFIG_TABLE)
            resp = table.get_item(Key={"user_id": user_id})
            user_config = resp.get("Item", {})
            prefs = user_config.get("user_preferences", {})
            if prefs.get("athlete_profile"):
                context_parts.append(f"Profil: {prefs['athlete_profile']}")
            if prefs.get("personal_records"):
                records = ", ".join(f"{r['distance']} en {r['time']}" for r in prefs['personal_records'])
                context_parts.append(f"Records: {records}")
        except Exception as e:
            logger.warning(f"Failed to get user config: {e}")
        
        # Get recent activities summary
        try:
            from datetime import datetime, timezone, timedelta
            table = dynamodb.Table(ACTIVITIES_TABLE)
            four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()
            resp = table.query(
                IndexName="UserActivitiesIndex",
                KeyConditionExpression="user_id = :uid AND created_at >= :since",
                ExpressionAttributeValues={":uid": user_id, ":since": four_weeks_ago},
                ProjectionExpression="activity_type, distance, moving_time, created_at",
                ScanIndexForward=False,
            )
            activities = resp.get("Items", [])
            if activities:
                total_km = sum(float(a.get("distance", 0)) for a in activities) / 1000
                context_parts.append(f"4 dernières semaines: {len(activities)} activités, {total_km:.0f}km")
        except Exception as e:
            logger.warning(f"Failed to get activities: {e}")
        
        context_str = "\n".join(context_parts) if context_parts else "Pas de contexte disponible."
        
        # Call Bedrock directly for conversational response
        bedrock = boto3.client("bedrock-runtime", region_name=REGION)
        
        system_prompt = f"""Tu es un coach running expert, bienveillant et direct. Tu réponds aux questions de l'athlète en te basant sur son contexte.

Contexte athlète:
{context_str}

Règles:
- Tutoiement
- Réponses concises (3-5 phrases max sauf si question complexe)
- Factuel, pas de blabla
- Si tu ne sais pas, dis-le"""
        
        response = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": question}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"maxTokens": 500, "temperature": 0.7},
        )
        
        output = response.get("output", {}).get("message", {}).get("content", [])
        answer = "".join(block.get("text", "") for block in output)
        
        logger.info(f"Coach ask: '{question[:50]}' → {len(answer)} chars")
        
        return create_success_response({
            "answer": answer,
            "question": question,
        }, cors_headers=CORS_HEADERS)
        
    except json.JSONDecodeError:
        return create_error_response(400, "Invalid JSON", cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Coach ask error: {e}")
        return create_error_response(500, "Failed to get coach response", cors_headers=CORS_HEADERS)
