"""Coach Ask API - Conversational endpoint using AgentCore Runtime session."""

import json
import os
import time
import re
import boto3
from typing import Any, Dict
from shared.logger import get_logger, inject_correlation_id
from shared.responses import CORS_HEADERS_READ as CORS_HEADERS, create_success_response, create_error_response

logger = get_logger("coach-ask-api")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
COACH_AGENT_ARN = os.environ.get("COACH_AGENT_ARN", "")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /coach/ask - conversational coach via AgentCore session."""
    inject_correlation_id(logger, event)

    try:
        body = json.loads(event.get("body", "{}"))
        question = body.get("question", "").strip()
        user_id = body.get("user_id", DEFAULT_USER_ID)
        session_id = body.get("session_id", "")

        if not question:
            return create_error_response(400, "Missing 'question' field", cors_headers=CORS_HEADERS)
        if len(question) > 500:
            return create_error_response(400, "Question too long (max 500 chars)", cors_headers=CORS_HEADERS)

        # Use a persistent session per user (survives across messages)
        if not session_id or len(session_id) < 33:
            import uuid
            session_id = f"coach-chat-session-{user_id}-{uuid.uuid4().hex}"

        # Build context for the agent
        context_parts = _build_user_context(user_id)

        # Read past coaching observations from memory
        memory_context = _retrieve_memory_observations(user_id)
        if memory_context:
            context_parts.append(f"Observations passées: {memory_context}")

        user_message = question
        if context_parts:
            user_message = f"[Contexte: {' | '.join(context_parts)}]\n\n{question}"

        # Invoke AgentCore Runtime with session (maintains conversation state)
        if COACH_AGENT_ARN:
            answer = _invoke_coach_session(user_message, session_id)
        else:
            # Fallback to direct Bedrock if no agent configured
            answer = _fallback_bedrock(question, context_parts, body.get("history", []))

        if not answer:
            return create_error_response(500, "No response from coach", cors_headers=CORS_HEADERS)

        # Write important exchanges to memory for long-term learning
        _write_chat_to_memory(user_id, question, answer)

        logger.info(f"Coach ask: '{question[:50]}' → {len(answer)} chars")

        return create_success_response({
            "answer": answer,
            "question": question,
            "session_id": session_id,
        }, cors_headers=CORS_HEADERS)

    except json.JSONDecodeError:
        return create_error_response(400, "Invalid JSON", cors_headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Coach ask error: {e}")
        return create_error_response(500, "Failed to get coach response", cors_headers=CORS_HEADERS)


def _invoke_coach_session(message: str, session_id: str) -> str:
    """Invoke coach agent via AgentCore Runtime with persistent session."""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
    except Exception:
        client = boto3.client("bedrock-agent-runtime", region_name=REGION)

    payload = json.dumps({"question": message, "mode": "conversation"}).encode("utf-8")

    # Retry for cold start
    for attempt in range(2):
        try:
            response = client.invoke_agent_runtime(
                agentRuntimeArn=COACH_AGENT_ARN,
                runtimeSessionId=session_id,
                payload=payload,
            )
            break
        except Exception as e:
            if attempt == 0 and "RuntimeClientError" in str(e):
                logger.warning("Coach agent cold start, retrying in 10s...")
                time.sleep(10)
            else:
                raise

    # Parse response
    completion = ""
    content_type = response.get("contentType", "")
    if "text/event-stream" in content_type:
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                try:
                    line = line.decode("utf-8", errors="replace")
                except Exception:
                    continue
                if line.startswith("data: "):
                    completion += line[6:]
    elif content_type == "application/json":
        chunks = []
        for chunk in response.get("response", []):
            try:
                chunks.append(chunk.decode("utf-8", errors="replace"))
            except Exception:
                continue
        completion = "".join(chunks)
    else:
        completion = str(response.get("response", ""))

    # Extract answer from agent response
    try:
        outer = json.loads(completion)
        return outer.get("response", completion) if isinstance(outer, dict) else completion
    except (json.JSONDecodeError, TypeError):
        return completion


def _fallback_bedrock(question: str, context_parts: list, history: list) -> str:
    """Fallback: direct Bedrock call when no AgentCore agent configured."""
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

    context_str = "\n".join(context_parts) if context_parts else "Pas de contexte disponible."
    system_prompt = f"""Tu es un coach running expert, bienveillant et direct.

Contexte athlète:
{context_str}

