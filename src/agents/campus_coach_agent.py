"""
Campus Coach Browser Tool Agent for Strava AI Boost

AgentCore Browser Tool agent for automated Campus Coach session extraction.
Handles session scraping, matching, and confidence scoring using Bedrock AI.
"""

from typing import Dict, Any, List, Optional, Tuple
import json
import logging
import boto3
import asyncio
from datetime import datetime, timezone, timedelta
import re
import hashlib
from botocore.exceptions import ClientError
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
                'max_tokens': 1000,
                'temperature': 0.7
            }
        }

logger = logging.getLogger(__name__)


class CampusCoachAgent:
    """
    AgentCore Browser Tool agent for Campus Coach integration
    
    Handles:
    - Automated session extraction via browser automation
    - Session matching with confidence scoring
    - Secure credential management via Secrets Manager
    - Retry logic for AgentCore Browser Tool cold start issues
    """
    
    def __init__(self, region: str = 'eu-west-1'):
        """
        Initialize Campus Coach Agent with AWS clients
        
        Args:
            region: AWS region for services
        """
        self.region = region
        self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.secretsmanager = boto3.client('secretsmanager', region_name=region)
        
        # Table names (will be set via environment variables in Lambda)
        self.sessions_table_name = 'campus-coaching-sessions'
        self.user_config_table_name = 'strava-ai-boost-user-configuration'
        
        # AgentCore Browser Tool configuration
        self.agentcore_agent_name = 'strava-ai-boost-campus-coach-scraper'
        self.max_retries = 3
        self.retry_delay_base = 2  # seconds
        
        logger.info("CampusCoachAgent initialized")
    
    async def extract_weekly_sessions(self, user_id: str) -> Dict[str, Any]:
        """
        Extract weekly training sessions from Campus Coach
        
        Args:
            user_id: User identifier for credential lookup
            
        Returns:
            Extraction results with sessions data
        """
        try:
            logger.info(f"Starting Campus Coach session extraction for user {user_id}")
            
            # Get user credentials
            credentials = await self.get_user_credentials(user_id)
            if not credentials:
                return {
                    'success': False,
                    'error': 'No Campus Coach credentials found',
                    'sessions_extracted': 0
                }
            
            # Extract sessions with retry logic for cold start issues
            sessions_data = await self.extract_sessions_with_retry(credentials)
            
            if sessions_data['success']:
                # Store sessions in DynamoDB
                stored_count = await self.store_sessions(sessions_data['sessions'])
                
                return {
                    'success': True,
                    'sessions_extracted': stored_count,
                    'extraction_timestamp': datetime.now(timezone.utc).isoformat(),
                    'sessions_data': sessions_data['sessions']
                }
            else:
                return {
                    'success': False,
                    'error': sessions_data.get('error', 'Unknown extraction error'),
                    'sessions_extracted': 0
                }
                
        except Exception as e:
            logger.error(f"Campus Coach extraction failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'sessions_extracted': 0
            }
    
    async def extract_sessions_with_retry(self, credentials: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract sessions with retry logic for AgentCore Browser Tool cold start issues
        
        Known issue: ~30% success rate on first try, 90% after retries
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Campus Coach extraction attempt {attempt + 1}/{self.max_retries}")
                
                # Call AgentCore Browser Tool agent
                result = await self.invoke_agentcore_browser_tool(credentials)
                
                if result['success']:
                    logger.info(f"Campus Coach extraction succeeded on attempt {attempt + 1}")
                    return result
                else:
                    last_error = result.get('error', 'Unknown error')
                    logger.warning(f"Attempt {attempt + 1} failed: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Attempt {attempt + 1} exception: {last_error}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                delay = self.retry_delay_base ** (attempt + 1)
                logger.info(f"Waiting {delay}s before retry...")
                await asyncio.sleep(delay)
        
        return {
            'success': False,
            'error': f'All {self.max_retries} attempts failed. Last error: {last_error}',
            'sessions': []
        }
    
    async def invoke_agentcore_browser_tool(self, credentials: Dict[str, str]) -> Dict[str, Any]:
        """
        Invoke AgentCore Browser Tool for Campus Coach scraping
        
        TODO: Replace with actual AgentCore Browser Tool invocation
        Currently simulated for development
        """
        try:
            # TODO: Replace with actual AgentCore Browser Tool invocation
            # agentcore_client = AgentCoreClient(region=self.region)
            # result = await agentcore_client.invoke_agent(
            #     agent_name=self.agentcore_agent_name,
            #     input_data={
            #         'action': 'extract_sessions',
            #         'credentials': credentials,
            #         'target_weeks': 2  # Extract current and next week
            #     }
            # )
            
            # Simulation of Campus Coach session extraction
            logger.info("Simulating Campus Coach session extraction...")
            
            # Simulate realistic session data
            sessions = await self.simulate_session_extraction()
            
            return {
                'success': True,
                'sessions': sessions,
                'extraction_method': 'simulated',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"AgentCore Browser Tool invocation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'sessions': []
            }
    
    async def simulate_session_extraction(self) -> List[Dict[str, Any]]:
        """
        Simulate Campus Coach session extraction for development
        
        Returns realistic training session data
        """
        # Get current week number
        current_date = datetime.now()
        week_number = current_date.isocalendar()[1]
        
        # Simulate weekly training sessions
        sessions = [
            {
                'session_id': f"week_{week_number}_session_1",
                'session_date': (current_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                'session_type': 'endurance_run',
                'planned_distance': 10.0,  # km
                'planned_duration': 50,    # minutes
                'planned_pace': '5:00',    # min/km
                'intensity': 'easy',
                'description': '10km endurance run at easy pace',
                'week_number': str(week_number),
                'extracted_at': datetime.now(timezone.utc).isoformat()
            },
            {
                'session_id': f"week_{week_number}_session_2",
                'session_date': (current_date + timedelta(days=3)).strftime('%Y-%m-%d'),
                'session_type': 'interval_training',
                'planned_distance': 8.0,
                'planned_duration': 45,
                'planned_pace': '4:20',
                'intensity': 'high',
                'description': '6x800m intervals at threshold pace',
                'intervals': {
                    'count': 6,
                    'distance': 800,  # meters
                    'target_pace': '4:20',
                    'recovery': '90s'
                },
                'week_number': str(week_number),
                'extracted_at': datetime.now(timezone.utc).isoformat()
            },
            {
                'session_id': f"week_{week_number}_session_3",
                'session_date': (current_date + timedelta(days=6)).strftime('%Y-%m-%d'),
                'session_type': 'long_run',
                'planned_distance': 18.0,
                'planned_duration': 95,
                'planned_pace': '5:15',
                'intensity': 'moderate',
                'description': '18km long run with progressive pace',
                'week_number': str(week_number),
                'extracted_at': datetime.now(timezone.utc).isoformat()
            }
        ]
        
        return sessions
    
    async def match_activity_to_session(
        self, 
        activity_data: Dict[str, Any], 
        user_id: str
    ) -> Dict[str, Any]:
        """
        Match Strava activity to planned Campus Coach session using Bedrock AI
        
        Args:
            activity_data: Complete Strava activity data
            user_id: User identifier for session lookup
            
        Returns:
            Matching results with confidence scoring
        """
        try:
            logger.info(f"Matching activity {activity_data.get('id')} to Campus Coach sessions")
            
            # Get recent sessions for the user
            recent_sessions = await self.get_recent_sessions(user_id)
            
            if not recent_sessions:
                return {
                    'match_found': False,
                    'confidence': 0.0,
                    'reason': 'No recent sessions available',
                    'session_data': None
                }
            
            # Use Bedrock AI for intelligent session matching
            match_result = await self.bedrock_session_matching(activity_data, recent_sessions)
            
            return match_result
            
        except Exception as e:
            logger.error(f"Session matching failed: {str(e)}")
            return {
                'match_found': False,
                'confidence': 0.0,
                'reason': f'Matching error: {str(e)}',
                'session_data': None
            }
    
    async def bedrock_session_matching(
        self, 
        activity_data: Dict[str, Any], 
        sessions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Use Bedrock AI for intelligent session matching with confidence scoring
        """
        try:
            # Build matching prompt for Claude
            matching_prompt = self.build_session_matching_prompt(activity_data, sessions)
            
            # Call Bedrock Claude
            bedrock_params = get_bedrock_params()
            response = self.bedrock.invoke_model(
                modelId=bedrock_params['modelId'],
                body=json.dumps({
                    **bedrock_params['body'],
                    'messages': [
                        {
                            'role': 'user',
                            'content': matching_prompt
                        }
                    ]
                })
            )
            
            # Parse Claude's matching analysis
            response_body = json.loads(response['body'].read())
            analysis_text = response_body['content'][0]['text']
            
            return self.parse_matching_result(analysis_text, sessions)
            
        except Exception as e:
            logger.error(f"Bedrock session matching failed: {str(e)}")
            return {
                'match_found': False,
                'confidence': 0.0,
                'reason': f'AI matching error: {str(e)}',
                'session_data': None
            }
    
    def build_session_matching_prompt(
        self, 
        activity_data: Dict[str, Any], 
        sessions: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for Claude session matching analysis"""
        
        activity_type = activity_data.get('type', 'Activity')
        distance = activity_data.get('distance', 0) / 1000  # km
        duration = activity_data.get('moving_time', 0) / 60  # minutes
        activity_date = activity_data.get('start_date_local', '')
        
        prompt = f"""Analyze this Strava activity and match it to the most appropriate planned Campus Coach session.

STRAVA ACTIVITY:
- Type: {activity_type}
- Distance: {distance:.2f} km
- Duration: {duration:.0f} minutes
- Date: {activity_date}
- Average pace: {(duration / distance):.2f} min/km (if distance > 0)

PLANNED SESSIONS:
"""
        
        for i, session in enumerate(sessions):
            prompt += f"""
Session {i+1}:
- Type: {session.get('session_type', 'unknown')}
- Planned distance: {session.get('planned_distance', 0)} km
- Planned duration: {session.get('planned_duration', 0)} minutes
- Planned pace: {session.get('planned_pace', 'unknown')}
- Date: {session.get('session_date', 'unknown')}
- Description: {session.get('description', 'No description')}
"""
        
        prompt += """
MATCHING CRITERIA:
1. Activity type compatibility (run vs planned session type)
2. Distance similarity (within 20% tolerance)
3. Duration similarity (within 25% tolerance)
4. Pace similarity (within 30s/km tolerance)
5. Date proximity (within 3 days of planned session)
6. Session characteristics (intervals, long run, easy run, etc.)

Return your analysis in JSON format:
{
    "match_found": true/false,
    "best_match_index": 0,
    "confidence": 0.85,
    "reasoning": "Detailed explanation of the match",
    "compliance_analysis": {
        "distance_compliance": 0.95,
        "pace_compliance": 0.80,
        "duration_compliance": 0.90,
        "overall_execution": "excellent/good/fair/poor"
    }
}

If no good match is found (confidence < 0.6), set match_found to false."""
        
        return prompt
    
    def parse_matching_result(
        self, 
        analysis_text: str, 
        sessions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Parse Claude's session matching analysis"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            
            if json_match:
                analysis_json = json.loads(json_match.group())
                
                match_found = analysis_json.get('match_found', False)
                confidence = analysis_json.get('confidence', 0.0)
                
                if match_found and confidence >= 0.6:
                    best_match_index = analysis_json.get('best_match_index', 0)
                    
                    # Validate index
                    if 0 <= best_match_index < len(sessions):
                        matched_session = sessions[best_match_index]
                        
                        return {
                            'match_found': True,
                            'confidence': confidence,
                            'reasoning': analysis_json.get('reasoning', ''),
                            'session_data': matched_session,
                            'compliance_analysis': analysis_json.get('compliance_analysis', {}),
                            'match_quality': 'high' if confidence >= 0.8 else 'medium'
                        }
                
                return {
                    'match_found': False,
                    'confidence': confidence,
                    'reasoning': analysis_json.get('reasoning', 'Low confidence match'),
                    'session_data': None
                }
            else:
                return {
                    'match_found': False,
                    'confidence': 0.0,
                    'reasoning': 'Failed to parse AI analysis',
                    'session_data': None
                }
                
        except Exception as e:
            logger.error(f"Failed to parse matching result: {str(e)}")
            return {
                'match_found': False,
                'confidence': 0.0,
                'reasoning': f'Parse error: {str(e)}',
                'session_data': None
            }
    
    async def get_user_credentials(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Get Campus Coach credentials from AWS Secrets Manager
        
        Args:
            user_id: User identifier
            
        Returns:
            Credentials dictionary or None if not found
        """
        try:
            secret_name = f"strava-ai-boost-campus-coach-{user_id}"
            
            response = self.secretsmanager.get_secret_value(SecretId=secret_name)
            credentials = json.loads(response['SecretString'])
            
            return {
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'user_id': user_id
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"No Campus Coach credentials found for user {user_id}")
                return None
            else:
                logger.error(f"Failed to get credentials: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Credential retrieval error: {str(e)}")
            return None
    
    async def store_sessions(self, sessions: List[Dict[str, Any]]) -> int:
        """
        Store extracted sessions in DynamoDB
        
        Args:
            sessions: List of session data dictionaries
            
        Returns:
            Number of sessions stored
        """
        try:
            table = self.dynamodb.Table(self.sessions_table_name)
            stored_count = 0
            
            for session in sessions:
                # Create composite key
                session_date = session.get('session_date', '')
                session_id = session.get('session_id', '')
                
                if session_date and session_id:
                    table.put_item(
                        Item={
                            'session_date': session_date,
                            'session_id': session_id,
                            'session_data': session,
                            'stored_at': datetime.now(timezone.utc).isoformat()
                        }
                    )
                    stored_count += 1
            
            logger.info(f"Stored {stored_count} Campus Coach sessions")
            return stored_count
            
        except Exception as e:
            logger.error(f"Failed to store sessions: {str(e)}")
            return 0
    
    async def get_recent_sessions(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent Campus Coach sessions for the user
        
        Args:
            user_id: User identifier
            days: Number of days to look back
            
        Returns:
            List of recent session data
        """
        try:
            table = self.dynamodb.Table(self.sessions_table_name)
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Scan for recent sessions (in production, use GSI for better performance)
            response = table.scan(
                FilterExpression='session_date BETWEEN :start_date AND :end_date',
                ExpressionAttributeValues={
                    ':start_date': start_date.strftime('%Y-%m-%d'),
                    ':end_date': end_date.strftime('%Y-%m-%d')
                }
            )
            
            sessions = []
            for item in response.get('Items', []):
                session_data = item.get('session_data', {})
                if session_data:
                    sessions.append(session_data)
            
            logger.info(f"Retrieved {len(sessions)} recent sessions for user {user_id}")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {str(e)}")
            return []


# Utility functions for Lambda integration

def create_campus_coach_agent(region: str = 'eu-west-1') -> CampusCoachAgent:
    """
    Factory function to create CampusCoachAgent instance
    
    Args:
        region: AWS region for services
        
    Returns:
        Configured CampusCoachAgent instance
    """
    return CampusCoachAgent(region=region)


def run_session_extraction(user_id: str, region: str = 'eu-west-1') -> Dict[str, Any]:
    """
    Synchronous wrapper for session extraction (Lambda compatibility)
    
    Args:
        user_id: User identifier
        region: AWS region
        
    Returns:
        Extraction results dictionary
    """
    agent = create_campus_coach_agent(region)
    
    # Run async function in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(agent.extract_weekly_sessions(user_id))
        return result
    finally:
        loop.close()


def run_session_matching(
    activity_data: Dict[str, Any], 
    user_id: str, 
    region: str = 'eu-west-1'
) -> Dict[str, Any]:
    """
    Synchronous wrapper for session matching (Lambda compatibility)
    
    Args:
        activity_data: Complete Strava activity data
        user_id: User identifier
        region: AWS region
        
    Returns:
        Matching results dictionary
    """
    agent = create_campus_coach_agent(region)
    
    # Run async function in event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            agent.match_activity_to_session(activity_data, user_id)
        )
        return result
    finally:
        loop.close()