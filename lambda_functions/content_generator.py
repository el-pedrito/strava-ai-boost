"""
Content Generator Lambda Function

Generates enhanced content using Bedrock AI and AgentCore Memory.
Integrates with Strands Agents for intelligent content generation.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError
import sys
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

# Add src directory to path for agent imports
sys.path.append('/opt/python')  # Lambda layer path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import LLM configuration
try:
    from config.llm_config import llm_config, get_bedrock_model_id, get_bedrock_params
except ImportError:
    # Fallback for development
    def get_bedrock_model_id():
        return "anthropic.claude-3-5-sonnet-20241022-v2:0"
    def get_bedrock_params():
        return {
            'modelId': get_bedrock_model_id(),
            'body': {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1200,
                'temperature': 0.7
            }
        }

# Import our agents
try:
    from agents.content_generation_agent import ContentGenerationAgent, run_content_generation
    from agents.campus_coach_agent import CampusCoachAgent, run_session_matching
except ImportError as e:
    logging.error(f"Failed to import agents: {e}")
    # Fallback imports for development
    ContentGenerationAgent = None
    CampusCoachAgent = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

# Environment variables
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')
USER_CONFIG_TABLE = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
COACHING_SESSIONS_TABLE = os.environ.get('COACHING_SESSIONS_TABLE', 'campus-coaching-sessions')
STRAVA_OAUTH_SECRET = os.environ.get('STRAVA_OAUTH_SECRET', 'strava-ai-boost-oauth-tokens')
CAMPUS_COACH_SECRET = os.environ.get('CAMPUS_COACH_SECRET', 'strava-ai-boost-campus-coach-credentials')
AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-1')


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for content generation
    
    Uses Strands Agent with AgentCore Memory for personalized content generation
    """
    try:
        activity_id = event.get('activity_id')
        user_id = event.get('user_id')
        activity_data = event.get('activity_data', {})
        
        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")
        
        logger.info(f"Generating content for activity {activity_id}, user {user_id}")
        
        # Get user configuration and active modules
        user_config = get_user_configuration(user_id)
        active_modules = get_active_modules(user_config)
        
        # Get streams data if available
        streams_data = event.get('streams_data')
        
        # Apply module-specific processing
        enhanced_modules = apply_module_processing(
            activity_data, streams_data, user_id, active_modules
        )
        
        # Generate enhanced content using Strands Agent
        enhanced_content = generate_enhanced_content_with_agent(
            activity_data, 
            streams_data, 
            user_id, 
            enhanced_modules
        )
        
        # Store generated content
        store_generated_content(activity_id, enhanced_content)
        
        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'enhanced_content': enhanced_content,
            'modules_applied': [m['name'] for m in enhanced_modules]
        }
        
    except Exception as e:
        logger.error(f"Content generation error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'activity_id': event.get('activity_id')
        }


def get_user_configuration(user_id: str) -> Dict[str, Any]:
    """Get user configuration from DynamoDB"""
    try:
        table = dynamodb.Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in response:
            return response['Item']
        else:
            # Return default configuration
            return {
                'user_id': user_id,
                'modules_config': {},
                'strava_connected': False
            }
            
    except Exception as e:
        logger.error(f"Failed to get user configuration: {str(e)}")
        return {'user_id': user_id, 'modules_config': {}}


