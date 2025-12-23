"""
Campus Coach Invoker Lambda Function

Invokes AgentCore Browser Tool agent for Campus Coach session extraction.
Handles retry logic for cold start issues and session data storage.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with region
REGION = os.environ.get('AWS_REGION', 'eu-west-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
secretsmanager = boto3.client('secretsmanager', region_name=REGION)
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=REGION)

# Environment variables
COACHING_SESSIONS_TABLE = os.environ['COACHING_SESSIONS_TABLE']
CAMPUS_COACH_SECRET = os.environ['CAMPUS_COACH_SECRET']

# AgentCore configuration
CAMPUS_COACH_AGENT_ID = os.environ.get('CAMPUS_COACH_AGENT_ID', 'campus-coach-scraper')
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for invoking Campus Coach AgentCore Browser Tool agent
    
    Handles retry logic for cold start issues and stores extracted sessions
    """
    try:
        action = event.get('action', 'extract_sessions')
        user_id = event.get('user_id')
        
        logger.info(f"Campus Coach invoker action: {action}")
        
        if action == 'extract_sessions':
            return extract_coaching_sessions(user_id)
        elif action == 'get_sessions':
            return get_stored_sessions(user_id)
        else:
            raise ValueError(f"Unknown action: {action}")
        
    except Exception as e:
        logger.error(f"Campus Coach invoker error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'action': event.get('action')
        }


def extract_coaching_sessions(user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract coaching sessions from Campus Coach using AgentCore Browser Tool
    
    Implements retry logic for cold start issues (30% first-try success rate)
    """
    try:
        # Get Campus Coach credentials
        credentials = get_campus_coach_credentials()
        
        # Prepare input for AgentCore agent
        agent_input = {
            'credentials': credentials,
            'action': 'extract_sessions',
            'user_id': user_id or 'default_user'
        }
        
        # Invoke AgentCore agent with retry logic
        sessions_data = invoke_agent_with_retry(agent_input)
        
        if not sessions_data:
            raise Exception("Failed to extract sessions after retries")
        
        # Store extracted sessions in DynamoDB
        stored_count = store_coaching_sessions(sessions_data)
        
        return {
            'statusCode': 200,
            'sessions_extracted': len(sessions_data),
            'sessions_stored': stored_count,
            'extraction_timestamp': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session extraction failed: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'sessions_extracted': 0
        }


def get_campus_coach_credentials() -> Dict[str, str]:
    """Get Campus Coach credentials from Secrets Manager"""
    try:
        response = secretsmanager.get_secret_value(SecretId=CAMPUS_COACH_SECRET)
        secrets = json.loads(response['SecretString'])
        
        username = secrets.get('username')
        password = secrets.get('password')
        
        if not username or not password:
            raise ValueError("Campus Coach credentials not found in secrets")
        
        return {
            'username': username,
            'password': password
        }
        
    except Exception as e:
        logger.error(f"Failed to get Campus Coach credentials: {str(e)}")
        raise


def invoke_agent_with_retry(agent_input: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Invoke AgentCore Browser Tool agent with retry logic
    
    Known issue: Cold start problem with ~30% first-try success rate
    Implements exponential backoff retry strategy
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"AgentCore invocation attempt {attempt}/{MAX_RETRIES}")
            
            # Invoke AgentCore Browser Tool agent
            sessions_data = invoke_agentcore_agent(agent_input)
            
            if sessions_data:
                logger.info(f"Successfully extracted {len(sessions_data)} sessions on attempt {attempt}")
                return sessions_data
            else:
                logger.warning(f"No sessions returned on attempt {attempt}")
                
        except Exception as e:
            logger.error(f"AgentCore invocation attempt {attempt} failed: {str(e)}")
            
            if attempt < MAX_RETRIES:
                # Exponential backoff
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                logger.error("All retry attempts exhausted")
                return None
    
    return None


def invoke_agentcore_agent(agent_input: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Invoke AgentCore Browser Tool agent using AWS Bedrock Agent Runtime
    
    Integrates with actual AgentCore Browser Tool for Campus Coach session extraction
    """
    try:
        # Get agent configuration from environment
        agent_name = os.environ.get('CAMPUS_COACH_AGENT_NAME', 'campuscoach')
        
        # Create session ID for this invocation
        session_id = f"campus-coach-{datetime.utcnow().timestamp()}"
        
        logger.info(f"Invoking AgentCore agent: {agent_name} with session: {session_id}")
        
        # Prepare input for AgentCore Browser Tool agent
        agent_prompt = json.dumps({
            'action': 'extract_sessions',
            'credentials': agent_input.get('credentials', {}),
            'user_id': agent_input.get('user_id', 'default_user'),
            'target_weeks': 2,  # Extract current and next week
            'retry_on_failure': True
        })
        
        # Invoke AgentCore agent via Bedrock Agent Runtime
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_name,
            agentAliasId='TSTALIASID',  # Test alias ID for AgentCore
            sessionId=session_id,
            inputText=agent_prompt
        )
        
        # Process streaming response
        completion = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    completion += chunk['bytes'].decode('utf-8')
        
        logger.info(f"AgentCore agent response length: {len(completion)}")
        
        # Parse agent response
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', completion, re.DOTALL)
            
            if json_match:
                agent_response = json.loads(json_match.group())
                
                # Extract sessions from agent response
                if agent_response.get('success', False):
                    sessions = agent_response.get('sessions', [])
                    logger.info(f"Successfully extracted {len(sessions)} sessions from AgentCore agent")
                    return sessions
                else:
                    error_msg = agent_response.get('error', 'Unknown agent error')
                    logger.error(f"AgentCore agent reported error: {error_msg}")
                    return None
            else:
                # Fallback: try to parse as plain text response
                logger.warning("Could not parse JSON from agent response, using fallback parsing")
                return parse_agent_text_response(completion)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse agent response as JSON: {str(e)}")
            return parse_agent_text_response(completion)
        
    except Exception as e:
        logger.error(f"AgentCore agent invocation failed: {str(e)}")
        
        # Check if this is a cold start issue (common with Browser Tool agents)
        if "timeout" in str(e).lower() or "unavailable" in str(e).lower():
            logger.warning("Possible cold start issue detected - this is expected on first invocation")
        
        raise


