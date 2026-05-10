"""
Coach Agent - Generates coaching feedback using Bedrock Converse API directly.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3

from agents.embedded_prompts import COACH_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5-20250514-v1:0")
REGION = os.environ.get("AWS_REGION", "us-east-1")

bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)


def retrieve_coaching_observations(memory_id: str, user_id: str) -> List[str]:
    """Retrieve past coaching observations from AgentCore Memory."""
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)
        response = client.retrieve_memory_records(
            memoryId=memory_id,
            namespace=f"coaching_observations/{user_id}",
            searchQuery="recent coaching observations and athlete patterns",
            topK=5,
        )
        records = response.get("memoryRecords", [])
        return [r.get("content", {}).get("text", "") for r in records if r.get("content")]
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
        # Build context
        user_prefs = user_config.get("user_preferences", {})
        athlete_profile = user_prefs.get("athlete_profile", "Non renseigné")
        historical_context = json.dumps(historical_summary or {}, ensure_ascii=False, default=str)
        activity_json = json.dumps(activity_data, ensure_ascii=False, default=str)

        # Retrieve past observations if memory available
        past_observations = ""
        if memory_id:
            user_id = user_config.get("user_id", "")
            obs = retrieve_coaching_observations(memory_id, user_id)
            if obs:
                past_observations = "\n\n## OBSERVATIONS PASSÉES\n" + "\n---\n".join(obs[:5])

        # Build system prompt
        system_prompt = COACH_AGENT_SYSTEM_PROMPT.replace(
            "{ATHLETE_PROFILE}", athlete_profile
        ).replace(
            "{HISTORICAL_CONTEXT}", historical_context
        ).replace(
            "{PAST_OBSERVATIONS}", past_observations
        )

        # Build user message
        user_message = f"Analyse cette activité et donne ton feedback coach :\n\n{activity_json}"

        # Call Bedrock Converse API
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"maxTokens": 1500, "temperature": 0.7},
        )

        # Extract response text
        output = response.get("output", {}).get("message", {}).get("content", [])
        response_text = ""
        for block in output:
            if "text" in block:
                response_text += block["text"]

        if not response_text:
            logger.warning("Empty response from Bedrock")
            return None

        # Parse JSON from response
        # Strip markdown code blocks if present
        cleaned = re.sub(r"```json\s*", "", response_text)
        cleaned = re.sub(r"```\s*", "", cleaned)

        # Find JSON object
        match = re.search(r"\{[^{}]*\"strava_block\"[^{}]*\}", cleaned, re.DOTALL)
        if not match:
            # Try broader match
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if match:
            result = json.loads(match.group())
            if "strava_block" in result:
                logger.info(f"Coach feedback generated: {len(result.get('strava_block', ''))} chars")
                return result

        logger.warning(f"Could not parse coach JSON from response: {response_text[:200]}")
        return None

    except Exception as e:
        logger.error(f"Coach agent error: {e}")
        return None
