"""
Campus Coach Agent for AgentCore Runtime

AgentCore-compatible agent with ALL prompts embedded directly.
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
from strands_tools.browser import browser_tool

# Import embedded prompts
from embedded_prompts import CAMPUS_COACH_PROMPT

# Initialize AgentCore app
app = BedrockAgentCoreApp()

logger = logging.getLogger(__name__)

# Environment variables
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")

@tool
def extract_campus_coach_sessions(
    user_id: str,
    week_number: Optional[int] = None
) -> Dict[str, Any]:
    """
    Extract weekly training sessions from Campus Coach using Browser Tool
    
    Args:
        user_id: User identifier for credential lookup
        week_number: Optional specific week number to extract
        
    Returns:
        Extraction results with sessions data
    """
    try:
        # Simplified extraction for AgentCore compatibility
        # This would use the Browser Tool to scrape Campus Coach
        
        # Mock session data for now (replace with actual Browser Tool logic)
        sessions = [
            {
                'session_type': 'tempo_run',
                'planned_distance': 8.0,
                'planned_duration': 40,
                'intensity': 'moderate',
                'week_number': week_number or 1
            }
        ]
        
        return {
            'success': True,
            'sessions_extracted': len(sessions),
            'sessions': sessions,
            'retry_attempted': False
        }
            
    except Exception as e:
        logger.error(f"Campus Coach extraction failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'sessions_extracted': 0,
            'retry_attempted': False
        }


@tool
def match_activity_to_session(
    activity_data: Dict[str, Any],
    user_id: str
) -> Dict[str, Any]:
    """
    Match Strava activity to Campus Coach planned session
    
    Args:
        activity_data: Complete Strava activity data (67+ fields)
        user_id: User identifier for session lookup
        
    Returns:
        Matching results with confidence score and session details
    """
    try:
        # Simplified matching logic for AgentCore compatibility
        activity_type = activity_data.get('type', '').lower()
        distance = activity_data.get('distance', 0) / 1000  # km
        duration = activity_data.get('moving_time', 0) / 60  # minutes
        
        # Basic matching logic
        if activity_type == 'run' and distance > 5:
            confidence = 0.8
            session_match = True
            session_type = 'tempo_run' if distance < 10 else 'long_run'
        else:
            confidence = 0.3
            session_match = False
            session_type = 'unknown'
        
        return {
            'session_match': session_match,
            'confidence': confidence,
            'planned_vs_actual': {
                'distance_compliance': 0.9,
                'pace_compliance': 0.8,
                'overall_score': confidence
            },
            'session_type': session_type,
            'compliance_score': confidence,
            'match_reasons': ['Distance and type match'] if session_match else ['No clear match found']
        }
            
    except Exception as e:
        logger.error(f"Session matching failed: {str(e)}")
        return {
            'session_match': False,
            'confidence': 0.0,
            'planned_vs_actual': {},
            'session_type': 'unknown',
            'compliance_score': 0.0,
            'error': str(e)
        }

@tool
def get_user_campus_coach_credentials(user_id: str) -> Dict[str, Any]:
    """
    Retrieve Campus Coach credentials for user
    
    Args:
        user_id: User identifier
        
    Returns:
        Credential status and configuration
    """
    try:
        # Simplified credential check for AgentCore compatibility
        # This would integrate with AWS Secrets Manager
        
        return {
            'credentials_found': True,
            'username': 'user@example.com',
            'login_url': 'https://campus.coach/login',
            'status': 'configured'
        }
            
    except Exception as e:
        logger.error(f"Credential lookup failed: {str(e)}")
        return {
            'credentials_found': False,
            'status': 'error',
            'error': str(e)
        }


@tool
def analyze_session_compliance(
    activity_data: Dict[str, Any],
    planned_session: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze compliance between actual activity and planned session
    
    Args:
        activity_data: Complete Strava activity data
        planned_session: Campus Coach planned session data
        
    Returns:
        Compliance analysis with scoring and insights
    """
    try:
        # Basic compliance analysis
        actual_distance = activity_data.get('distance', 0) / 1000  # km
        actual_duration = activity_data.get('moving_time', 0) / 60  # minutes
        
        planned_distance = planned_session.get('planned_distance', 0)
        planned_duration = planned_session.get('planned_duration', 0)
        
        # Calculate compliance scores
        distance_compliance = 1.0
        if planned_distance > 0:
            distance_diff = abs(actual_distance - planned_distance) / planned_distance
            distance_compliance = max(0.0, 1.0 - distance_diff)
        
        duration_compliance = 1.0
        if planned_duration > 0:
            duration_diff = abs(actual_duration - planned_duration) / planned_duration
            duration_compliance = max(0.0, 1.0 - duration_diff)
        
        # Overall execution assessment
        overall_score = (distance_compliance + duration_compliance) / 2
        
        if overall_score >= 0.9:
            execution = 'excellent'
        elif overall_score >= 0.7:
            execution = 'good'
        elif overall_score >= 0.5:
            execution = 'fair'
        else:
            execution = 'poor'
        
        return {
            'compliance_analysis': {
                'distance_compliance': distance_compliance,
                'pace_compliance': 0.8,  # Placeholder
                'duration_compliance': duration_compliance,
                'overall_execution': execution,
                'overall_score': overall_score
            },
            'match_found': True,
            'confidence': overall_score
        }
            
    except Exception as e:
        logger.error(f"Compliance analysis failed: {str(e)}")
        return {
            'compliance_analysis': {
                'distance_compliance': 0.0,
                'pace_compliance': 0.0,
                'duration_compliance': 0.0,
                'overall_execution': 'error'
            },
            'error': str(e)
        }

