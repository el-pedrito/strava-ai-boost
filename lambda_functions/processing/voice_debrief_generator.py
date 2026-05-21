"""
Voice Debrief Generator Lambda

Triggered by DynamoDB Stream on the activities table. For each MODIFY/INSERT
event whose new image has processing_status=completed and no
audio_debrief_generated_at yet, generate a 60-90s audio debrief:

  1. Load the activity item + user preferences (language).
  2. Build a compact context payload (title, distance, pace, HR, modules,
     coach feedback excerpt).
  3. Ask Bedrock Haiku 4.5 to write a 140-200 word spoken script.
  4. Synthesize MP3 with Amazon Polly (neural engine).
  5. Upload to s3://<AUDIO_DEBRIEF_BUCKET>/<user_id>/<activity_id>.mp3
     (private, BLOCK_ALL public access — accessed only via presigned URL).
  6. Update DynamoDB with audio_debrief_url (s3:// reference, NOT public),
     audio_debrief_generated_at, audio_debrief_duration_sec.

Idempotency: skip if audio_debrief_generated_at is already set on the new image.

Failure handling: per-record errors are reported via batchItemFailures so the
stream can retry only the failing item, not the whole batch.
"""

import io
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from shared.logger import get_logger, inject_correlation_id

# Load shared prompts from src/agents (mounted into the layer at runtime)
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
try:
    from agents.embedded_prompts import (  # type: ignore
        VOICE_DEBRIEF_PROMPT_EN,
        VOICE_DEBRIEF_PROMPT_FR,
    )
except ImportError:
    # Fallback: embed inline if the prompts module is not packaged in the layer
    VOICE_DEBRIEF_PROMPT_FR = (
        "Tu es coach running personnel. Tu fais un debrief audio bref et "
        "chaleureux d'une seance. 60-90 secondes de parole (140-200 mots). "
        "Parle directement a l'athlete au tutoiement. Mets en avant : le type "
        "de seance, une observation positive, un insight cle (allure, FC, "
        "charge), une note prospective courte. Langage parle naturel, pas de "
        "markdown, pas de listes, pas d'emojis. Retourne UNIQUEMENT le texte."
    )
    VOICE_DEBRIEF_PROMPT_EN = (
        "You are a personal running coach giving a brief, warm, audio debrief "
        "of a session. 60-90 seconds of speech (140-200 words). Speak directly "
        "to the athlete. Highlight: type of session, one positive observation, "
        "one key insight (pace, HR, load), one short forward-looking note. "
        "Natural spoken language, no markdown, no lists, no emojis. Output "
        "ONLY the script text."
    )


logger = get_logger("voice-debrief-generator")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
REGION = os.environ.get("AWS_REGION", "us-east-1")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
AUDIO_BUCKET = os.environ.get("AUDIO_DEBRIEF_BUCKET", "")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)
POLLY_VOICE_FR = os.environ.get("POLLY_VOICE_FR", "Lea")
POLLY_VOICE_EN = os.environ.get("POLLY_VOICE_EN", "Joanna")
POLLY_ENGINE = os.environ.get("POLLY_ENGINE", "neural")

# Approximate spoken-words-per-minute for duration estimation
WORDS_PER_MINUTE = 155

# AWS clients (module-level for warm-start reuse)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


# ----------------------------------------------------------------------
# Handler
# ----------------------------------------------------------------------
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """DynamoDB Stream handler. Returns batchItemFailures for partial retries."""
    inject_correlation_id(logger, event)

    if not AUDIO_BUCKET:
        logger.error("AUDIO_DEBRIEF_BUCKET env var not configured")
        return {"batchItemFailures": []}

    failures: List[Dict[str, str]] = []
    records = event.get("Records", [])
    logger.info(f"Voice debrief generator received {len(records)} stream records")

    for record in records:
        sequence_number = record.get("dynamodb", {}).get("SequenceNumber", "")
        try:
            _process_record(record)
        except Exception as exc:  # noqa: BLE001 — we want to mark the record as failed
            logger.error(f"Record {sequence_number} failed: {exc}", exc_info=True)
            if sequence_number:
                failures.append({"itemIdentifier": sequence_number})

    return {"batchItemFailures": failures}


