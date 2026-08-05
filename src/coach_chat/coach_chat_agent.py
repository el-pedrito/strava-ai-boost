"""Conversational coach agent — AG-UI server for AgentCore Runtime (chantier A1+A2b).

This is the *agentic* conversational coach: instead of stuffing a frozen context
blob into the prompt (the approach used by the buffered ``/coach/ask`` Lambda and
the Starlette stream), the agent is given four Strands tools and fetches exactly
the data it needs, when it needs it. That unlocks questions the stuffed context
cannot answer (e.g. "compare mes 6 dernières séances de seuil").

Runtime contract (Amazon Bedrock AgentCore, ``--protocol AGUI``):
    * FastAPI server on port 8080
    * ``POST /invocations`` — AG-UI event stream (Server-Sent Events)
    * ``GET /ping``        — health check

Design notes:
    * ``user_id`` is taken from the JWT ``custom:strava_id`` claim (validated
      upstream by the runtime customJWT authorizer), never from the request body.
      It is injected out-of-band via a ``ContextVar`` so the four tools keep a
      PURE signature — their docstring + type hints are the whole tool spec the
      model sees, with no ``user_id`` argument the model could spoof.
    * Tools are ``async`` and offload the blocking boto3 work with
      ``asyncio.to_thread`` (which propagates the ContextVar), so the event loop
      is never blocked and the injected identity is always visible to the tool.
    * Multi-turn is handled natively by AG-UI ``RunAgentInput.messages`` via the
      ``ag-ui-strands`` wrapper.
    * AgentCore Memory writes (session ``coach-chat-{user_id}``) are preserved: the run
      writes the exchange with :func:`write_chat_to_memory` at the end.

Deployment (IAM + ``agentcore configure --protocol AGUI``) is handled separately.
This module intentionally does not deploy anything.
"""

import asyncio
import base64
import contextvars
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import boto3
import uvicorn
from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_strands import StrandsAgent
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from strands import Agent, tool
from strands.models import BedrockModel

from prompts import COACH_CHAT_SYSTEM_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Configuration (environment) ---------------------------------------------

REGION = os.environ.get("AWS_REGION", "us-east-1")
# Model ID: injected at deploy time from the central registry
# (src/config/llm_config.py via scripts/deploy_agentcore_agents.sh).
MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
# Existing Bedrock Guardrail (same resource as the content pipeline). When set,
# it is applied natively by Strands' BedrockModel — closes threat-model T4.
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get(
    "USER_CONFIG_TABLE", "strava-ai-boost-user-configuration"
)
COACHING_SESSIONS_TABLE = os.environ.get(
    "COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"
)
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID", "")
# Identity fallback when the JWT lacks the custom:strava_id claim. NOTE: this is
# LIVE in production, not just local testing — any valid pool JWT without the
# claim resolves to this identity. Acceptable single-user; the customJWT
# authorizer should additionally REQUIRE the claim (see deploy notes in
# docs/design/agentcore-agentic-improvements.md).
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")

# How far back queries look when the caller omits ``date_from``.
_DEFAULT_LOOKBACK_DAYS = 28

dynamodb = boto3.resource("dynamodb", region_name=REGION)

# Per-request athlete identity, resolved from the JWT and read by the pure tools.
_USER_ID: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


# --- Identity helpers ---------------------------------------------------------


