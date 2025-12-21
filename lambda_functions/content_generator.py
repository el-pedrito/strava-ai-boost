"""
Content Generator Lambda Function

Generates enhanced content using Bedrock AI and AgentCore Memory.
Integrates with Strands Agents for intelligent content generation.
"""

import json
import os
import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')
secretsmanager = boto3.client('secretsmanager')

# Environment variables
ACTIVITIES_TABLE = os.environ['ACTIVITIES_TABLE']
USER_CONFIG_TABLE = os.environ['USER_CONFIG_TABLE']
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
STRAVA_OAUTH_SECRET = os.environ['STRAVA_OAUTH_SECRET']
CAMPUS_COACH_SECRET = os.environ['CAMPUS_COACH_SECRET']


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for content generation
    
    Uses Bedrock AI and AgentCore Memory for personalized content generation
    """
    try:
        activity_id = event.get('activity_id')
        user_id = event.get('user_id')
        activity_data = event.get('activity_data', {})
        
        if not activity_id or not user_id:
            raise ValueError("Missing required parameters: activity_id, user_id")
        
        logger.info(f"Generating content for activity {activity_id}")
        
        # Get user configuration and active modules
        user_config = get_user_configuration(user_id)
        active_modules = get_active_modules(user_config)
        
        # Get streams data if available
        streams_data = event.get('streams_data')
        
        # Generate enhanced content
        enhanced_content = generate_enhanced_content(
            activity_data, 
            streams_data, 
            user_id, 
            active_modules
        )
        
        # Store generated content
        store_generated_content(activity_id, enhanced_content)
        
        return {
            'statusCode': 200,
            'activity_id': activity_id,
            'enhanced_content': enhanced_content
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
        
        return active_modules
        
    except Exception as e:
        logger.error(f"Failed to get active modules: {str(e)}")
        return []


def generate_enhanced_content(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    user_id: str,
    modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate enhanced content using Bedrock AI and AgentCore Memory
    
    TODO: Integrate with Strands Agents and AgentCore Memory
    """
    try:
        # TODO: Initialize Strands Agent with AgentCore Memory
        # content_agent = ContentGenerationAgent()
        # enhanced_content = await content_agent.generate_content(
        #     activity_data, streams_data, user_id, modules
        # )
        
        # Placeholder implementation using Bedrock directly
        enhanced_content = generate_with_bedrock(activity_data, streams_data, modules)
        
        return enhanced_content
        
    except Exception as e:
        logger.error(f"Content generation failed: {str(e)}")
        # Return fallback content
        return {
            'title': f"Enhanced: {activity_data.get('name', 'Activity')}",
            'description': f"AI-enhanced description for {activity_data.get('type', 'activity')}",
            'style_elements': ['fallback'],
            'modules_used': [],
            'error': str(e)
        }


def generate_with_bedrock(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Generate content using Bedrock Claude directly"""
    try:
        # Prepare prompt for Claude
        prompt = build_content_prompt(activity_data, streams_data, modules)
        
        # Call Bedrock Claude
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1000,
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
        
        # Parse generated content (assuming structured format)
        return parse_generated_content(generated_text)
        
    except Exception as e:
        logger.error(f"Bedrock generation failed: {str(e)}")
        raise


def build_content_prompt(
    activity_data: Dict[str, Any],
    streams_data: Optional[Dict[str, Any]],
    modules: List[Dict[str, Any]]
) -> str:
    """Build prompt for Claude content generation"""
    
    activity_type = activity_data.get('type', 'Activity')
    distance = activity_data.get('distance', 0) / 1000  # Convert to km
    duration = activity_data.get('moving_time', 0) / 60  # Convert to minutes
    
    prompt = f"""Generate an engaging title and description for a Strava {activity_type.lower()} activity.

Activity Details:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Original name: {activity_data.get('name', 'Untitled')}
"""
    
    if streams_data:
        prompt += "\n- Detailed performance data available for analysis"
    
    if modules:
        prompt += f"\n- Active modules: {', '.join([m['name'] for m in modules])}"
    
    prompt += """

Requirements:
1. Create a motivational and engaging title (max 50 characters)
2. Write a description that's technical but fun (max 200 words)
3. Use sport-specific terminology
4. Maintain an authentic, personal tone
5. Avoid repetitive expressions

Return the response in this JSON format:
{
    "title": "Generated title here",
    "description": "Generated description here",
    "style_elements": ["motivational", "technical"],
    "confidence": 0.85
}"""
    
    return prompt


def parse_generated_content(generated_text: str) -> Dict[str, Any]:
    """Parse Claude's generated content response"""
    try:
        # Try to extract JSON from the response
        import re
        json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
        
        if json_match:
            content_json = json.loads(json_match.group())
            return {
                'title': content_json.get('title', 'Enhanced Activity'),
                'description': content_json.get('description', 'AI-enhanced description'),
                'style_elements': content_json.get('style_elements', ['ai_generated']),
                'confidence': content_json.get('confidence', 0.8),
                'modules_used': []
            }
        else:
            # Fallback parsing
            lines = generated_text.strip().split('\n')
            return {
                'title': lines[0] if lines else 'Enhanced Activity',
                'description': '\n'.join(lines[1:]) if len(lines) > 1 else 'AI-enhanced description',
                'style_elements': ['ai_generated'],
                'confidence': 0.7,
                'modules_used': []
            }
            
    except Exception as e:
        logger.error(f"Failed to parse generated content: {str(e)}")
        return {
            'title': 'Enhanced Activity',
            'description': 'AI-enhanced description',
            'style_elements': ['fallback'],
            'confidence': 0.5,
            'modules_used': []
        }


def store_generated_content(activity_id: str, content: Dict[str, Any]) -> None:
    """Store generated content in DynamoDB"""
    try:
        table = dynamodb.Table(ACTIVITIES_TABLE)
        
        table.update_item(
            Key={'activity_id': activity_id},
            UpdateExpression="SET enhanced_title = :title, enhanced_description = :desc, generation_metadata = :meta",
            ExpressionAttributeValues={
                ':title': content['title'],
                ':desc': content['description'],
                ':meta': {
                    'style_elements': content.get('style_elements', []),
                    'confidence': content.get('confidence', 0.0),
                    'modules_used': content.get('modules_used', []),
                    'generated_at': context.aws_request_id
                }
            }
        )
        
        logger.info(f"Stored generated content for activity {activity_id}")
        
    except Exception as e:
        logger.error(f"Failed to store generated content: {str(e)}")
        # Don't raise - content generation succeeded even if storage failed