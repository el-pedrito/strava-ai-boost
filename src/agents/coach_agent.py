"""
Coach Agent - Generates coaching feedback using Strands Agent with Claude Sonnet.
"""

import json
import logging
from typing import Any, Dict, Optional

from strands import Agent
from agents.embedded_prompts import COACH_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"


def generate_coaching_feedback(
    activity_data: Dict[str, Any],
    user_config: Dict[str, Any],
    historical_summary: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate coaching feedback for an activity.

    Returns dict with 'strava_block' and 'detailed_analysis', or None on failure.
    """
    try:
        # Build prompt variables
        athlete_profile = json.dumps(user_config.get("user_preferences", {}), ensure_ascii=False)
        historical_context = json.dumps(historical_summary or {}, ensure_ascii=False)
        activity_json = json.dumps(activity_data, ensure_ascii=False, default=str)

        system_prompt = (
            COACH_AGENT_SYSTEM_PROMPT
            .replace("{athlete_profile}", athlete_profile)
            .replace("{historical_context}", historical_context)
            .replace("{activity_data}", activity_json)
        )

        agent = Agent(model=MODEL_ID, system_prompt=system_prompt)

        result = agent("Analyse cette activité et génère le coaching feedback en JSON.")

        response_text = result.message.get("content", [{}])[0].get("text", str(result))

        # Extract JSON from response
        import re
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