Règles: tutoiement, réponses concises (3-5 phrases), factuel."""

    messages = [*[{"role": m["role"], "content": [{"text": m["content"]}]} for m in history[-10:]], {"role": "user", "content": [{"text": question}]}]

    response = bedrock.converse(
        modelId=model_id,
        messages=messages,
        system=[{"text": system_prompt}],
        inferenceConfig={"maxTokens": 500, "temperature": 0.7},
    )

    output = response.get("output", {}).get("message", {}).get("content", [])
    return "".join(block.get("text", "") for block in output)


def _build_user_context(user_id: str) -> list:
    """Build athlete context from DynamoDB.

    Includes athlete profile, records, weekly volume summary, and a detailed
    list of recent enriched activities so the coach can refer to specific sessions
    (title, date, type, distance, pace, HR, modules, AI title/description, coach feedback).
    """
    context_parts = []
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        resp = table.get_item(Key={"user_id": user_id})
        user_config = resp.get("Item", {})
        prefs = user_config.get("user_preferences", {})
        if prefs.get("athlete_profile"):
            context_parts.append(f"Profil: {prefs['athlete_profile'][:200]}")
        if prefs.get("personal_records"):
            records = ", ".join(f"{r['distance']} en {r['time']}" for r in prefs['personal_records'])
            context_parts.append(f"Records: {records}")
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")

    try:
        from datetime import datetime, timezone, timedelta
        table = dynamodb.Table(ACTIVITIES_TABLE)
        four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()
        resp = table.query(
            IndexName="UserActivitiesIndex",
            KeyConditionExpression="user_id = :uid AND created_at >= :since",
            ExpressionAttributeValues={":uid": user_id, ":since": four_weeks_ago},
        )
        activities = resp.get("Items", [])
        if activities:
            # Aggregate summary
            total_km = sum(float(a.get("distance", 0) or 0) for a in activities) / 1000
            context_parts.append(f"4 semaines: {len(activities)} activités, {total_km:.0f}km")

            # Build detailed list of last 12 activities (most recent first) so
            # the coach can answer questions about specific sessions.
            activities.sort(key=lambda a: a.get("start_date") or a.get("created_at", ""), reverse=True)
            details = _format_recent_activities(activities[:12])
            if details:
                context_parts.append("Dernières séances détaillées:\n" + details)
    except Exception as e:
        logger.warning(f"Failed to get activities: {e}")

    return context_parts


def _format_recent_activities(activities: list) -> str:
    """Format a list of activities into a compact textual block for the coach prompt.

    Each line: date | type | title | distance | duration | pace | HR | modules | feedback summary.
    Truncated to keep the prompt within token budget (~150 chars per session max).
    """
    lines = []
    for a in activities:
        try:
            date = (a.get("start_date") or a.get("start_date_local") or a.get("created_at", ""))[:10]
            atype = a.get("activity_type", "?")
            title = a.get("enhanced_title") or a.get("original_name", "Activité")
            title = title[:60]

            distance_m = float(a.get("distance", 0) or 0)
            distance_str = f"{distance_m / 1000:.1f}km" if distance_m else "-"

            moving_s = float(a.get("moving_time", 0) or 0)
            duration_str = f"{int(moving_s // 60)}min" if moving_s else "-"

            # Pace (min/km) for runs
            pace_str = "-"
            if atype == "Run" and distance_m > 0 and moving_s > 0:
                pace_s_per_km = moving_s / (distance_m / 1000)
                pace_str = f"{int(pace_s_per_km // 60)}:{int(pace_s_per_km % 60):02d}/km"

            avg_hr = a.get("average_heartrate")
            max_hr = a.get("max_heartrate")
            hr_parts = []
            if avg_hr:
                hr_parts.append(f"avg {int(float(avg_hr))}")
            if max_hr:
                hr_parts.append(f"max {int(float(max_hr))}")
            hr_str = f"FC {' / '.join(hr_parts)}" if hr_parts else ""

            modules = a.get("modules_used", []) or []
            mod_str = f"modules: {', '.join(modules[:4])}" if modules else ""

            ai_desc = a.get("enhanced_description") or ""
            if ai_desc:
                ai_desc = ai_desc[:120].replace("\n", " ")

            # Coach feedback: extract short strava_block summary if present
            fb = a.get("coach_feedback")
            fb_str = ""
            if fb:
                if isinstance(fb, str):
                    try:
                        fb = json.loads(fb)
                    except (json.JSONDecodeError, TypeError):
                        fb = None
                if isinstance(fb, dict):
                    block = fb.get("strava_block") or fb.get("detailed_analysis") or ""
                    if isinstance(block, str) and block:
                        fb_str = f"feedback: {block[:140].replace(chr(10), ' ')}"

            parts = [
                f"- {date} | {atype} | {title} | {distance_str} | {duration_str} | {pace_str}",
            ]
            if hr_str:
                parts.append(hr_str)
            if mod_str:
                parts.append(mod_str)
            if ai_desc:
                parts.append(f"desc: {ai_desc}")
            if fb_str:
                parts.append(fb_str)
            lines.append(" | ".join(parts))
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Skipping activity in context: {e}")
            continue
    return "\n".join(lines)


MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID", "")


def _retrieve_memory_observations(user_id: str) -> str:
    """Retrieve past coaching observations from AgentCore Memory."""
    if not MEMORY_ID:
        return ""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespace=user_id,
            searchCriteria={"semanticSearch": {"query": "coaching observations athlete patterns progression"}},
            maxResults=3,
        )
        records = response.get("memoryRecords", [])
        if records:
            texts = [r.get("content", {}).get("text", "") for r in records if r.get("content")]
            return " | ".join(t[:150] for t in texts if t)
    except Exception as e:
        logger.warning(f"Failed to retrieve memory: {e}")
    return ""


def _write_chat_to_memory(user_id: str, question: str, answer: str) -> None:
    """Write chat exchange to memory for long-term learning."""
    if not MEMORY_ID:
        return
    # Only write substantial exchanges (not greetings or short questions)
    if len(question) < 20 or len(answer) < 100:
        return
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        client.create_event(
            memoryId=MEMORY_ID,
            actorId=str(user_id),
            sessionId=f"coach-chat-{user_id}",
            payload=[
                {"conversational": {"role": "USER", "content": {"text": question}}},
                {"conversational": {"role": "ASSISTANT", "content": {"text": answer[:500]}}},
            ],
            eventTimestamp=time.time(),
        )
        logger.info(f"Wrote chat exchange to memory for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to write chat to memory: {e}")