def _extract_user_id_from_jwt(auth_header: Optional[str]) -> str:
    """Decode the ``custom:strava_id`` claim from a Bearer JWT.

    The AgentCore customJWT authorizer already validated the token (signature,
    expiry, issuer) before the request reached this container, so we only need to
    decode the payload segment — no re-verification. Returns an empty string on
    any malformed input.
    """
    if not auth_header:
        return ""
    try:
        token = auth_header.split(" ", 1)[1] if " " in auth_header else auth_header
        segments = token.split(".")
        if len(segments) < 2:
            return ""
        payload_b64 = segments[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        return str(claims.get("custom:strava_id", "") or "")
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.warning("Failed to decode JWT claim custom:strava_id: %s", e)
        return ""


def _resolve_user_id() -> str:
    """Return the current request's athlete id (JWT claim, else local fallback)."""
    return _USER_ID.get() or DEFAULT_USER_ID


# --- Serialization / formatting helpers ---------------------------------------


def _jsonable(obj: Any) -> Any:
    """Recursively convert DynamoDB values (Decimal) into JSON-safe primitives."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def _to_float(value: Any) -> float:
    """Best-effort float cast (handles Decimal/str/None)."""
    try:
        return float(value) if value not in (None, "") else 0.0
    except (ValueError, TypeError):
        return 0.0


# --- Campus Coach status resolution (local mirror of shared.campus_status) -----
#
# The coach_chat runtime is deployed via `agentcore configure --entrypoint
# src/coach_chat/coach_chat_agent.py --deployment-type direct_code_deploy` (see
# scripts/deploy_agentcore_agents.sh). direct_code_deploy bundles only the
# src/coach_chat/ directory — the flat `from prompts import ...` above confirms
# it — so this module has NO access to lambda_functions/shared/campus_status.py.
# We therefore reimplement effective_status() here with the EXACT same precedence
# order (local_status -> matched_activity_id/completed_at -> provider_status ->
# todo). The raw legacy `status` field is deliberately NOT consulted (shared
# contract B1): the sync never rewrites it, so it holds stale mixed values that
# made the coach recommend already-done sessions; its completion signal has been
# migrated into `local_status`. Keep in sync with campus_status.py.
_STATUS_DONE = "done"
_STATUS_SKIP = "skip"
_STATUS_TODO = "todo"
_DONE_VALUES = {
    "done", "fait", "faite", "complete", "completed", "complétée",
    "completée", "validée",
}
_SKIP_VALUES = {
    "skip", "skipped", "sauté", "saute", "sautée", "ignoré", "ignorée",
}
_TODO_VALUES = {"todo", "to do", "à faire", "a faire", "planned", "pending", ""}


def _normalize_status(raw: Optional[str]) -> Optional[str]:
    """Normalize a legacy or provider status to a canonical execution state."""
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in _DONE_VALUES:
        return _STATUS_DONE
    if value in _SKIP_VALUES:
        return _STATUS_SKIP
    if value in _TODO_VALUES:
        return _STATUS_TODO
    return None


def _effective_status(session: dict) -> str:
    """Resolve local, matched, and provider state in precedence order.

    The raw legacy ``status`` field is deliberately NOT consulted (shared
    contract B1) — it is stale and made the coach treat already-done sessions as
    still to do. Mirror of shared.campus_status.effective_status.
    """
    local = _normalize_status(session.get("local_status"))
    if local is not None:
        return local
    if session.get("matched_activity_id") or session.get("completed_at"):
        return _STATUS_DONE
    provider = _normalize_status(session.get("provider_status"))
    if provider is not None:
        return provider
    return _STATUS_TODO


def _normalize_range(date_from: str, date_to: str) -> tuple[str, str]:
    """Normalize an ISO date window for a ``created_at`` GSI range query.

    Bare ``YYYY-MM-DD`` dates are expanded to cover the full day; missing bounds
    default to the last ``_DEFAULT_LOOKBACK_DAYS`` days up to now.
    """
    now = datetime.now(timezone.utc)
    start = date_from or (now - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).date().isoformat()
    end = date_to or now.date().isoformat()
    if len(start) == 10:
        start = f"{start}T00:00:00"
    if len(end) == 10:
        end = f"{end}T23:59:59.999999"
    return start, end


def _parse_activity_item(item: dict) -> dict:
    """Merge a DynamoDB activity item's top-level fields with its JSON blob."""
    raw = item.get("activity_data_json")
    data: dict = {}
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError):
            data = {}
    return data


# --- ISO week labelling (local mirror of shared.iso_week) ---------------------
#
# Same bundle constraint as _effective_status above: direct_code_deploy bundles
# only src/coach_chat/, so lambda_functions/shared/iso_week.py is unreachable.
# We reimplement iso_week_label() here with the EXACT same contract — a week
# identity is always the ISO string 'YYYY-Www' (e.g. '2026-W32'), never a bare
# integer, and an unparseable/empty input yields '' (a distinct, testable
# "unknown week" case). A bare week number cannot be compared against the
# week_date_iso values the Campus sync writes, and a flat date-sorted list with
# no week identity is exactly what let the model sum a rolling 7-day window and
# call it "cette semaine" (35km announced for a real 6.4km ISO week, with a
# bogus +32% ramp alert). Keep in sync with shared/iso_week.py; locked by
# test_coach_chat_tools.test_matches_shared_iso_week_label.


