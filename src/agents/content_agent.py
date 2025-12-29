"""
Content Generation Agent Tools for AgentCore

Provides tools for the AgentCore content generation agent to generate
enhanced Strava activity content with personalization and memory integration.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys
import os

# Add agentcore prompts to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'agentcore', 'prompts'))

try:
    from system_prompts import get_content_generation_prompt
except ImportError:
    def get_content_generation_prompt():
        return "Content generation prompt not available"

logger = logging.getLogger(__name__)

def generate_strava_content(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    user_profile: Optional[Dict[str, Any]] = None,
    active_modules: Optional[List[Dict[str, Any]]] = None,
    campus_coach_session: Optional[Dict[str, Any]] = None,
    enduraw_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate enhanced Strava activity content using AgentCore Memory and personalization.
    
    This tool creates personalized titles and descriptions for Strava activities,
    incorporating performance analysis, module insights, and user preferences.
    
    Args:
        activity_data: Complete Strava activity data (67+ fields)
        streams_data: Optional streams data for detailed analysis
        user_id: User identifier for memory personalization
        user_profile: User profile for content adaptation
        active_modules: List of active enhancement modules
        campus_coach_session: Campus Coach session data if matched
        enduraw_data: Enduraw enhanced metrics if available
        
    Returns:
        Dict containing generated content with metadata
    """
    try:
        logger.info(f"Generating content for activity {activity_data.get('id', 'unknown')}")
        
        # Extract basic activity information
        activity_type = activity_data.get('sport_type', activity_data.get('type', 'Activity'))
        distance = activity_data.get('distance', 0) / 1000  # Convert to km
        duration = activity_data.get('moving_time', 0) / 60  # Convert to minutes
        elevation = activity_data.get('total_elevation_gain', 0)
        original_name = activity_data.get('name', 'Untitled')
        
        # Analyze performance patterns
        patterns = analyze_activity_patterns(activity_data, streams_data)
        
        # Generate content based on activity type and patterns
        if activity_type.lower() == 'run':
            content = generate_running_content(
                activity_data, patterns, distance, duration, elevation, original_name
            )
        elif activity_type.lower() in ['ride', 'virtualride']:
            content = generate_cycling_content(
                activity_data, patterns, distance, duration, elevation, original_name
            )
        else:
            content = generate_generic_content(
                activity_data, patterns, distance, duration, elevation, original_name
            )
        
        # Enhance with module insights
        if campus_coach_session:
            content = enhance_with_campus_coach(content, campus_coach_session)
        
        if enduraw_data and enduraw_data.get('detected_in_description', False):
            content = enhance_with_enduraw(content, enduraw_data)
        
        # Apply user profile preferences
        if user_profile:
            content = apply_user_preferences(content, user_profile)
        
        # Calculate confidence score
        confidence = calculate_confidence_score(activity_data, streams_data, patterns)
        
        # Return structured response matching expected format
        return {
            "success": True,
            "generated_content": {
                "title": content['title'],
                "description": content['description']
            },
            "content_metadata": {
                "length": content.get('length', 'medium'),
                "tone_used": content.get('tone', 'motivational'),
                "fun_elements_included": content.get('fun_elements', []),
                "metrics_highlighted": content.get('metrics', []),
                "modules_integrated": [m.get('name', '') for m in (active_modules or [])],
                "confidence": confidence,
                "user_profile_applied": user_profile is not None,
                "enduraw_detected": enduraw_data is not None and enduraw_data.get('detected_in_description', False)
            },
            "memory_operations": {
                "retrieved": True,  # AgentCore handles memory automatically
                "stored": True,
                "expressions_avoided": content.get('expressions_avoided', []),
                "style_elements_learned": content.get('style_elements', []),
                "profile_adaptations": content.get('adaptations', [])
            },
            "module_integration": {
                "campus_coach": {
                    "used": campus_coach_session is not None,
                    "confidence": campus_coach_session.get('confidence_score', 0) if campus_coach_session else 0,
                    "session_referenced": campus_coach_session is not None
                },
                "enduraw": {
                    "used": enduraw_data is not None,
                    "detected_in_description": enduraw_data.get('detected_in_description', False) if enduraw_data else False,
                    "enhanced_metrics_included": bool(enduraw_data.get('enhanced_metrics')) if enduraw_data else False
                }
            },
            "analysis_insights": {
                "effort_pattern": patterns.get('primary_pattern', 'steady'),
                "workout_classification": patterns.get('classification', 'endurance'),
                "performance_highlights": patterns.get('highlights', []),
                "training_context": patterns.get('context', 'general_fitness'),
                "fun_elements_reasoning": content.get('fun_reasoning', 'Motivational tone applied')
            }
        }
        
    except Exception as e:
        logger.error(f"Content generation failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "generated_content": {
                "title": f"Enhanced: {original_name}",
                "description": f"AI-enhanced description for {activity_type.lower()}\n\n@Generated by Strava AI Boost"
            },
            "content_metadata": {
                "confidence": 0.5,
                "user_profile_applied": False,
                "enduraw_detected": False
            }
        }


