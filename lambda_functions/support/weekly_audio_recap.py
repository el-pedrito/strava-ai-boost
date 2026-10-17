"""
Weekly Audio Recap Generator

Generates a 2-3 minute audio recap of the past week's training.
Triggered by:
- EventBridge schedule (Sunday 20:00 UTC)
- On-demand via API (POST /coach/recaps/generate)

Flow: DynamoDB query (7 days) → Bedrock script → Polly TTS → S3 → DynamoDB metadata
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import boto3
from aws_lambda_powertools.metrics import single_metric
from botocore.exceptions import ClientError

from shared.llm_models import no_thinking
from shared.pace_zones import effective_pace_zones

from shared.logger import get_logger, MetricUnit, METRICS_NAMESPACE

logger = get_logger("weekly_audio_recap")

# Business metric "an artefact was produced" (reliability plan, lot 1).
#
# Failures used to answer {"statusCode": 500}, which no alarm reads. Now every run that
# reaches a decision records one WeeklyRecapProduced datapoint, and a failure RAISES so
# Lambda Errors counts it (and the async invocation retries; the recap is idempotent):
#   ok        -- MP3 + metadata stored
#   degraded  -- stored, but a best-effort context read failed (memory, Campus goal)
#   empty     -- no activity in the window: nothing to recap (not raised, keeps the
#                "recap missing" alarm quiet on a rest week)
#   failed    -- script, audio or storage failed (raised)
# An idempotent skip (recap already stored for that week) emits nothing: the run
# that stored it already emitted ok.
RECAP_METRIC_NAME = "WeeklyRecapProduced"

# Best-effort reads that failed during the CURRENT invocation, reset at handler entry.
_DEGRADATIONS: List[str] = []


class GenerationFailed(RuntimeError):
    """The recap could not be produced."""


def _mark_degraded(reason: str) -> None:
    """Record that a best-effort read failed; the recap is still produced."""
    _DEGRADATIONS.append(reason)


def _record_outcome(outcome: str) -> None:
    """Emit WeeklyRecapProduced{outcome} as its own EMF blob (dimensions: outcome)."""
    try:
        with single_metric(
            name=RECAP_METRIC_NAME, unit=MetricUnit.Count, value=1,
            namespace=METRICS_NAMESPACE,
        ) as metric:
            metric.add_dimension(name="outcome", value=outcome)
    except Exception as exc:  # noqa: BLE001 - a metric must never mask the real error
        logger.warning(f"Could not emit {RECAP_METRIC_NAME}{{outcome={outcome}}}: {exc}")

# AWS clients
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
polly = boto3.client("polly")
s3 = boto3.client("s3")

# Environment
ACTIVITIES_TABLE = os.environ["ACTIVITIES_TABLE"]
USER_CONFIG_TABLE = os.environ["USER_CONFIG_TABLE"]
AUDIO_BUCKET = os.environ["AUDIO_DEBRIEF_BUCKET"]
RECAP_TABLE = os.environ.get("RECAP_TABLE", ACTIVITIES_TABLE)
from shared.llm_models import resolve_sonnet_model_id

MODEL_ID = resolve_sonnet_model_id()
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID") or os.environ.get("MEMORY_ID")
REGION = os.environ.get("AWS_REGION", "us-east-1")
POLLY_VOICE_FR = os.environ.get("POLLY_VOICE_FR", "Lea")
POLLY_VOICE_EN = os.environ.get("POLLY_VOICE_EN", "Joanna")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler. Supports EventBridge schedule and API invocation.

    Raises on failure, after emitting outcome=failed.
    """
    _DEGRADATIONS.clear()
    try:
        result, outcome = _generate_recap(event)
    except Exception as exc:
        logger.exception(f"Weekly audio recap not produced: {exc}")
        _record_outcome("failed")
        raise
    if outcome:
        _record_outcome(outcome)
    return result


