"""
Content Generation Agent for Strava AI Boost

Strands Agent that uses AgentCore Memory for personalized content generation.
Integrates with Amazon Bedrock Claude for intelligent activity analysis.
"""

from typing import Dict, Any, List, Optional
import json
import logging
import boto3
import asyncio
from datetime import datetime, timezone
import hashlib
import re
import sys
import os

# Add config directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

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

logger = logging.getLogger(__name__)


class ContentGenerationAgent:
    """
    Strands Agent for generating personalized Strava activity content
    
    Uses AgentCore Memory for:
    - Personal style learning and storage
    - Expression tracking to avoid repetition
    - Performance pattern memory for context
    """
    
    def __init__(self, region: str = 'eu-west-1'):
        """
        Initialize Content Generation Agent with AWS clients
        
        Args:
            region: AWS region for services
        """
        self.region = region
        self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # AgentCore Memory simulation using DynamoDB
        # In production, this would be replaced with actual AgentCore Memory client
        self.memory_table_name = 'strava-ai-boost-user-memory'
        
        logger.info("ContentGenerationAgent initialized")
    
    async def generate_content(
        self, 
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]],
        user_id: str,
        modules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate enhanced content for Strava activity
        
        Args:
            activity_data: Complete Strava activity data (67+ fields)
            streams_data: Strava streams data (velocity, heartrate, etc.)
            user_id: User identifier for memory lookup
            modules: Active modules (Campus Coach, Enduraw, etc.)
            
        Returns:
            Enhanced content with title and description
        """
        try:
            logger.info(f"Generating content for user {user_id}, activity {activity_data.get('id')}")
            
            # 1. Retrieve user's personal style from memory
            personal_style = await self.get_user_style(user_id)
            previous_expressions = await self.get_used_expressions(user_id)
            
            # 2. Analyze activity patterns using Bedrock
            patterns = await self.analyze_patterns(streams_data, activity_data)
            
            # 3. Apply active modules (Campus Coach matching, etc.)
            module_insights = await self.apply_modules(activity_data, modules)
            
            # 4. Generate personalized content avoiding repetition
            content = await self.bedrock_generate(
                activity_data,
                patterns, 
                module_insights, 
                personal_style,
                previous_expressions
            )
            
            # 5. Store new expressions and style updates in memory
            await self.store_generated_content(user_id, content)
            await self.update_user_style(user_id, content.get('style_elements', []))
            
            logger.info(f"Generated content for activity {activity_data.get('id')}")
            return content
            
        except Exception as e:
            logger.error(f"Content generation failed: {str(e)}")
            # Return fallback content instead of raising
            return {
                'title': f"Enhanced: {activity_data.get('name', 'Activity')}",
                'description': f"AI-enhanced description for {activity_data.get('type', 'activity')}",
                'style_elements': ['fallback'],
                'modules_used': [module['name'] for module in modules],
                'confidence': 0.5,
                'error': str(e)
            }
    
    
    async def analyze_patterns(
        self, 
        streams_data: Optional[Dict[str, Any]], 
        activity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze activity patterns using Bedrock AI
        
        Detects:
        - Effort patterns and intervals
        - Heart rate zones
        - Workout classification
        """
        try:
            if not streams_data:
                # Basic analysis from activity data only
                return await self.analyze_basic_patterns(activity_data)
            
            # Prepare streams analysis prompt for Claude
            analysis_prompt = self.build_pattern_analysis_prompt(streams_data, activity_data)
            
            # Call Bedrock Claude
            bedrock_params = get_bedrock_params()
            response = self.bedrock.invoke_model(
                modelId=bedrock_params['modelId'],
                body=json.dumps({
                    **bedrock_params['body'],
                    'messages': [
                        {
                            'role': 'user',
                            'content': analysis_prompt
                        }
                    ]
                })
            )
            
            # Parse Claude's analysis
            response_body = json.loads(response['body'].read())
            analysis_text = response_body['content'][0]['text']
            
            return self.parse_pattern_analysis(analysis_text)
            
        except Exception as e:
            logger.error(f"Pattern analysis failed: {str(e)}")
            return await self.analyze_basic_patterns(activity_data)
    
    async def analyze_basic_patterns(self, activity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback analysis using basic activity data"""
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
            'analysis_type': 'basic'
        }
    
    def build_pattern_analysis_prompt(
        self, 
        streams_data: Dict[str, Any], 
        activity_data: Dict[str, Any]
    ) -> str:
        """Build prompt for Claude pattern analysis"""
        
        activity_type = activity_data.get('type', 'Activity')
        distance = activity_data.get('distance', 0) / 1000
        duration = activity_data.get('moving_time', 0) / 60
        
        # Sample streams data for analysis (first 10 points)
        velocity_sample = streams_data.get('velocity_smooth', [])[:10]
        heartrate_sample = streams_data.get('heartrate', [])[:10]
        
        prompt = f"""Analyze this {activity_type.lower()} activity for effort patterns and workout classification.

Activity Overview:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes

Streams Data Sample (first 10 points):
- Velocity: {velocity_sample}
- Heart Rate: {heartrate_sample}

Please analyze and return a JSON response with:
1. Effort patterns detected (steady, intervals, fartlek, etc.)
2. Workout classification (easy, tempo, threshold, speed_work, etc.)
3. Estimated effort zones (zone1, zone2, zone3, zone4, zone5)
4. Number of intervals detected
5. Key insights about the workout structure

Format:
{{
    "patterns": ["pattern1", "pattern2"],
    "classification": "workout_type",
    "effort_zones": ["zone1", "zone2"],
    "intervals_count": 0,
    "insights": ["insight1", "insight2"]
}}"""
        
        return prompt
    
    def parse_pattern_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """Parse Claude's pattern analysis response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            
            if json_match:
                analysis_json = json.loads(json_match.group())
                return {
                    'patterns': analysis_json.get('patterns', ['steady_effort']),
                    'classification': analysis_json.get('classification', 'moderate'),
                    'effort_zones': analysis_json.get('effort_zones', ['zone2']),
                    'intervals_count': analysis_json.get('intervals_count', 0),
                    'insights': analysis_json.get('insights', []),
                    'analysis_type': 'ai_enhanced'
                }
            else:
                # Fallback parsing
                return {
                    'patterns': ['steady_effort'],
                    'classification': 'moderate',
                    'effort_zones': ['zone2'],
                    'intervals_count': 0,
                    'insights': [analysis_text[:100] + '...'],
                    'analysis_type': 'text_parsed'
                }
                
        except Exception as e:
            logger.error(f"Failed to parse pattern analysis: {str(e)}")
            return {
                'patterns': ['unknown'],
                'classification': 'unknown',
                'effort_zones': ['zone2'],
                'intervals_count': 0,
                'insights': [],
                'analysis_type': 'error'
            }
    
    
    async def apply_modules(
        self, 
        activity_data: Dict[str, Any], 
        modules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Apply active module analysis (Campus Coach, Enduraw, etc.)
        """
        insights = {}
        
        for module in modules:
            try:
                if module['name'] == 'campus_coach' and module.get('enabled', False):
                    insights['campus_coach'] = await self.apply_campus_coach_module(
                        activity_data, module.get('config', {})
                    )
                elif module['name'] == 'enduraw' and module.get('enabled', False):
                    insights['enduraw'] = await self.apply_enduraw_module(
                        activity_data, module.get('config', {})
                    )
            except Exception as e:
                logger.error(f"Module {module['name']} analysis failed: {str(e)}")
                insights[module['name']] = {'error': str(e)}
        
        return insights
    
    async def apply_campus_coach_module(
        self, 
        activity_data: Dict[str, Any], 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply Campus Coach session matching analysis"""
        try:
            # TODO: Integrate with actual Campus Coach Browser Tool agent
            # For now, simulate session matching logic
            
            activity_type = activity_data.get('type', '').lower()
            distance = activity_data.get('distance', 0) / 1000
            duration = activity_data.get('moving_time', 0) / 60
            
            # Simulate session matching based on activity characteristics
            if activity_type == 'run' and distance > 5:
                return {
                    'session_match': True,
                    'confidence': 0.85,
                    'planned_vs_actual': 'good_execution',
                    'session_type': 'endurance_run',
                    'compliance_score': 0.9,
                    'notes': f'Matched {distance:.1f}km endurance session'
                }
            else:
                return {
                    'session_match': False,
                    'confidence': 0.3,
                    'planned_vs_actual': 'no_match',
                    'session_type': 'unknown',
                    'compliance_score': 0.0,
                    'notes': 'No matching planned session found'
                }
                
        except Exception as e:
            logger.error(f"Campus Coach module error: {str(e)}")
            return {'error': str(e)}
    
    async def apply_enduraw_module(
        self, 
        activity_data: Dict[str, Any], 
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply Enduraw enhanced metrics analysis"""
        try:
            # TODO: Integrate with actual Enduraw API
            # For now, simulate enhanced metrics
            
            distance = activity_data.get('distance', 0) / 1000
            duration = activity_data.get('moving_time', 0) / 60
            
            if distance > 0 and duration > 0:
                base_pace = duration / distance  # min/km
                
                return {
                    'pace_without_wind': f"{base_pace - 0.1:.1f} min/km",
                    'weather_impact': 'minimal_headwind',
                    'elevation_cost': f"{0.05 * distance:.0f}s/km",
                    'efficiency_score': 0.87,
                    'enhanced_metrics_available': True
                }
            else:
                return {
                    'enhanced_metrics_available': False,
                    'reason': 'insufficient_data'
                }
                
        except Exception as e:
            logger.error(f"Enduraw module error: {str(e)}")
            return {'error': str(e)}
    
    async def bedrock_generate(
        self,
        activity_data: Dict[str, Any],
        patterns: Dict[str, Any],
        module_insights: Dict[str, Any],
        personal_style: Dict[str, Any],
        previous_expressions: List[str]
    ) -> Dict[str, Any]:
        """Generate personalized content using Bedrock Claude"""
        try:
            # Build comprehensive prompt
            prompt = self.build_content_generation_prompt(
                activity_data, patterns, module_insights, personal_style, previous_expressions
            )
            
            # Call Bedrock Claude
            bedrock_params = get_bedrock_params()
            response = self.bedrock.invoke_model(
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
            
            return self.parse_generated_content(generated_text)
            
        except Exception as e:
            logger.error(f"Bedrock content generation failed: {str(e)}")
            raise
    
    def build_content_generation_prompt(
        self,
        activity_data: Dict[str, Any],
        patterns: Dict[str, Any],
        module_insights: Dict[str, Any],
        personal_style: Dict[str, Any],
        previous_expressions: List[str]
    ) -> str:
        """Build comprehensive prompt for content generation"""
        
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
"""
        
        # Add module insights
        if module_insights:
            prompt += "\nMODULE INSIGHTS:\n"
            for module, insights in module_insights.items():
                if 'error' not in insights:
                    prompt += f"- {module.title()}: {json.dumps(insights, indent=2)}\n"
        
        # Add personalization context
        user_tone = personal_style.get('tone', 'motivational')
        user_style = personal_style.get('style_elements', ['technical', 'fun'])
        
        prompt += f"""
PERSONALIZATION:
- Preferred tone: {user_tone}
- Style elements: {', '.join(user_style)}
- Avoid these expressions: {', '.join(previous_expressions[-10:])}  # Last 10 to avoid

REQUIREMENTS:
1. Create a motivational and engaging title (max 50 characters)
2. Write a description that's {user_tone} and technical (max 200 words)
3. Use sport-specific terminology for {activity_type.lower()}
4. Maintain an authentic, personal tone
5. Avoid the listed previous expressions
6. Include insights from performance analysis
7. Reference module insights if available

Return response in JSON format:
{{
    "title": "Generated title here",
    "description": "Generated description here",
    "style_elements": ["element1", "element2"],
    "confidence": 0.85,
    "expressions_used": ["new_expression1", "new_expression2"]
}}"""
        
        return prompt
    
    def parse_generated_content(self, generated_text: str) -> Dict[str, Any]:
        """Parse Claude's generated content response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
            
            if json_match:
                content_json = json.loads(json_match.group())
                return {
                    'title': content_json.get('title', 'Enhanced Activity')[:50],  # Enforce limit
                    'description': content_json.get('description', 'AI-enhanced description'),
                    'style_elements': content_json.get('style_elements', ['ai_generated']),
                    'confidence': content_json.get('confidence', 0.8),
                    'expressions_used': content_json.get('expressions_used', []),
                    'modules_used': []
                }
            else:
                # Fallback parsing
                lines = generated_text.strip().split('\n')
                return {
                    'title': (lines[0] if lines else 'Enhanced Activity')[:50],
                    'description': '\n'.join(lines[1:]) if len(lines) > 1 else 'AI-enhanced description',
                    'style_elements': ['ai_generated'],
                    'confidence': 0.7,
                    'expressions_used': [],
                    'modules_used': []
                }
                
        except Exception as e:
            logger.error(f"Failed to parse generated content: {str(e)}")
            return {
                'title': 'Enhanced Activity',
                'description': 'AI-enhanced description',
                'style_elements': ['fallback'],
                'confidence': 0.5,
                'expressions_used': [],
                'modules_used': []
            }
    
    # AgentCore Memory Simulation Methods
    # In production, these would be replaced with actual AgentCore Memory client calls
    
    async def get_user_style(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve user's personal style from AgentCore Memory
        
        Simulated using DynamoDB until AgentCore Memory is integrated
        """
        try:
            # TODO: Replace with AgentCore Memory client
            # memory_client = AgentCoreMemoryClient()
            # return await memory_client.get_user_style(user_id)
            
            # Simulation using DynamoDB
            table = self.dynamodb.Table(self.memory_table_name)
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'memory_type': 'personal_style'
                }
            )
            
            if 'Item' in response:
                return response['Item'].get('style_data', {})
            else:
                # Default style for new users
                return {
                    'tone': 'motivational',
                    'style_elements': ['technical', 'fun'],
                    'preferred_length': 'medium',
                    'sport_focus': 'running'
                }
                
        except Exception as e:
            logger.error(f"Failed to get user style: {str(e)}")
            return {
                'tone': 'motivational',
                'style_elements': ['technical'],
                'preferred_length': 'medium',
                'sport_focus': 'general'
            }
    
    async def get_used_expressions(self, user_id: str) -> List[str]:
        """
        Retrieve recently used expressions to avoid repetition
        
        Simulated using DynamoDB until AgentCore Memory is integrated
        """
        try:
            # TODO: Replace with AgentCore Memory client
            # memory_client = AgentCoreMemoryClient()
            # return await memory_client.get_used_expressions(user_id, limit=20)
            
            # Simulation using DynamoDB
            table = self.dynamodb.Table(self.memory_table_name)
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'memory_type': 'used_expressions'
                }
            )
            
            if 'Item' in response:
                expressions = response['Item'].get('expressions', [])
                # Return last 20 expressions
                return expressions[-20:] if len(expressions) > 20 else expressions
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get used expressions: {str(e)}")
            return []
    
    async def store_generated_content(self, user_id: str, content: Dict[str, Any]) -> None:
        """
        Store generated content and expressions in AgentCore Memory
        
        Simulated using DynamoDB until AgentCore Memory is integrated
        """
        try:
            # TODO: Replace with AgentCore Memory client
            # memory_client = AgentCoreMemoryClient()
            # await memory_client.store_generated_content(user_id, content)
            
            # Store expressions used in this generation
            expressions_used = content.get('expressions_used', [])
            if expressions_used:
                await self.update_used_expressions(user_id, expressions_used)
            
            # Store generation metadata
            table = self.dynamodb.Table(self.memory_table_name)
            
            # Create content hash for deduplication
            content_hash = hashlib.md5(
                f"{content.get('title', '')}{content.get('description', '')}".encode()
            ).hexdigest()
            
            table.put_item(
                Item={
                    'user_id': user_id,
                    'memory_type': 'generated_content',
                    'content_hash': content_hash,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'content_data': {
                        'title': content.get('title', ''),
                        'description': content.get('description', ''),
                        'style_elements': content.get('style_elements', []),
                        'confidence': content.get('confidence', 0.0),
                        'expressions_used': expressions_used
                    }
                }
            )
            
            logger.info(f"Stored generated content for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to store generated content: {str(e)}")
            # Don't raise - content generation succeeded even if storage failed
    
    async def update_used_expressions(self, user_id: str, new_expressions: List[str]) -> None:
        """Update the list of used expressions for the user"""
        try:
            table = self.dynamodb.Table(self.memory_table_name)
            
            # Get current expressions
            response = table.get_item(
                Key={
                    'user_id': user_id,
                    'memory_type': 'used_expressions'
                }
            )
            
            current_expressions = []
            if 'Item' in response:
                current_expressions = response['Item'].get('expressions', [])
            
            # Add new expressions
            updated_expressions = current_expressions + new_expressions
            
            # Keep only last 50 expressions to avoid unlimited growth
            if len(updated_expressions) > 50:
                updated_expressions = updated_expressions[-50:]
            
            # Store updated list
            table.put_item(
                Item={
                    'user_id': user_id,
                    'memory_type': 'used_expressions',
                    'expressions': updated_expressions,
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to update used expressions: {str(e)}")
    
    async def update_user_style(self, user_id: str, style_elements: List[str]) -> None:
        """
        Update user's personal style based on successful generations
        
        Simulated using DynamoDB until AgentCore Memory is integrated
        """
        try:
            # TODO: Replace with AgentCore Memory client
            # memory_client = AgentCoreMemoryClient()
            # await memory_client.update_user_style(user_id, style_elements)
            
            # Get current style
            current_style = await self.get_user_style(user_id)
            
            # Update style elements (simple frequency-based learning)
            current_elements = current_style.get('style_elements', [])
            
            # Add new elements that aren't already present
            for element in style_elements:
                if element not in current_elements and element not in ['fallback', 'error']:
                    current_elements.append(element)
            
            # Keep only last 10 style elements to avoid unlimited growth
            if len(current_elements) > 10:
                current_elements = current_elements[-10:]
            
            # Update style data
            updated_style = {
                **current_style,
                'style_elements': current_elements,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
            # Store updated style
            table = self.dynamodb.Table(self.memory_table_name)
            table.put_item(
                Item={
                    'user_id': user_id,
                    'memory_type': 'personal_style',
                    'style_data': updated_style,
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
            )
            
            logger.info(f"Updated user style for {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to update user style: {str(e)}")


# Utility function for Lambda integration
def create_content_agent(region: str = 'eu-west-1') -> ContentGenerationAgent:
    """
    Factory function to create ContentGenerationAgent instance
    
    Args:
        region: AWS region for services
        
    Returns:
        Configured ContentGenerationAgent instance
    """
    return ContentGenerationAgent(region=region)


# Async wrapper for Lambda compatibility
def run_content_generation(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]],
    region: str = 'eu-west-1'
) -> Dict[str, Any]:
    """
    Synchronous wrapper for content generation (Lambda compatibility)
    
    Args:
        activity_data: Complete Strava activity data
        streams_data: Strava streams data (optional)
        user_id: User identifier
        modules: Active modules list
        region: AWS region
        
    Returns:
        Enhanced content dictionary
    """
    agent = create_content_agent(region)
    
    # Run async function in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            agent.generate_content(activity_data, streams_data, user_id, modules)
        )
        return result
    finally:
        loop.close()