def _process_record(record: Dict[str, Any]) -> None:
    event_name = record.get("eventName", "")
    if event_name not in ("INSERT", "MODIFY"):
        return

    new_image = record.get("dynamodb", {}).get("NewImage")
    if not new_image:
        return

    item = _deserialize_image(new_image)
    activity_id = item.get("activity_id")
    user_id = item.get("user_id")

    if not activity_id or not user_id:
        logger.debug("Stream record missing activity_id/user_id, skipping")
        return

    # Idempotency: skip if already generated
    if item.get("audio_debrief_generated_at"):
        return

    # Only after enrichment is complete
    processing_status = item.get("processing_status")
    if processing_status != "completed":
        return

    # Skip if neither coach feedback nor enhanced description is present
    if not item.get("coach_feedback") and not item.get("enhanced_description"):
        logger.info(
            f"Activity {activity_id}: no coach_feedback / enhanced_description yet, skipping"
        )
        return

    logger.info(f"Generating voice debrief for activity {activity_id} (user {user_id})")

    language = _resolve_language(user_id)
    activity_data = _load_activity_data(activity_id)

    script = _generate_script(item, activity_data, language)
    if not script:
        raise RuntimeError("Bedrock returned an empty script")

    voice_id = POLLY_VOICE_FR if language == "fr" else POLLY_VOICE_EN
    mp3_bytes = _synthesize_speech(script, voice_id)
    if not mp3_bytes:
        raise RuntimeError("Polly returned empty audio bytes")

    s3_key = f"{user_id}/{activity_id}.mp3"
    _upload_to_s3(mp3_bytes, s3_key, activity_id, user_id, language)

    duration_sec = _estimate_duration_seconds(script)

    _update_activity_record(
        activity_id=activity_id,
        s3_key=s3_key,
        duration_sec=duration_sec,
        language=language,
        voice_id=voice_id,
    )

    logger.info(
        f"Voice debrief stored s3://{AUDIO_BUCKET}/{s3_key} "
        f"({len(mp3_bytes)} bytes, ~{duration_sec}s, {language}/{voice_id})"
    )


# ----------------------------------------------------------------------
# Stream image -> python dict
# ----------------------------------------------------------------------
def _deserialize_image(image: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a DynamoDB stream image (with type tags) to a plain dict."""
    return {key: _deserialize_value(val) for key, val in image.items()}


def _deserialize_value(value: Dict[str, Any]) -> Any:
    if "S" in value:
        return value["S"]
    if "N" in value:
        try:
            num = float(value["N"])
            return int(num) if num.is_integer() else num
        except (TypeError, ValueError):
            return value["N"]
    if "BOOL" in value:
        return value["BOOL"]
    if "NULL" in value:
        return None
    if "L" in value:
        return [_deserialize_value(v) for v in value["L"]]
    if "M" in value:
        return {k: _deserialize_value(v) for k, v in value["M"].items()}
    if "SS" in value:
        return list(value["SS"])
    if "NS" in value:
        return [float(n) for n in value["NS"]]
    return None


# ----------------------------------------------------------------------
# Language + activity data
# ----------------------------------------------------------------------
def _resolve_language(user_id: str) -> str:
    """Resolve 'fr' or 'en' from user_preferences.content_language. Default fr."""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(
            Key={"user_id": user_id},
            ProjectionExpression="user_preferences",
        )
        prefs = response.get("Item", {}).get("user_preferences", {}) or {}
        raw = (prefs.get("content_language") or "french").lower()
    except ClientError as exc:
        logger.warning(f"Could not read user preferences for {user_id}: {exc}")
        return "fr"

    if raw in ("english", "en"):
        return "en"
    # French is the default; other languages fall back to French voice for V1
    return "fr"


def _load_activity_data(activity_id: str) -> Dict[str, Any]:
    """Load full activity_data_json from the activities table (best-effort)."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={"activity_id": activity_id})
        item = response.get("Item", {}) or {}
        raw = item.get("activity_data_json", "{}")
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (ClientError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not load activity_data for {activity_id}: {exc}")
        return {}


# ----------------------------------------------------------------------
# Script generation (Bedrock Haiku 4.5)
# ----------------------------------------------------------------------
def _generate_script(
    item: Dict[str, Any],
    activity_data: Dict[str, Any],
    language: str,
) -> Optional[str]:
    """Call Bedrock Haiku 4.5 via Converse API to produce the spoken script."""
    system_prompt = VOICE_DEBRIEF_PROMPT_FR if language == "fr" else VOICE_DEBRIEF_PROMPT_EN
    user_prompt = _build_user_prompt(item, activity_data, language)

    try:
        response = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"maxTokens": 600, "temperature": 0.6},
        )
    except ClientError as exc:
        logger.error(f"Bedrock converse error: {exc}")
        raise

    output = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(block.get("text", "") for block in output).strip()

    return _clean_script(text)


