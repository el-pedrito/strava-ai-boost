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
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger

logger = get_logger("weekly_audio_recap")

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
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
POLLY_VOICE_FR = os.environ.get("POLLY_VOICE_FR", "Lea")
POLLY_VOICE_EN = os.environ.get("POLLY_VOICE_EN", "Joanna")
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler. Supports EventBridge schedule and API invocation."""
    user_id = event.get("user_id") or DEFAULT_USER_ID
    if not user_id:
        return {"statusCode": 400, "error": "No user_id"}

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
        return {"statusCode": 200, "recap": existing}

    # Fetch week activities
    activities = _fetch_week_activities(user_id, start)
    if not activities:
        logger.info(f"No activities for {week_label}, skipping")
        return {"statusCode": 200, "message": "No activities this week"}

    # Get user config for language and profile
    user_config = _get_user_config(user_id)
    language = user_config.get("user_preferences", {}).get("language", "fr")
    athlete_profile = user_config.get("user_preferences", {}).get("athlete_profile", "")

    # Generate script via Bedrock
    script = _generate_script(activities, athlete_profile, language, week_label)
    if not script:
        return {"statusCode": 500, "error": "Script generation failed"}

    # Synthesize audio via Polly
    voice = POLLY_VOICE_FR if language == "fr" else POLLY_VOICE_EN
    audio_bytes, duration_sec = _synthesize_audio(script, voice)
    if not audio_bytes:
        return {"statusCode": 500, "error": "Audio synthesis failed"}

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
    return {"statusCode": 200, "recap": recap_item}


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


def _generate_script(activities: list, athlete_profile: str, language: str, week: str) -> Optional[str]:
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

        summaries.append(f"- {title} ({sport}, {dist_km}km, {time_min}min" +
                        (f", FC moy {hr}bpm" if hr else "") + ")" +
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
- Parle des sensations, pas juste des chiffres"""

    user_msg = f"""Profil athlète : {athlete_profile or 'Non renseigné'}

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
                "temperature": 0.7,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_msg}],
            }),
        )
        result = json.loads(resp["body"].read())
        return result["content"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Bedrock script generation failed: {e}")
        return None


def _synthesize_audio(script: str, voice: str) -> tuple:
    """Synthesize speech with Polly. Returns (audio_bytes, duration_sec)."""
    try:
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
