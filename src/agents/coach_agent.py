"""
Coach Agent - Generates coaching feedback using Strands Agent with Claude Sonnet.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3
from strands import Agent
from agents.embedded_prompts import COACH_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.getenv("AWS_REGION", "eu-west-1")


def retrieve_coaching_observations(memory_id: str, user_id: str) -> List[str]:
    """Retrieve past coaching observations from AgentCore Memory."""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespace=f"coaching_observations/{user_id}",
            searchCriteria={"searchQuery": "recent coaching observations patterns progress"},
            maxResults=5,
        )
        records = response.get("memoryRecordSummaries", [])
        observations = []
        for r in records:
            text = r.get("content", {}).get("text", "")
            if text:
                observations.append(text)
        if observations:
            logger.info(f"Retrieved {len(observations)} coaching observations from memory")
        return observations
    except Exception as e:
        logger.warning(f"Failed to retrieve coaching observations: {e}")
        return []


def generate_coaching_feedback(
    activity_data: Dict[str, Any],
    user_config: Dict[str, Any],
    historical_summary: Optional[Dict[str, Any]] = None,
    memory_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate coaching feedback for an activity.

    Returns dict with 'strava_block' and 'detailed_analysis', or None on failure.
    """
    try:
        # Build prompt variables
        athlete_profile = json.dumps(user_config.get("user_preferences", {}), ensure_ascii=False)
        historical_context = json.dumps(historical_summary or {}, ensure_ascii=False)
        activity_json = json.dumps(activity_data, ensure_ascii=False, default=str)

        # Retrieve past coaching observations from memory
        observations_context = ""
        user_id = user_config.get("user_id") or activity_data.get("athlete", {}).get("id")
        if memory_id and user_id:
            observations = retrieve_coaching_observations(memory_id, str(user_id))
            if observations:
                observations_context = (
                    "\n\n## PAST COACHING OBSERVATIONS (from long-term memory)\n"
                    + "\n".join(f"- {obs}" for obs in observations)
                    + "\n\nUse these to ensure continuity and track progress.\n"
                )

        system_prompt = (
            COACH_AGENT_SYSTEM_PROMPT
            .replace("{athlete_profile}", athlete_profile)
            .replace("{historical_context}", historical_context)
            .replace("{activity_data}", activity_json)
        ) + observations_context

        agent = Agent(model=MODEL_ID, system_prompt=system_prompt)

        result = agent("Analyse cette activité et génère le coaching feedback en JSON.")

        response_text = result.message.get("content", [{}])[0].get("text", str(result))

        # Extract JSON from response
        response_text = re.sub(r"```json\s*", "", response_text)
        response_text = re.sub(r"```\s*$", "", response_text)
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            logger.error("No JSON found in coach agent response")
            return None

        parsed = json.loads(json_match.group())

        strava_block = parsed.get("strava_block")
        detailed_analysis = parsed.get("detailed_analysis")

        if not strava_block or not detailed_analysis:
            logger.error(f"Missing required fields in coach response: {list(parsed.keys())}")
            return None

        return {"strava_block": strava_block, "detailed_analysis": detailed_analysis}

    except Exception as e:
        logger.error(f"Coach agent failed: {e}")
        return None