def iso_week_label(start_date: Optional[str]) -> str:
    """Return an ISO week label 'YYYY-Www' from an ISO datetime/date string.

    Mirror of shared.iso_week.iso_week_label. Empty/unparseable input -> ''.
    """
    if not start_date:
        return ""
    try:
        parsed = datetime.fromisoformat(str(start_date).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return ""
    iso = parsed.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _monday_of_iso_week(week_label: str) -> Optional[date]:
    """Monday of an ISO week label 'YYYY-Www'. None when unparseable.

    Mirror of coach_generator._monday_of_iso_week (same bundle constraint).
    """
    if not week_label or "-W" not in week_label:
        return None
    year_part, week_part = week_label.split("-W", 1)
    try:
        return date.fromisocalendar(int(year_part), int(week_part), 1)
    except (ValueError, TypeError):
        return None


def _compact_activity(item: dict) -> dict:
    """Produce a compact, coach-relevant view of one activity."""
    data = _parse_activity_item(item)
    atype = data.get("type") or item.get("activity_type") or "?"
    distance_m = _to_float(data.get("distance") or item.get("distance"))
    moving_s = _to_float(data.get("moving_time") or item.get("moving_time"))
    date = (
        data.get("start_date_local")
        or data.get("start_date")
        or item.get("created_at", "")
    )[:10]

    pace = ""
    if atype == "Run" and distance_m > 0 and moving_s > 0:
        pace_s = moving_s / (distance_m / 1000)
        pace = f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"

    record = {
        "activity_id": item.get("activity_id"),
        "date": date,
        "iso_week": iso_week_label(date),
        "type": atype,
        "name": data.get("name") or item.get("enhanced_title") or "",
        "distance_km": round(distance_m / 1000, 2) if distance_m else 0,
        "duration_min": round(moving_s / 60) if moving_s else 0,
        "pace": pace,
        "avg_hr": data.get("average_heartrate") or item.get("average_heartrate"),
        "max_hr": data.get("max_heartrate") or item.get("max_heartrate"),
    }
    # Two narrative fields, kept distinct on purpose:
    #  - description: the athlete's OWN original note (raw Strava input) — the most
    #    authentic subjective signal (how the session felt, intervals actually done).
    #  - enhanced_description: the AI-published text. Useful for continuity but is
    #    generated (avoid the coach reasoning solely on its own prior output).
    # Both truncated to keep the tool payload bounded across many activities.
    original = (
        item.get("original_description")
        or data.get("description")
        or ""
    )
    enhanced = item.get("enhanced_description") or data.get("enhanced_description") or ""
    if isinstance(original, str) and original.strip():
        record["description"] = original.strip()[:500]
    if isinstance(enhanced, str) and enhanced.strip():
        record["enhanced_description"] = enhanced.strip()[:500]
    return _jsonable(record)


# --- Data access (blocking, run via asyncio.to_thread) ------------------------


def _query_all(table, **kwargs) -> list:
    """Run a DynamoDB query following LastEvaluatedKey until exhausted.

    Prevents silent truncation to the first 1 MB page when the model asks for a
    long date range (e.g. comparing threshold sessions over several months).
    """
    items: list = []
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def _scan_all(table, **kwargs) -> list:
    """Run a DynamoDB scan following LastEvaluatedKey until exhausted."""
    items: list = []
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def _query_activities_impl(
    user_id: str, activity_type: str, date_from: str, date_to: str
) -> list:
    """Query the UserActivitiesIndex GSI and return compact activities."""
    if not user_id:
        return []
    start, end = _normalize_range(date_from, date_to)
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        items = _query_all(
            table,
            IndexName="UserActivitiesIndex",
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("created_at").between(start, end),
        )
    except Exception as e:
        logger.warning("query_activities failed: %s", e)
        return []

    wanted = (activity_type or "").strip().lower()
    # Map common FR/EN aliases to the Strava canonical type substring: the agent
    # often passes a natural-language type ("muscu", "course") that would never
    # match Strava's English types ("WeightTraining", "Run") under substring
    # matching, silently returning nothing.
    _TYPE_ALIASES = {
        "weighttraining": ("muscu", "musculation", "renfo", "renforcement", "force", "poids", "gym", "weight"),
        "run": ("course", "cap", "running", "footing", "trail"),
        "ride": ("velo", "vélo", "cyclisme", "bike", "cycling"),
        "swim": ("natation", "nage", "swim"),
    }
    for canonical, aliases in _TYPE_ALIASES.items():
        if wanted and (wanted == canonical or wanted in aliases):
            wanted = canonical
            break
    results = []
    for item in items:
        record = _compact_activity(item)
        if wanted and wanted not in str(record.get("type", "")).lower():
            continue
        results.append(record)
    results.sort(key=lambda r: r.get("date", ""), reverse=True)
    return results


def _get_campus_plan_impl(week_iso: str) -> dict:
    """Return Campus Coach sessions for a given ISO week + athlete context.

    Note: the coaching_sessions table has no user partition — the Campus Coach
    plan is global per deployment (single-athlete design). A paginated scan is
    used deliberately here (small table, ~a dozen sessions; consistent with
    campus_coach_sync.py). The "queries, no scans" rule in AGENTS.md targets
    user-scoped tables (activities via GSI), not this global config table.

    Kept as a Scan for an additional, harder reason: a labelled week
    (``session_date = week-YYYY-Www``) and the ``athlete-context`` partition are
    both single-partition reads that a Query would serve more precisely and
    cheaply. This runtime's IAM role, however, is granted only ``dynamodb:Scan``
    on this table (policy CoachChatToolsDataAccess in
    scripts/deploy_agentcore_agents.sh); a Query would fail with AccessDenied in
    production. Converting this read therefore requires first widening that policy
    to include ``dynamodb:Query``. Until then the Scan stays. See the report.
    """
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        items = _scan_all(table)
    except Exception as e:
        logger.warning("get_campus_plan failed: %s", e)
        return {"week_iso": week_iso, "sessions": [], "athlete_context": {}}

    sessions = [s for s in items if s.get("session_date") != "athlete-context"]
    context_rows = [s for s in items if s.get("session_date") == "athlete-context"]

    target = (week_iso or "").strip()
    if target:
        selected = [s for s in sessions if str(s.get("week_date_iso", "")) == target]
    else:
        selected = [s for s in sessions if s.get("is_current_week")]

    formatted = [
        {
            "title": s.get("title", ""),
            "session_number": s.get("session_number", ""),
            "week_date_iso": s.get("week_date_iso", ""),
            # Canonical execution status, not the raw legacy `status` field
            # (never rewritten by the sync — see B1).
            "status": _effective_status(s),
            "sport": s.get("sport", ""),
            "expected_distance_km": s.get("expected_distance_km"),
            "expected_duration_min": s.get("expected_duration_min"),
            "difficulty": s.get("difficulty"),
            "intervals": s.get("intervals", []),
            "is_current_week": bool(s.get("is_current_week")),
            "is_future": bool(s.get("is_future")),
        }
        for s in selected
    ]

    athlete_context: dict = {}
    if context_rows:
        ctx = context_rows[0]
        athlete_context = {
            "goal": ctx.get("goal", {}),
            "assiduity": ctx.get("assiduity", ""),
            "sport_profile": ctx.get("sport_profile", ""),
        }

    return _jsonable(
        {
            "week_iso": target or "current",
            "sessions": formatted,
            "athlete_context": athlete_context,
        }
    )


def _get_pace_zones_impl(user_id: str) -> dict:
    """Return pace zones, personal records and FCmax from user configuration."""
    if not user_id:
        return {}
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        item = table.get_item(Key={"user_id": user_id}).get("Item", {})
    except Exception as e:
        logger.warning("get_pace_zones failed: %s", e)
        return {}

    prefs = item.get("user_preferences", {})
    return _jsonable(
        {
            "pace_zones": prefs.get("pace_zones", {}),
            "personal_records": prefs.get("personal_records", []),
            "max_hr": prefs.get("max_hr"),
            "athlete_zones": item.get("athlete_zones", {}),
            "best_efforts_prs": item.get("best_efforts_prs", {}),
        }
    )


def _get_intervals_metrics_impl(user_id: str, date_from: str, date_to: str) -> dict:
    """Return Intervals.icu CTL/ATL/Form/HRV/decoupling stored on activities."""
    if not user_id:
        return {"series": [], "latest": {}}
    start, end = _normalize_range(date_from, date_to)
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        items = _query_all(
            table,
            IndexName="UserActivitiesIndex",
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("created_at").between(start, end),
            ProjectionExpression="activity_id, created_at, activity_data_json, intervals_icu_json",
        )
    except Exception as e:
        logger.warning("get_intervals_metrics failed: %s", e)
        return {"series": [], "latest": {}}

    series = []
    for item in items:
        raw = item.get("intervals_icu_json")
        if not raw:
            continue
        try:
            icu = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(icu, dict):
            continue
        data = _parse_activity_item(item)
        date = (data.get("start_date_local") or data.get("start_date") or item.get("created_at", ""))[:10]
        fitness = icu.get("fitness", {}) if isinstance(icu.get("fitness"), dict) else {}
        trends = icu.get("trends", {}) if isinstance(icu.get("trends"), dict) else {}
        decoupling = None
        if isinstance(trends.get("decoupling"), dict):
            decoupling = trends["decoupling"].get("current")
        entry = {
            "date": date,
            "ctl": fitness.get("ctl"),
            "atl": fitness.get("atl"),
            "form": fitness.get("form"),
            "hrv": icu.get("hrv"),
            "decoupling": decoupling if decoupling is not None else icu.get("decoupling"),
            "training_load": icu.get("training_load"),
        }
        if any(v is not None for k, v in entry.items() if k != "date"):
            series.append(entry)

    series.sort(key=lambda e: e.get("date", ""))
    latest = series[-1] if series else {}
    return _jsonable({"series": series, "latest": latest})


# --- Weekly totals (code-computed, mirror of build_week_overview counting) ----


def _get_weekly_totals_impl(user_id: str, weeks_back: int) -> list:
    """Aggregate activities into per-ISO-week totals, computed in code.

    Mirror of coach_generator.build_week_overview's counting: same source fields
    (start_date_local/start_date from the activity blob), same type buckets
    (Run -> runs+run_km, WeightTraining -> strength, else -> other), same 1-decimal
    rounding on km. This is what actually fixed the pipeline — a total computed in
    code, not a labelled list the model re-sums by hand. Locked to
    build_week_overview by
    test_coach_chat_tools.test_weekly_totals_match_build_week_overview.
    """
    if not user_id:
        return []
    try:
        weeks_back = max(1, min(int(weeks_back), 12))
    except (ValueError, TypeError):
        weeks_back = 4

    now = datetime.now(timezone.utc)
    current_label = iso_week_label(now.date().isoformat())
    cur_monday = _monday_of_iso_week(current_label)

    # Target set: the current ISO week plus the weeks_back-1 preceding weeks.
    target_labels: list[str] = []
    if cur_monday:
        for i in range(weeks_back):
            monday_i = cur_monday - timedelta(weeks=i)
            target_labels.append(iso_week_label(monday_i.isoformat()))
    target_set = set(target_labels)

    oldest_monday = cur_monday - timedelta(weeks=weeks_back - 1) if cur_monday else None
    if oldest_monday:
        since = f"{(oldest_monday - timedelta(days=3)).isoformat()}T00:00:00"
    else:
        since = f"{(now - timedelta(days=weeks_back * 7 + 7)).date().isoformat()}T00:00:00"
    end = f"{now.date().isoformat()}T23:59:59.999999"

    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        items = _query_all(
            table,
            IndexName="UserActivitiesIndex",
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("created_at").between(since, end),
            ProjectionExpression="activity_id, activity_data_json",
        )
    except Exception as e:
        logger.warning("get_weekly_totals failed: %s", e)
        return []

    buckets: dict = {}
    for item in items:
        data = _parse_activity_item(item)
        start = data.get("start_date_local") or data.get("start_date", "")
        wk = iso_week_label(start)
        if not wk or wk not in target_set:
            continue
        bucket = buckets.setdefault(
            wk, {"runs": 0, "run_km": 0.0, "strength": 0, "other": 0}
        )
        atype = data.get("type", "")
        if atype == "Run":
            bucket["runs"] += 1
            bucket["run_km"] += _to_float(data.get("distance", 0)) / 1000
        elif atype == "WeightTraining":
            bucket["strength"] += 1
        else:
            bucket["other"] += 1

    result = []
    for label in target_labels:  # most recent first (i=0 is the current week)
        bucket = buckets.get(label, {"runs": 0, "run_km": 0.0, "strength": 0, "other": 0})
        is_current = label == current_label
        monday = _monday_of_iso_week(label)
        if monday:
            sunday = monday + timedelta(days=6)
            if is_current:
                human = (
                    f"Cette semaine ({monday.strftime('%d/%m')}-{sunday.strftime('%d/%m')})"
                )
            else:
                human = f"Semaine du {monday.strftime('%d/%m')} au {sunday.strftime('%d/%m')}"
        else:
            human = label
        runs, strength, other = bucket["runs"], bucket["strength"], bucket["other"]
        result.append(
            {
                "iso_week": label,
                "label": human,
                "runs": runs,
                "run_km": round(bucket["run_km"], 1),
                "strength": strength,
                "other": other,
                "total": runs + strength + other,
                "is_current": is_current,
            }
        )
    return result


# --- Strength sessions (code-computed set/rep counts + explicit-weight tonnage) -


def _compute_strength_totals(parsed_sets: list) -> dict:
    """Code-computed set/rep counts and explicit-weight-only tonnage.

    Counts come from ``sets_detail`` (authoritative: one entry per set actually
    performed) and fall back to the flat sets/reps summary only when no detail is
    stored. Volume is Σ reps×weight_kg over the sets whose load is explicit;
    bodyweight or unknown loads are EXCLUDED and flagged (``volume_kg_incomplete``),
    never resolved to a default weight — an arbitrary default would produce a
    plausible but false figure, the exact class of error this chantier exists to
    kill. Full bodyweight/unilateral tonnage is WP5's shared.strength_volume
    (out of the chat runtime's bundle); until it lands, this reports honest
    counts and a partial, flagged tonnage.
    """
    total_sets = 0
    total_reps = 0
    volume_kg = 0.0
    incomplete = False
    per_exercise: list[dict] = []
    for entry in parsed_sets or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("exercise") or "?"
        detail = entry.get("sets_detail")
        ex_sets = ex_reps = 0
        ex_volume = 0.0
        ex_incomplete = False
        if isinstance(detail, list) and detail:
            for one in detail:
                if not isinstance(one, dict):
                    continue
                ex_sets += 1
                reps = one.get("reps")
                weight = one.get("weight_kg")
                reps_i = int(reps) if isinstance(reps, (int, float)) else 0
                ex_reps += reps_i
                if weight is not None and reps_i:
                    ex_volume += float(weight) * reps_i
                else:
                    ex_incomplete = True
        else:
            sets = entry.get("sets")
            reps = entry.get("reps")
            weight = entry.get("weight_kg")
            sets_i = int(sets) if isinstance(sets, (int, float)) else 0
            reps_i = int(reps) if isinstance(reps, (int, float)) else 0
            ex_sets = sets_i
            ex_reps = reps_i * sets_i
            if weight is not None and reps_i and sets_i:
                ex_volume = float(weight) * reps_i * sets_i
            else:
                ex_incomplete = True
        total_sets += ex_sets
        total_reps += ex_reps
        volume_kg += ex_volume
        incomplete = incomplete or ex_incomplete
        per_exercise.append(
            {
                "exercise": name,
                "sets": ex_sets,
                "reps": ex_reps,
                "volume_kg": round(ex_volume, 1) if not ex_incomplete else None,
            }
        )
    return {
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_kg": round(volume_kg, 1),
        "volume_kg_incomplete": incomplete,
        "per_exercise": per_exercise,
    }


def _get_strength_sessions_impl(user_id: str, weeks_back: int) -> list:
    """Return WeightTraining sessions with code-computed totals.

    Source: ``user_preferences.strength_history.entries`` via get_item on the
    user-configuration table — the runtime IAM already grants dynamodb:GetItem
    there (no policy change). Reps/sets/tonnage are NEVER counted from the raw
    description; they come from the stored ``parsed_sets``/``sets_detail`` and are
    computed in code (:func:`_compute_strength_totals`).
    """
    if not user_id:
        return []
    try:
        weeks_back = max(1, min(int(weeks_back), 12))
    except (ValueError, TypeError):
        weeks_back = 4
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        item = table.get_item(Key={"user_id": user_id}).get("Item", {})
    except Exception as e:
        logger.warning("get_strength_sessions failed: %s", e)
        return []

    prefs = item.get("user_preferences", {})
    entries = ((prefs.get("strength_history") or {}).get("entries")) or []
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=weeks_back * 7)
    ).date().isoformat()

    sessions: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        day = (entry.get("date") or "")[:10]
        if day and day < cutoff:
            continue
        # Prefer the figures computed at write time by the pipeline's
        # shared/strength_volume.py. That module is the single definition of
        # tonnage: it applies the bodyweight coefficients and the unilateral
        # doubling, which this runtime cannot replicate (it cannot import
        # lambda_functions/shared/, its deploy bundles only src/coach_chat/).
        # Recomputing here produced a second, lower figure for the same session.
        # The local fallback only covers rows written before the wiring landed.
        if entry.get("total_reps") is not None:
            totals = {
                "total_sets": entry.get("total_sets"),
                "total_reps": entry.get("total_reps"),
                "volume_kg": entry.get("volume_kg"),
                "body_weight_kg_used": entry.get("body_weight_kg_used"),
                "volume_kg_incomplete": bool(entry.get("volume_kg_incomplete")),
                "excluded_exercises": entry.get("excluded_exercises") or [],
                "figures_source": "pipeline",
            }
        else:
            totals = dict(_compute_strength_totals(entry.get("parsed_sets") or []))
            # Explicit-weight-only tonnage: no bodyweight coefficient applied.
            totals["volume_kg_incomplete"] = True
            totals["figures_source"] = "legacy_local_fallback"
        sessions.append(
            _jsonable(
                {
                    "activity_id": entry.get("activity_id"),
                    "date": day,
                    "iso_week": iso_week_label(day),
                    "duration_min": entry.get("duration_min"),
                    **totals,
                }
            )
        )
    sessions.sort(key=lambda s: s.get("date", ""), reverse=True)
    return sessions


