"""
Campus Coach Agent for AgentCore Runtime

Autonomous agent that:
1. Retrieves credentials from Secrets Manager
2. Scrapes Campus Coach sessions using Browser Tool
3. Writes directly to DynamoDB
4. Runs asynchronously (Lambda invoker returns immediately)
"""

import os
import json
import logging
from typing import Dict, Any
from datetime import datetime
from decimal import Decimal
import boto3

# Required AgentCore imports
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands_tools.browser import AgentCoreBrowser

# Import embedded prompts
from embedded_prompts import CAMPUS_COACH_PROMPT

# Initialize AgentCore app
app = BedrockAgentCoreApp()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Environment variables
REGION = os.getenv("AWS_REGION", "eu-west-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
COACHING_SESSIONS_TABLE = os.getenv("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions")
CAMPUS_COACH_SECRET = os.getenv("CAMPUS_COACH_SECRET", "strava-ai-boost-campus-coach-credentials")


def get_campus_credentials(region: str = "eu-west-1"):
    """Retrieve Campus Coach credentials from Secrets Manager"""
    client = boto3.client('secretsmanager', region_name=region)
    
    try:
        response = client.get_secret_value(SecretId=CAMPUS_COACH_SECRET)
        secret = json.loads(response['SecretString'])
        return secret.get('username'), secret.get('password')
    except Exception as e:
        logger.error(f"❌ Error retrieving credentials: {e}")
        return None, None


def save_sessions_to_dynamodb(sessions_data: dict, region: str = "eu-west-1"):
    """Save training sessions to DynamoDB"""
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(COACHING_SESSIONS_TABLE)
    
    sessions = sessions_data.get('sessions_found', [])
    saved_count = 0
    
    for session in sessions:
        try:
            # Convert floats to Decimal for DynamoDB
            if session.get('targetedMetrics'):
                metrics = session['targetedMetrics']
                if 'target_distance_km' in metrics and metrics['target_distance_km'] is not None:
                    metrics['target_distance_km'] = Decimal(str(metrics['target_distance_km']))
            
            session_date = session.get('session_date', datetime.now().isoformat())
            session_id = session.get('id', f"session_{datetime.now().timestamp()}")
            
            # Store in DynamoDB with session_date + session_id as composite key
            table.put_item(
                Item={
                    'session_date': session_date,
                    'session_id': session_id,
                    'week_number': session.get('week_number', ''),
                    'session_number': session.get('session_number', ''),
                    'title': session.get('title', ''),
                    'workout': session.get('workout', ''),
                    'status': session.get('status', ''),
                    'targetedMetrics': session.get('targetedMetrics'),
                    'intervals': session.get('intervals', []),
                    'coach_advice': session.get('coach_advice'),
                    'description': session.get('description', ''),
                    'objectives': session.get('objectives', []),
                    'updated_at': datetime.now().isoformat()
                }
            )
            
            saved_count += 1
            logger.info(f"✅ Saved session: {session_id} (week {session.get('week_number')})")
            
        except Exception as e:
            logger.error(f"❌ Error saving session {session.get('id')}: {e}")
    
    return saved_count


@app.async_task
async def scrape_campus_sessions(region, campus_username, campus_password):
    """Background task to scrape Campus Coach sessions"""
    
    logger.info(f"✅ Credentials retrieved for user: {campus_username}")
    
    try:
        logger.info("🔄 Initializing Strands Agent with Browser Tool...")
        
        browser_tool = AgentCoreBrowser(region=region)
        
        agent = Agent(
            tools=[browser_tool.browser],
            system_prompt=CAMPUS_COACH_PROMPT,
            model=MODEL_ID
        )
        logger.info("✅ Agent initialized with Browser Tool")
        
        # Prepare extraction task
        combined_task = f"""
        MISSION COMPLÈTE: Connexion à Campus Coach et extraction des séances d'entraînement.
        
        ÉTAPE 1 - CONNEXION:
        1. Va sur https://app.campus.coach/auth
        2. Si popup cookies: accepter
        3. Clique "Continue with your email" puis "Log In"
        4. Email: {campus_username}
        5. Password: {campus_password}
        6. Clique connexion
        7. Attendre redirection dashboard
        
        ÉTAPE 2 - EXTRACTION:
        1. Scroll progressivement pour voir toutes les séances
        2. Capturer le contenu des séances visibles
        3. Extraire les 5 séances de la semaine
        
        ÉTAPE 3 - ANALYSE:
        Retourner un JSON avec ce format:
        {{
            "total_found": 5,
            "sessions_found": [
                {{
                    "id": "session-id",
                    "title": "Titre de la séance",
                    "week_number": "15-12",
                    "session_number": "1/5",
                    "session_date": "2026-01-02",
                    "workout": "ROUTE",
                    "status": "À faire",
                    "targetedMetrics": {{"target_distance_km": 8.0, "target_duration_min": 40, "difficulty": 3}},
                    "intervals": [],
                    "coach_advice": {{"main_advice": "Conseil du coach"}},
                    "description": "Description",
                    "objectives": ["Endurance"]
                }}
            ]
        }}
        
        Retourner UNIQUEMENT le JSON final.
        """
        
        logger.info("🚀 Executing complete mission (login + extraction)...")
        result = agent(combined_task)
        logger.info(f"✅ Mission result: {str(result)[:200]}...")
        
        # Parse JSON and save to DynamoDB
        try:
            response_text = str(result)
            if '```json' in response_text:
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                json_text = response_text[start:end].strip()
            else:
                json_text = response_text.strip()
            
            sessions_data = json.loads(json_text)
            
            logger.info("💾 Saving to DynamoDB...")
            saved_count = save_sessions_to_dynamodb(sessions_data, region)
            logger.info(f"✅ {saved_count} sessions saved")
            
            result = {
                "success": True,
                "sessions": sessions_data,
                "saved_count": saved_count,
                "message": f"Campus Coach: {saved_count} sessions extracted and saved to DynamoDB"
            }
            
            # Cleanup and return
            agent.cleanup()
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"⚠️ JSON parsing error: {e}")
            return {
                "success": True,
                "sessions": str(result),
                "saved_count": 0,
                "message": "Extraction completed but JSON parsing failed"
            }
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}


@app.entrypoint
async def invoke(payload, context=None):
    """
    AgentCore entrypoint for Campus Coach scraping
    
    Launches async task and returns immediately (non-blocking)
    """
    
    region = payload.get("region", REGION)
    
    # Retrieve credentials from Secrets Manager
    logger.info("🔑 Retrieving credentials from Secrets Manager...")
    campus_username, campus_password = get_campus_credentials(region)
    
    if not campus_username or not campus_password:
        return {"success": False, "error": "Failed to retrieve credentials from Secrets Manager"}
    
    # Launch async task in background without awaiting
    logger.info("🚀 Starting background scraping task...")
    import asyncio
    asyncio.create_task(scrape_campus_sessions(region, campus_username, campus_password))
    
    return {"success": True, "message": "Scraping task started in background"}


if __name__ == "__main__":
    app.run()