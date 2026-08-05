"""
Coach Generator Lambda Function

Generates coaching feedback using AgentCore agent (or direct Bedrock fallback).
"""

import json
import os
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import boto3

from shared.logger import get_logger, inject_correlation_id, metrics, MetricUnit
from shared.env_validation import validate_env_vars
from shared.campus_status import STATUS_DONE, STATUS_SKIP, effective_status
from processing.coach_output_check import (
    strip_false_claims,
    verify_weekly_claims,
)
from shared.iso_week import iso_week_label
from shared.coach_context import format_weekly_breakdown
from processing.modules_processing import match_campus_session

logger = get_logger("coach-generator")

# AWS clients
REGION = os.environ.get("AWS_REGION", "eu-west-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

# Environment variables
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID") or os.environ.get("MEMORY_ID")
COACH_AGENT_ARN = os.environ.get("COACH_AGENT_ARN", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for coaching feedback generation."""
    try:
        inject_correlation_id(logger, event)
        logger.info(f"Coach generator received event: {json.dumps(event, default=str)}")

        validate_env_vars(["ACTIVITIES_TABLE"], "CoachGenerator")

        activity_id = event.get("activity_id")
        user_id = event.get("user_id")
        user_config = event.get("user_config", {})

        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")

        # Retrieve activity data
        activity_data = retrieve_activity_data(activity_id)
        if not activity_data:
            raise ValueError(f"Activity {activity_id} not found in DynamoDB")

        # Week identity of the activity being analysed, as an ISO label
        # 'YYYY-Www' (never a bare int). This is the single reference week:
        # week_overview owns it, and build_historical_summary excludes it from
        # the past-week fields, so no field ever describes the same week twice.
        activity_week = iso_week_label(
            activity_data.get("start_date_local") or activity_data.get("start_date", "")
        )

        # Build historical summary from last 4 weeks (strictly PAST weeks: the
        # activity's own week is owned by week_overview, added further down).
        historical_summary = build_historical_summary(user_id, activity_id, activity_week)

        # Extract and accumulate best efforts (PRs) from this activity
        extract_and_store_prs(user_id, activity_data)

        # Personal-record status is Strava-authoritative (best_efforts.pr_rank),
        # never inferred by the model from a time comparison. Surface the
        # distances set as a PR in THIS activity so the coach states records from
        # a code-provided list instead of comparing times itself.
        prs_set = [
            effort.get("name", "")
            for effort in (activity_data.get("best_efforts") or [])
            if effort.get("pr_rank") == 1 and effort.get("name")
        ]
        if prs_set:
            historical_summary["prs_set_this_activity"] = prs_set

        # Generate coaching feedback via AgentCore
        if not COACH_AGENT_ARN:
            raise ValueError("COACH_AGENT_ARN not configured - coach agent must be deployed to AgentCore")

        # Enrich historical summary with athlete context from user_config
        table = dynamodb.Table(USER_CONFIG_TABLE)
        try:
            uc_response = table.get_item(
                Key={"user_id": user_id},
                ProjectionExpression="athlete_zones, best_efforts_prs, segment_prs, user_preferences"
            )
            uc_item = uc_response.get("Item", {})
            if uc_item.get("athlete_zones"):
                historical_summary["athlete_zones"] = uc_item["athlete_zones"]
                # Also inject into activity_data for metrics computation
                activity_data["_athlete_zones"] = uc_item["athlete_zones"]
                # Recompute metrics now that zones are available
                if activity_data.get("_laps"):
                    activity_data["_computed_metrics"] = _compute_coach_metrics(
                        activity_data["_laps"], activity_data
                    )
            if uc_item.get("best_efforts_prs"):
                historical_summary["best_efforts_prs"] = uc_item["best_efforts_prs"]
            if uc_item.get("segment_prs"):
                historical_summary["segment_prs"] = uc_item["segment_prs"]
            prefs = uc_item.get("user_preferences", {})
            if prefs.get("personal_records"):
                historical_summary["personal_records"] = prefs["personal_records"]
            if prefs.get("max_hr"):
                activity_data["_max_hr_ref"] = prefs["max_hr"]
                # Recompute metrics with max_hr available
                if activity_data.get("_laps"):
                    activity_data["_computed_metrics"] = _compute_coach_metrics(
                        activity_data["_laps"], activity_data
                    )
            # Inject strength program + history for global training vision
            if prefs.get("strength_program"):
                historical_summary["strength_program"] = prefs["strength_program"]
            if prefs.get("strength_history"):
                # Only pass last 8 entries to keep context manageable
                history = prefs["strength_history"]
                entries = history.get("entries", [])
                historical_summary["strength_history"] = entries[-8:] if entries else []
        except Exception as e:
            logger.warning(f"Failed to enrich historical summary: {e}")

        # Add suffer_score and athlete_stats from current activity
        suffer_score = activity_data.get("suffer_score")
        if suffer_score:
            historical_summary["current_suffer_score"] = suffer_score

        # Add Campus Coach sessions (current week + all future weeks)
        try:
            sessions_table = dynamodb.Table(os.environ.get("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"))
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
                    all_sessions = fallback_items
                    # Mark latest week as "current" for compat
                    latest_week = max(fallback_items, key=lambda x: x.get("updated_at", "")).get("week_number", "")
                    for s in all_sessions:
                        s["is_current_week"] = (s.get("week_number") == latest_week)
                        s["is_future"] = False

            current_week = [s for s in all_sessions if s.get("is_current_week")]
            future_sessions = sorted(
                [s for s in all_sessions if s.get("is_future") and not s.get("is_current_week")],
                key=lambda s: s.get("week_date", 0)
            )

            def _format_plan_session(s):
                return {
                    "title": s.get("title", ""),
                    "intervals": s.get("intervals", []),
                    "expected_distance_km": s.get("expected_distance_km"),
                    "expected_duration_min": s.get("expected_duration_min"),
                    # Canonical execution status (never the raw legacy `status`
                    # field, which the sync never rewrites — see B1). This makes
                    # a session with provider_status='done' but status='todo'
                    # correctly appear as done.
                    "status": effective_status(s),
                    "week_date_iso": s.get("week_date_iso", ""),
                    "sport": s.get("sport", ""),
                    "difficulty": s.get("difficulty", ""),
                }

            if current_week:
                # Label the current-week block with its ISO week so the LLM can
                # tell it apart from the future-week plans (B5). Sessions carry
                # their own week_date_iso; take the first as the block's week.
                current_week_iso = current_week[0].get("week_date_iso", "")
                historical_summary["campus_coach_plan"] = {
                    "week": current_week_iso,
                    "sessions": [_format_plan_session(s) for s in current_week],
                }
                # Remaining-session count is NOT emitted as a separate field
                # anymore: it was strictly redundant with
                # week_overview['campus_remaining'] (same sessions, same
                # effective statuses), and two fields answering "how many
                # sessions are left" is exactly the multiplicity that let the
                # coach quote a wrong number. week_overview is the sole source.

            # Single merged view of the week, computed in code: Campus plan plus
            # the athlete's own strength program, current activity included.
            historical_summary["week_overview"] = build_week_overview(
                user_id,
                activity_data,
                current_week,
                historical_summary.get("strength_program"),
            )

            # Group all future weeks
            if future_sessions:
                future_by_week = {}
                for s in future_sessions:
                    week_iso = s.get("week_date_iso", "")
                    if week_iso not in future_by_week:
                        future_by_week[week_iso] = []
                    future_by_week[week_iso].append(_format_plan_session(s))
                historical_summary["campus_coach_future_weeks"] = future_by_week

            # Also inject athlete context if available
            ctx_resp = sessions_table.scan(
                FilterExpression="session_date = :sd",
                ExpressionAttributeValues={":sd": "athlete-context"},
            )
            ctx_items = ctx_resp.get("Items", [])
            if ctx_items:
                ctx = ctx_items[0]
                historical_summary["campus_coach_goal"] = ctx.get("goal", {})
                historical_summary["campus_coach_assiduity"] = ctx.get("assiduity", "")

            # Authoritative "this activity closes plan session X" signal.
            #
            # The coach used to infer the link from the narrative context alone.
            # Running the same deterministic matcher the content branch uses
            # removes that inference: the coach is told which session the
            # activity completes, with its score and ISO week. Recomputing from
            # laps rather than reading the stored completion marker keeps this
            # race-free, since the content branch writes that marker in parallel.
            #
            # Guarded separately: this is an extra DynamoDB scan, and a failure
            # here must degrade to "no authoritative signal" rather than cost us
            # the weekly plan context built above.
            historical_summary["campus_matched_session"] = None
            try:
                matched = match_campus_session(
                    activity_data,
                    laps=activity_data.get("_laps") or [],
                    current_activity_id=activity_id,
                )
                matched_session = matched["matched_session"]
                if matched_session:
                    historical_summary["campus_matched_session"] = {
                        "title": matched_session.get("title", ""),
                        "week_date_iso": matched_session.get("week_date_iso", ""),
                        "sport": matched_session.get("sport", ""),
                        "expected_duration_min": matched_session.get("expected_duration_min"),
                        "intervals": matched_session.get("intervals", []),
                        "match_score": round(matched["match_score"], 2),
                    }
                    logger.info(
                        "Coach informed of matched session '%s' (%s, score=%.2f)",
                        matched_session.get("title"),
                        matched_session.get("week_date_iso"),
                        matched["match_score"],
                    )
                else:
                    logger.info(
                        "No Campus session matched this activity (best=%.2f)",
                        matched["match_score"],
                    )
            except Exception as match_error:
                logger.warning(
                    "Campus match for coach failed, continuing without the "
                    "authoritative signal: %s",
                    match_error,
                )
        except Exception as e:
            logger.warning(f"Failed to fetch Campus Coach sessions: {e}")

        feedback = _invoke_coach_agent(
            activity_data, user_config, historical_summary
        )

        if not feedback:
            logger.warning(f"Coach agent returned no feedback for activity {activity_id}")
            return {
                "statusCode": 200,
                "activity_id": activity_id,
                "user_id": user_id,
                "coach_feedback": None,
            }

        # Verify the figures the model stated against the ones the code computed.
        #
        # Every figure is now computed, labelled and named in the prompt as the sole
        # source, which fixed every case where the model read the wrong field. It did
        # not fix the last one: the model sometimes states a figure present in no
        # field at all ("320 reps" for a 238-rep session, wrapped in an invented fun
        # fact). One regeneration, then removal of the offending sentence. Never
        # blocking: a late coach beats no coach, but a wrong count costs the trust in
        # every other figure.
        week_overview = (historical_summary or {}).get("week_overview")
        strength_session = (historical_summary or {}).get("strength_session")
        problems = verify_weekly_claims(feedback, week_overview, strength_session)
        if problems:
            logger.warning(
                "Coach stated figures contradicting the computed ones, regenerating once",
                extra={"activity_id": activity_id, "problems": problems},
            )
            retry_summary = dict(historical_summary or {})
            retry_summary["verification_errors"] = problems
            retried = _invoke_coach_agent(activity_data, user_config, retry_summary)
            if retried:
                remaining = verify_weekly_claims(retried, week_overview, strength_session)
                if not remaining:
                    feedback = retried
                    problems = []
                else:
                    feedback, removed = strip_false_claims(
                        retried, week_overview, strength_session
                    )
                    problems = remaining
                    feedback["unverified_claims"] = removed
            else:
                feedback, removed = strip_false_claims(
                    feedback, week_overview, strength_session
                )
                feedback["unverified_claims"] = removed

            if problems:
                # Emit a metric: without it the phenomenon is only visible by reading
                # outputs by hand, which is how it went unnoticed for weeks.
                metrics.add_metric(
                    name="CoachClaimMismatch", unit=MetricUnit.Count, value=1
                )

        # Write coaching observation to memory for long-term learning
        write_coaching_observation(user_id, feedback)

        # Store feedback in DynamoDB
        store_coach_feedback(activity_id, feedback)

        # Strip em/en dashes (anti-AI writing rule)
        for key in ("strava_block", "detailed_analysis", "recommendation_next"):
            if key in feedback and isinstance(feedback[key], str):
                feedback[key] = feedback[key].replace('—', ',').replace('–', ',')

        return {
            "statusCode": 200,
            "activity_id": activity_id,
            "user_id": user_id,
            "coach_feedback": feedback,
        }

    except Exception as e:
        logger.error(f"Coach generation error: {e}")
        return {
            "statusCode": 500,
            "error": str(e),
            "activity_id": event.get("activity_id"),
            "user_id": event.get("user_id"),
        }


def _invoke_coach_agent(
    activity_data: Dict[str, Any],
    user_config: Dict[str, Any],
    historical_summary: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Invoke coach agent via AgentCore runtime with retry for cold starts."""
    import re
    import time

    try:
        agentcore_client = boto3.client("bedrock-agentcore", region_name=REGION)
    except Exception:
        agentcore_client = boto3.client("bedrock-agent-runtime", region_name=REGION)

    session_id = f"coach-{uuid.uuid4().hex}"

    # Extract activity date for correct week identification
    activity_start = activity_data.get("start_date_local") or activity_data.get("start_date", "")
    # Week identity as an ISO string 'YYYY-Www' (never a bare int) so the coach
    # agent can match it against the campus_coach_future_weeks keys (B5).
    activity_iso_week = iso_week_label(activity_start) or iso_week_label(
        datetime.now(timezone.utc).isoformat()
    )
    try:
        activity_dt = datetime.fromisoformat(activity_start.replace("Z", "+00:00"))
        activity_date_str = activity_dt.strftime("%Y-%m-%d")
        activity_time_local = activity_dt.strftime("%Hh%M")
        activity_weekday = ['lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche'][activity_dt.weekday()]
    except (ValueError, AttributeError):
        activity_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        activity_time_local = ''
        activity_weekday = ''

    payload = json.dumps({
        "activity_data": activity_data,
        "activity_date": activity_date_str,
        "activity_iso_week": activity_iso_week,
        "activity_time_local": activity_time_local,
        "activity_weekday": activity_weekday,
        "user_config": user_config,
        "historical_summary": historical_summary,
        "memory_id": MEMORY_ID,
    }, default=lambda o: float(o) if hasattr(o, '__float__') else str(o)).encode("utf-8")

    # Retry with exponential backoff for cold start (up to 3 attempts)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = agentcore_client.invoke_agent_runtime(
                agentRuntimeArn=COACH_AGENT_ARN,
                runtimeSessionId=f"{session_id}-{attempt}",
                payload=payload,
            )
            break  # Success
        except Exception as e:
            if "RuntimeClientError" in str(e) and attempt < max_retries - 1:
                wait = (attempt + 1) * 10  # 10s, 20s
                logger.warning(f"Coach agent cold start (attempt {attempt+1}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise

    # Process response (same pattern as content_generator.py)
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

    if not completion:
        logger.warning("Empty response from AgentCore coach agent")
        return None

    # Parse outer response envelope
    try:
        outer = json.loads(completion)
        response_text = outer.get("response", completion) if isinstance(outer, dict) else completion
    except (json.JSONDecodeError, TypeError):
        response_text = completion

    # Parse coaching JSON
    cleaned = re.sub(r"```json\s*", "", response_text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    match = re.search(r"\{[^{}]*\"strava_block\"[^{}]*\}", cleaned, re.DOTALL)
    if not match:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)

    if match:
        result = json.loads(match.group())
        if "strava_block" in result:
            logger.info("Coach feedback generated via AgentCore")
            return result

    logger.warning(f"Could not parse AgentCore coach response: {response_text[:200]}")
    return None


def retrieve_activity_data(activity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve activity data from DynamoDB."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={"activity_id": activity_id})
        item = response.get("Item")
        if not item:
            return None
        raw = item.get("activity_data_json", "{}")
        data = json.loads(raw) if isinstance(raw, str) else raw
        # Attach athlete_stats if available (for coach context)
        stats_raw = item.get("athlete_stats_json")
        if stats_raw:
            stats = json.loads(stats_raw) if isinstance(stats_raw, str) else stats_raw
            data["_athlete_stats"] = stats
        # Attach detailed laps if available
        laps_raw = item.get("laps_json")
        if laps_raw:
            laps = json.loads(laps_raw) if isinstance(laps_raw, str) else laps_raw
            data["_laps"] = laps
            # Compute Efficiency Factor and zone distribution
            data["_computed_metrics"] = _compute_coach_metrics(laps, data)
        return data
    except Exception as e:
        logger.error(f"Failed to retrieve activity {activity_id}: {e}")
        return None


def _safe_float(val: Any) -> float:
    """Cast DynamoDB Decimal/string values to float (0 on failure).

    Manual/indoor Strava activities store numeric fields as strings in
    activity_data_json (e.g. distance='5000.0') — every numeric read must
    go through this guard.
    """
    try:
        return float(val) if val else 0
    except (ValueError, TypeError):
        return 0


def _compute_coach_metrics(laps: list, activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute EF (pace/HR ratio) and grey zone time from laps."""
    metrics: Dict[str, Any] = {}

    _f = _safe_float

    # Average pace and Efficiency Factor (pace @ HR), formatted in code so the
    # coach never converts average_speed (m/s) to a pace itself: that division
    # is exactly what produces impossible values like "4:87/km".
    avg_speed = _f(activity_data.get("average_speed", 0))
    avg_hr = _f(activity_data.get("average_heartrate", 0))
    if avg_speed > 0:
        pace_sec = 1000 / avg_speed
        pace_str = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}/km"
        metrics["avg_pace"] = pace_str
        if avg_hr > 0:
            metrics["ef_pace_at_hr"] = f"{pace_str} @ {int(avg_hr)}bpm"

    # %FCmax for average and max HR
    max_hr_ref = _f(activity_data.get("_max_hr_ref"))
    if max_hr_ref > 0:
        if avg_hr:
            metrics["avg_hr_pct_max"] = round(avg_hr / max_hr_ref * 100, 1)
        act_max_hr = _f(activity_data.get("max_heartrate", 0))
        if act_max_hr:
            metrics["max_hr_pct_max"] = round(act_max_hr / max_hr_ref * 100, 1)
        metrics["fcmax_reference"] = int(max_hr_ref)

    # Intensity distribution: detect time spent in "no benefit" zone (too fast for EF, too slow for tempo)
    # Uses athlete HR zones if available (from user_config), otherwise skips
    # Zone 3 upper / Zone 4 lower boundary = the problematic intensity
    athlete_zones = activity_data.get("_athlete_zones")
    if athlete_zones and laps:
        # Extract HR zone boundaries from Strava athlete zones
        hr_zones = None
        if isinstance(athlete_zones, dict):
            hr_zones = athlete_zones.get("heart_rate", {}).get("zones")
        elif isinstance(athlete_zones, list):
            for z in athlete_zones:
                if z.get("type") == "heartrate":
                    hr_zones = z.get("distribution_buckets") or z.get("zones")
                    break

        # If we have zones, use Z3 boundaries (typically 80-88% FCmax)
        if hr_zones and isinstance(hr_zones, list) and len(hr_zones) >= 4:
            # Strava zones: Z1, Z2, Z3, Z4, Z5 — Z3 is the "moderate" zone
            z3 = hr_zones[2] if len(hr_zones) > 2 else None
            if z3 and isinstance(z3, dict):
                z3_min = _f(z3.get("min", 0))
                z3_max = _f(z3.get("max", 0))
                if z3_min and z3_max:
                    moderate_time = 0
                    total_time = 0
                    for lap in laps:
                        lap_hr = _f(lap.get("average_heartrate", 0))
                        lap_time = _f(lap.get("moving_time", 0))
                        total_time += lap_time
                        if z3_min <= lap_hr <= z3_max:
                            moderate_time += lap_time
                    if total_time > 0 and moderate_time > 0:
                        metrics["zone3_moderate_pct"] = round(moderate_time / total_time * 100, 1)
                        metrics["zone3_moderate_minutes"] = round(moderate_time / 60, 1)
                        metrics["zone3_range_bpm"] = f"{z3_min}-{z3_max}bpm"

    return metrics


def extract_and_store_prs(user_id: str, activity_data: Dict[str, Any]) -> None:
    """Extract best_efforts with pr_rank==1 from activity and accumulate in user_config."""
    # Auto-update max_hr if observed HR is higher
    observed_max_hr = activity_data.get("max_heartrate")
    if observed_max_hr and isinstance(observed_max_hr, (int, float)):
        observed_max_hr = int(observed_max_hr)
        try:
            table = dynamodb.Table(USER_CONFIG_TABLE)
            response = table.get_item(Key={"user_id": user_id}, ProjectionExpression="user_preferences")
            stored_max_hr = response.get("Item", {}).get("user_preferences", {}).get("max_hr", 0)
            if observed_max_hr > stored_max_hr:
                table.update_item(
                    Key={"user_id": user_id},
                    UpdateExpression="SET user_preferences.max_hr = :hr",
                    ExpressionAttributeValues={":hr": observed_max_hr},
                )
                logger.info(f"Updated max_hr for {user_id}: {stored_max_hr} → {observed_max_hr}")
        except Exception as e:
            logger.warning(f"Failed to update max_hr: {e}")

    best_efforts = activity_data.get("best_efforts", [])
    if not best_efforts:
        return

    new_prs = {}
    for effort in best_efforts:
        if effort.get("pr_rank") == 1:
            name = effort.get("name", "")
            elapsed = effort.get("elapsed_time")
            start_date = effort.get("start_date", "")
            distance = effort.get("distance")
            if name and elapsed:
                new_prs[name] = {
                    "elapsed_time": elapsed,
                    "date": start_date[:10] if start_date else "",
                    "distance_m": distance,
                }

    if not new_prs:
        return

    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={"user_id": user_id}, ProjectionExpression="best_efforts_prs")
        existing_prs = response.get("Item", {}).get("best_efforts_prs", {})

        # Merge: keep the faster time for each distance
        updated = False
        for name, pr in new_prs.items():
            existing = existing_prs.get(name)
            if not existing or pr["elapsed_time"] < existing.get("elapsed_time", 999999):
                existing_prs[name] = pr
                updated = True
                logger.info(f"New PR for {user_id}: {name} = {pr['elapsed_time']}s on {pr['date']}")

        if updated:
            table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET best_efforts_prs = :prs",
                ExpressionAttributeValues={":prs": existing_prs},
            )
    except Exception as e:
        logger.warning(f"Failed to store PRs for {user_id}: {e}")

    # Also extract segment PRs (pr_rank 1 or 2)
    _extract_segment_prs(user_id, activity_data)


def _extract_segment_prs(user_id: str, activity_data: Dict[str, Any]) -> None:
    """Extract segment efforts with pr_rank <= 2 and store top 20 most recent."""
    segment_efforts = activity_data.get("segment_efforts", [])
    if not segment_efforts:
        return

    new_segment_prs = []
    for effort in segment_efforts:
        pr_rank = effort.get("pr_rank")
        if pr_rank and pr_rank <= 2:
            segment = effort.get("segment", {})
            new_segment_prs.append({
                "segment_name": segment.get("name", ""),
                "segment_id": str(segment.get("id", "")),
                "elapsed_time": effort.get("elapsed_time"),
                "date": (effort.get("start_date") or "")[:10],
                "pr_rank": pr_rank,
                "distance_m": segment.get("distance"),
            })

    if not new_segment_prs:
        return

    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={"user_id": user_id}, ProjectionExpression="segment_prs")
        existing = response.get("Item", {}).get("segment_prs", [])

        # Merge: update if faster for same segment_id, add if new
        by_id = {s["segment_id"]: s for s in existing}
        for seg in new_segment_prs:
            sid = seg["segment_id"]
            if sid not in by_id or seg["elapsed_time"] < by_id[sid].get("elapsed_time", 999999):
                by_id[sid] = seg

        # Keep only 20 most recent PRs
        all_prs = sorted(by_id.values(), key=lambda s: s.get("date", ""), reverse=True)[:20]

        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET segment_prs = :sp",
            ExpressionAttributeValues={":sp": all_prs},
        )
        logger.info(f"Stored {len(new_segment_prs)} segment PRs for {user_id} (total: {len(all_prs)})")
    except Exception as e:
        logger.warning(f"Failed to store segment PRs for {user_id}: {e}")


def _build_fitness_trend(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract fitness trend from Intervals.icu data if available across activities."""
    ctl_values = []
    for a in sorted(activities, key=lambda x: x.get("start_date", "")):
        icu = a.get("_intervals_icu")
        if icu and isinstance(icu, dict):
            fitness = icu.get("fitness", {})
            ctl = fitness.get("ctl")
            if ctl is not None:
                try:
                    ctl_values.append({"date": a.get("start_date", "")[:10], "ctl": float(ctl)})
                except (ValueError, TypeError):
                    pass
    if not ctl_values:
        return {}
    return {
        "fitness_trend": {
            "source": "intervals_icu",
            "ctl_progression": ctl_values,
            "ctl_start": round(ctl_values[0]["ctl"], 1),
            "ctl_current": round(ctl_values[-1]["ctl"], 1),
            "ctl_delta": round(ctl_values[-1]["ctl"] - ctl_values[0]["ctl"], 1),
        }
    }


def _compute_volume_ramp(weekly_km_by_iso: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """Volume progression between the two most recent COMPLETE ISO weeks.

    Deterministic ramp rate, computed in code so the coach never derives it
    itself. In production the coach summed a rolling 7-day window, called it
    "cette semaine", compared it against a real ISO week and raised a bogus
    "+32% (au-dessus des 10% recommandes)" alert. The partial activity week is
    excluded upstream, so both operands here are complete weeks and the
    percentage is meaningful. Returns None when fewer than two weeks are
    available or the earlier week has no distance.
    """
    if len(weekly_km_by_iso) < 2:
        return None
    # ISO labels 'YYYY-Www' sort chronologically as plain strings.
    ordered = sorted(weekly_km_by_iso.items())
    (prev_week, prev_km), (last_week, last_km) = ordered[-2], ordered[-1]
    if prev_km <= 0:
        return None
    delta_pct = round((last_km - prev_km) / prev_km * 100, 1)
    return {
        "from_week": prev_week,
        "to_week": last_week,
        "from_km": round(prev_km, 1),
        "to_km": round(last_km, 1),
        "delta_pct": delta_pct,
        "exceeds_10pct": delta_pct > 10,
    }


def _monday_of_iso_week(week_label: str) -> Optional[date]:
    """Monday of an ISO week label 'YYYY-Www'. None when unparseable."""
    if not week_label or "-W" not in week_label:
        return None
    year_part, week_part = week_label.split("-W", 1)
    try:
        return date.fromisocalendar(int(year_part), int(week_part), 1)
    except (ValueError, TypeError):
        return None


def build_week_overview(
    user_id: str,
    activity_data: Dict[str, Any],
    campus_current_week: List[Dict[str, Any]],
    strength_program: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """One authoritative view of the athlete's week, computed in code.

    Two gaps made the coach state weekly figures that contradicted the data:

    * ``build_historical_summary`` deliberately skips the activity being
      processed, so its ``weekly_breakdown`` reported "1 course" and no strength
      session on a day the athlete had just logged one. The coach had to add the
      current activity itself, and got the arithmetic wrong (it reported two
      strength sessions where there was one).
    * the weekly plan was the Campus plan alone, while the athlete's real week is
      Campus running sessions PLUS his own strength program (Upper A, Upper B,
      Rappel), so "what is left this week" was always partial.

    This counts the ISO week of the *activity* (not of "now", which differs for a
    Sunday session processed on Monday), includes the current activity, and merges
    both plans. Every figure the coach needs about the week is therefore given to
    it, not inferred.
    """
    week = iso_week_label(
        activity_data.get("start_date_local") or activity_data.get("start_date", "")
    )
    overview: Dict[str, Any] = {"week": week}

    # Human-readable label, on purpose.
    #
    # `weekly_breakdown` carries friendly French labels ("Semaine derniere",
    # "Il y a 2 semaines") while this field only had an ISO code. Asked for "cette
    # semaine", the model reached for the labelled source and read the
    # "Semaine derniere" line as if it were the current week, mixing a run count
    # from here with a strength count from the previous week. Giving this field an
    # equally explicit label removes that asymmetry.
    monday = _monday_of_iso_week(week)
    if monday:
        sunday = monday + timedelta(days=6)
        overview["label"] = (
            f"Cette semaine ({monday.strftime('%d/%m')}-{sunday.strftime('%d/%m')})"
        )
    else:
        overview["label"] = "Cette semaine"

    runs = run_km = strength = other = 0
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        since = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
        resp = table.query(
            IndexName="UserActivitiesIndex",
            KeyConditionExpression="user_id = :uid AND created_at >= :since",
            ExpressionAttributeValues={":uid": user_id, ":since": since},
            ProjectionExpression="activity_id, activity_data_json",
        )
        for item in resp.get("Items", []):
            try:
                data = json.loads(item.get("activity_data_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            start = data.get("start_date_local") or data.get("start_date", "")
            if iso_week_label(start) != week:
                continue
            atype = data.get("type", "")
            if atype == "Run":
                runs += 1
                run_km += _safe_float(data.get("distance", 0)) / 1000
            elif atype == "WeightTraining":
                strength += 1
            else:
                other += 1
    except Exception as e:
        logger.warning(f"Failed to count week activities: {e}")
        overview["counts_incomplete"] = True

    overview["done_this_week"] = {
        "runs": runs,
        "run_km": round(run_km, 1),
        "strength": strength,
        "other": other,
        "total": runs + strength + other,
        "includes_current_activity": True,
    }

    remaining = [
        s for s in campus_current_week
        if effective_status(s) not in (STATUS_DONE, STATUS_SKIP)
    ]
    overview["campus_remaining"] = {
        "count": len(remaining),
        "running_count": len([s for s in remaining if s.get("sport") != "ppg"]),
        "titles": [s.get("title", "") for s in remaining],
    }

    sessions = (strength_program or {}).get("sessions") or []
    if sessions:
        planned = 0
        for s in sessions:
            freq = str(s.get("frequency", "")).lower()
            planned += 2 if freq.startswith("2x") else 1
        overview["own_strength_program"] = {
            "planned_per_week": planned,
            "done_this_week": strength,
            "remaining": max(0, planned - strength),
            "session_names": [s.get("name") or s.get("id", "") for s in sessions],
        }
    return overview


def build_historical_summary(
    user_id: str,
    current_activity_id: str,
    current_activity_week: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a summary of the last 4 weeks of activities.

    ``current_activity_week`` is the ISO label ('YYYY-Www') of the activity being
    analysed. When provided, that week is EXCLUDED from every past-week field
    (``weekly_breakdown``, ``volume_ramp``, the trailing average): its authority
    belongs to ``week_overview`` alone, so no two fields ever describe the same
    week. When None (legacy callers, tests) nothing is excluded.
    """
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()

        response = table.query(
            IndexName="UserActivitiesIndex",
            KeyConditionExpression="user_id = :uid AND created_at >= :since",
            ExpressionAttributeValues={
                ":uid": user_id,
                ":since": four_weeks_ago,
            },
            ProjectionExpression="activity_id, activity_data_json, created_at, intervals_icu_json, coach_feedback, modules_used",
        )
        items = response.get("Items", [])

        activities: List[Dict[str, Any]] = []
        for item in items:
            if item.get("activity_id") == current_activity_id:
                continue
            try:
                data = json.loads(item.get("activity_data_json", "{}"))
                # Manual/indoor activities store numerics as strings — coerce
                # once here so every downstream sum/round/comparison is safe
                # (this crashed the whole historical summary: int + str).
                for field in ("distance", "moving_time", "average_speed", "average_heartrate"):
                    if data.get(field) is not None:
                        data[field] = _safe_float(data[field])
                # Attach integration data if available
                if item.get("intervals_icu_json"):
                    icu = json.loads(item["intervals_icu_json"]) if isinstance(item["intervals_icu_json"], str) else item["intervals_icu_json"]
                    data["_intervals_icu"] = icu
                if item.get("coach_feedback"):
                    data["_prev_coach_feedback"] = item["coach_feedback"]
                if item.get("modules_used"):
                    data["_modules_used"] = [m.get("S", m) if isinstance(m, dict) else m for m in item["modules_used"]]
                activities.append(data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not activities:
            return {"weeks": 4, "total_activities": 0}

        total_distance = sum(a.get("distance", 0) for a in activities) / 1000
        total_time = sum(a.get("moving_time", 0) for a in activities) / 3600
        avg_pace_ms = (
            sum(a.get("average_speed", 0) for a in activities) / len(activities)
        )

        weekly_distances: Dict[str, float] = {}
        for a in activities:
            start = a.get("start_date_local") or a.get("start_date", "")
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                # ISO label, never a bare week number: a bare integer is not
                # comparable with the week_date_iso values used everywhere else,
                # and gives the coach a second, ambiguous notion of "week".
                week_key = iso_week_label(start) or f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                weekly_distances[week_key] = weekly_distances.get(week_key, 0) + a.get("distance", 0) / 1000
            except (ValueError, AttributeError):
                continue

        # Strictly PAST weeks: the activity's own week is owned by week_overview,
        # so excluding it here guarantees no two fields describe the same week.
        past_weekly_distances = {
            week: km for week, km in weekly_distances.items()
            if week != current_activity_week
        }

        weeks_active = len(weekly_distances)
        # Trailing average over the PAST complete weeks. Renamed from the bare
        # `avg_weekly_km`, which read like a weekly total and invited the coach to
        # quote it as "cette semaine". It is a 4-week baseline, never a week total.
        avg_weekly_km_history = (
            sum(past_weekly_distances.values()) / len(past_weekly_distances)
            if past_weekly_distances else 0.0
        )

        # Per-activity breakdown for trend analysis (all activities in 4-week window, max 30)
        recent_activities = sorted(
            activities,
            key=lambda a: a.get("start_date", ""),
            reverse=True,
        )[:30]
        recent_breakdown = []
        for a in recent_activities:
            dist_km = round(a.get("distance", 0) / 1000, 1)
            duration_min = round(a.get("moving_time", 0) / 60)
            avg_speed = a.get("average_speed", 0)
            pace_str = ""
            if avg_speed > 0:
                pace_total_sec = 1000 / avg_speed
                pace_str = f"{int(pace_total_sec // 60)}:{int(pace_total_sec % 60):02d}/km"
            entry: Dict[str, Any] = {
                "date": a.get("start_date", "")[:10],
                # Every activity states its own ISO week, so a session is never
                # attributed to the wrong week when quoted individually.
                "iso_week": iso_week_label(
                    a.get("start_date_local") or a.get("start_date", "")
                ),
                "type": a.get("type", "Run"),
                "name": a.get("name", ""),
                "distance_km": dist_km,
                "duration_min": duration_min,
                "pace": pace_str,
                "avg_hr": a.get("average_heartrate"),
            }
            # EF: pace @ HR for trend comparison
            a_hr = a.get("average_heartrate")
            if avg_speed > 0 and a_hr:
                entry["ef_pace_at_hr"] = f"{pace_str} @ {int(a_hr)}bpm"
            # Intervals.icu fitness data (if available)
            icu = a.get("_intervals_icu")
            if icu and isinstance(icu, dict):
                fitness = icu.get("fitness", {})
                if fitness:
                    entry["ctl"] = fitness.get("ctl")
                    entry["atl"] = fitness.get("atl")
                    entry["form"] = fitness.get("form")
                trends = icu.get("trends", {})
                decoupling = trends.get("decoupling", {}).get("current")
                if decoupling:
                    entry["decoupling"] = decoupling
                if not decoupling and icu.get("decoupling"):
                    entry["decoupling"] = icu["decoupling"]
                if icu.get("training_load"):
                    entry["training_load"] = icu["training_load"]
            # Previous coach recommendation (if available)
            prev_fb = a.get("_prev_coach_feedback")
            if prev_fb and isinstance(prev_fb, dict):
                sb = prev_fb.get("strava_block", prev_fb.get("S", ""))
                if isinstance(sb, dict):
                    sb = sb.get("S", "")
                if sb:
                    # Qualify the note with the ISO week of the activity it
                    # describes (B6). Without this label the LLM rereads a past
                    # session count (e.g. "7x1min") as if it were the current
                    # week, propagating stale figures forward.
                    note_week = iso_week_label(
                        a.get("start_date_local") or a.get("start_date", "")
                    )
                    note_prefix = f"[semaine {note_week}] " if note_week else ""
                    entry["prev_coach_note"] = f"{note_prefix}{sb[:150]}"
            recent_breakdown.append(entry)

        # Group the per-activity detail by ISO week.
        #
        # A flat list carrying a `date` and a `distance_km` per activity is all
        # the material needed to invent a weekly total: the coach summed a
        # rolling 7-day window, called it "cette semaine" and compared it with a
        # real ISO week, producing a bogus ramp-rate alert. Prompt rules alone did
        # not hold. Making the ISO week the *structure* of the data is what fixed
        # the same class of error on the Campus plan, so apply it here too: the
        # detail stays available for a specific session (exercises, loads, paces,
        # CTL, previous note) but no cross-week window can be assembled without
        # deliberately merging buckets. Per-week totals live in
        # `weekly_breakdown`, which is computed in code.
        recent_by_week: Dict[str, List[Dict[str, Any]]] = {}
        for entry in recent_breakdown:
            week = entry.get("iso_week") or "semaine inconnue"
            recent_by_week.setdefault(week, []).append(entry)
        # Most recent week first, so the current week reads at the top.
        recent_by_week = {
            week: recent_by_week[week] for week in sorted(recent_by_week, reverse=True)
        }

        # Explicit per-week session counts (runs/km/strength) for the PAST weeks
        # only, so the coach states real weekly figures instead of hallucinating
        # "5 seances cette semaine". The activity's own week is excluded here so
        # this never competes with week_overview: week_overview answers "this
        # week", weekly_breakdown answers strictly earlier weeks. Reuses the same
        # helper as the chat; normalize field names first (activity_data_json
        # uses `type`, the helper expects `activity_type`).
        normalized = [
            {
                "activity_type": a.get("type", a.get("activity_type", "")),
                "distance": a.get("distance", 0),
                "start_date": a.get("start_date_local") or a.get("start_date", ""),
            }
            for a in activities
            if iso_week_label(a.get("start_date_local") or a.get("start_date", ""))
            != current_activity_week
        ]
        weekly_breakdown = format_weekly_breakdown(normalized)

        summary: Dict[str, Any] = {
            "weeks": 4,
            "total_activities": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_time_hours": round(total_time, 1),
            "avg_pace_ms": round(avg_pace_ms, 2),
            # Trailing 4-week baseline, explicitly NOT a weekly total (see the
            # rename note above). Never quote it as the current week's volume.
            "avg_weekly_km_last_4_weeks": round(avg_weekly_km_history, 1),
            "weeks_active": weeks_active,
            "consistency": f"{weeks_active}/4 weeks",
            "weekly_breakdown": weekly_breakdown,
            "recent_activities_by_week": recent_by_week,
            **_build_fitness_trend(activities),
        }
        # Deterministic volume ramp between the two most recent COMPLETE weeks
        # (the partial activity week is already excluded from
        # past_weekly_distances). The coach must never derive a ramp-rate
        # percentage itself.
        ramp = _compute_volume_ramp(past_weekly_distances)
        if ramp:
            summary["volume_ramp"] = ramp
        return summary

    except Exception as e:
        logger.error(f"Failed to build historical summary: {e}")
        return {"weeks": 4, "total_activities": 0, "error": str(e)}


def store_coach_feedback(activity_id: str, feedback: Dict[str, Any]) -> None:
    """Store coaching feedback in the activity DynamoDB record."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        table.update_item(
            Key={"activity_id": activity_id},
            UpdateExpression="SET coach_feedback = :fb, coach_generated_at = :ts",
            ExpressionAttributeValues={
                ":fb": feedback,
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Stored coach feedback for activity {activity_id}")
    except Exception as e:
        logger.error(f"Failed to store coach feedback: {e}")


def write_coaching_observation(user_id: str, feedback: Dict[str, Any]) -> None:
    """Write a coaching observation summary to AgentCore Memory."""
    if not MEMORY_ID:
        return
    try:
        # Both strava_block and detailed_analysis are strings
        strava_block = feedback.get("strava_block", "")
        detailed_analysis = feedback.get("detailed_analysis", "")

        observation_text = detailed_analysis or strava_block
        if not observation_text:
            return
        if not isinstance(observation_text, str):
            observation_text = json.dumps(observation_text, ensure_ascii=False)

        # Truncate to reasonable size for memory storage
        observation_text = observation_text[:1000]

        import time
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        client.create_event(
            memoryId=MEMORY_ID,
            actorId=str(user_id),
            sessionId=f"coaching-observations-{user_id}",
            payload=[{"conversational": {"role": "ASSISTANT", "content": {"text": observation_text}}}],
            eventTimestamp=time.time(),
        )
        logger.info(f"Wrote coaching observation to memory for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to write coaching observation to memory: {e}")