# --- Strands tools (PURE: docstring + type hints are the whole spec) ----------


@tool
async def query_activities(activity_type: str, date_from: str, date_to: str) -> list:
    """Récupère les activités passées de l'athlète, filtrées par type et période.

    Utilise cet outil pour répondre à toute question portant sur des séances
    réalisées (comparaison de séances, volume, allures, FC, dates précises).

    Args:
        activity_type: Filtre par correspondance partielle insensible à la casse
            sur le type Strava, ex. "Run" (matche aussi TrailRun/VirtualRun),
            "WeightTraining", "Ride". Les alias français courants sont acceptés
            ("muscu"/"musculation" → WeightTraining, "course" → Run, "vélo" →
            Ride, "natation" → Swim). Chaîne vide pour ne pas filtrer.
        date_from: Date de début incluse au format ISO "AAAA-MM-JJ". Vide = 4
            dernières semaines. La fenêtre s'applique à la date de synchronisation
            de l'activité (une activité importée tardivement peut différer de sa
            date réelle, indiquée dans le champ ``date`` de chaque résultat).
        date_to: Date de fin incluse au format ISO "AAAA-MM-JJ". Vide = aujourd'hui.

    Returns:
        Liste d'activités (plus récentes d'abord), chacune avec: activity_id, date,
        type, name, distance_km, duration_min, pace (min/km pour la course), avg_hr,
        max_hr. Quand disponibles (tronqués à 500 caractères) :
        - description : la note ORIGINALE écrite par l'athlète (ressenti, détail de
          la séance dans ses propres mots) — signal subjectif le plus fiable.
        - enhanced_description : le texte publié généré par l'IA (contexte, à
          pondérer car ce n'est pas la parole directe de l'athlète).
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(
        _query_activities_impl, user_id, activity_type, date_from, date_to
    )


@tool
async def get_weekly_totals(weeks_back: int = 4) -> list:
    """Récupère les totaux hebdomadaires par semaine ISO, calculés côté serveur.

    UTILISE CET OUTIL pour toute question de volume ou de décompte hebdomadaire
    ("combien de séances cette semaine", "mon volume la semaine dernière",
    "combien de km"). Les totaux sont calculés en code, par semaine ISO
    (lundi-dimanche) : ne recompte JAMAIS en parcourant query_activities, et ne
    construis jamais un total sur 7 jours glissants.

    Args:
        weeks_back: Nombre de semaines ISO à renvoyer, semaine en cours incluse
            (défaut 4, borné à 12).

    Returns:
        Liste par semaine, la plus récente d'abord, chacune avec: iso_week
        (AAAA-Www), label (libellé lisible), runs, run_km, strength, other, total,
        is_current (True pour la semaine en cours). Une semaine sans activité
        renvoie des zéros (ce n'est pas une donnée manquante).
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(_get_weekly_totals_impl, user_id, weeks_back)


@tool
async def get_campus_plan(week_iso: str) -> dict:
    """Récupère les séances Campus Coach planifiées pour une semaine donnée.

    Utilise cet outil quand l'athlète demande son plan, sa prochaine séance, ou
    ce qui est prévu cette semaine / une semaine future.

    Args:
        week_iso: Identifiant ISO de la semaine (champ "week_date_iso" des séances).
            Chaîne vide pour la semaine en cours.

    Returns:
        Dict avec: week_iso, sessions (liste de séances avec title, session_number,
        status, sport, expected_distance_km, expected_duration_min, difficulty,
        intervals, is_current_week, is_future) et athlete_context (goal, assiduity,
        sport_profile).
    """
    return await asyncio.to_thread(_get_campus_plan_impl, week_iso)


@tool
async def get_pace_zones() -> dict:
    """Récupère les zones d'allure, records personnels et FCmax de l'athlète.

    Utilise cet outil pour situer une allure ou une FC par rapport aux zones de
    l'athlète, ou pour rappeler ses records personnels.

    Returns:
        Dict avec: pace_zones, personal_records, max_hr, athlete_zones (zones FC
        Strava) et best_efforts_prs (records accumulés automatiquement).
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(_get_pace_zones_impl, user_id)


@tool
async def get_intervals_metrics(date_from: str, date_to: str) -> dict:
    """Récupère les métriques Intervals.icu (CTL/ATL/Form/HRV/decoupling) sur une période.

    Utilise cet outil pour analyser la charge d'entraînement, la forme, la fatigue
    ou l'efficacité aérobie sur une fenêtre temporelle.

    Args:
        date_from: Date de début incluse au format ISO "AAAA-MM-JJ". Vide = 4
            dernières semaines.
        date_to: Date de fin incluse au format ISO "AAAA-MM-JJ". Vide = aujourd'hui.

    Returns:
        Dict avec: series (points datés {date, ctl, atl, form, hrv, decoupling,
        training_load}) et latest (dernier point disponible). Vide si Intervals.icu
        n'est pas configuré.
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(
        _get_intervals_metrics_impl, user_id, date_from, date_to
    )


def _get_coach_observations_impl(user_id: str, topic: str) -> list:
    """Retrieve long-term coaching observations from AgentCore Memory.

    Records are extracted by the memory strategies into
    /strategies/{strategyId}/actors/{actorId}/ namespaces. The runtime role has
    RetrieveMemoryRecords only (no GetMemory), so we use the "/strategies/"
    prefix and filter results to this user's namespaces — same account-safe
    pattern as the weekly recap (docs/design/memory-improvements.md).
    """
    if not MEMORY_ID or not user_id:
        return []
    query = topic.strip() or "coaching observations athlete progression patterns"
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=MEMORY_ID,
            namespace="/strategies/",
            searchCriteria={"searchQuery": query, "topK": 8},
        )
        records = response.get("memoryRecordSummaries", [])
        return [
            r["content"]["text"]
            for r in records
            if r.get("content", {}).get("text")
            and any(f"/actors/{user_id}/" in ns for ns in (r.get("namespaces") or []))
        ][:5]
    except Exception as e:
        logger.warning("Failed to retrieve coach observations: %s", e)
        return []


