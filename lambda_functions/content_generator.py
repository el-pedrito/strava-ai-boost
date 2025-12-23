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
        import os
        return os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')
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

# Initialize AWS clients with region
REGION = os.environ.get('AWS_REGION', 'eu-west-1')
bedrock = boto3.client('bedrock-runtime', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)

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
    """Get list of active modules for the user using module registry"""
    try:
        from modules import module_registry
        
        modules_config = user_config.get('modules_config', {})
        active_modules = []
        
        # Get available modules from registry
        available_modules = module_registry.get_available_modules()
        
        for module_id in available_modules:
            config = modules_config.get(module_id, {})
            if config.get('enabled', False):
                # Get module info from registry
                module_info = module_registry.get_module_info(module_id)
                if module_info:
                    active_modules.append({
                        'name': module_id,
                        'config': config,
                        'enabled': True,
                        'info': module_info
                    })
        
        logger.info(f"Found {len(active_modules)} active modules from registry")
        return active_modules
        
    except ImportError:
        logger.warning("Module registry not available, using fallback")
        # Fallback to original implementation
        modules_config = user_config.get('modules_config', {})
        active_modules = []
        
        for module_id, config in modules_config.items():
            if config.get('enabled', False):
                active_modules.append({
                    'name': module_id,
                    'config': config,
                    'enabled': True
                })
        
        logger.info(f"Found {len(active_modules)} active modules (fallback)")
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
    Apply module-specific processing using module registry
    
    Enhances modules with additional data (e.g., Campus Coach session matching)
    """
    enhanced_modules = []
    
    try:
        from modules import module_registry, ModuleConfig
        
        for module in modules:
            try:
                module_id = module['name']
                
                # Create module instance from registry
                config_data = module.get('config', {})
                module_config = ModuleConfig(
                    module_id=module_id,
                    enabled=module.get('enabled', False),
                    credentials=config_data.get('credentials'),
                    settings=config_data.get('settings', {})
                )
                
                module_instance = module_registry.create_module_instance(module_id, module_config)
                
                if module_instance:
                    # Process with module instance
                    enhanced_module = apply_module_instance_processing(
                        activity_data, streams_data, user_id, module, module_instance
                    )
                    enhanced_modules.append(enhanced_module)
                else:
                    # Fallback to legacy processing
                    enhanced_module = apply_legacy_module_processing(
                        activity_data, streams_data, user_id, module
                    )
                    enhanced_modules.append(enhanced_module)
                    
            except Exception as e:
                logger.error(f"Module {module.get('name', 'unknown')} processing failed: {str(e)}")
                # Include module with error info
                module_with_error = module.copy()
                module_with_error['processing_error'] = str(e)
                enhanced_modules.append(module_with_error)
    
    except ImportError:
        logger.warning("Module registry not available, using legacy processing")
        # Fallback to legacy processing for all modules
        for module in modules:
            try:
                enhanced_module = apply_legacy_module_processing(
                    activity_data, streams_data, user_id, module
                )
                enhanced_modules.append(enhanced_module)
            except Exception as e:
                logger.error(f"Legacy module {module.get('name', 'unknown')} processing failed: {str(e)}")
                module_with_error = module.copy()
                module_with_error['processing_error'] = str(e)
                enhanced_modules.append(module_with_error)
    
    return enhanced_modules


def apply_module_instance_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    module: Dict[str, Any],
    module_instance
) -> Dict[str, Any]:
    """Apply processing using module registry instance"""
    try:
        # Use asyncio to run the async module method
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            insight = loop.run_until_complete(
                module_instance.analyze_activity_with_timeout(activity_data, streams_data)
            )
            
            # Enhance module with insight results
            enhanced_module = module.copy()
            enhanced_module['insight'] = {
                'module_id': insight.module_id,
                'insights': insight.insights,
                'confidence': insight.confidence,
                'metadata': insight.metadata,
                'processing_time_ms': insight.processing_time_ms,
                'error_message': insight.error_message
            }
            
            logger.info(f"Module {module['name']} processed with confidence: {insight.confidence}")
            return enhanced_module
            
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Module instance processing error: {str(e)}")
        enhanced_module = module.copy()
        enhanced_module['processing_error'] = str(e)
        return enhanced_module


def apply_legacy_module_processing(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    module: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply legacy module processing for backward compatibility"""
    try:
        module_name = module['name']
        
        if module_name == 'campus_coach' and module.get('enabled', False):
            # Apply Campus Coach session matching
            enhanced_module = apply_campus_coach_processing(
                activity_data, user_id, module
            )
            return enhanced_module
            
        elif module_name == 'enduraw' and module.get('enabled', False):
            # Enduraw processing (wait logic handled in webhook processor)
            return module
            
        else:
            # Other modules - pass through
            return module
            
    except Exception as e:
        logger.error(f"Legacy module {module.get('name', 'unknown')} processing failed: {str(e)}")
        module_with_error = module.copy()
        module_with_error['processing_error'] = str(e)
        return module_with_error


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
    
    Uses actual AgentCore agent invocation via Bedrock Agent Runtime
    """
    try:
        logger.info("Generating content with AgentCore Content Generation Agent...")
        
        # Use Bedrock Agent Runtime to invoke AgentCore Content Generation Agent
        bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
        
        # Create session ID for this invocation
        session_id = f"content-gen-{datetime.utcnow().timestamp()}"
        
        # Prepare input for AgentCore Content Generation Agent
        agent_input = {
            'action': 'generate_content',
            'activity_data': activity_data,
            'streams_data': streams_data,
            'user_id': user_id,
            'modules': modules,
            'use_memory': True,
            'personalization': True
        }
        
        # Get agent name from environment
        agent_name = os.environ.get('CONTENT_GENERATION_AGENT_NAME', 'contentgen')
        
        logger.info(f"Invoking AgentCore Content Generation Agent: {agent_name}")
        
        # Invoke AgentCore Content Generation Agent
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_name,
            agentAliasId='TSTALIASID',  # Test alias ID for AgentCore
            sessionId=session_id,
            inputText=json.dumps(agent_input)
        )
        
        # Process streaming response
        completion = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    completion += chunk['bytes'].decode('utf-8')
        
        logger.info(f"AgentCore Content Generation Agent response length: {len(completion)}")
        
        # Parse agent response
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', completion, re.DOTALL)
            
            if json_match:
                agent_response = json.loads(json_match.group())
                
                # Validate response structure
                if 'title' in agent_response and 'description' in agent_response:
                    enhanced_content = {
                        'title': agent_response.get('title', 'Enhanced Activity')[:50],
                        'description': agent_response.get('description', 'AI-enhanced description'),
                        'style_elements': agent_response.get('style_elements', ['ai_generated']),
                        'confidence': agent_response.get('confidence', 0.8),
                        'modules_used': [m['name'] for m in modules],
                        'patterns_detected': agent_response.get('patterns_detected', []),
                        'analysis_type': 'agentcore_memory',
                        'memory_used': agent_response.get('memory_used', False),
                        'expressions_avoided': agent_response.get('expressions_avoided', [])
                    }
                    
                    logger.info(f"Content generated with confidence: {enhanced_content.get('confidence', 0.0)}")
                    return enhanced_content
                else:
                    logger.warning("Invalid response structure from AgentCore agent")
                    return generate_enhanced_content_fallback(
                        activity_data, streams_data, user_id, modules
                    )
            else:
                logger.warning("Could not parse JSON from AgentCore agent response")
                return generate_enhanced_content_fallback(
                    activity_data, streams_data, user_id, modules
                )
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AgentCore agent response: {str(e)}")
            return generate_enhanced_content_fallback(
                activity_data, streams_data, user_id, modules
            )
            
    except Exception as e:
        logger.error(f"AgentCore Content Generation Agent invocation failed: {str(e)}")
        
        # Check if this is a cold start or availability issue
        if "timeout" in str(e).lower() or "unavailable" in str(e).lower():
            logger.warning("Possible AgentCore agent cold start or availability issue")
        
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
            # Extract Campus Coach insights
            if 'insight' in module:
                insight_data = module['insight']
                campus_insights = insight_data.get('insights', {})
                
                if campus_insights.get('session_matched', False):
                    insights['campus_coach'] = {
                        'session_match': True,
                        'confidence': insight_data.get('confidence', 0.0),
                        'session_type': campus_insights.get('planned_session', {}).get('session_type', 'unknown'),
                        'performance_analysis': campus_insights.get('performance_analysis', {}),
                        'match_reasons': campus_insights.get('match_reasons', [])
                    }
                else:
                    insights['campus_coach'] = {
                        'session_match': False,
                        'reason': campus_insights.get('match_reasons', ['No match found'])[0] if campus_insights.get('match_reasons') else 'No match found'
                    }
            else:
                # Legacy session matching format
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
            # Extract Enduraw insights
            if 'insight' in module:
                insight_data = module['insight']
                enduraw_insights = insight_data.get('insights', {})
                
                if enduraw_insights.get('enduraw_available', False):
                    insights['enduraw'] = {
                        'enhanced_metrics_available': True,
                        'weather_analysis': enduraw_insights.get('weather_analysis', {}),
                        'enhanced_metrics': enduraw_insights.get('enhanced_metrics', {}),
                        'performance_insights': enduraw_insights.get('performance_insights', {}),
                        'recommendations': enduraw_insights.get('recommendations', []),
                        'processing_time': insight_data.get('metadata', {}).get('enduraw_processing_time')
                    }
                else:
                    insights['enduraw'] = {
                        'enhanced_metrics_available': False,
                        'reason': enduraw_insights.get('error', 'Processing timeout or unavailable')
                    }
            else:
                # Legacy or simple format
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
    
    # Add module insights with enhanced formatting
    if module_insights:
        prompt += "\nMODULE INSIGHTS:\n"
        
        # Campus Coach insights
        if 'campus_coach' in module_insights:
            cc_insights = module_insights['campus_coach']
            if cc_insights.get('session_match', False):
                prompt += f"- Campus Coach: Matched planned {cc_insights.get('session_type', 'session')} "
                prompt += f"(confidence: {cc_insights.get('confidence', 0):.1f})\n"
                if cc_insights.get('performance_analysis'):
                    prompt += f"  Performance: {cc_insights['performance_analysis']}\n"
            else:
                prompt += f"- Campus Coach: No session match ({cc_insights.get('reason', 'unknown')})\n"
        
        # Enduraw insights
        if 'enduraw' in module_insights:
            enduraw_insights = module_insights['enduraw']
            if enduraw_insights.get('enhanced_metrics_available', False):
                prompt += "- Enduraw: Enhanced analytics available\n"
                
                # Weather analysis
                weather = enduraw_insights.get('weather_analysis', {})
                if weather:
                    impact = weather.get('impact_assessment', 'neutral')
                    prompt += f"  Weather impact: {impact}\n"
                
                # Enhanced metrics
                metrics = enduraw_insights.get('enhanced_metrics', {})
                if metrics.get('pace_without_wind'):
                    pace_data = metrics['pace_without_wind']
                    if isinstance(pace_data, dict) and pace_data.get('wind_adjustment_seconds', 0) > 2:
                        prompt += f"  Wind adjustment: +{pace_data['wind_adjustment_seconds']:.0f}s/km\n"
                
                if metrics.get('elevation_cost'):
                    elev_data = metrics['elevation_cost']
                    if isinstance(elev_data, dict):
                        efficiency = elev_data.get('elevation_efficiency', 0)
                        prompt += f"  Elevation efficiency: {efficiency:.1%}\n"
                
                # Recommendations
                recommendations = enduraw_insights.get('recommendations', [])
                if recommendations:
                    prompt += f"  Key insight: {recommendations[0]}\n"
            else:
                prompt += f"- Enduraw: {enduraw_insights.get('reason', 'Not available')}\n"
    
    prompt += """
REQUIREMENTS:
1. Create a motivational and engaging title (max 50 characters)
2. Write a description that's technical but fun (max 200 words)
3. Use sport-specific terminology
4. Include insights from performance analysis and modules
5. Reference weather/environmental factors if available from Enduraw
6. Mention training session context if Campus Coach match found
7. Maintain an authentic, personal tone that varies from previous activities

Return response in JSON format:
{
    "title": "Generated title here",
    "description": "Generated description here",
    "style_elements": ["motivational", "technical", "weather_aware"],
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