"""
Campus Coach Agent for AgentCore Runtime

Autonomous agent that:
1. Retrieves credentials from Secrets Manager
2. Scrapes Campus Coach sessions using Browser Tool
3. Writes directly to DynamoDB
4. Runs asynchronously (Lambda invoker returns immediately)
5. Uses AgentCore Memory to learn from previous extractions
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
from bedrock_agentcore.memory import MemoryClient
from strands import Agent
from strands_tools.browser import AgentCoreBrowser
from strands.hooks import AgentInitializedEvent, BeforeToolCallEvent, HookProvider, MessageAddedEvent

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
# Campus Coach uses Haiku 4.5 (scraping task, no need for Sonnet's capabilities)
# Cost: ~4x cheaper than Sonnet 4.5. See docs/OPTIMIZATION-PLAN.md P0.6
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
# Max turns to prevent infinite loops. Successful run = ~130 turns. See P0.3
MAX_TURNS = int(os.getenv("CAMPUS_COACH_MAX_TURNS", "150"))
COACHING_SESSIONS_TABLE = os.getenv("COACHING_SESSIONS_TABLE", "strava-ai-boost-campus-coaching-sessions")
CAMPUS_COACH_SECRET = os.getenv("CAMPUS_COACH_SECRET", "strava-ai-boost-campus-coach-credentials")

# AgentCore Memory configuration
MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")

# Initialize memory client if memory is configured
memory_client = None
if MEMORY_ID:
    try:
        memory_client = MemoryClient(region_name=REGION)
        logger.info(f"AgentCore Memory client initialized for Campus Coach: {MEMORY_ID}")
    except Exception as e:
        logger.warning(f"Failed to initialize memory client: {e}")
        memory_client = None


class MaxToolCountsHook(HookProvider):
    """P0.3: Stop the agent loop after max_tool_calls tool invocations.

    Strands Python SDK has no native max_turns arg; we use the official hook
    pattern: set request_state["stop_event_loop"] = True to break the loop.
    See: https://strandsagents.com/docs/user-guide/concepts/agents/hooks/#limit-tool-counts
    """

    def __init__(self, max_tool_calls: int):
        self.max_tool_calls = max_tool_calls
        self.count = 0

    def _on_before_tool_call(self, event):
        self.count += 1
        if self.count > self.max_tool_calls:
            event.cancel_tool = (
                f"Max tool call limit ({self.max_tool_calls}) reached. "
                "Stop immediately and return the JSON with what you have."
            )
            event.invocation_state.setdefault("request_state", {})["stop_event_loop"] = True
            logger.warning(f"⛔ Max tool calls ({self.max_tool_calls}) reached, stopping agent loop")

    def register_hooks(self, registry):
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool_call)


class AgentCoreMemoryHook(HookProvider):
    """Hook for AgentCore Memory integration with Campus Coach Agent"""
    
    def on_agent_initialized(self, event):
        """Load previous extraction context from memory"""
        if not MEMORY_ID or not memory_client:
            return
        
        try:
            session_id = event.agent.state.get("session_id") or "default"
            actor_id = event.agent.state.get("actor_id") or "default_user"
            
            # Get last 3 extraction sessions from memory
            turns = memory_client.get_last_k_turns(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id=session_id,
                k=3
            )
            
            if turns:
                context = "\n".join([
                    f"{m['role']}: {m['content']['text'][:200]}..." 
                    for t in turns for m in t
                ])
                event.agent.system_prompt += f"\n\nPREVIOUS EXTRACTIONS (from Memory):\n{context}"
                logger.info(f"Loaded {len(turns)} previous extraction turns from memory")
        except Exception as e:
            logger.warning(f"Failed to load memory context: {e}")
    
    def on_message_added(self, event):
        """Save extraction to memory after processing"""
        if not MEMORY_ID or not memory_client:
            return
        
        try:
            session_id = event.agent.state.get("session_id") or "default"
            actor_id = event.agent.state.get("actor_id") or "default_user"
            
            # Save only assistant messages
            msg = event.agent.messages[-1]
            
            if msg.get("role") != "assistant":
                return
            
            # Extract content and limit size
            content = str(msg.get("content", ""))
            if len(content) > 9000:
                content = content[:9000] + "... [truncated]"
            
            memory_client.create_event(
                memory_id=MEMORY_ID,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(content, msg["role"])]
            )
            logger.info(f"Saved extraction to memory for actor {actor_id}")
        except Exception as e:
            logger.warning(f"Failed to save to memory: {e}")
    
    def register_hooks(self, registry):
        """Register hooks with the agent"""
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self.on_message_added)


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
    """Save training sessions to DynamoDB (upsert to avoid duplicates)"""
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
            
            # Use week_number + session_number as unique key to avoid duplicates
            week_number = session.get('week_number', 'unknown')
            session_number = session.get('session_number', '1/5')
            
            # Create deterministic session_date and session_id from week_number + session_number
            session_date = f"week-{week_number}"
            session_id = f"{week_number}-{session_number}"
            
            # Use put_item with the unique key (will overwrite if exists)
            table.put_item(
                Item={
                    'session_date': session_date,
                    'session_id': session_id,
                    'week_number': week_number,
                    'session_number': session_number,
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
        
        # Guardrails disabled for Campus Coach (internal scraping agent)
        # Reason: Credentials in prompt would be blocked by guardrail
        # No user input = no prompt injection risk
        logger.info("Campus Coach agent: Guardrails disabled (internal scraping agent)")
        model = MODEL_ID
        
        hooks = [MaxToolCountsHook(MAX_TURNS)]
        if MEMORY_ID:
            hooks.append(AgentCoreMemoryHook())
        agent = Agent(
            model=model,
            tools=[browser_tool.browser],
            system_prompt=CAMPUS_COACH_PROMPT,
            hooks=hooks,
            state={
                "session_id": f"campus-extraction-{datetime.now().strftime('%Y%m%d')}",
                "actor_id": "campus_coach_agent"
            }
        )
        
        if MEMORY_ID:
            logger.info(f"✅ Agent initialized with Browser Tool and Memory (LTM)")
        else:
            logger.info("✅ Agent initialized with Browser Tool (no memory)")
        
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

        ⚠️ IMPORTANT - AUTH FAILURE HANDLING:
        Si la connexion échoue (message d'erreur visible, pas de redirection après 3 tentatives max de click),
        ABANDONNE IMMÉDIATEMENT et retourne ce JSON sans tenter de recommencer depuis zéro:
        {{"error": "Authentication failed", "total_found": 0, "sessions_found": []}}
        NE RECOMMENCE PAS le flow de login depuis le début. Une auth qui échoue = on stoppe.
        
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

            # P0.4: Abort on auth failure - do not retry, just return
            if sessions_data.get('error') and 'auth' in str(sessions_data['error']).lower():
                logger.error(f"❌ Auth failed, aborting (no retry): {sessions_data['error']}")
                agent.cleanup()
                return {
                    "success": False,
                    "error": sessions_data['error'],
                    "retry": False,
                    "message": "Campus Coach authentication failed - credentials may need refresh"
                }

            logger.info("💾 Saving to DynamoDB...")
            saved_count = save_sessions_to_dynamodb(sessions_data, region)
            logger.info(f"✅ {saved_count} sessions saved")
            
            # Save extraction summary to memory (only final result, not intermediate messages)
            if MEMORY_ID and memory_client:
                try:
                    extraction_summary = f"Extraction réussie : {saved_count} séances extraites pour la semaine {sessions_data.get('sessions_found', [{}])[0].get('week_number', 'unknown')}"
                    memory_client.create_event(
                        memory_id=MEMORY_ID,
                        actor_id="campus_coach_agent",
                        session_id=f"campus-extraction-{datetime.now().strftime('%Y%m%d')}",
                        messages=[(extraction_summary, "assistant")]
                    )
                    logger.info("💾 Saved extraction summary to memory")
                except Exception as mem_error:
                    logger.warning(f"Failed to save to memory: {mem_error}")
            
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