@tool
async def get_coach_observations(topic: str) -> list:
    """Récupère les observations long-terme mémorisées sur l'athlète.

    Utilise cet outil pour retrouver ce qui a déjà été observé sur l'athlète au
    fil des séances : patterns d'entraînement, habitudes, ressentis récurrents,
    points de vigilance passés. Complémentaire de query_activities (données
    brutes) : ici ce sont des synthèses qualitatives apprises, pas des chiffres.
    Pour les charges et le tonnage de musculation, utilise get_strength_sessions.

    Args:
        topic: Sujet de recherche en langage naturel, ex. "endurance
            fondamentale allure", "fatigue récupération", "régularité
            entraînement". Chaîne vide pour les observations générales.

    Returns:
        Liste de textes d'observations (max 5), les plus pertinents d'abord.
        Liste vide si rien n'a encore été mémorisé sur ce sujet.
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(_get_coach_observations_impl, user_id, topic)


@tool
async def get_strength_sessions(weeks_back: int = 4) -> list:
    """Récupère les séances de musculation avec exercices et totaux calculés.

    UTILISE CET OUTIL pour toute question sur la musculation : charges, séries,
    répétitions, tonnage, progression muscu. Les totaux (séries, répétitions,
    tonnage) sont calculés côté serveur à partir des séries enregistrées : ne les
    recompte JAMAIS depuis la description d'une activité.

    Args:
        weeks_back: Nombre de semaines à remonter (défaut 4, borné à 12).

    Returns:
        Liste de séances, la plus récente d'abord, chacune avec: activity_id,
        date, iso_week, duration_min, total_sets, total_reps, volume_kg,
        volume_kg_incomplete (True si des charges manquent — poids du corps ou
        inconnu — le tonnage est alors partiel, ne le présente pas comme exact),
        per_exercise (par exercice: sets, reps, volume_kg). Liste vide si aucune
        séance de musculation n'est enregistrée.
    """
    user_id = _resolve_user_id()
    return await asyncio.to_thread(_get_strength_sessions_impl, user_id, weeks_back)


# --- Memory (writes feed the extraction strategies; reads via get_coach_observations tool) ---


def write_chat_to_memory(user_id: str, question: str, answer: str) -> None:
    """Write a chat exchange to AgentCore Memory for long-term learning.

    Mirrors the existing behaviour in shared/coach_context.py: only substantial
    exchanges are stored, keeping the memory extraction quality high.
    """
    if not MEMORY_ID or not user_id:
        return
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
            eventTimestamp=datetime.now(timezone.utc),
        )
        logger.info("Wrote chat exchange to memory for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to write chat to memory: %s", e)


# --- Agent construction -------------------------------------------------------

_TOOLS_ADDENDUM = """