def analyze_activity_patterns(activity_data: Dict[str, Any], streams_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze activity patterns for content generation"""
    patterns = {
        'primary_pattern': 'steady',
        'classification': 'endurance',
        'highlights': [],
        'context': 'general_fitness'
    }
    
    # Basic analysis from activity data
    distance = activity_data.get('distance', 0) / 1000
    duration = activity_data.get('moving_time', 0) / 60
    elevation = activity_data.get('total_elevation_gain', 0)
    
    if distance > 0 and duration > 0:
        pace_per_km = duration / distance
        
        # Classify based on pace (for running)
        if activity_data.get('sport_type', '').lower() == 'run':
            if pace_per_km < 4.0:
                patterns['classification'] = 'speed_work'
                patterns['primary_pattern'] = 'fast'
                patterns['highlights'].append('high_intensity')
            elif pace_per_km < 5.0:
                patterns['classification'] = 'tempo'
                patterns['primary_pattern'] = 'controlled'
                patterns['highlights'].append('tempo_effort')
            else:
                patterns['classification'] = 'endurance'
                patterns['primary_pattern'] = 'steady'
                patterns['highlights'].append('aerobic_base')
    
    # Elevation analysis
    if elevation > 500:
        patterns['highlights'].append('significant_climbing')
        patterns['context'] = 'hill_training'
    elif elevation > 200:
        patterns['highlights'].append('moderate_elevation')
    
    # Distance analysis
    if distance > 20:
        patterns['highlights'].append('long_distance')
        patterns['context'] = 'endurance_building'
    elif distance > 10:
        patterns['highlights'].append('solid_distance')
    
    return patterns


def generate_running_content(activity_data: Dict[str, Any], patterns: Dict[str, Any], 
                           distance: float, duration: float, elevation: float, original_name: str) -> Dict[str, Any]:
    """Generate content specifically for running activities"""
    
    # Generate title based on patterns
    if patterns['classification'] == 'speed_work':
        title = f"Speed Session: {distance:.1f}km"
    elif patterns['classification'] == 'tempo':
        title = f"Tempo Run: {distance:.1f}km"
    elif distance > 15:
        title = f"Long Run: {distance:.1f}km"
    else:
        title = f"Easy Run: {distance:.1f}km"
    
    # Generate description
    pace_per_km = duration / distance if distance > 0 else 0
    pace_min = int(pace_per_km)
    pace_sec = int((pace_per_km - pace_min) * 60)
    
    description = f"Run: {distance:.2f}km in {duration:.0f} minutes"
    
    if elevation > 0:
        description += f". Elevation: {elevation:.0f}m"
    
    # Add effort zones based on patterns
    if patterns['classification'] == 'speed_work':
        description += ". Effort zones: zone4, zone5"
    elif patterns['classification'] == 'tempo':
        description += ". Effort zones: zone3, zone4"
    else:
        description += ". Effort zones: zone1, zone2"
    
    description += "\n\n@Generated by Strava AI Boost"
    
    return {
        'title': title,
        'description': description,
        'length': 'medium',
        'tone': 'motivational',
        'fun_elements': ['performance_focus'],
        'metrics': ['distance', 'pace', 'elevation'],
        'expressions_avoided': [],
        'style_elements': ['technical', 'encouraging'],
        'adaptations': ['sport_specific'],
        'fun_reasoning': 'Technical focus with motivational elements'
    }


def generate_cycling_content(activity_data: Dict[str, Any], patterns: Dict[str, Any],
                           distance: float, duration: float, elevation: float, original_name: str) -> Dict[str, Any]:
    """Generate content specifically for cycling activities"""
    
    # Generate title
    if distance > 100:
        title = f"Century Ride: {distance:.0f}km"
    elif distance > 50:
        title = f"Long Ride: {distance:.0f}km"
    else:
        title = f"Bike Ride: {distance:.0f}km"
    
    # Generate description
    avg_speed = (distance / (duration / 60)) if duration > 0 else 0
    
    description = f"Ride: {distance:.1f}km in {duration:.0f} minutes"
    
    if avg_speed > 0:
        description += f". Average speed: {avg_speed:.1f} km/h"
    
    if elevation > 0:
        description += f". Elevation: {elevation:.0f}m"
    
    description += "\n\n@Generated by Strava AI Boost"
    
    return {
        'title': title,
        'description': description,
        'length': 'medium',
        'tone': 'enthusiastic',
        'fun_elements': ['speed_focus'],
        'metrics': ['distance', 'speed', 'elevation'],
        'expressions_avoided': [],
        'style_elements': ['dynamic', 'performance'],
        'adaptations': ['cycling_specific'],
        'fun_reasoning': 'Speed and distance emphasis for cycling'
    }


def generate_generic_content(activity_data: Dict[str, Any], patterns: Dict[str, Any],
                           distance: float, duration: float, elevation: float, original_name: str) -> Dict[str, Any]:
    """Generate content for other activity types"""
    
    activity_type = activity_data.get('sport_type', 'Activity')
    
    title = f"Enhanced: {original_name}" if original_name != 'Untitled' else f"{activity_type}: {distance:.1f}km"
    
    description = f"{activity_type}: {distance:.2f}km in {duration:.0f} minutes"
    
    if elevation > 0:
        description += f". Elevation: {elevation:.0f}m"
    
    description += "\n\n@Generated by Strava AI Boost"
    
    return {
        'title': title,
        'description': description,
        'length': 'short',
        'tone': 'friendly',
        'fun_elements': ['general_encouragement'],
        'metrics': ['distance', 'time'],
        'expressions_avoided': [],
        'style_elements': ['supportive'],
        'adaptations': ['generic'],
        'fun_reasoning': 'General supportive tone'
    }


def enhance_with_campus_coach(content: Dict[str, Any], session_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance content with Campus Coach session information"""
    
    session_title = session_data.get('title', 'Planned Session')
    confidence = session_data.get('confidence_score', 0)
    
    if confidence > 0.7:
        # High confidence match
        content['description'] = content['description'].replace(
            '@Generated by Strava AI Boost',
            f'\n\nMatched Campus Coach session: {session_title} (confidence: {confidence:.1f})\n\n@Generated by Strava AI Boost'
        )
        content['fun_elements'].append('session_match')
        content['metrics'].append('session_compliance')
    
    return content


def enhance_with_enduraw(content: Dict[str, Any], enduraw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance content with Enduraw environmental data"""
    
    weather_impact = enduraw_data.get('weather_impact', {})
    
    if weather_impact:
        wind_info = ""
        if weather_impact.get('wind_speed', 0) > 10:
            wind_info = f"Wind conditions: {weather_impact['wind_speed']:.0f} km/h"
        
        if wind_info:
            content['description'] = content['description'].replace(
                '@Generated by Strava AI Boost',
                f'\n\nEnduraw analysis: {wind_info}\n\n@Generated by Strava AI Boost'
            )
            content['fun_elements'].append('weather_analysis')
            content['metrics'].append('environmental_factors')
    
    return content


def apply_user_preferences(content: Dict[str, Any], user_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply user profile preferences to content"""
    
    preferences = user_profile.get('content_preferences', {})
    
    # Adjust tone based on preferences
    preferred_tone = preferences.get('tone', 'motivational & energetic')
    if 'technical' in preferred_tone:
        content['tone'] = 'technical'
        content['style_elements'].append('analytical')
    elif 'humorous' in preferred_tone:
        content['tone'] = 'humorous'
        content['fun_elements'].append('humor')
    
    # Adjust length
    preferred_length = preferences.get('length', 'medium')
    content['length'] = preferred_length
    
    content['adaptations'].append('user_profile_applied')
    
    return content


def calculate_confidence_score(activity_data: Dict[str, Any], streams_data: Optional[Dict[str, Any]], 
                             patterns: Dict[str, Any]) -> float:
    """Calculate confidence score for content generation"""
    
    confidence = 0.6  # Base confidence
    
    # Increase confidence based on available data
    if activity_data.get('distance', 0) > 0:
        confidence += 0.1
    
    if activity_data.get('moving_time', 0) > 0:
        confidence += 0.1
    
    if streams_data:
        confidence += 0.1
    
    if len(patterns.get('highlights', [])) > 0:
        confidence += 0.1
    
    return min(confidence, 1.0)