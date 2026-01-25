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
import boto3

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

# Guardrail configuration (for input validation only)
GUARDRAIL_ID = os.getenv("GUARDRAIL_ID")
GUARDRAIL_VERSION = os.getenv("GUARDRAIL_VERSION", "DRAFT")
GUARDRAIL_ENABLED = os.getenv("GUARDRAIL_ENABLED", "false").lower() == "true"

# Initialize Bedrock Runtime client for guardrail validation
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION) if GUARDRAIL_ENABLED and GUARDRAIL_ID else None

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


def validate_user_input_with_guardrail(text: str, field_name: str) -> tuple[str, bool]:
    """
    Validate user input (title/description) with Bedrock Guardrail
    
    This applies guardrail ONLY to user-provided content (Strava title/description)
    to detect prompt injection, without processing the entire prompt.
    
    Args:
        text: User input to validate (title or description)
        field_name: Name of the field for logging
        
    Returns:
        tuple: (validated_text, is_blocked)
            - validated_text: Original text or sanitized version
            - is_blocked: True if guardrail blocked the content
    """
    if not GUARDRAIL_ENABLED or not GUARDRAIL_ID or not bedrock_runtime:
        logger.debug(f"Guardrail validation skipped for {field_name} (not enabled)")
        return text, False
    
    if not text or len(text.strip()) == 0:
        return text, False
    
    try:
        logger.info(f"🛡️ Validating {field_name} with guardrail ({len(text)} chars)")
        logger.info(f"   Guardrail ID: {GUARDRAIL_ID}")
        logger.info(f"   Guardrail Version: {GUARDRAIL_VERSION}")
        logger.info(f"   Text preview: {text[:100]}...")
        
        # Call ApplyGuardrail API directly (not via model inference)
        logger.info(f"   Calling bedrock_runtime.apply_guardrail()...")
        response = bedrock_runtime.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source="INPUT",
            content=[{
                "text": {
                    "text": text
                }
            }]
        )
        
        logger.info(f"   API Response received: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
        
        # Check if content was blocked
        action = response.get('action', 'NONE')
        logger.info(f"   Guardrail action: {action}")
        
        if action == 'GUARDRAIL_INTERVENED':
            logger.warning(f"⚠️ Guardrail blocked {field_name}: {text[:100]}...")
            
            # Log assessment details
            assessments = response.get('assessments', [])
            logger.warning(f"   Assessments count: {len(assessments)}")
            for assessment in assessments:
                content_policy = assessment.get('contentPolicy', {})
                if content_policy:
                    filters = content_policy.get('filters', [])
                    for filter_item in filters:
                        filter_type = filter_item.get('type')
                        confidence = filter_item.get('confidence')
                        action = filter_item.get('action')
                        logger.warning(f"   Filter: {filter_type}, Confidence: {confidence}, Action: {action}")
            
            # Return sanitized version
            sanitized = f"[Contenu bloqué - {field_name}]"
            return sanitized, True
        
        logger.info(f"✅ Guardrail passed for {field_name}")
        logger.info(f"   Usage: {response.get('usage', {})}")
        return text, False
        
    except Exception as e:
        logger.error(f"❌ Guardrail validation failed for {field_name}: {e}")
        logger.error(f"   Exception type: {type(e).__name__}")
        logger.error(f"   Exception details: {str(e)}")
        # On error, allow content through (fail open for availability)
        return text, False


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
        
        # Load user feedback patterns from AgentCore Memory (if available)
        feedback_instructions = ""
        if MEMORY_ID and memory_client:
            try:
                # Get feedback patterns from system actor (written by feedback_analyzer)
                # Use fixed session_id for feedback to make it easier to retrieve
                feedback_turns = memory_client.get_last_k_turns(
                    memory_id=MEMORY_ID,
                    actor_id="system",
                    session_id="feedback_learning",  # Fixed session_id for feedback
                    k=1  # Latest feedback update
                )
                
                if feedback_turns:
                    # Parse feedback data
                    for turn in feedback_turns:
                        for message in turn:
                            if 'content' in message:
                                try:
                                    content_text = message['content'].get('text', '') if isinstance(message.get('content'), dict) else str(message.get('content', ''))
                                    feedback_data = json.loads(content_text)
                                    patterns = feedback_data.get('patterns_by_type', {})
                                    
                                    if patterns:
                                        feedback_instructions = "\n\n## 🎯 FEEDBACK UTILISATEUR (Préférences Apprises)\n\n"
                                        feedback_instructions += "**Ces préférences ont été détectées depuis tes modifications manuelles. RESPECTE-LES.**\n\n"
                                        
                                        # Length preferences
                                        if 'length_preferences' in patterns:
                                            length_pref = patterns['length_preferences'][0]
                                            feedback_instructions += f"**Longueur** : {length_pref.get('pattern', 'N/A')} (avg: {length_pref.get('avg_reduction', 0)} chars)\n"
                                        
                                        # Expression preferences
                                        if 'expression_preference' in patterns:
                                            feedback_instructions += "\n**Expressions à éviter/préférer** :\n"
                                            for expr in patterns['expression_preference'][:5]:
                                                feedback_instructions += f"- Évite '{expr.get('avoid')}' → Préfère '{expr.get('prefer')}' (fréquence: {expr.get('frequency')})\n"
                                        
                                        # Emoji preferences
                                        if 'emoji_preferences' in patterns:
                                            emoji_pref = patterns['emoji_preferences'][0]
                                            removed = [e['emoji'] for e in emoji_pref.get('frequently_removed', [])]
                                            added = [e['emoji'] for e in emoji_pref.get('frequently_added', [])]
                                            if removed:
                                                feedback_instructions += f"\n**Emojis à éviter** : {' '.join(removed)}\n"
                                            if added:
                                                feedback_instructions += f"**Emojis préférés** : {' '.join(added)}\n"
                                        
                                        # Structure preferences
                                        if 'structure_preference' in patterns:
                                            struct_pref = patterns['structure_preference'][0]
                                            feedback_instructions += f"\n**Structure préférée** : {struct_pref.get('pattern', 'N/A')}\n"
                                        
                                        # Tone preferences
                                        if 'tone_preference' in patterns:
                                            tone_pref = patterns['tone_preference'][0]
                                            feedback_instructions += f"**Ton préféré** : {tone_pref.get('pattern', 'N/A')}\n"
                                        
                                        logger.info(f"✅ Loaded feedback patterns from AgentCore Memory")
                                        logger.info(f"   Patterns types: {list(patterns.keys())}")
                                        break
                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse feedback data from memory: {e}")
                                    continue
                else:
                    logger.info("No feedback patterns found in memory yet")
            except Exception as e:
                logger.warning(f"Failed to load feedback patterns from memory: {e}")
        
        # Append feedback instructions if available
        if feedback_instructions:
            system_prompt += feedback_instructions
        
        # Create Strands agent WITHOUT guardrails on the model
        # Guardrails are applied manually on user inputs only (title/description)
        from strands.models import BedrockModel
        
        logger.info(f"Creating agent without model-level guardrails (input validation done separately)")
        agent = Agent(
            model=MODEL_ID,  # No guardrails on model - we validate inputs manually
            system_prompt=system_prompt,
            hooks=[],  # Disabled: AgentCoreMemoryHook() - Memory writes only after feedback validation
            state={
                "session_id": f"activity-{activity_id}",
                "actor_id": str(user_id)
            }
        )
        
        if MEMORY_ID:
            logger.info(f"Agent created with AgentCore Memory (LTM) READ-ONLY for user {user_id}, activity {activity_id}")
            logger.info(f"⚠️ Memory writes disabled - will be written after feedback validation")
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
        streams_compressed = payload.get('streams_compressed')  # Compressed 30s blocks (no interpretation)
        user_profile = payload.get('user_profile')
        active_modules = payload.get('active_modules', [])
        campus_coach_session = payload.get('campus_coach_session')
        enduraw_data = payload.get('enduraw_data')
        athlete_stats = payload.get('athlete_stats', {})
        athlete_profile = payload.get('athlete_profile', {})
        gear_details = payload.get('gear_details', {})
        
        # Log Campus Coach data details
        if campus_coach_session:
            if isinstance(campus_coach_session, list):
                logger.info(f"🎯 Campus Coach: Received {len(campus_coach_session)} sessions for matching")
                for i, session in enumerate(campus_coach_session[:3]):  # Log first 3 sessions
                    logger.info(f"   Session {i+1}: {session.get('title', 'Unknown')} - {session.get('targetedMetrics', {}).get('target_distance_km', 0)}km")
            else:
                logger.info(f"🎯 Campus Coach: Received single session - {campus_coach_session.get('title', 'Unknown')}")
        else:
            logger.info("ℹ️ Campus Coach: No sessions provided")
        
        # Log detailed invocation info
        logger.info(f"=== Content Generation Started ===")
        logger.info(f"Activity ID: {activity_id}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Activity Type: {activity_data.get('type', 'unknown')}")
        logger.info(f"Distance: {activity_data.get('distance', 0)/1000:.2f} km")
        logger.info(f"Speed: Avg {activity_data.get('average_speed', 0)*3.6:.1f} km/h, Max {activity_data.get('max_speed', 0)*3.6:.1f} km/h")
        if activity_data.get('average_cadence'):
            logger.info(f"Cadence: Avg {activity_data.get('average_cadence'):.0f} spm")
        if activity_data.get('average_watts'):
            logger.info(f"Power: Avg {activity_data.get('average_watts'):.0f}W, Weighted {activity_data.get('weighted_average_watts', 0):.0f}W")
        if activity_data.get('calories'):
            logger.info(f"Calories: {activity_data.get('calories'):.0f} kcal")
        if activity_data.get('suffer_score'):
            logger.info(f"Suffer Score: {activity_data.get('suffer_score'):.0f}/100")
        logger.info(f"Active Modules: {[m.get('name') for m in active_modules]}")
        logger.info(f"Campus Coach Session: {'Yes' if campus_coach_session else 'No'}")
        logger.info(f"Enduraw Data: {'Yes' if enduraw_data else 'No'}")
        logger.info(f"Streams Compressed: {'Yes' if streams_compressed else 'No'}")
        logger.info(f"Memory Enabled: {MEMORY_ID is not None}")
        logger.info(f"Achievements: {activity_data.get('achievement_count', 0)}, PRs: {activity_data.get('pr_count', 0)}, Kudos: {activity_data.get('kudos_count', 0)}")
        logger.info(f"Segment Efforts: {len(activity_data.get('segment_efforts', []))}, Best Efforts: {len(activity_data.get('best_efforts', []))}")
        
        # Log athlete stats if available
        if athlete_stats:
            ytd_run = athlete_stats.get('ytd_run_totals', {})
            if ytd_run and ytd_run.get('distance'):
                logger.info(f"Athlete YTD: {ytd_run.get('distance', 0)/1000:.0f} km in {ytd_run.get('count', 0)} runs")
        else:
            logger.info(f"Athlete Stats: Not available")
        
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
        
        # CRITICAL: Validate user-provided content with guardrail BEFORE including in prompt
        # This prevents prompt injection without processing the entire 230K+ char prompt
        original_title = activity_data.get('name', 'Untitled')
        original_description = activity_data.get('description', 'No description provided')
        
        validated_title, title_blocked = validate_user_input_with_guardrail(original_title, "title")
        validated_description, desc_blocked = validate_user_input_with_guardrail(original_description, "description")
        
        if title_blocked or desc_blocked:
            logger.warning(f"🛡️ Guardrail intervention detected:")
            logger.warning(f"   Title blocked: {title_blocked}")
            logger.warning(f"   Description blocked: {desc_blocked}")
            
            # Return safe fallback content
            return {
                "response": json.dumps({
                    "title": f"{activity_data.get('type', 'Activity')} - {activity_data.get('distance', 0)/1000:.1f}km",
                    "description": f"Activité de {activity_data.get('moving_time', 0)//60} minutes.\n\n@Generated by Strava AI Boost (Safe Mode)",
                    "confidence": 0.5,
                    "guardrail_blocked": True,
                    "blocked_fields": {
                        "title": title_blocked,
                        "description": desc_blocked
                    }
                }),
                "user_id": user_id,
                "activity_id": activity_id,
                "guardrail_intervention": True
            }
        
        # Generate prompt for content creation with ALL user preferences
        activity_type = activity_data.get('sport_type', activity_data.get('type', 'Activity'))
        distance = activity_data.get('distance', 0) / 1000  # km
        duration = activity_data.get('moving_time', 0) / 60  # minutes
        elapsed_time = activity_data.get('elapsed_time', 0) / 60  # minutes
        elevation = activity_data.get('total_elevation_gain', 0)
        avg_hr = activity_data.get('average_heartrate')
        max_hr = activity_data.get('max_heartrate')
        
        # Speed metrics
        avg_speed = activity_data.get('average_speed', 0) * 3.6  # m/s to km/h
        max_speed = activity_data.get('max_speed', 0) * 3.6  # m/s to km/h
        
        # Cadence metrics
        avg_cadence = activity_data.get('average_cadence')
        max_cadence = activity_data.get('max_cadence')
        
        # Power metrics
        avg_watts = activity_data.get('average_watts')
        max_watts = activity_data.get('max_watts')
        weighted_avg_watts = activity_data.get('weighted_average_watts')
        device_watts = activity_data.get('device_watts', False)
        
        # Performance metrics
        calories = activity_data.get('calories')
        suffer_score = activity_data.get('suffer_score')
        workout_type = activity_data.get('workout_type')
        workout_type_names = {0: 'Default', 1: 'Race', 2: 'Long Run', 3: 'Workout', 10: 'Tempo', 11: 'Intervals', 12: 'Recovery'}
        workout_type_str = workout_type_names.get(workout_type, 'Unknown') if workout_type is not None else None
        
        # Equipment
        gear_name = activity_data.get('gear', {}).get('name') if activity_data.get('gear') else None
        
        # Extract athlete profile and gear from payload
        athlete_profile = payload.get('athlete_profile', {})
        gear_details = payload.get('gear_details', {})
        
        # Build athlete context (FTP, weight, power-to-weight ratio)
        athlete_context = ""
        ftp = athlete_profile.get('ftp')
        weight = athlete_profile.get('weight')
        if ftp and weight and avg_watts:
            watts_per_kg = avg_watts / weight
            ftp_percentage = (avg_watts / ftp) * 100 if ftp > 0 else 0
            athlete_context += f"💪 Power-to-Weight: {watts_per_kg:.1f} W/kg (FTP: {ftp}W, Weight: {weight}kg)\n"
            athlete_context += f"📊 Effort Level: {ftp_percentage:.0f}% of FTP\n"
        
        # Build gear context (mileage, brand, model)
        gear_context = ""
        if gear_details:
            gear_name_full = gear_details.get('name', gear_name)
            gear_brand = gear_details.get('brand_name')
            gear_model = gear_details.get('model_name')
            gear_distance = gear_details.get('distance', 0) / 1000  # km
            
            if gear_name_full:
                gear_context += f"👟 Equipment: {gear_name_full}"
                if gear_brand and gear_model:
                    gear_context += f" ({gear_brand} {gear_model})"
                gear_context += f"\n"
            if gear_distance > 0:
                gear_context += f"📏 Equipment Mileage: {gear_distance:.0f} km\n"
        elif gear_name:
            gear_context = f"👟 Equipment: {gear_name}\n"
        
        if not gear_context:
            gear_context = "No equipment data"
        
        # Splits
        splits_metric = activity_data.get('splits_metric', [])
        splits_standard = activity_data.get('splits_standard', [])
        laps = activity_data.get('laps', [])
        
        # Build data payload for agent (system_prompt already has all instructions)
        user_profile_str = json.dumps(user_profile, indent=2) if user_profile else 'No user profile provided'
        active_modules_str = ', '.join([m.get('name', 'unknown') for m in active_modules]) if active_modules else 'No active modules'
        campus_session_str = json.dumps(campus_coach_session, indent=2) if campus_coach_session else 'No Campus Coach session matched'
        enduraw_str = json.dumps(enduraw_data, indent=2) if enduraw_data else 'No Enduraw data available'
        streams_compressed_str = json.dumps(streams_compressed, indent=2) if streams_compressed else 'No compressed streams data available'
        
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
        
        # Extract achievements and performance highlights
        achievement_count = activity_data.get('achievement_count', 0)
        pr_count = activity_data.get('pr_count', 0)
        kudos_count = activity_data.get('kudos_count', 0)
        segment_efforts = activity_data.get('segment_efforts', [])
        best_efforts = activity_data.get('best_efforts', [])
        
        # Build achievements context
        achievements_context = ""
        if achievement_count > 0:
            achievements_context += f"🏆 {achievement_count} achievement(s) unlocked!\n"
        if pr_count > 0:
            achievements_context += f"⭐ {pr_count} personal record(s) set!\n"
        if best_efforts:
            achievements_context += f"💪 Best efforts: {len(best_efforts)} recorded\n"
            # Add details of best efforts (e.g., best 1km, 5km, etc.)
            for effort in best_efforts[:3]:  # Top 3 best efforts
                effort_name = effort.get('name', 'Unknown')
                effort_time = effort.get('elapsed_time', 0)
                achievements_context += f"   - {effort_name}: {effort_time//60}:{effort_time%60:02d}\n"
        if segment_efforts:
            achievements_context += f"🎯 {len(segment_efforts)} segment(s) completed\n"
        
        if not achievements_context:
            achievements_context = "No achievements or PRs for this activity"
        
        # Build athlete stats context (yearly totals, records, etc.)
        athlete_stats_context = ""
        if athlete_stats:
            # Year-to-date totals
            ytd_run = athlete_stats.get('ytd_run_totals', {})
            if ytd_run and ytd_run.get('distance'):
                ytd_distance = ytd_run.get('distance', 0) / 1000  # km
                ytd_count = ytd_run.get('count', 0)
                ytd_time = ytd_run.get('moving_time', 0) / 3600  # hours
                ytd_elevation = ytd_run.get('elevation_gain', 0)
                athlete_stats_context += f"📊 Year-to-Date (2025): {ytd_distance:.0f} km in {ytd_count} runs ({ytd_time:.0f}h, {ytd_elevation:.0f}m D+)\n"
            
            # All-time totals
            all_run = athlete_stats.get('all_run_totals', {})
            if all_run and all_run.get('distance'):
                all_distance = all_run.get('distance', 0) / 1000  # km
                all_count = all_run.get('count', 0)
                athlete_stats_context += f"🏃 All-Time: {all_distance:.0f} km in {all_count} runs\n"
            
            # Recent totals (last 4 weeks)
            recent_run = athlete_stats.get('recent_run_totals', {})
            if recent_run and recent_run.get('distance'):
                recent_distance = recent_run.get('distance', 0) / 1000  # km
                recent_count = recent_run.get('count', 0)
                athlete_stats_context += f"📅 Last 4 Weeks: {recent_distance:.0f} km in {recent_count} runs\n"
            
            # Records
            biggest_ride = athlete_stats.get('biggest_ride_distance')
            biggest_climb = athlete_stats.get('biggest_climb_elevation_gain')
            if biggest_ride:
                athlete_stats_context += f"🚴 Longest Ride: {biggest_ride:.1f} km\n"
            if biggest_climb:
                athlete_stats_context += f"⛰️ Biggest Climb: {biggest_climb:.0f}m D+\n"
        
        if not athlete_stats_context:
            athlete_stats_context = "No athlete stats available"
        
        # Build data-only prompt (instructions are in system_prompt from CONTENT_GENERATION_PROMPT)
        # BUT add explicit size reminder since model ignores system prompt limits
        content_length_pref = user_profile.get('content_preferences', {}).get('length', 'medium')
        size_limits = {
            'short': 300,
            'medium': 800,
            'detailed': 1500
        }
        max_chars = size_limits.get(content_length_pref, 800)
        
        prompt = f"""⚠️ CRITICAL SIZE LIMIT: User preference is "{content_length_pref}" = MAX {max_chars} characters for description (including signature)!
If you exceed {max_chars} chars, CUT content to fit. Keep most important elements, preserve signature.

ACTIVITY DATA:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes (Moving: {duration:.0f} min, Elapsed: {elapsed_time:.0f} min)
- Elevation: {elevation:.0f} m
- Average Speed: {avg_speed:.1f} km/h
- Max Speed: {max_speed:.1f} km/h
- Average HR: {avg_hr} bpm (Max: {max_hr} bpm)
{f"- Average Cadence: {avg_cadence:.0f} spm (Max: {max_cadence:.0f} spm)" if avg_cadence else ""}
{f"- Power: Avg {avg_watts:.0f}W, Max {max_watts:.0f}W, Weighted {weighted_avg_watts:.0f}W {'(Device)' if device_watts else '(Estimated)'}" if avg_watts else ""}
{f"- Calories: {calories:.0f} kcal" if calories else ""}
{f"- Suffer Score: {suffer_score:.0f}/100" if suffer_score else ""}
{f"- Workout Type: {workout_type_str}" if workout_type_str else ""}
- Date: {activity_data.get('start_date', 'Unknown')}

ATHLETE CONTEXT (Power-to-Weight, FTP):
{athlete_context}

EQUIPMENT CONTEXT (Gear Mileage):
{gear_context}

ACHIEVEMENTS & PERFORMANCE HIGHLIGHTS:
{achievements_context}

ATHLETE STATS (Yearly Progress & Records):
{athlete_stats_context}

SPLITS & LAPS:
{f"- Metric Splits: {len(splits_metric)} km splits available" if splits_metric else ""}
{f"- Standard Splits: {len(splits_standard)} mile splits available" if splits_standard else ""}
{f"- Laps: {len(laps)} lap(s) recorded" if laps else ""}

ORIGINAL USER INPUT:
- Original Title: "{validated_title}"
- Original Description: "{validated_description}"
{f"⚠️ Note: Title was sanitized by security filters" if title_blocked else ""}
{f"⚠️ Note: Description was sanitized by security filters" if desc_blocked else ""}

LOCATION & WEATHER:
{location_context}

USER PROFILE:
{user_profile_str}

ACTIVE MODULES:
{active_modules_str}

CAMPUS COACH SESSION:
{campus_session_str}

ENDURAW DATA:
{enduraw_str}

STREAMS DATA (compressed 30s blocks):
{streams_compressed_str}

Generate content now."""
        
        # Invoke agent
        logger.info(f"Invoking agent with prompt length: {len(prompt)} characters")
        result = agent(prompt)
        
        # No need to check guardrail intervention on model (we validated inputs separately)
        # Parse the response directly
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