## Outils disponibles
Tu disposes d'outils pour récupérer les données de l'athlète à la demande. Ne suppose JAMAIS un chiffre : appelle l'outil adéquat, puis cite les chiffres exacts qu'il renvoie.
- query_activities(activity_type, date_from, date_to) : activités passées filtrées par type et période (dates ISO AAAA-MM-JJ, vides = 4 dernières semaines). Chaque activité porte un champ iso_week (AAAA-Www).
- get_weekly_totals(weeks_back) : totaux par semaine ISO (runs, run_km, strength, other, total), calculés côté serveur. C'est LA source de tout total ou décompte hebdomadaire.
- get_campus_plan(week_iso) : séances Campus Coach planifiées (week_iso vide = semaine en cours).
- get_pace_zones() : zones d'allure, records personnels, FCmax.
- get_intervals_metrics(date_from, date_to) : CTL/ATL/Form/HRV/decoupling Intervals.icu sur une période.
- get_coach_observations(topic) : observations qualitatives long-terme mémorisées (patterns, habitudes, points de vigilance). À utiliser pour la continuité ("la dernière fois", "d'habitude").
- get_strength_sessions(weeks_back) : séances de musculation avec exercices et totaux (séries, répétitions, tonnage) calculés côté serveur. C'est LA source de tout chiffre de musculation.

