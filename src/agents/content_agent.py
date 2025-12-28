"""
AgentCore Content Generation Agent for Strava AI Boost

Strands Agent compatible with AgentCore Runtime and Memory.
Uses the original ContentGenerationAgent logic with AgentCore Memory integration.
Stays faithful to original prompts and uses dynamic LLM configuration.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
import sys

# Add config directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import LLM configuration dynamically
try:
    from config.llm_config import DEFAULT_BEDROCK_MODEL_ID, get_bedrock_model_id, get_bedrock_params
except ImportError:
    # Fallback for development
    DEFAULT_BEDROCK_MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
    def get_bedrock_model_id():
        return os.environ.get('BEDROCK_MODEL_ID', DEFAULT_BEDROCK_MODEL_ID)
    def get_bedrock_params():
        return {
            'modelId': get_bedrock_model_id(),
            'body': {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 2000,
                'temperature': 0.7
            }
        }

# Import existing content generation logic
from .content_generation_agent import ContentGenerationAgent

app = BedrockAgentCoreApp()

# Environment variables
MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = get_bedrock_model_id()  # Use dynamic configuration

logger = logging.getLogger(__name__)

@tool
def generate_strava_content(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]] = None,
    user_id: str = "default_user",
    modules: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate personalized content for Strava activity using original agent logic
    
    Args:
        activity_data: Complete Strava activity data (67+ fields)
        streams_data: Optional streams data (velocity, heartrate, etc.)
        user_id: User identifier for personalization and memory
        modules: Active modules (Campus Coach, Enduraw, etc.)
        
    Returns:
        Enhanced content with title, description, and style elements
    """
    try:
        if modules is None:
            modules = []
            
        # Use existing ContentGenerationAgent with all original logic and prompts
        content_agent = ContentGenerationAgent(region=REGION)
        
        # Run content generation using original async method - stay faithful to original implementation
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                content_agent.generate_content(
                    activity_data=activity_data,
                    streams_data=streams_data,
                    user_id=user_id,
                    modules=modules
                )
            )
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Content generation failed: {str(e)}")
        return {
            'title': f"Enhanced: {activity_data.get('name', 'Activity')}",
            'description': f"AI-enhanced description for {activity_data.get('type', 'activity')}. Original error: {str(e)}",
            'style_elements': ['fallback'],
            'modules_used': [module.get('name', 'unknown') for module in modules],
            'confidence': 0.5,
            'error': str(e)
        }

@tool
def analyze_activity_patterns(
    streams_data: Optional[Dict[str, Any]],
    activity_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze activity patterns using original agent logic and dynamic LLM config
    
    Args:
        streams_data: Strava streams data (velocity, heartrate, etc.)
        activity_data: Complete Strava activity data
        
    Returns:
        Pattern analysis with effort zones, intervals, and classification
    """
    try:
        # Use existing ContentGenerationAgent pattern analysis with original prompts
        content_agent = ContentGenerationAgent(region=REGION)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                content_agent.analyze_patterns(streams_data, activity_data)
            )
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Pattern analysis failed: {str(e)}")
        return {
            'patterns': ['unknown'],
            'classification': 'error',
            'effort_zones': ['zone2'],
            'intervals_count': 0,
            'insights': [],
            'analysis_type': 'error',
            'error': str(e)
        }

@tool
def get_user_style_preferences(user_id: str) -> Dict[str, Any]:
    """
    Retrieve user's personal style from AgentCore Memory using original agent logic
    
    Args:
        user_id: User identifier
        
    Returns:
        User style preferences and writing patterns
    """
    try:
        content_agent = ContentGenerationAgent(region=REGION)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                content_agent.get_user_style(user_id)
            )
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Style retrieval failed: {str(e)}")
        return {
            'tone': 'motivational',
            'style_elements': ['technical'],
            'preferred_length': 'medium',
            'sport_focus': 'general',
            'error': str(e)
        }

@tool
def apply_module_insights(
    activity_data: Dict[str, Any],
    modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Apply active module analysis using original agent logic
    
    Args:
        activity_data: Complete Strava activity data
        modules: Active modules configuration
        
    Returns:
        Module insights and analysis results
    """
    try:
        content_agent = ContentGenerationAgent(region=REGION)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                content_agent.apply_modules(activity_data, modules)
            )
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Module insights failed: {str(e)}")
        return {
            'error': str(e),
            'modules_processed': [module.get('name', 'unknown') for module in modules]
        }

