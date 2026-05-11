"""
Coach Generator Lambda Function

Generates coaching feedback using AgentCore agent (or direct Bedrock fallback).
"""

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import boto3

from shared.logger import get_logger, inject_correlation_id
from shared.env_validation import validate_env_vars

logger = get_logger("coach-generator")

# AWS clients
REGION = os.environ.get("AWS_REGION", "eu-west-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

# Environment variables
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")
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

        # Build historical summary from last 4 weeks
        historical_summary = build_historical_summary(user_id, activity_id)

        # Extract and accumulate best efforts (PRs) from this activity
        extract_and_store_prs(user_id, activity_data)

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
        except Exception as e:
            logger.warning(f"Failed to enrich historical summary: {e}")

        # Add suffer_score and athlete_stats from current activity
        suffer_score = activity_data.get("suffer_score")
        if suffer_score:
            historical_summary["current_suffer_score"] = suffer_score

        # Add Campus Coach sessions for current week (if available)
        try:
            sessions_table = dynamodb.Table(os.environ.get("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions"))
            sessions_resp = sessions_table.scan(Limit=10)
            sessions = sessions_resp.get("Items", [])
            if sessions:
                # Get most recent week's sessions
                sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                current_week = sessions[0].get("week_number", "")
                week_sessions = [s for s in sessions if s.get("week_number") == current_week]
                if week_sessions:
                    historical_summary["campus_coach_plan"] = [
                        {
                            "title": s.get("title", ""),
                            "session_number": s.get("session_number", ""),
                            "intervals": s.get("intervals", []),
                            "target_distance_km": (s.get("targetedMetrics") or {}).get("target_distance_km"),
                            "target_duration_min": (s.get("targetedMetrics") or {}).get("target_duration_min"),
                            "status": s.get("status", ""),
                        }
                        for s in week_sessions
                    ]
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

        # Write coaching observation to memory for long-term learning
        write_coaching_observation(user_id, feedback)

        # Store feedback in DynamoDB
        store_coach_feedback(activity_id, feedback)

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

    payload = json.dumps({
        "activity_data": activity_data,
        "user_config": user_config,
        "historical_summary": historical_summary,
        "memory_id": MEMORY_ID,
    }, default=str).encode("utf-8")

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


def _compute_coach_metrics(laps: list, activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute EF (pace/HR ratio) and grey zone time from laps."""
    metrics: Dict[str, Any] = {}

    # Cast DynamoDB Decimal/string values to float
    def _f(val) -> float:
        try:
            return float(val) if val else 0
        except (ValueError, TypeError):
            return 0

    # Efficiency Factor: pace @ HR (for trend comparison across activities)
    avg_speed = _f(activity_data.get("average_speed", 0))
    avg_hr = _f(activity_data.get("average_heartrate", 0))
    if avg_speed > 0 and avg_hr > 0:
        pace_sec = 1000 / avg_speed
        metrics["ef_pace_at_hr"] = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}/km @ {int(avg_hr)}bpm"

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


USER_CONFIG_TABLE = os.environ.get("USER_CONFIG_TABLE", "strava-ai-boost-user-configuration")


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


def build_historical_summary(user_id: str, current_activity_id: str) -> Dict[str, Any]:
    """Build a summary of the last 4 weeks of activities."""
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

        weekly_distances: Dict[int, float] = {}
        for a in activities:
            start = a.get("start_date_local") or a.get("start_date", "")
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                week_num = dt.isocalendar()[1]
                weekly_distances[week_num] = weekly_distances.get(week_num, 0) + a.get("distance", 0) / 1000
            except (ValueError, AttributeError):
                continue

        weeks_active = len(weekly_distances)
        avg_weekly_km = total_distance / max(weeks_active, 1)

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
                    entry["prev_coach_note"] = sb[:150]
            recent_breakdown.append(entry)

        return {
            "weeks": 4,
            "total_activities": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_time_hours": round(total_time, 1),
            "avg_pace_ms": round(avg_pace_ms, 2),
            "avg_weekly_km": round(avg_weekly_km, 1),
            "weeks_active": weeks_active,
            "consistency": f"{weeks_active}/4 weeks",
            "weekly_km": {str(k): round(v, 1) for k, v in weekly_distances.items()},
            "recent_activities": recent_breakdown,
            **_build_fitness_trend(activities),
        }

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