def parse_agent_text_response(response_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fallback parser for agent text responses when JSON parsing fails
    
    Attempts to extract session information from plain text response
    """
    try:
        sessions = []
        
        # Look for session patterns in text
        # This is a simplified parser - in production, the agent should return structured JSON
        lines = response_text.split('\n')
        
        current_session = {}
        for line in lines:
            line = line.strip()
            
            # Look for session indicators
            if 'session' in line.lower() and ':' in line:
                if current_session:
                    sessions.append(current_session)
                    current_session = {}
                
                # Extract session ID/name
                session_id = line.split(':')[1].strip()
                current_session['session_id'] = session_id
                current_session['extracted_at'] = datetime.utcnow().isoformat()
            
            elif 'date:' in line.lower():
                current_session['session_date'] = line.split(':')[1].strip()
            
            elif 'type:' in line.lower():
                current_session['session_type'] = line.split(':')[1].strip()
            
            elif 'distance:' in line.lower():
                try:
                    distance_str = line.split(':')[1].strip()
                    current_session['planned_distance'] = float(distance_str.replace('km', '').strip())
                except:
                    pass
            
            elif 'description:' in line.lower():
                current_session['description'] = line.split(':')[1].strip()
        
        # Add last session if exists
        if current_session:
            sessions.append(current_session)
        
        if sessions:
            logger.info(f"Parsed {len(sessions)} sessions from text response")
            return sessions
        else:
            logger.warning("No sessions found in text response")
            return None
            
    except Exception as e:
        logger.error(f"Failed to parse agent text response: {str(e)}")
        return None


def store_coaching_sessions(sessions_data: List[Dict[str, Any]]) -> int:
    """Store extracted coaching sessions in DynamoDB"""
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        stored_count = 0
        
        for session in sessions_data:
            try:
                session_date = session.get('session_date', datetime.utcnow().isoformat())
                session_id = session.get('session_id', f"session_{datetime.utcnow().timestamp()}")
                
                table.put_item(
                    Item={
                        'session_date': session_date,
                        'session_id': session_id,
                        'week_number': session.get('week_number', ''),
                        'session_type': session.get('session_type', ''),
                        'description': session.get('description', ''),
                        'workout_structure': session.get('workout_structure', {}),
                        'session_data': session,
                        'extracted_at': datetime.utcnow().isoformat()
                    }
                )
                
                stored_count += 1
                
            except Exception as e:
                logger.error(f"Failed to store session {session.get('session_id')}: {str(e)}")
                # Continue with other sessions
        
        logger.info(f"Stored {stored_count}/{len(sessions_data)} sessions")
        
        return stored_count
        
    except Exception as e:
        logger.error(f"Failed to store coaching sessions: {str(e)}")
        return 0


def get_stored_sessions(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve stored coaching sessions from DynamoDB"""
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        
        # Scan table for recent sessions (last 30 days)
        # TODO: Implement more efficient query with date range
        response = table.scan(
            Limit=100  # Limit to recent sessions
        )
        
        sessions = response.get('Items', [])
        
        # Sort by session_date descending
        sessions.sort(key=lambda x: x.get('session_date', ''), reverse=True)
        
        return {
            'statusCode': 200,
            'sessions': sessions,
            'count': len(sessions)
        }
        
    except Exception as e:
        logger.error(f"Failed to retrieve stored sessions: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'sessions': [],
            'count': 0
        }
