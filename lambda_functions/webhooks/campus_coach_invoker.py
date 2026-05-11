"""
Campus Coach Invoker Lambda Function

Invokes AgentCore Browser Tool agent for Campus Coach session extraction.
Handles retry logic for cold start issues and session data storage.
"""

import json
import os
from typing import Dict, Any, Optional, List
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import time
from shared.logger import get_logger

logger = get_logger("campus-coach-invoker")

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
    Lambda handler for invoking Campus Coach AgentCore agent
    
    Launches agent asynchronously and returns immediately (non-blocking)
    """
    try:
        action = event.get('action', 'extract_sessions')
        user_id = event.get('user_id', 'default_user')
        
        logger.info(f"Campus Coach invoker action: {action}")
        
        # Get agent ARN from environment
        agent_arn = os.environ.get('CAMPUS_COACH_AGENT_ARN', '')
        
        if not agent_arn:
            logger.error("CAMPUS_COACH_AGENT_ARN environment variable not set")
            return {
                'statusCode': 500,
                'error': 'Campus Coach agent not configured'
            }
        
        # Prepare payload for AgentCore agent
        agent_payload = {
            'action': action,
            'user_id': user_id,
            'region': REGION
        }
        
        # Invoke AgentCore agent asynchronously (fire and forget)
        bedrock_agentcore_client = boto3.client('bedrock-agentcore', region_name=REGION)
        
        # Create session ID
        import uuid
        session_id = f"campus-coach-{uuid.uuid4().hex}"
        
        logger.info(f"Invoking Campus Coach agent asynchronously: {agent_arn}")
        
        # Invoke agent (non-blocking)
        response = bedrock_agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            runtimeSessionId=session_id,
            payload=json.dumps(agent_payload).encode('utf-8')
        )
        
        logger.info("✅ Campus Coach agent invoked successfully (async)")
        
        return {
            'statusCode': 200,
            'message': 'Campus Coach extraction started in background',
            'session_id': session_id,
            'agent_arn': agent_arn
        }
        
    except Exception as e:
        logger.error(f"Campus Coach invoker error: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'action': event.get('action')
        }


def get_stored_sessions(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve stored coaching sessions from DynamoDB"""
    try:
        table = dynamodb.Table(COACHING_SESSIONS_TABLE)
        
        # Scan table for recent sessions (last 30 days)
        # Small table (~100 items), scan is acceptable here
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
