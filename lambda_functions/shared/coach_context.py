"""Shared coach context builders.

Extracted from coach_ask_api so both the buffered (API Gateway) handler and the
streaming (FastAPI + Lambda Web Adapter) handler build identical athlete context
without duplicating logic.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import boto3

from shared.logger import get_logger

logger = get_logger("coach-context")

REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
COACHING_SESSIONS_TABLE = os.environ.get(
    "COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"
)
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID", "")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def build_user_context(user_id: str) -> list[str]:
    """Build athlete context from DynamoDB.

    Includes athlete profile, records, weekly volume summary, and a detailed
    list of recent enriched activities so the coach can refer to specific sessions
    (title, date, type, distance, pace, HR, modules, AI title/description, coach feedback).
    """
    context_parts: list[str] = []
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        resp = table.get_item(Key={"user_id": user_id})
        user_config = resp.get("Item", {})
        prefs = user_config.get("user_preferences", {})
        if prefs.get("athlete_profile"):
            context_parts.append(f"Profil: {prefs['athlete_profile'][:200]}")
        if prefs.get("personal_records"):
            records = ", ".join(
                f"{r['distance']} en {r['time']}" for r in prefs["personal_records"]
            )
            context_parts.append(f"Records: {records}")
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")

    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()
        resp = table.query(
            IndexName="UserActivitiesIndex",
            KeyConditionExpression="user_id = :uid AND created_at >= :since",
            ExpressionAttributeValues={":uid": user_id, ":since": four_weeks_ago},
        )
        activities = resp.get("Items", [])
        if activities:
            total_km = sum(float(a.get("distance", 0) or 0) for a in activities) / 1000
            context_parts.append(f"4 semaines: {len(activities)} activités, {total_km:.0f}km")

            # Explicit per-week breakdown so the coach answers "la semaine dernière"
            # with exact numbers instead of inventing them from the 4-week blob.
            weekly = format_weekly_breakdown(activities)
            if weekly:
                context_parts.append("Récapitulatif par semaine:\n" + weekly)

            activities.sort(
                key=lambda a: a.get("start_date") or a.get("created_at", ""), reverse=True
            )
            details = format_recent_activities(activities[:12])
            if details:
                context_parts.append("Dernières séances détaillées:\n" + details)
    except Exception as e:
        logger.warning(f"Failed to get activities: {e}")

    weekly_plan = fetch_campus_weekly_plan(user_id)
    if weekly_plan:
        context_parts.append(weekly_plan)

    return context_parts


def fetch_campus_weekly_plan(user_id: str) -> str:
    """Fetch Campus Coach sessions for current week and next week.

    Uses Scan with FilterExpression on is_current_week / is_future flags.
    Returns a compact text block. Empty string if nothing found.
    """
    try:
        sessions_table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        resp = sessions_table.scan(
            FilterExpression="is_current_week = :cw OR is_future = :ft",
            ExpressionAttributeValues={":cw": True, ":ft": True},
        )
        all_sessions = resp.get("Items", [])

        # Fallback: old Browser Tool format (no is_current_week flag)
        if not all_sessions:
            fallback_resp = sessions_table.scan()
            fallback_items = fallback_resp.get("Items", [])
            if fallback_items and "week_number" in fallback_items[0]:
                latest_week = max(
                    fallback_items, key=lambda x: x.get("updated_at", "")
                ).get("week_number", "")
                for s in fallback_items:
                    s["is_current_week"] = s.get("week_number") == latest_week
                    s["is_future"] = False
                all_sessions = fallback_items

        if not all_sessions:
            return ""

        current_week = [s for s in all_sessions if s.get("is_current_week")]
        future_sessions = sorted(
            [s for s in all_sessions if s.get("is_future") and not s.get("is_current_week")],
            key=lambda s: s.get("week_date", 0),
        )

        parts: list[str] = []
        if current_week:
            parts.append(
                "Plan Campus Coach cette semaine:\n" + format_campus_sessions(current_week)
            )

        # Group all future weeks
        if future_sessions:
            future_by_week: dict[str, list] = {}
            for s in future_sessions:
                week_iso = s.get("week_date_iso", "")
                future_by_week.setdefault(week_iso, []).append(s)
            for week_iso in sorted(future_by_week.keys()):
                parts.append(
                    f"Plan Campus Coach {week_iso}:\n"
                    + format_campus_sessions(future_by_week[week_iso])
                )

        # Add athlete context (goal, assiduity)
        ctx_resp = sessions_table.query(
            KeyConditionExpression="session_date = :sd",
            ExpressionAttributeValues={":sd": "athlete-context"},
        )
        ctx_items = ctx_resp.get("Items", [])
        if ctx_items:
            ctx = ctx_items[0]
            goal = ctx.get("goal", {})
            if goal:
                parts.append(
                    f"Objectif Campus: {goal.get('type','')} | "
                    f"{goal.get('trainings_done','')}/{goal.get('trainings_total','')} séances | "
                    f"Assiduité: {ctx.get('assiduity','')}"
                )

        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"Failed to fetch Campus weekly plan: {e}")
        return ""


def format_campus_sessions(sessions: list) -> str:
    """Format Campus Coach sessions into a compact text block for the prompt."""
    lines: list[str] = []
    for s in sessions:
        try:
            title = (s.get("title") or "Séance").strip()[:80]
            status = (s.get("status") or "").strip() or "à venir"
            dist = s.get("expected_distance_km")
            dur = s.get("expected_duration_min")

            target_parts: list[str] = []
            if dist:
                try:
                    target_parts.append(f"{float(dist):.1f}km")
                except (ValueError, TypeError):
                    pass
            if dur:
                try:
                    target_parts.append(f"{float(dur):.0f}min")
                except (ValueError, TypeError):
                    pass
            target_str = " / ".join(target_parts) if target_parts else "objectif libre"

            header = f"- {title} ({target_str}, statut: {status})"

            intervals = s.get("intervals") or []
            interval_summary = ""
            if isinstance(intervals, list) and intervals:
                pieces: list[str] = []
                for iv in intervals[:6]:
                    if isinstance(iv, str):
                        pieces.append(iv[:50])
                    elif isinstance(iv, dict):
                        label = iv.get("label") or iv.get("type") or "bloc"
                        iv_parts = [str(label)[:30]]
                        if iv.get("repeats"):
                            iv_parts.append(f"x{iv['repeats']}")
                        if iv.get("distance"):
                            iv_parts.append(str(iv["distance"])[:20])
                        if iv.get("pace"):
                            iv_parts.append(str(iv["pace"])[:20])
                        pieces.append(" ".join(iv_parts))
                if pieces:
                    interval_summary = "  Intervalles: " + " ; ".join(pieces)

            lines.append(header)
            if interval_summary:
                lines.append(interval_summary)
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Skipping Campus session in context: {e}")
            continue
    return "\n".join(lines)


def _activity_date(a: dict) -> str:
    """Best-effort activity date (YYYY-MM-DD) for week bucketing."""
    return (a.get("start_date") or a.get("start_date_local") or a.get("created_at", ""))[:10]


def format_weekly_breakdown(activities: list) -> str:
    """Group activities into ISO weeks relative to now and summarize each week.

    Produces lines like:
        - Cette semaine (15-21 juin): 1 course (10.9km), 1 muscu
        - Semaine derniere (8-14 juin): 3 courses (30.5km), 2 muscu
    so the coach can answer week-scoped questions with exact figures instead of
    extrapolating from the 4-week aggregate.
    """
    now = datetime.now(timezone.utc)
    # Monday of the current ISO week.
    current_monday = (now - timedelta(days=now.weekday())).date()

    buckets: dict[int, dict] = {}
    for a in activities:
        date_str = _activity_date(a)
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        # Number of weeks back from the current week (0 = this week).
        week_monday = d - timedelta(days=d.weekday())
        weeks_back = (current_monday - week_monday).days // 7
        if weeks_back < 0 or weeks_back > 4:
            continue
        b = buckets.setdefault(
            weeks_back, {"runs": 0, "run_km": 0.0, "strength": 0, "other": 0}
        )
        atype = a.get("activity_type", "")
        dist_km = float(a.get("distance", 0) or 0) / 1000
        if atype == "Run":
            b["runs"] += 1
            b["run_km"] += dist_km
        elif atype == "WeightTraining":
            b["strength"] += 1
        else:
            b["other"] += 1

    labels = {
        0: "Cette semaine",
        1: "Semaine derniere",
        2: "Il y a 2 semaines",
        3: "Il y a 3 semaines",
        4: "Il y a 4 semaines",
    }
    lines: list[str] = []
    for weeks_back in sorted(buckets.keys()):
        b = buckets[weeks_back]
        monday = current_monday - timedelta(weeks=weeks_back)
        sunday = monday + timedelta(days=6)
        date_range = f"{monday.strftime('%d/%m')}-{sunday.strftime('%d/%m')}"
        parts = []
        if b["runs"]:
            parts.append(f"{b['runs']} course{'s' if b['runs'] > 1 else ''} ({b['run_km']:.1f}km)")
        if b["strength"]:
            parts.append(f"{b['strength']} muscu")
        if b["other"]:
            parts.append(f"{b['other']} autre{'s' if b['other'] > 1 else ''}")
        summary = ", ".join(parts) if parts else "aucune activité"
        lines.append(f"- {labels[weeks_back]} ({date_range}): {summary}")
    return "\n".join(lines)


def format_recent_activities(activities: list) -> str:
    """Format a list of activities into a compact textual block for the coach prompt.

    Each line: date | type | title | distance | duration | pace | HR | modules | feedback summary.
    Truncated to keep the prompt within token budget (~150 chars per session max).
    """
    lines: list[str] = []
    for a in activities:
        try:
            date = (
                a.get("start_date") or a.get("start_date_local") or a.get("created_at", "")
            )[:10]
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
            hr_parts: list[str] = []
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


def retrieve_memory_observations(user_id: str) -> str:
    """Retrieve past coaching observations from AgentCore Memory."""
    if not MEMORY_ID:
        return ""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespace=user_id,
            searchCriteria={
                "semanticSearch": {
                    "query": "coaching observations athlete patterns progression"
                }
            },
            maxResults=3,
        )
        records = response.get("memoryRecords", [])
        if records:
            texts = [r.get("content", {}).get("text", "") for r in records if r.get("content")]
            return " | ".join(t[:150] for t in texts if t)
    except Exception as e:
        logger.warning(f"Failed to retrieve memory: {e}")
    return ""


def write_chat_to_memory(user_id: str, question: str, answer: str) -> None:
    """Write chat exchange to memory for long-term learning."""
    if not MEMORY_ID:
        return
    # Only write substantial exchanges (not greetings or short questions)
    if len(question) < 20 or len(answer) < 100:
        return
    try:
        import time

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


COACH_CONVERSATION_PROMPT = """Tu es un coach running expert, bienveillant et direct. Tu réponds aux questions de l'athlète.