@app.entrypoint
def invoke(payload, context=None):
    """
    AgentCore entrypoint for Campus Coach operations
    
    Args:
        payload: Input data containing action and parameters
        context: AgentCore context (optional)
        
    Returns:
        Campus Coach operation results
    """
    try:
        logger.info(f"Campus Coach agent invoked with action: {payload.get('action', 'unknown')}")
        
        # Use the embedded complete prompt
        system_prompt = CAMPUS_COACH_PROMPT
        
        # Create Strands agent with Campus Coach tools
        agent = Agent(
            model=MODEL_ID,
            system_prompt=system_prompt,
            tools=[extract_campus_coach_sessions, match_activity_to_session, 
                   get_user_campus_coach_credentials, analyze_session_compliance, browser_tool]
        )
        
        # Extract parameters from payload
        action = payload.get('action', 'extract_sessions')
        user_id = payload.get('user_id', 'default_user')
        activity_data = payload.get('activity_data', {})
        planned_session = payload.get('planned_session', {})
        week_number = payload.get('week_number')
        
        # Generate prompt based on action
        if action == 'extract_sessions':
            prompt = f"""Extract training sessions from Campus Coach for user {user_id}.

{'Focus on week number ' + str(week_number) if week_number else 'Extract current week sessions'}.

Use the extract_campus_coach_sessions tool to get the latest training plan.
Return detailed session information including session types, distances, and planned intensities."""
            
        elif action == 'match_activity':
            activity_type = activity_data.get('type', 'Unknown')
            distance = activity_data.get('distance', 0) / 1000
            duration = activity_data.get('moving_time', 0) / 60
            
            prompt = f"""Match this Strava activity to a Campus Coach planned session:

Activity Details:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Date: {activity_data.get('start_date', 'Unknown')}

User ID: {user_id}

Use the match_activity_to_session tool to find the best matching planned session.
Provide confidence scoring and compliance analysis."""
            
        elif action == 'check_credentials':
            prompt = f"""Check Campus Coach credentials for user {user_id}.

Use the get_user_campus_coach_credentials tool to verify if the user has configured their Campus Coach login credentials.
Return credential status and configuration details."""
            
        elif action == 'analyze_compliance':
            if not planned_session:
                return {
                    "error": "planned_session data required for compliance analysis",
                    "action": action,
                    "user_id": user_id
                }
            
            prompt = f"""Analyze compliance between actual activity and planned session:

Actual Activity:
- Type: {activity_data.get('type', 'Unknown')}
- Distance: {activity_data.get('distance', 0) / 1000:.2f} km
- Duration: {activity_data.get('moving_time', 0) / 60:.0f} minutes

Planned Session:
- Type: {planned_session.get('session_type', 'Unknown')}
- Planned Distance: {planned_session.get('planned_distance', 0)} km
- Planned Duration: {planned_session.get('planned_duration', 0)} minutes

Use the analyze_session_compliance tool to perform detailed compliance analysis."""
            
        else:
            return {
                "error": f"Unknown action: {action}",
                "supported_actions": ["extract_sessions", "match_activity", "check_credentials", "analyze_compliance"]
            }
        
        # Invoke the agent
        result = agent(prompt)
        
        return {
            "response": result.message.get('content', [{}])[0].get('text', str(result)),
            "action": action,
            "user_id": user_id,
            "model_id": MODEL_ID,
            "agentcore_runtime": "campus_coach_browser_tool"
        }
        
    except Exception as e:
        logger.error(f"Campus Coach operation failed: {str(e)}")
        return {
            "error": str(e),
            "action": payload.get('action', 'unknown'),
            "user_id": payload.get('user_id', 'unknown'),
            "model_id": MODEL_ID,
            "agentcore_runtime": "campus_coach_browser_tool"
        }


# Required AgentCore app.run() call
if __name__ == "__main__":
    app.run()