def _generate_recap(event: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Produce and store the recap. Returns (response payload, metric outcome or None)."""
    user_id = event.get("user_id") or DEFAULT_USER_ID
    if not user_id:
        raise GenerationFailed("No user_id")

    # Determine which week to generate
    target_date = event.get("target_date")  # ISO date string, optional
    if target_date:
        end = datetime.fromisoformat(target_date).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)

    # On-demand recaps use date range label; scheduled (EventBridge) use ISO week
    is_scheduled = event.get("source", "").startswith("aws.events") or event.get("detail-type") == "Scheduled Event"
    iso_week = end.strftime("%G-W%V")

    if is_scheduled:
        # Scheduled: cover Monday to Sunday of current ISO week
        monday = end - timedelta(days=end.weekday())
        start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        week_label = iso_week
    else:
        # On-demand: cover last 7 days
        start = end - timedelta(days=7)
        week_label = f"{start.strftime('%d_%m')}-{end.strftime('%d_%m')}"

    # Check idempotency
    recap_table = dynamodb.Table(RECAP_TABLE)
    existing = _get_existing_recap(recap_table, user_id, week_label)
    if existing and not event.get("force"):
        logger.info(f"Recap already exists for {week_label}, skipping")
        # Counted (outcome=exists) so the weekly "missing" alarm sees that this
        # week is covered; emitting nothing let it fire on a week already done.
        return {"statusCode": 200, "recap": existing}, "exists"

    # Fetch week activities
    activities = _fetch_week_activities(user_id, start)
    if not activities:
        logger.info(f"No activities for {week_label}, skipping")
        return {"statusCode": 200, "message": "No activities this week"}, "empty"

    # Get user config for language and profile
    user_config = _get_user_config(user_id)
    language = user_config.get("user_preferences", {}).get("language", "fr")
    athlete_profile = user_config.get("user_preferences", {}).get("athlete_profile", "")

    # Generate script via Bedrock
    script = _generate_script(activities, athlete_profile, language, week_label, user_config=user_config, user_id=user_id)
    if not script:
        raise GenerationFailed("Script generation failed")

    # Synthesize audio via Polly
    voice = POLLY_VOICE_FR if language == "fr" else POLLY_VOICE_EN
    audio_bytes, duration_sec = _synthesize_audio(script, voice)
    if not audio_bytes:
        raise GenerationFailed("Audio synthesis failed")

    # Store in S3
    s3_key = f"recaps/{user_id}/{week_label}.mp3"
    _upload_to_s3(audio_bytes, s3_key, user_id, week_label)

    # Store metadata in DynamoDB
    recap_item = {
        "user_id": user_id,
        "week": week_label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "s3_key": s3_key,
        "duration_seconds": duration_sec,
        "script_text": script,
        "language": language,
        "voice": voice,
        "activity_count": len(activities),
    }
    recap_table.put_item(Item=recap_item)

    logger.info(f"Recap generated: {week_label}, {duration_sec}s, {len(activities)} activities")
    if _DEGRADATIONS:
        logger.warning("Recap produced with degraded context", extra={"degraded": list(_DEGRADATIONS)})
        return {"statusCode": 200, "recap": recap_item}, "degraded"
    return {"statusCode": 200, "recap": recap_item}, "ok"


def _get_existing_recap(table, user_id: str, week: str) -> Optional[Dict]:
    try:
        resp = table.get_item(Key={"user_id": user_id, "week": week})
        return resp.get("Item")
    except ClientError:
        return None


def _fetch_week_activities(user_id: str, since: datetime) -> list:
    table = dynamodb.Table(ACTIVITIES_TABLE)
    resp = table.query(
        IndexName="UserActivitiesIndex",
        KeyConditionExpression="user_id = :uid AND created_at >= :since",
        ExpressionAttributeValues={":uid": user_id, ":since": since.isoformat()},
        ScanIndexForward=True,
    )
    items = resp.get("Items", [])
    # Parse activity data
    activities = []
    for item in items:
        raw = item.get("activity_data_json")
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                data["coach_feedback"] = item.get("coach_feedback", {})
                data["enhanced_title"] = item.get("enhanced_title", "")
                activities.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
    return activities


def _get_user_config(user_id: str) -> Dict:
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        resp = table.get_item(Key={"user_id": user_id})
        return resp.get("Item", {})
    except ClientError:
        return {}


def _get_campus_goal_context() -> str:
    """Fetch Campus Coach goal context for the recap."""
    try:
        table = dynamodb.Table(os.environ.get("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"))
        resp = table.scan(
            FilterExpression="session_date = :sd",
            ExpressionAttributeValues={":sd": "athlete-context"},
        )
        items = resp.get("Items", [])
        if not items:
            return ""
        ctx = items[0]
        goal = ctx.get("goal", {})
        if not goal:
            return ""
        return (
            f"Objectif Campus Coach : {goal.get('type', '')} | "
            f"{goal.get('trainings_done', '?')}/{goal.get('trainings_total', '?')} séances | "
            f"Assiduité : {ctx.get('assiduity', '?')}"
        )
    except Exception as e:  # noqa: BLE001 - best-effort context
        logger.warning(f"Failed to read Campus goal context for recap: {e}")
        _mark_degraded("campus_goal")
        return ""


def _retrieve_memory_observations(user_id: str) -> str:
    """Retrieve recent coaching observations from AgentCore Memory.

    Fixed 2026-07-17 (docs/design/memory-improvements.md): the previous
    implementation used a raw user_id namespace and the pre-GA API shape
    (semanticSearch/memoryRecords) — it silently returned nothing. Long-term
    records live under /strategies/{strategyId}/actors/{actorId}/; the
    "/strategies/" prefix + the actor filter in searchQuery is account-safe
    (no hardcoded strategy id).
    """
    if not MEMORY_ID or not user_id:
        return ""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespace="/strategies/",
            searchCriteria={
                "searchQuery": "weekly training progression trends fatigue recovery observations",
                "topK": 5,
            },
        )
        records = response.get("memoryRecordSummaries", [])
        # Prefix match spans all strategies/actors: keep only this user's records.
        texts = [
            r.get("content", {}).get("text", "")
            for r in records
            if r.get("content", {}).get("text")
            and any(f"/actors/{user_id}/" in ns for ns in (r.get("namespaces") or []))
        ]
        if texts:
            return " | ".join(t[:200] for t in texts)
    except Exception as e:
        logger.warning(f"Failed to retrieve memory for recap: {e}")
        _mark_degraded("memory_read")
    return ""


def _athlete_rpe_of(activity: Dict[str, Any]) -> Optional[int]:
    """The athlete's RPE for a session (int 1-10, from activity_data_json), or None.

    A bool, an out-of-range or a non-integral value counts as absent, so a session
    without input renders exactly as before.
    """
    value = activity.get("athlete_rpe")
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        if number != int(number):  # non-integral
            return None
    except (TypeError, ValueError, OverflowError):  # not a number, nan, inf
        return None
    rpe = int(number)
    return rpe if 1 <= rpe <= 10 else None


def _generate_script(activities: list, athlete_profile: str, language: str, week: str, user_config: Dict = None, user_id: str = "") -> Optional[str]:
    """Generate podcast-style script via Bedrock."""
    # Build activity summaries
    summaries = []
    total_km = 0
    total_time_min = 0
    run_count = 0
    other_count = 0

    for a in activities:
        sport = a.get("sport_type", a.get("type", "Unknown"))
        dist_km = round(float(a.get("distance", 0)) / 1000, 1)
        time_min = round(float(a.get("moving_time", 0)) / 60)
        title = a.get("enhanced_title") or a.get("name", "")
        hr = a.get("average_heartrate")
        coach = a.get("coach_feedback", {})
        strava_block = coach.get("strava_block", "") if isinstance(coach, dict) else ""

        total_km += dist_km
        total_time_min += time_min
        if sport == "Run":
            run_count += 1
        else:
            other_count += 1

        rpe = _athlete_rpe_of(a)
        summaries.append(f"- {title} ({sport}, {dist_km}km, {time_min}min" +
                        (f", FC moy {hr}bpm" if hr else "") +
                        (f", RPE de l'athlète {rpe}/10" if rpe is not None else "") + ")" +
                        (f" Coach: {strava_block[:100]}" if strava_block else ""))

    activities_text = "\n".join(summaries)

    system_prompt = f"""Tu es un coach sportif bienveillant qui fait le récap audio hebdomadaire de l'athlète.
Ton style : podcast perso, tu parles directement à l'athlète comme un pote attentionné.
Langue : {"français" if language == "fr" else "English"}.

Règles :
- 200-300 mots (environ 2 minutes de parole)
- Commence par "Salut ! Voici ton récap de la semaine {week}."
- Mentionne les faits marquants (volume, intensité, progression, repos)
- Termine par une projection sur la semaine à venir (encouragement ou conseil)
- Ton naturel, pas de jargon excessif, pas de listes à puces
- Pas de em dash (—), pas de formules AI-generated
- Parle des sensations, pas juste des chiffres
- Si tu as des observations passées (mémoire), fais le lien avec les semaines précédentes
- Si les records personnels montrent un événement récent (< 2 mois), contextualise la semaine par rapport à cet événement (ex: reconstruction post-marathon, prépa avant course)"""

    # Build rich user context from config
    prefs = (user_config or {}).get("user_preferences", {})
    # Campus zones first, legacy manual zones as fallback (shared.pace_zones).
    pace_zones, _zones_source = effective_pace_zones(user_config)
    personal_records = prefs.get("personal_records", [])
    max_hr = prefs.get("max_hr", "")

    context_parts = [f"Profil athlète : {athlete_profile or 'Non renseigné'}"]
    if max_hr:
        context_parts.append(f"FC max : {max_hr} bpm")
    if pace_zones:
        # A single-value zone (min == max, Campus "Tempo 5:15") reads as one pace.
        zones_str = ", ".join(
            f"{k}: {v.get('min','')}/km" if v.get('min') == v.get('max')
            else f"{k}: {v.get('min','')}-{v.get('max','')}/km"
            for k, v in pace_zones.items() if isinstance(v, dict))
        if zones_str:
            context_parts.append(f"Zones d'allure : {zones_str}")
    if personal_records:
        prs_str = ", ".join(f"{pr.get('distance','')}: {pr.get('time','')}" for pr in personal_records[:5] if isinstance(pr, dict))
        if prs_str:
            context_parts.append(f"Records personnels : {prs_str}")

    # Retrieve memory observations for continuity
    memory_context = _retrieve_memory_observations(user_id)
    if memory_context:
        context_parts.append(f"Observations coach récentes (mémoire) : {memory_context}")

    # Campus Coach goal context
    campus_context = _get_campus_goal_context()
    if campus_context:
        context_parts.append(campus_context)

    user_msg = f"""{chr(10).join(context_parts)}

Semaine {week} : {run_count} courses + {other_count} autres = {len(activities)} séances
Volume total : {round(total_km, 1)}km en {total_time_min}min

Détail des séances :
{activities_text}"""

    try:
        resp = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 800,
                # No temperature: Claude 5.5 models reject it ("deprecated for this model").
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_msg}],
                # Claude 5.5 thinks by default: content[0] became a thinking block
                # and `["text"]` raised KeyError (2026-10-11 recap lost).
                **no_thinking(MODEL_ID),
            }),
        )
        result = json.loads(resp["body"].read())
        text = "".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
        return text.strip() or None
    except Exception as e:
        logger.error(f"Bedrock script generation failed: {e}")
        return None


def _prepare_text_for_tts(text: str) -> str:
    """Preprocess text for TTS to avoid misreadings (e.g. 4:27 read as 4h27)."""
    import re
    # Convert pace notation: "4:27/km" → "4 minutes 27 par kilomètre"
    text = re.sub(r'(\d+):(\d{2})/km', r'\1 minutes \2 par kilomètre', text)
    # Convert pace without /km: "4:27" in running context → "4 minutes 27"
    text = re.sub(r'(\d+):(\d{2})(?!\d)', r'\1 minutes \2', text)
    # Convert "km/h" to spoken form
    text = re.sub(r'(\d+(?:\.\d+)?)\s*km/h', r'\1 kilomètres heure', text)
    # Convert "bpm" to spoken form
    text = re.sub(r'(\d+)\s*bpm', r'\1 battements par minute', text)
    return text


def _synthesize_audio(script: str, voice: str) -> tuple:
    """Synthesize speech with Polly. Returns (audio_bytes, duration_sec)."""
    try:
        # Preprocess text for TTS: convert pace notation (4:27/km → 4 minutes 27 par km)
        script = _prepare_text_for_tts(script)

        resp = polly.synthesize_speech(
            Text=script,
            OutputFormat="mp3",
            VoiceId=voice,
            Engine=os.environ.get("POLLY_ENGINE", "generative"),
            SampleRate="22050",
            TextType="text",
        )
        audio_bytes = resp["AudioStream"].read()
        # Compute duration from MP3 byte length (48kbps at 22050Hz)
        duration_sec = round(len(audio_bytes) * 8 / 48000)
        return audio_bytes, duration_sec
    except Exception as e:
        logger.error(f"Polly synthesis failed: {e}")
        return None, 0


def _upload_to_s3(audio_bytes: bytes, s3_key: str, user_id: str, week: str):
    """Upload MP3 to S3 with metadata."""
    s3.put_object(
        Bucket=AUDIO_BUCKET,
        Key=s3_key,
        Body=audio_bytes,
        ContentType="audio/mpeg",
        ServerSideEncryption="AES256",
        Metadata={
            "user-id": user_id,
            "week": week,
            "generated-at": datetime.now(timezone.utc).isoformat(),
        },
    )