Données disponibles dans le message utilisateur:
Le message commence souvent par un bloc "[Contexte: ...]" qui contient le profil de l'athlète, ses records, son volume hebdomadaire et la liste détaillée de ses dernières séances (date, type, titre, distance, durée, allure, FC, modules d'entraînement détectés, description IA, feedback coach précédent).
Le contexte peut aussi contenir un bloc "Plan Campus Coach de la semaine en cours" listant les séances prévues (titre, numéro, distance/durée cible, statut, intervalles). Si l'athlète demande "qu'est-ce que j'ai de prévu", "ma prochaine séance", "le plan de la semaine" ou similaire, tu DOIS citer ce bloc explicitement (titre de la séance, distance/durée cible, intervalles si pertinents, statut).
Tu DOIS exploiter ces données pour répondre. Si la question porte sur les séances récentes, cite les séances explicitement (date, type, allure, FC, etc.).
NE DIS JAMAIS "je n'ai pas accès" ou "je ne vois qu'un résumé global": le contexte fourni contient le détail des séances. Si une info précise manque dans le contexte, dis simplement quelle info manque (ex: "le contexte ne contient pas la cadence de cette séance").

Règles:
- Tutoiement
- Réponses concises (3-5 phrases max sauf si question complexe)
- Factuel, cite des chiffres et dates quand pertinent
- Si tu ne sais pas et que l'info n'est pas dans le contexte, dis-le précisément
- Texte brut uniquement: PAS de **bold**, PAS de *italic*, PAS de listes à puces, PAS de markdown
- Utilise des tirets simples ou des retours à la ligne pour structurer si besoin"""