@app.entrypoint
def invoke(payload, context):
    """
    AgentCore entrypoint for content generation using original agent logic and prompts
    
    Payload format:
    {
        "activity_data": {...},      // Complete Strava activity data (67+ fields)
        "streams_data": {...},       // Optional streams data
        "user_id": "user123",        // User identifier for memory
        "modules": [...],            // Active modules configuration
        "action": "generate_content" // Optional action specification
    }
    """
    try:
        # Get runtime session ID for isolation
        session_id = getattr(context, 'session_id', 'default')
        actor_id = payload.get('user_id', 'default_user')
        
        # Configure AgentCore Memory if available
        session_manager = None
        if MEMORY_ID:
            memory_config = AgentCoreMemoryConfig(
                memory_id=MEMORY_ID,
                session_id=session_id,
                actor_id=actor_id
            )
            session_manager = AgentCoreMemorySessionManager(memory_config, REGION)
        
        # Create Strands agent with content generation tools and ORIGINAL prompts from ContentGenerationAgent
        agent = Agent(
            model=MODEL_ID,  # Use dynamic LLM configuration
            session_manager=session_manager,
            system_prompt="""You are a specialized Strava content generation assistant for Strava AI Boost.

Your role is to create engaging, personalized titles and descriptions for fitness activities using the original ContentGenerationAgent logic and prompts.

Key capabilities:
1. Generate personalized content with AgentCore Memory integration for style learning
2. Analyze activity patterns and effort zones using Bedrock Claude with original analysis prompts
3. Apply module insights (Campus Coach session matching, Enduraw weather analysis) for enhanced context
4. Learn and adapt to user's personal writing style through persistent memory
5. Avoid repetitive expressions through memory-based tracking and original expression management

Available tools:
- generate_strava_content: Main content generation with full original ContentGenerationAgent logic
- analyze_activity_patterns: Pattern analysis using original Bedrock Claude prompts
- get_user_style_preferences: Retrieve personal style from AgentCore Memory using original methods
- apply_module_insights: Process active module data with original module processing logic

Guidelines (from original ContentGenerationAgent):
- Create motivational and engaging titles (max 50 characters)
- Write technical but accessible descriptions (max 200 words) 
- Use sport-specific terminology appropriate for the activity type
- Maintain an authentic, personal tone based on user preferences from memory
- Include performance insights from pattern analysis using original analysis methods
- Reference module insights when available (Campus Coach sessions, Enduraw metrics)
- Avoid previously used expressions through AgentCore Memory integration
- Use original prompts and logic from ContentGenerationAgent for consistency

The system uses AgentCore Memory for persistent personalization and style learning across activities, maintaining the original agent's approach to content generation.""",
            tools=[generate_strava_content, analyze_activity_patterns, get_user_style_preferences, apply_module_insights]
        )
        
        # Extract parameters from payload
        activity_data = payload.get('activity_data', {})
        streams_data = payload.get('streams_data')
        user_id = payload.get('user_id', 'default_user')
        modules = payload.get('modules', [])
        action = payload.get('action', 'generate_content')
        
        # Generate comprehensive prompt using original agent patterns and prompts
        activity_type = activity_data.get('type', 'Unknown')
        distance = activity_data.get('distance', 0) / 1000
        duration = activity_data.get('moving_time', 0) / 60
        elevation = activity_data.get('total_elevation_gain', 0)
        original_name = activity_data.get('name', 'Untitled')
        
        if action == 'generate_content':
            # Use original ContentGenerationAgent prompt structure
            prompt = f"""Generate enhanced content for this Strava {activity_type.lower()} activity using the original ContentGenerationAgent logic and prompts:

Activity Details:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Elevation: {elevation:.0f} m
- Original Name: {original_name}
- Activity ID: {activity_data.get('id', 'Unknown')}

User Context:
- User ID: {user_id}
- Active Modules: {[m.get('name') for m in modules]}
- Streams Data Available: {'Yes' if streams_data else 'No'}

Please use the generate_strava_content tool to create personalized content using the original agent logic.
The tool will handle:
1. Pattern analysis using original Bedrock AI prompts and methods
2. Module insights application (Campus Coach session matching, Enduraw weather analysis)
3. Personal style retrieval from AgentCore Memory using original style management
4. Expression tracking to avoid repetition using original memory methods
5. Comprehensive content generation with confidence scoring using original algorithms

Return the enhanced title and description with technical insights using the original ContentGenerationAgent approach."""
            
        elif action == 'analyze_patterns':
            prompt = f"""Analyze patterns for this {activity_type.lower()} activity using original ContentGenerationAgent methods:

Activity: {distance:.2f}km in {duration:.0f} minutes
Streams Available: {'Yes' if streams_data else 'No'}

Use the analyze_activity_patterns tool to detect effort patterns, intervals, and workout classification using the original agent's analysis logic."""
            
        elif action == 'get_style':
            prompt = f"""Retrieve personal style preferences for user {user_id} using original ContentGenerationAgent methods.

Use the get_user_style_preferences tool to get their writing tone, style elements, and preferences from AgentCore Memory using the original agent's style management approach."""
            
        else:
            prompt = f"""Process this request for user {user_id}: {action}

Use the appropriate tools based on the request type, maintaining the original ContentGenerationAgent logic and prompts."""
        
        # Invoke the agent with original ContentGenerationAgent context and approach
        result = agent(prompt)
        
        return {
            "response": result.message.get('content', [{}])[0].get('text', str(result)),
            "session_id": session_id,
            "user_id": user_id,
            "action": action,
            "model_id": MODEL_ID,  # Include dynamic model ID
            "agentcore_runtime": "content_generation_memory"
        }
        
    except Exception as e:
        logger.error(f"AgentCore content generation failed: {str(e)}")
        return {
            "error": str(e),
            "fallback_content": {
                "title": f"Enhanced: {payload.get('activity_data', {}).get('name', 'Activity')}",
                "description": "AI-enhanced content generation encountered an error but system remains functional."
            },
            "user_id": payload.get('user_id', 'unknown'),
            "model_id": MODEL_ID,  # Include dynamic model ID
            "agentcore_runtime": "content_generation_memory"
        }

if __name__ == "__main__":
    app.run()