## Règles de chiffres (CRITIQUE)
- Tout total ou décompte hebdomadaire (nombre de séances, kilométrage, nombre de séances de muscu) vient de get_weekly_totals. INTERDIT de le recompter en parcourant query_activities, et INTERDIT de sommer une fenêtre de 7 jours glissants pour l'appeler "cette semaine".
- Chaque activité renvoyée porte iso_week (AAAA-Www) : regroupe par ce champ, jamais par un calcul de date à la main.
- Tout chiffre de musculation (séries, répétitions, tonnage) vient de get_strength_sessions, jamais d'un comptage sur les descriptions. Si volume_kg_incomplete est vrai, ne présente pas le tonnage comme exact.

Enchaîne plusieurs appels si nécessaire (ex : "compare mes 6 dernières séances de seuil" = query_activities filtré, puis analyse). Si un outil renvoie une liste vide, dis simplement que la donnée n'est pas disponible."""


def _fetch_athlete_profile(user_id: str) -> str:
    """Fetch a minimal athlete profile block for context stuffing (profile only)."""
    if not user_id:
        return ""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        item = table.get_item(Key={"user_id": user_id}).get("Item", {})
    except Exception as e:
        logger.warning("Failed to fetch athlete profile: %s", e)
        return ""

    prefs = item.get("user_preferences", {})
    parts: list[str] = []
    if prefs.get("athlete_profile"):
        parts.append(f"Profil: {str(prefs['athlete_profile'])[:400]}")
    if prefs.get("personal_records"):
        records = ", ".join(
            f"{r.get('distance')} en {r.get('time')}"
            for r in prefs["personal_records"]
            if isinstance(r, dict)
        )
        if records:
            parts.append(f"Records: {records}")
    if prefs.get("max_hr"):
        parts.append(f"FCmax: {prefs['max_hr']}")
    return "\n".join(parts)