def get_active_modules(user_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get list of active modules for the user"""
    try:
        modules_config = user_config.get('modules_config', {})
        active_modules = []
        
        for module_id, config in modules_config.items():
            if config.get('enabled', False):
                active_modules.append({
                    'name': module_id,
                    'config': config,
                    'enabled': True
                })
        
        logger.info(f"Found {len(active_modules)} active modules")
        return active_modules
        
    except Exception as e:
        logger.error(f"Failed to get active modules: {str(e)}")
        return []


def apply_module_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Apply module-specific processing before content generation
    
    Enhances modules with additional data (e.g., Campus Coach session matching)
    """
    enhanced_modules = []
    
    for module in modules:
        try:
            if module['name'] == 'campus_coach' and module.get('enabled', False):
                # Apply Campus Coach session matching
                enhanced_module = apply_campus_coach_processing(
                    activity_data, user_id, module
                )
                enhanced_modules.append(enhanced_module)
                
            elif module['name'] == 'enduraw' and module.get('enabled', False):
                # Enduraw processing (wait logic handled in webhook processor)
                enhanced_modules.append(module)
                
            else:
                # Other modules - pass through
                enhanced_modules.append(module)
                
        except Exception as e:
            logger.error(f"Module {module['name']} processing failed: {str(e)}")
            # Include module with error info
            module_with_error = module.copy()
            module_with_error['processing_error'] = str(e)
            enhanced_modules.append(module_with_error)
    
    return enhanced_modules


def apply_campus_coach_processing(
    activity_data: Dict[str, Any],
    user_id: str,
    module: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply Campus Coach session matching processing"""
    try:
        logger.info("Applying Campus Coach session matching...")
        
        # Use Campus Coach agent for session matching
        if CampusCoachAgent:
            matching_result = run_session_matching(activity_data, user_id, AWS_REGION)
            
            # Enhance module with matching results
            enhanced_module = module.copy()
            enhanced_module['session_matching'] = matching_result
            
            logger.info(f"Campus Coach matching: {matching_result.get('match_found', False)}")
            return enhanced_module
        else:
            logger.warning("Campus Coach agent not available, using fallback")
            enhanced_module = module.copy()
            enhanced_module['session_matching'] = {
                'match_found': False,
                'confidence': 0.0,
                'reason': 'Agent not available',
                'session_data': None
            }
            return enhanced_module
            
    except Exception as e:
        logger.error(f"Campus Coach processing error: {str(e)}")
        enhanced_module = module.copy()
        enhanced_module['session_matching'] = {
            'match_found': False,
            'confidence': 0.0,
            'reason': f'Processing error: {str(e)}',
            'session_data': None
        }
        return enhanced_module


def generate_enhanced_content_with_agent(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate enhanced content using Strands Agent with AgentCore Memory
    """
    try:
        logger.info("Generating content with Strands Agent...")
        
        # Use Content Generation Agent if available
        if ContentGenerationAgent:
            enhanced_content = run_content_generation(
                activity_data, streams_data, user_id, modules, AWS_REGION
            )
            
            logger.info(f"Content generated with confidence: {enhanced_content.get('confidence', 0.0)}")
            return enhanced_content
        else:
            logger.warning("Content Generation Agent not available, using fallback")
            return generate_enhanced_content_fallback(
                activity_data, streams_data, user_id, modules
            )
            
    except Exception as e:
        logger.error(f"Agent content generation failed: {str(e)}")
        # Fallback to direct Bedrock generation
        return generate_enhanced_content_fallback(
            activity_data, streams_data, user_id, modules
        )


def generate_enhanced_content_fallback(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Fallback content generation using Bedrock directly
    
    Used when Strands Agent is not available
    """
    try:
        logger.info("Using fallback content generation...")
        
        # Analyze streams data for effort patterns
        patterns = analyze_streams_data_fallback(streams_data, activity_data)
        
        # Extract module insights
        module_insights = extract_module_insights(modules)
        
        # Generate content with Bedrock directly
        enhanced_content = generate_with_bedrock_enhanced(
            activity_data, patterns, module_insights
        )
        
        return enhanced_content
        
    except Exception as e:
        logger.error(f"Fallback content generation failed: {str(e)}")
        # Return basic fallback content
        return {
            'title': f"Enhanced: {activity_data.get('name', 'Activity')}",
            'description': f"AI-enhanced description for {activity_data.get('type', 'activity')}",
            'style_elements': ['fallback'],
            'modules_used': [m['name'] for m in modules],
            'confidence': 0.5,
            'error': str(e)
        }


def analyze_streams_data_fallback(
    streams_data: Optional[Dict[str, Any]], 
    activity_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Fallback streams data analysis for effort patterns and heart rate zones
    """
    try:
        if not streams_data:
            return analyze_basic_activity_patterns(activity_data)
        
        # Basic analysis of streams data
        velocity_data = streams_data.get('velocity_smooth', [])
        heartrate_data = streams_data.get('heartrate', [])
        
        patterns = []
        effort_zones = []
        intervals_count = 0
        
        # Analyze velocity patterns for intervals
        if velocity_data and len(velocity_data) > 10:
            # Simple interval detection based on velocity variation
            velocity_changes = []
            for i in range(1, len(velocity_data)):
                if velocity_data[i-1] > 0:  # Avoid division by zero
                    change = abs(velocity_data[i] - velocity_data[i-1]) / velocity_data[i-1]
                    velocity_changes.append(change)
            
            # Count significant velocity changes (potential intervals)
            significant_changes = [c for c in velocity_changes if c > 0.2]  # 20% change
            intervals_count = len(significant_changes) // 2  # Pairs of up/down changes
            
            if intervals_count > 3:
                patterns.append('interval_training')
            elif intervals_count > 0:
                patterns.append('fartlek')
            else:
                patterns.append('steady_effort')
        
        # Analyze heart rate zones
        if heartrate_data:
            avg_hr = sum(heartrate_data) / len(heartrate_data)
            max_hr = max(heartrate_data)
            
            # Simple zone estimation (assuming max HR ~190 for average athlete)
            estimated_max_hr = 190
            hr_percentage = avg_hr / estimated_max_hr
            
            if hr_percentage < 0.6:
                effort_zones.append('zone1')
            elif hr_percentage < 0.7:
                effort_zones.append('zone2')
            elif hr_percentage < 0.8:
                effort_zones.append('zone3')
            elif hr_percentage < 0.9:
                effort_zones.append('zone4')
            else:
                effort_zones.append('zone5')
        
        return {
            'patterns': patterns if patterns else ['steady_effort'],
            'classification': classify_workout_type(patterns, intervals_count),
            'effort_zones': effort_zones if effort_zones else ['zone2'],
            'intervals_count': intervals_count,
            'analysis_type': 'streams_fallback'
        }
        
    except Exception as e:
        logger.error(f"Streams analysis failed: {str(e)}")
        return analyze_basic_activity_patterns(activity_data)


def analyze_basic_activity_patterns(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Basic activity pattern analysis from activity data only"""
    activity_type = activity_data.get('type', 'Activity').lower()
    distance = activity_data.get('distance', 0) / 1000  # km
    duration = activity_data.get('moving_time', 0) / 60  # minutes
    
    # Basic classification based on pace/speed
    classification = 'unknown'
    if activity_type == 'run' and distance > 0 and duration > 0:
        pace_per_km = duration / distance  # minutes per km
        if pace_per_km < 4.0:
            classification = 'speed_work'
        elif pace_per_km < 5.0:
            classification = 'tempo_run'
        elif pace_per_km < 6.0:
            classification = 'moderate_run'
        else:
            classification = 'easy_run'
    
    return {
        'patterns': ['steady_effort'],
        'classification': classification,
        'effort_zones': ['zone2'],
        'intervals_count': 0,
        'analysis_type': 'basic_fallback'
    }


def classify_workout_type(patterns: List[str], intervals_count: int) -> str:
    """Classify workout type based on detected patterns"""
    if 'interval_training' in patterns:
        return 'interval_session'
    elif 'fartlek' in patterns:
        return 'fartlek_run'
    elif intervals_count > 0:
        return 'varied_pace'
    else:
        return 'steady_run'


def extract_module_insights(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract insights from processed modules"""
    insights = {}
    
    for module in modules:
        module_name = module.get('name', 'unknown')
        
        if module_name == 'campus_coach':
            session_matching = module.get('session_matching', {})
            if session_matching.get('match_found', False):
                insights['campus_coach'] = {
                    'session_match': True,
                    'confidence': session_matching.get('confidence', 0.0),
                    'session_type': session_matching.get('session_data', {}).get('session_type', 'unknown'),
                    'compliance_analysis': session_matching.get('compliance_analysis', {}),
                    'reasoning': session_matching.get('reasoning', '')
                }
            else:
                insights['campus_coach'] = {
                    'session_match': False,
                    'reason': session_matching.get('reason', 'No match found')
                }
        
        elif module_name == 'enduraw':
            # Enduraw insights would be extracted here
            insights['enduraw'] = {
                'enhanced_metrics_available': True,
                'note': 'Enduraw processing completed'
            }
    
    return insights


def generate_with_bedrock_enhanced(
    activity_data: Dict[str, Any],
    patterns: Dict[str, Any],
    module_insights: Dict[str, Any]
) -> Dict[str, Any]:
    """Enhanced Bedrock content generation with pattern and module analysis"""
    try:
        # Build enhanced prompt
        prompt = build_enhanced_content_prompt(activity_data, patterns, module_insights)
        
        # Call Bedrock Claude
        bedrock_params = get_bedrock_params()
        response = bedrock.invoke_model(
            modelId=bedrock_params['modelId'],
            body=json.dumps({
                **bedrock_params['body'],
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            })
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        generated_text = response_body['content'][0]['text']
        
        return parse_enhanced_content(generated_text, patterns, module_insights)
        
    except Exception as e:
        logger.error(f"Enhanced Bedrock generation failed: {str(e)}")
        raise


def build_enhanced_content_prompt(
    activity_data: Dict[str, Any],
    patterns: Dict[str, Any],
    module_insights: Dict[str, Any]
) -> str:
    """Build enhanced prompt with pattern analysis and module insights"""
    
    activity_type = activity_data.get('type', 'Activity')
    distance = activity_data.get('distance', 0) / 1000
    duration = activity_data.get('moving_time', 0) / 60
    elevation = activity_data.get('total_elevation_gain', 0)
    
    prompt = f"""Generate an engaging title and description for a Strava {activity_type.lower()} activity.

ACTIVITY DATA:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Elevation: {elevation:.0f} m
- Original name: {activity_data.get('name', 'Untitled')}

PERFORMANCE ANALYSIS:
- Classification: {patterns.get('classification', 'unknown')}
- Effort patterns: {', '.join(patterns.get('patterns', []))}
- Effort zones: {', '.join(patterns.get('effort_zones', []))}
- Intervals detected: {patterns.get('intervals_count', 0)}
- Analysis type: {patterns.get('analysis_type', 'unknown')}
"""
    
    # Add module insights
    if module_insights:
        prompt += "\nMODULE INSIGHTS:\n"
        for module, insights in module_insights.items():
            prompt += f"- {module.title()}: {json.dumps(insights, indent=2)}\n"
    
    prompt += """
REQUIREMENTS:
1. Create a motivational and engaging title (max 50 characters)
2. Write a description that's technical but fun (max 200 words)
3. Use sport-specific terminology
4. Include insights from performance analysis
5. Reference module insights if available
6. Maintain an authentic, personal tone

Return response in JSON format:
{
    "title": "Generated title here",
    "description": "Generated description here",
    "style_elements": ["motivational", "technical"],
    "confidence": 0.85
}"""
    
    return prompt


def parse_enhanced_content(
    generated_text: str, 
    patterns: Dict[str, Any], 
    module_insights: Dict[str, Any]
) -> Dict[str, Any]:
    """Parse enhanced content with additional metadata"""
    try:
        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        
        if json_match:
            content_json = json.loads(json_match.group())
            return {
                'title': content_json.get('title', 'Enhanced Activity')[:50],
                'description': content_json.get('description', 'AI-enhanced description'),
                'style_elements': content_json.get('style_elements', ['ai_generated']),
                'confidence': content_json.get('confidence', 0.8),
                'patterns_detected': patterns.get('patterns', []),
                'modules_used': list(module_insights.keys()),
                'analysis_type': patterns.get('analysis_type', 'unknown')
            }
        else:
            # Fallback parsing
            lines = generated_text.strip().split('\n')
            return {
                'title': (lines[0] if lines else 'Enhanced Activity')[:50],
                'description': '\n'.join(lines[1:]) if len(lines) > 1 else 'AI-enhanced description',
                'style_elements': ['ai_generated'],
                'confidence': 0.7,
                'patterns_detected': patterns.get('patterns', []),
                'modules_used': list(module_insights.keys()),
                'analysis_type': patterns.get('analysis_type', 'unknown')
            }
            
    except Exception as e:
        logger.error(f"Failed to parse enhanced content: {str(e)}")
        return {
            'title': 'Enhanced Activity',
            'description': 'AI-enhanced description',
            'style_elements': ['fallback'],
            'confidence': 0.5,
            'patterns_detected': [],
            'modules_used': [],
            'analysis_type': 'error'
        }



def store_generated_content(activity_id: str, content: Dict[str, Any]) -> None:
    """Store generated content in DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        # Convert float values to Decimal for DynamoDB compatibility
        def convert_floats_to_decimal(obj):
            """Recursively convert float values to Decimal for DynamoDB"""
            if isinstance(obj, float):
                return Decimal(str(obj))
            elif isinstance(obj, dict):
                return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats_to_decimal(item) for item in obj]
            else:
                return obj
        
        # Prepare metadata with Decimal conversion
        metadata = {
            'style_elements': content.get('style_elements', []),
            'confidence': convert_floats_to_decimal(content.get('confidence', 0.0)),
            'modules_used': content.get('modules_used', []),
            'patterns_detected': content.get('patterns_detected', []),
            'analysis_type': content.get('analysis_type', 'unknown'),
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET enhanced_title = :title, enhanced_description = :desc, generation_metadata = :meta",
            ExpressionAttributeValues={
                ':title': content['title'],
                ':desc': content['description'],
                ':meta': metadata
            }
        )
        
        logger.info(f"Stored generated content for activity {activity_id}")
        
    except Exception as e:
        logger.error(f"Failed to store generated content: {str(e)}")
        # Don't raise - content generation succeeded even if storage failed