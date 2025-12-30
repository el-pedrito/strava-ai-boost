"""
Content Generation Agent for AgentCore Runtime

AgentCore-compatible agent with ALL prompts and tools embedded directly.
Uses embedded_prompts.py for complete prompt definitions.
NO external dependencies - maximum reliability.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Required AgentCore imports
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent, tool

# Import embedded prompts
from embedded_prompts import CONTENT_GENERATION_PROMPT

# Initialize AgentCore app
app = BedrockAgentCoreApp()

logger = logging.getLogger(__name__)

# Environment variables
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")


@app.entrypoint
def invoke(payload, context=None):
    """
    AgentCore entrypoint for content generation operations
    
    Args:
        payload: Input data containing activity data and generation parameters
        context: AgentCore context (optional)
        
    Returns:
        Generated content with metadata and analysis
    """
    try:
        activity_id = payload.get('activity_data', {}).get('id', 'unknown')
        
        # Use the embedded complete prompt
        system_prompt = CONTENT_GENERATION_PROMPT
        
        # Create Strands agent WITHOUT tools - let Claude generate directly
        agent = Agent(
            model=MODEL_ID,
            system_prompt=system_prompt
        )
        
        # Extract parameters from payload
        activity_data = payload.get('activity_data', {})
        streams_data = payload.get('streams_data')
        user_id = payload.get('user_id', 'default_user')
        user_profile = payload.get('user_profile')
        active_modules = payload.get('active_modules', [])
        campus_coach_session = payload.get('campus_coach_session')
        enduraw_data = payload.get('enduraw_data')
        
        # Validate required data
        if not activity_data:
            return {
                "error": "activity_data is required for content generation",
                "user_id": user_id
            }
        
        # Generate prompt for content creation with ALL user preferences
        activity_type = activity_data.get('sport_type', activity_data.get('type', 'Activity'))
        distance = activity_data.get('distance', 0) / 1000  # km
        duration = activity_data.get('moving_time', 0) / 60  # minutes
        elevation = activity_data.get('total_elevation_gain', 0)
        avg_hr = activity_data.get('average_heartrate')
        max_hr = activity_data.get('max_heartrate')
        
        # Build comprehensive prompt with user preferences
        user_profile_str = json.dumps(user_profile, indent=2) if user_profile else 'No user profile provided'
        active_modules_str = ', '.join([m.get('name', 'unknown') for m in active_modules]) if active_modules else 'No active modules'
        campus_session_str = json.dumps(campus_coach_session, indent=2) if campus_coach_session else 'No Campus Coach session matched'
        enduraw_str = json.dumps(enduraw_data, indent=2) if enduraw_data else 'No Enduraw data available'
        streams_str = json.dumps(streams_data, indent=2) if streams_data else 'No streams data available'
        
        prompt = f"""Generate personalized Strava content for this activity.

ACTIVITY DATA:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Elevation: {elevation:.0f} m
- Average HR: {avg_hr} bpm (if available)
- Max HR: {max_hr} bpm (if available)
- Date: {activity_data.get('start_date', 'Unknown')}

ORIGINAL USER INPUT (IMPORTANT - Use as context):
- Original Title: "{activity_data.get('name', 'Untitled')}"
- Original Description: "{activity_data.get('description', 'No description provided')}"

CRITICAL: If the user provided an original title or description, USE THEM as context and inspiration.
The user's original input contains personal notes, feelings, or context that should be PRESERVED and ENRICHED.
- If original description has specific details (weather, feelings, context), INTEGRATE them into enhanced content
- If original title has specific focus (tempo, recovery, interval, etc.), RESPECT and ENHANCE that intent
- ENHANCE and ENRICH the user's input, don't ignore or replace it
- If original content is generic (just activity name), then create from scratch using data

USER PREFERENCES:
User ID: {user_id}
User Profile: {user_profile_str}

ACTIVE MODULES:
{active_modules_str}

CAMPUS COACH SESSION:
{campus_session_str}

ENDURAW DATA:
{enduraw_str}

STREAMS DATA (for detailed analysis):
{streams_str}

INSTRUCTIONS:
Generate a personalized, engaging title and description that:
1. Matches the user's style and preferences from their profile
2. Incorporates performance analysis from activity data and streams
3. Integrates available module insights (Campus Coach, Enduraw) appropriately
4. Uses technical precision with fun, motivational elements
5. Leverages AgentCore Memory to avoid repetitive expressions
6. Adapts to user's age, interests, and sport approach
7. Creates authentic French content with appropriate emojis

Return ONLY a JSON response in this exact format:
{{
  "title": "Generated title here (max 50 chars)",
  "description": "Generated description here\\n\\n@Generated by Strava AI Boost",
  "confidence": 0.85
}}"""
        
        # Invoke the agent - Claude will generate directly using the system prompt
        result = agent(prompt)
        
        # Parse the response
        response_text = result.message.get('content', [{}])[0].get('text', str(result))
        
        # Return the structured response
        return {
            "response": response_text,
            "user_id": user_id,
            "activity_id": activity_data.get('id', 'unknown'),
            "model_id": MODEL_ID,
            "agentcore_runtime": "content_generation_with_memory",
            "prompt_source": "embedded_detailed_prompt"
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "user_id": payload.get('user_id', 'unknown'),
            "activity_id": payload.get('activity_data', {}).get('id', 'unknown'),
            "model_id": MODEL_ID,
            "agentcore_runtime": "content_generation_with_memory"
        }


# Required AgentCore app.run() call
if __name__ == "__main__":
    app.run()