def _build_user_prompt(
    item: Dict[str, Any],
    activity_data: Dict[str, Any],
    language: str,
) -> str:
    """Compact context payload for the LLM."""
    title = (
        item.get("enhanced_title")
        or activity_data.get("name")
        or item.get("original_name")
        or ""
    )
    activity_type = activity_data.get("type") or item.get("activity_type") or ""

    distance_m = activity_data.get("distance") or item.get("distance") or 0
    moving_time = activity_data.get("moving_time") or item.get("moving_time") or 0
    avg_hr = activity_data.get("average_heartrate") or item.get("average_heartrate")
    max_hr = activity_data.get("max_heartrate") or item.get("max_heartrate")
    elev = activity_data.get("total_elevation_gain") or item.get("total_elevation_gain")

    distance_km = round(float(distance_m) / 1000, 2) if distance_m else 0.0
    duration_min = round(float(moving_time) / 60, 1) if moving_time else 0.0
    pace = ""
    try:
        if distance_km > 0 and moving_time:
            sec_per_km = float(moving_time) / distance_km
            m, s = int(sec_per_km // 60), int(sec_per_km % 60)
            pace = f"{m}:{s:02d}/km"
    except (TypeError, ValueError):
        pace = ""

    coach_block = ""
    cf = item.get("coach_feedback")
    if isinstance(cf, dict):
        coach_block = (cf.get("strava_block") or cf.get("detailed_analysis") or "")[:600]

    modules = item.get("modules_used") or []

    facts: Dict[str, Any] = {
        "title": title,
        "activity_type": activity_type,
        "distance_km": distance_km,
        "duration_minutes": duration_min,
        "pace": pace,
        "average_heart_rate": avg_hr,
        "max_heart_rate": max_hr,
        "elevation_gain_m": elev,
        "modules_used": modules,
        "coach_feedback_excerpt": coach_block,
    }
    facts = {k: v for k, v in facts.items() if v not in (None, "", 0, 0.0, [])}

    if language == "fr":
        header = (
            "Voici les donnees structurees de la seance. Ecris un script "
            "audio de 60 a 90 secondes (140 a 200 mots) en t'appuyant "
            "uniquement sur ces donnees."
        )
    else:
        header = (
            "Here are the structured facts of the session. Write a 60-90 "
            "second audio script (140-200 words) using only these facts."
        )

    return f"{header}\n\n{json.dumps(facts, ensure_ascii=False, indent=2, default=str)}"


def _clean_script(text: str) -> str:
    """Strip markdown, code fences, and surrounding quotes."""
    if not text:
        return ""

    text = re.sub(r"```[a-z]*\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    # Remove leading/trailing matching quotes (curly + straight)
    stripped = text.strip()
    quote_pairs = [("\"", "\""), ("'", "'"), ("“", "”"), ("«", "»")]
    for opener, closer in quote_pairs:
        if stripped.startswith(opener) and stripped.endswith(closer) and len(stripped) > 1:
            stripped = stripped[len(opener):-len(closer)].strip()
            break
    # Collapse whitespace
    return re.sub(r"\s+\n", "\n", stripped).strip()


# ----------------------------------------------------------------------
# Polly synthesis
# ----------------------------------------------------------------------
def _prepare_for_tts(text: str) -> str:
    """Preprocess text for TTS to avoid misreadings."""
    import re
    text = re.sub(r'(\d+):(\d{2})/km', r'\1 minutes \2 par kilomètre', text)
    text = re.sub(r'(\d+):(\d{2})(?!\d)', r'\1 minutes \2', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*km/h', r'\1 kilomètres heure', text)
    text = re.sub(r'(\d+)\s*bpm', r'\1 battements par minute', text)
    return text


def _synthesize_speech(script: str, voice_id: str) -> bytes:
    """Synthesize MP3 audio with Amazon Polly."""
    # Preprocess for TTS: convert pace notation (4:27/km → 4 minutes 27 par kilomètre)
    script = _prepare_for_tts(script)
    response = polly.synthesize_speech(
        Text=script,
        OutputFormat="mp3",
        VoiceId=voice_id,
        Engine=POLLY_ENGINE,
        SampleRate="22050",
        TextType="text",
    )
    audio_stream = response.get("AudioStream")
    if audio_stream is None:
        return b""

    buffer = io.BytesIO()
    chunk = audio_stream.read(4096)
    while chunk:
        buffer.write(chunk)
        chunk = audio_stream.read(4096)
    return buffer.getvalue()


def _estimate_duration_seconds(script: str) -> int:
    """Estimate spoken duration from word count (Polly does not return it)."""
    word_count = len(re.findall(r"\w+", script))
    if word_count <= 0:
        return 0
    return int(math.ceil(word_count / WORDS_PER_MINUTE * 60))


# ----------------------------------------------------------------------
# S3 + DynamoDB persistence
# ----------------------------------------------------------------------
def _upload_to_s3(
    mp3_bytes: bytes,
    s3_key: str,
    activity_id: str,
    user_id: str,
    language: str,
) -> None:
    s3.put_object(
        Bucket=AUDIO_BUCKET,
        Key=s3_key,
        Body=mp3_bytes,
        ContentType="audio/mpeg",
        ServerSideEncryption="AES256",
        Metadata={
            "activity-id": str(activity_id),
            "user-id": str(user_id),
            "language": language,
            "engine": POLLY_ENGINE,
            "generated-at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _update_activity_record(
    activity_id: str,
    s3_key: str,
    duration_sec: int,
    language: str,
    voice_id: str,
) -> None:
    table = dynamodb.Table(ACTIVITIES_TABLE)
    s3_uri = f"s3://{AUDIO_BUCKET}/{s3_key}"
    table.update_item(
        Key={"activity_id": activity_id},
        UpdateExpression=(
            "SET audio_debrief_url = :u, "
            "audio_debrief_s3_key = :k, "
            "audio_debrief_generated_at = :ts, "
            "audio_debrief_duration_sec = :d, "
            "audio_debrief_language = :l, "
            "audio_debrief_voice = :v"
        ),
        ExpressionAttributeValues={
            ":u": s3_uri,
            ":k": s3_key,
            ":ts": datetime.now(timezone.utc).isoformat(),
            ":d": duration_sec,
            ":l": language,
            ":v": voice_id,
        },
    )
