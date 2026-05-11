"""
Coach Agent - Generates coaching feedback.

Works as:
- A module imported by the Lambda (generate_coaching_feedback function)
- An AgentCore agent entry point (when deployed to AgentCore runtime)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3

from embedded_prompts import COACH_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
REGION = os.environ.get("AWS_REGION", "eu-west-1")
MEMORY_ID = os.environ.get("BEDROCK_AGENTCORE_MEMORY_ID")


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


def _build_prompt_parts(
    activity_data: Dict[str, Any],
    user_config: Dict[str, Any],
    historical_summary: Optional[Dict[str, Any]] = None,
    memory_id: Optional[str] = None,
) -> tuple:
    """Build system prompt and user message. Returns (system_prompt, user_message)."""
    user_prefs = user_config.get("user_preferences", {})
    athlete_profile = user_prefs.get("athlete_profile", "Non renseigné")

    # Include pace zones and personal records if available
    pace_zones = user_prefs.get("pace_zones")
    personal_records = user_prefs.get("personal_records")
    profile_parts = [athlete_profile]
    if pace_zones:
        zones_str = ", ".join(f"{k}: {v['min']}-{v['max']}" for k, v in pace_zones.items())
        profile_parts.append(f"\nZones d'allure: {zones_str}")
    if personal_records:
        records_str = ", ".join(f"{r['distance']} en {r['time']}" + (f" ({r['date']})" if r.get('date') else "") for r in personal_records)
        profile_parts.append(f"\nRecords personnels: {records_str}")
    athlete_profile = "\n".join(profile_parts)
    historical_context = json.dumps(historical_summary or {}, ensure_ascii=False, default=str)
    activity_json = json.dumps(activity_data, ensure_ascii=False, default=str)

    past_observations = ""
    if memory_id:
        user_id = user_config.get("user_id", "")
        obs = retrieve_coaching_observations(memory_id, user_id)
        if obs:
            past_observations = "\n\n## OBSERVATIONS PASSÉES\n" + "\n---\n".join(obs[:5])

    system_prompt = COACH_AGENT_SYSTEM_PROMPT.replace(
        "{athlete_profile}", athlete_profile
    ).replace(
        "{historical_context}", historical_context
    )

    # Inject past observations if available
    if past_observations:
        system_prompt += past_observations

    user_message = f"Analyse cette activité et donne ton feedback coach :\n\n{activity_json}"
    return system_prompt, user_message


def _parse_coach_response(response_text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON coaching response from model output."""
    if not response_text:
        return None

    cleaned = re.sub(r"```json\s*", "", response_text)
    cleaned = re.sub(r"```\s*", "", cleaned)

    match = re.search(r"\{[^{}]*\"strava_block\"[^{}]*\}", cleaned, re.DOTALL)
    if not match:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)

    if match:
        result = json.loads(match.group())
        if "strava_block" in result:
            return result

    logger.warning(f"Could not parse coach JSON: {response_text[:200]}")
    return None


def generate_coaching_feedback(
    activity_data: Dict[str, Any],
    user_config: Dict[str, Any],
    historical_summary: Optional[Dict[str, Any]] = None,
    memory_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate coaching feedback via direct Bedrock Converse API.

    Returns dict with 'strava_block' and 'detailed_analysis', or None on failure.
    """
    try:
        system_prompt, user_message = _build_prompt_parts(
            activity_data, user_config, historical_summary, memory_id
        )

        bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            system=[{"text": system_prompt}],
            inferenceConfig={"maxTokens": 1500, "temperature": 0.7},
        )

        output = response.get("output", {}).get("message", {}).get("content", [])
        response_text = "".join(block.get("text", "") for block in output)

        return _parse_coach_response(response_text)

    except Exception as e:
        logger.error(f"Coach agent error: {e}")
        return None


# --- AgentCore Runtime Entrypoint ---

try:
    from bedrock_agentcore import BedrockAgentCoreApp
    from strands import Agent

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload, context=None):
        """AgentCore entrypoint for coach agent."""
        try:
            mode = payload.get("mode", "feedback")

            # Conversation mode: respond in prose (not JSON)
            if mode == "conversation":
                question = payload.get("question", "")
                conv_prompt = """Tu es un coach running expert, bienveillant et direct. Tu réponds aux questions de l'athlète.

Règles:
- Tutoiement
- Réponses concises (3-5 phrases max sauf si question complexe)
- Factuel, cite des chiffres quand pertinent
- Si tu ne sais pas, dis-le
- Réponds en prose, PAS en JSON"""

                agent = Agent(model=MODEL_ID, system_prompt=conv_prompt)
                result = agent(question)
                response_text = result.message.get("content", [{}])[0].get("text", str(result))
                return {"response": response_text}

            # Feedback mode: standard JSON output
            activity_data = payload.get("activity_data", {})
            user_config = payload.get("user_config", {})
            historical_summary = payload.get("historical_summary")
            mem_id = MEMORY_ID or payload.get("memory_id")

            system_prompt, user_message = _build_prompt_parts(
                activity_data, user_config, historical_summary, mem_id
            )

            agent = Agent(model=MODEL_ID, system_prompt=system_prompt)
            result = agent(user_message)

            response_text = result.message.get("content", [{}])[0].get("text", str(result))

            return {
                "response": response_text,
                "user_id": user_config.get("user_id", "unknown"),
                "activity_id": activity_data.get("id", "unknown"),
            }
        except Exception as e:
            logger.error(f"AgentCore coach invoke error: {e}")
            return {"error": str(e)}

except ImportError:
    # bedrock_agentcore not available (Lambda environment) — module-only mode
    app = None


if __name__ == "__main__":
    if app:
        app.run()
