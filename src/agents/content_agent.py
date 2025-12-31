"""
Content Generation Agent for AgentCore Runtime

AgentCore-compatible agent with ALL prompts and tools embedded directly.
Uses embedded_prompts.py for complete prompt definitions.
Includes AgentCore Memory (LTM) integration for personalization.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Required AgentCore imports
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands import Agent, tool
from strands.hooks import AgentInitializedEvent, HookProvider, MessageAddedEvent

# Import embedded prompts
from embedded_prompts import CONTENT_GENERATION_PROMPT

# Initialize AgentCore app
app = BedrockAgentCoreApp()

# Configure logging level
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Also set root logger to INFO for more visibility
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Environment variables
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")

# AgentCore Memory configuration
MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")

# Initialize memory client if memory is configured
memory_client = None
if MEMORY_ID:
    try:
        memory_client = MemoryClient(region_name=REGION)
        logger.info(f"AgentCore Memory client initialized: {MEMORY_ID}")
    except Exception as e:
        logger.warning(f"Failed to initialize memory client: {e}")
        memory_client = None


class AgentCoreMemoryHook(HookProvider):
    """
    Hook for AgentCore Memory integration with Strands Agent
    
    Based on official AgentCore documentation example.
    Automatically handles:
    - Loading previous conversation/activity context when agent starts
    - Saving each interaction to memory for long-term learning
    """
    
    def on_agent_initialized(self, event):
        """Load previous context from memory when agent starts"""
        if not MEMORY_ID or not memory_client:
            return
        
        try:
            session_id = event.agent.state.get("session_id") or "default"
            actor_id = event.agent.state.get("actor_id") or "default_user"
            
            # Get last 5 conversation turns from memory
            turns = memory_client.get_last_k_turns(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id=session_id,
                k=5  # Last 5 activities for context
            )
            
            if turns:
                # Add conversation history to agent's context
                context = "\n".join([
                    f"{m['role']}: {m['content']['text']}" 
                    for t in turns for m in t
                ])
                event.agent.system_prompt += f"\n\nPREVIOUS ACTIVITIES CONTEXT (from AgentCore LTM):\n{context}"
                logger.info(f"Loaded {len(turns)} previous turns from memory for actor {actor_id}")
        except Exception as e:
            logger.warning(f"Failed to load memory context: {e}")
    
    def on_message_added(self, event):
        """Save interaction to memory after processing"""
        if not MEMORY_ID or not memory_client:
            return
        
        try:
            session_id = event.agent.state.get("session_id") or "default"
            actor_id = event.agent.state.get("actor_id") or "default_user"
            
            # Save only assistant messages (responses) to memory, not user prompts
            msg = event.agent.messages[-1]
            
            # Only save assistant messages (skip user prompts which are too long)
            if msg.get("role") != "assistant":
                logger.debug(f"Skipping memory save for non-assistant message (role: {msg.get('role')})")
                return
            
            # Extract content and limit size to 9000 characters (AgentCore Memory limit)
            content = str(msg.get("content", ""))
            if len(content) > 9000:
                content = content[:9000] + "... [truncated]"
                logger.info(f"Truncated message content from {len(str(msg.get('content')))} to 9000 chars for memory")
            
            memory_client.create_event(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(content, msg["role"])]
            )
            logger.info(f"Saved message to memory for actor {actor_id}, session {session_id} ({len(content)} chars)")
        except Exception as e:
            logger.warning(f"Failed to save to memory: {e}")
    
    def register_hooks(self, registry):
        """Register hooks with the agent"""
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)


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
        # Extract parameters from payload first
        activity_data = payload.get('activity_data', {})
        activity_id = activity_data.get('id', 'unknown')
        user_id = payload.get('user_id', 'default_user')
        
        # Use the embedded complete prompt
        system_prompt = CONTENT_GENERATION_PROMPT
        
        # Create Strands agent with AgentCore Memory hooks
        agent = Agent(
            model=MODEL_ID,
            system_prompt=system_prompt,
            hooks=[AgentCoreMemoryHook()] if MEMORY_ID else [],
            state={
                "session_id": f"activity-{activity_id}",
                "actor_id": str(user_id)
            }
        )
        
        if MEMORY_ID:
            logger.info(f"Agent created with AgentCore Memory (LTM) for user {user_id}, activity {activity_id}")
        else:
            logger.info(f"Agent created without memory (MEMORY_ID not configured)")
        
        # Define callback handler for model reasoning logs
        def reasoning_callback_handler(**kwargs):
            """Log model reasoning and tool usage"""
            if kwargs.get("init_event_loop"):
                logger.info("🔄 Agent event loop initialized")
            elif kwargs.get("start_event_loop"):
                logger.info("▶️ Agent event loop cycle starting")
            elif kwargs.get("reasoning"):
                # Log reasoning events (extended thinking from models like Claude)
                reasoning_text = kwargs.get("reasoningText", "")
                if reasoning_text:
                    logger.info(f"🧠 Model reasoning: {reasoning_text[:500]}...")
                reasoning_sig = kwargs.get("reasoning_signature")
                if reasoning_sig:
                    logger.info(f"   Reasoning signature: {reasoning_sig}")
            elif "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
                tool_name = kwargs["current_tool_use"]["name"]
                tool_input = kwargs["current_tool_use"].get("input", {})
                logger.info(f"🔧 Agent using tool: {tool_name}")
                logger.info(f"   Tool input: {str(tool_input)[:200]}...")
            elif "message" in kwargs:
                role = kwargs["message"].get("role")
                content_preview = str(kwargs["message"].get("content", ""))[:200]
                logger.info(f"📬 Message created: {role} ({len(str(kwargs['message'].get('content', '')))} chars)")
                logger.info(f"   Preview: {content_preview}...")
            elif kwargs.get("complete"):
                logger.info("✅ Agent event loop cycle completed")
            elif kwargs.get("force_stop"):
                logger.warning(f"🛑 Agent force-stopped: {kwargs.get('force_stop_reason', 'unknown')}")
        
        # Add callback handler to agent for reasoning logs
        agent.callback_handler = reasoning_callback_handler
        
        # Extract remaining parameters from payload
        streams_data = payload.get('streams_data')
        user_profile = payload.get('user_profile')
        active_modules = payload.get('active_modules', [])
        campus_coach_session = payload.get('campus_coach_session')
        enduraw_data = payload.get('enduraw_data')
        
        # Log detailed invocation info
        logger.info(f"=== Content Generation Started ===")
        logger.info(f"Activity ID: {activity_id}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Activity Type: {activity_data.get('type', 'unknown')}")
        logger.info(f"Distance: {activity_data.get('distance', 0)/1000:.2f} km")
        logger.info(f"Active Modules: {[m.get('name') for m in active_modules]}")
        logger.info(f"Campus Coach Session: {'Yes' if campus_coach_session else 'No'}")
        logger.info(f"Enduraw Data: {'Yes' if enduraw_data else 'No'}")
        logger.info(f"Streams Data: {'Yes' if streams_data else 'No'}")
        logger.info(f"Memory Enabled: {MEMORY_ID is not None}")
        
        # Log user preferences if available
        if user_profile:
            logger.info(f"=== User Preferences ===")
            content_prefs = user_profile.get('content_preferences', {})
            logger.info(f"Content Tone: {content_prefs.get('tone') or 'not set'}")
            logger.info(f"Content Length: {content_prefs.get('length') or 'not set'}")
            logger.info(f"Technical Detail: {content_prefs.get('technical_detail') or 'not set'}")
            logger.info(f"Emoji Usage: {content_prefs.get('emoji_usage') or 'not set'}")
            logger.info(f"Language: {content_prefs.get('language') or 'not set'}")
            logger.info(f"Sport Approach: {user_profile.get('sport_approach') or 'not set'}")
            logger.info(f"Interests: {user_profile.get('interests') or []}")
            logger.info(f"Age Range: {user_profile.get('age_range') or 'not set'}")
        else:
            logger.info(f"User Preferences: Not configured")
        
        # Validate required data
        if not activity_data:
            logger.error("Missing activity_data in payload")
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
        
        # Extract location and weather data (always used when available)
        location_city = activity_data.get('location_city', '')
        location_country = activity_data.get('location_country', '')
        avg_temp = activity_data.get('average_temp')
        start_latlng = activity_data.get('start_latlng', [])
        fetched_weather = activity_data.get('fetched_weather', {})  # From Open-Meteo via activity_fetcher
        
        location_context = ""
        if location_city or location_country:
            location_parts = [p for p in [location_city, location_country] if p]
            location_context = f"Location: {', '.join(location_parts)}"
        if avg_temp is not None:
            location_context += f"\nTemperature (Strava): {avg_temp}°C"
        if fetched_weather:
            location_context += f"\nWeather (Open-Meteo): Temp {fetched_weather.get('temperature')}°C, Wind {fetched_weather.get('wind_speed')}km/h, Humidity {fetched_weather.get('humidity')}%"
        if not location_context:
            location_context = "No location data available"
        
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

LOCATION & WEATHER (from Strava - use when Enduraw not active):
{location_context}

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
7. Creates authentic content in user's preferred language with appropriate emojis
8. **Uses location and weather data** (always when available):
   - Location (city/country): Mention if interesting or adds context
   - Weather (Open-Meteo): Temperature, wind, humidity - use subtly
   - Enduraw data: Bonus advanced analysis (wind-corrected pace, detailed impact)
   - Keep it brief and authentic (1-2 sentences max)
   - Examples: "Sortie matinale à Paris sous un ciel parfait ☀️"
   - Examples: "Session à Madrid avec 15km/h de vent - conditions challengeantes ! 💨"

Return ONLY a JSON response in this exact format:
{{
  "title": "Generated title here (max 50 chars)",
  "description": "Generated description here\\n\\n@Generated by Strava AI Boost",
  "confidence": 0.85
}}"""
        
        # Invoke the agent - Claude will generate directly using the system prompt
        # Invoke agent
        logger.info(f"Invoking agent with prompt length: {len(prompt)} characters")
        result = agent(prompt)
        
        # Parse the response
        response_text = result.message.get('content', [{}])[0].get('text', str(result))
        
        logger.info(f"=== Content Generation Completed ===")
        logger.info(f"Response length: {len(response_text)} characters")
        logger.info(f"Model used: {MODEL_ID}")
        logger.info(f"Memory used: {MEMORY_ID is not None}")
        
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
        logger.error(f"=== Content Generation Failed ===")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Activity ID: {payload.get('activity_data', {}).get('id', 'unknown')}")
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