def _build_system_prompt(user_id: str) -> str:
    """Assemble the system prompt: persona + tools guidance + minimal profile.

    Context stuffing is intentionally minimal (athlete profile only); everything
    else is fetched on demand through the tools — the core idea of chantier A1.
    """
    prompt = COACH_CHAT_SYSTEM_PROMPT + _TOOLS_ADDENDUM
    # The model has no inherent notion of "today" and otherwise guesses the year
    # (observed: it passed 2025 date filters against 2026 data → empty results).
    # Anchor all relative date reasoning and tool date arguments to the real date.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = (
        f"{prompt}\n\n## Date du jour\n{today} (UTC). Utilise TOUJOURS cette date "
        f"(et surtout cette année) pour tout raisonnement temporel — « cette "
        f"semaine », « début juillet », « 4 dernières semaines » — et pour les "
        f"arguments date_from/date_to que tu passes aux outils."
    )
    profile = _fetch_athlete_profile(user_id)
    if profile:
        prompt = f"{prompt}\n\n## Profil athlète (contexte minimal)\n{profile}"
    return prompt


def _build_agent(user_id: str) -> Agent:
    """Build a fresh Strands agent bound to the caller for this request.

    The existing Bedrock Guardrail is applied natively by Strands' BedrockModel
    when GUARDRAIL_ID is configured (closes the threat-model T4 gap: the legacy
    Starlette chat path had no guardrail). Without GUARDRAIL_ID the agent runs
    unguarded, matching the legacy behaviour.
    """
    if GUARDRAIL_ID:
        model: Any = BedrockModel(
            model_id=MODEL_ID,
            guardrail_id=GUARDRAIL_ID,
            guardrail_version=GUARDRAIL_VERSION,
        )
    else:
        model = MODEL_ID
    return Agent(
        model=model,
        system_prompt=_build_system_prompt(user_id),
        tools=[query_activities, get_weekly_totals, get_campus_plan, get_pace_zones, get_intervals_metrics, get_coach_observations, get_strength_sessions],
    )


def _last_user_message(run_input: RunAgentInput) -> str:
    """Extract the latest user message text (for the end-of-run memory write)."""
    messages = getattr(run_input, "messages", None) or []
    for msg in reversed(messages):
        if getattr(msg, "role", "") == "user":
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                return content
    return ""


def _text_delta(event: Any) -> str:
    """Return the assistant text delta of a TEXT_MESSAGE_CONTENT AG-UI event."""
    etype = getattr(event, "type", None)
    name = getattr(etype, "value", etype)
    if name == "TEXT_MESSAGE_CONTENT":
        return getattr(event, "delta", "") or ""
    return ""


# --- FastAPI server (AgentCore AGUI contract: :8080, /invocations, /ping) ------

app = FastAPI(title="Strava AI Boost — Coach Chat (AG-UI)")


@app.post("/invocations")
async def invocations(request: Request) -> StreamingResponse:
    """AG-UI entrypoint: stream the coach's answer as SSE events."""
    body = await request.json()
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    user_id = _extract_user_id_from_jwt(auth_header) or DEFAULT_USER_ID
    _USER_ID.set(user_id)

    encoder = EventEncoder(accept=request.headers.get("accept"))
    run_input = RunAgentInput.model_validate(body)
    question = _last_user_message(run_input)

    # Blocking DynamoDB read — keep it off the event loop (m2).
    agent = await asyncio.to_thread(_build_agent, user_id)
    agui_agent = StrandsAgent(
        agent=agent,
        name="strava_coach_chat",
        description="Coach running conversationnel avec accès aux données de l'athlète.",
    )

    async def event_generator():
        answer_parts: list[str] = []
        completed = False
        async for event in agui_agent.run(run_input):
            answer_parts.append(_text_delta(event))
            etype = getattr(event, "type", "")
            if getattr(etype, "value", etype) == "RUN_FINISHED":
                completed = True
            yield encoder.encode(event)
        # Only persist fully completed exchanges: a mid-stream disconnect or
        # error would otherwise write a truncated answer to memory (m6).
        answer = "".join(answer_parts)
        if completed and question and answer:
            await asyncio.to_thread(write_chat_to_memory, user_id, question, answer)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@app.get("/ping")
async def ping() -> JSONResponse:
    """Health check probe required by AgentCore Runtime."""
    return JSONResponse({"status": "Healthy"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
