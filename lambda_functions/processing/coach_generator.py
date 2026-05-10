"""
Coach Generator Lambda Function

Generates coaching feedback using the coach agent with historical context.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

from shared.logger import get_logger, inject_correlation_id
from shared.env_validation import validate_env_vars

logger = get_logger("coach-generator")

# AWS clients
REGION = os.environ.get("AWS_REGION", "eu-west-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)

# Environment variables
ACTIVITIES_TABLE = os.environ.get("ACTIVITIES_TABLE", "strava-ai-boost-activities")


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

        # Generate coaching feedback
        from agents.coach_agent import generate_coaching_feedback

        feedback = generate_coaching_feedback(activity_data, user_config, historical_summary)

        if not feedback:
            logger.warning(f"Coach agent returned no feedback for activity {activity_id}")
            return {
                "statusCode": 200,
                "activity_id": activity_id,
                "user_id": user_id,
                "coach_feedback": None,
            }

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


def retrieve_activity_data(activity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve activity data from DynamoDB."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        response = table.get_item(Key={"activity_id": activity_id})
        item = response.get("Item")
        if not item:
            return None
        raw = item.get("activity_data_json", "{}")
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        logger.error(f"Failed to retrieve activity {activity_id}: {e}")
        return None


def build_historical_summary(user_id: str, current_activity_id: str) -> Dict[str, Any]:
    """Build a summary of the last 4 weeks of activities."""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).isoformat()

        response = table.scan(
            FilterExpression=Attr("user_id").eq(user_id) & Attr("created_at").gte(four_weeks_ago),
            ProjectionExpression="activity_id, activity_data_json, created_at",
        )
        items = response.get("Items", [])

        activities: List[Dict[str, Any]] = []
        for item in items:
            if item.get("activity_id") == current_activity_id:
                continue
            try:
                data = json.loads(item.get("activity_data_json", "{}"))
                activities.append(data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not activities:
            return {"weeks": 4, "total_activities": 0}

        total_distance = sum(a.get("distance", 0) for a in activities) / 1000
        total_time = sum(a.get("moving_time", 0) for a in activities) / 3600
        avg_pace_ms = (
            sum(a.get("average_speed", 0) for a in activities) / len(activities)
            if activities
            else 0
        )

        # Weekly breakdown
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

        return {
            "weeks": 4,
            "total_activities": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_time_hours": round(total_time, 1),
            "avg_pace_ms": round(avg_pace_ms, 2),
            "avg_weekly_km": round(avg_weekly_km, 1),
            "weeks_active": weeks_active,
            "consistency": f"{weeks_active}/4 weeks",
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
