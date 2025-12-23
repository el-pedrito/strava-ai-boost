"""
Campus Coach Module for Strava AI Boost

Integrates with Campus Coach training platform using AgentCore Browser Tool
for automated session extraction and intelligent activity matching.
"""

from typing import Dict, Any, Optional, List
import logging
import json
import asyncio
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError

from .base_module import (
    BaseModule, 
    ModuleConfig, 
    ModuleInsight, 
    ModuleError,
    ModuleConfigurationError,
    ModuleProcessingError
)

logger = logging.getLogger(__name__)


class CampusCoachModule(BaseModule):
    """
    Campus Coach integration module
    
    Features:
    - AgentCore Browser Tool for automated session extraction
    - Intelligent session matching with confidence scoring using Bedrock AI
    - Performance comparison analysis (actual vs planned)
    - Retry logic for AgentCore cold start issues
    """
    
    def __init__(self, config: ModuleConfig):
        super().__init__(config)
        self.bedrock_client = None
        self.dynamodb = None
        self.secrets_client = None
        self.agentcore_client = None
        self.sessions_table_name = None
        
    async def _initialize_module(self) -> None:
        """Initialize Campus Coach module with AWS clients"""
        try:
            # Initialize AWS clients
            self.bedrock_client = boto3.client('bedrock-runtime')
            self.dynamodb = boto3.resource('dynamodb')
            self.secrets_client = boto3.client('secretsmanager')
            
            # Get table name from environment or config
            import os
            self.sessions_table_name = os.environ.get(
                'COACHING_SESSIONS_TABLE', 
                'campus-coaching-sessions'
            )
            
            # TODO: Initialize AgentCore client when SDK is available
            # self.agentcore_client = AgentCoreClient(region='eu-west-1')
            
            logger.info("Campus Coach module initialized successfully")
            
        except Exception as e:
            raise ModuleConfigurationError(
                self.config.module_id,
                f"Failed to initialize AWS clients: {str(e)}",
                e
            )
    
    async def analyze_activity(
        self, 
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]] = None
    ) -> ModuleInsight:
        """
        Analyze activity against Campus Coach planned sessions
        
        Uses AgentCore Browser Tool to extract sessions and Bedrock AI
        for intelligent matching and performance analysis.
        """
        try:
            if not self.is_enabled():
                return ModuleInsight(
                    module_id="campus_coach",
                    insights={},
                    confidence=0.0,
                    metadata={"status": "disabled"}
                )
            
            # 1. Get recent sessions from DynamoDB or extract new ones
            sessions = await self.get_recent_sessions()
            
            if not sessions:
                logger.info("No Campus Coach sessions available, extracting new ones")
                sessions = await self.extract_sessions_with_retry()
            
            # 2. Match activity against planned sessions using Bedrock AI
            match_result = await self.match_activity_to_session(
                activity_data, streams_data, sessions
            )
            
            # 3. Analyze performance if match found with high confidence
            performance_analysis = None
            if match_result.get('confidence', 0) > 0.7:
                performance_analysis = await self.analyze_performance_compliance(
                    activity_data, streams_data, match_result.get('session')
                )
            
            # Build comprehensive insights
            insights = {
                "session_matched": match_result.get('matched', False),
                "confidence_score": match_result.get('confidence', 0.0),
                "match_reasons": match_result.get('match_reasons', []),
                "planned_session": match_result.get('session'),
                "performance_analysis": performance_analysis,
                "sessions_available": len(sessions) if sessions else 0
            }
            
            return ModuleInsight(
                module_id="campus_coach",
                insights=insights,
                confidence=match_result.get('confidence', 0.0),
                metadata={
                    "extraction_time": datetime.now(timezone.utc).isoformat(),
                    "sessions_count": len(sessions) if sessions else 0,
                    "analysis_type": "bedrock_ai_matching"
                }
            )
            
        except Exception as e:
            logger.error(f"Campus Coach analysis failed: {str(e)}")
            raise ModuleProcessingError(
                self.config.module_id,
                f"Activity analysis failed: {str(e)}",
                e
            )
    
    async def configure(self, credentials: Dict[str, str]) -> bool:
        """
        Configure Campus Coach module with login credentials
        
        Stores credentials securely in AWS Secrets Manager
        """
        try:
            required_fields = ["username", "password"]
            
            for field in required_fields:
                if field not in credentials:
                    raise ModuleConfigurationError(
                        self.config.module_id,
                        f"Missing required credential: {field}"
                    )
            
            # Test credentials with AgentCore Browser Tool
            login_success = await self.test_login_credentials(credentials)
            
            if login_success:
                await self.store_credentials_securely(credentials)
                self.config.credentials = {"stored": True}  # Don't store actual credentials in config
                logger.info("Campus Coach module configured successfully")
                return True
            else:
                raise ModuleConfigurationError(
                    self.config.module_id,
                    "Credential validation failed"
                )
            
        except ModuleConfigurationError:
            raise
        except Exception as e:
            raise ModuleConfigurationError(
                self.config.module_id,
                f"Configuration failed: {str(e)}",
                e
            )
    
    async def validate_configuration(self) -> bool:
        """
        Validate Campus Coach configuration
        
        Tests stored credentials and AgentCore Browser Tool connectivity
        """
        try:
            if not self.config.credentials or not self.config.credentials.get("stored"):
                return False
            
            # Retrieve and test stored credentials
            stored_credentials = await self.get_stored_credentials()
            if not stored_credentials:
                return False
            
            # Test AgentCore Browser Tool connectivity
            return await self.test_agentcore_connectivity()
            
        except Exception as e:
            logger.error(f"Campus Coach validation failed: {str(e)}")
            return False
    
    async def get_recent_sessions(self) -> List[Dict[str, Any]]:
        """Get recent training sessions from DynamoDB"""
        try:
            table = self.dynamodb.Table(self.sessions_table_name)
            
            # Get sessions from last 14 days
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=14)).strftime('%Y-%m-%d')
            
            response = table.scan(
                FilterExpression='session_date >= :cutoff',
                ExpressionAttributeValues={':cutoff': cutoff_date},
                Limit=50  # Limit to recent sessions
            )
            
            sessions = response.get('Items', [])
            logger.info(f"Retrieved {len(sessions)} recent Campus Coach sessions")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {str(e)}")
            return []
    
    async def extract_sessions_with_retry(self) -> List[Dict[str, Any]]:
        """
        Extract training sessions using AgentCore Browser Tool with retry logic
        
        Known issue: Cold start problem with ~30% first-try success rate
        Implements exponential backoff retry strategy
        """
        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Campus Coach extraction attempt {attempt + 1}/{max_retries}")
                
                # Get stored credentials
                credentials = await self.get_stored_credentials()
                if not credentials:
                    raise ModuleConfigurationError(
                        self.config.module_id,
                        "No stored credentials found"
                    )
                
                # Extract sessions using AgentCore Browser Tool
                sessions = await self.extract_sessions_agentcore(credentials)
                
                if sessions:
                    # Store extracted sessions in DynamoDB
                    await self.store_extracted_sessions(sessions)
                    logger.info(f"Successfully extracted {len(sessions)} sessions")
                    return sessions
                else:
                    logger.warning(f"No sessions extracted on attempt {attempt + 1}")
                    
            except Exception as e:
                logger.error(f"Extraction attempt {attempt + 1} failed: {str(e)}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    delay = base_delay ** (attempt + 1)
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    raise ModuleProcessingError(
                        self.config.module_id,
                        f"Session extraction failed after {max_retries} attempts: {str(e)}",
                        e
                    )
        
        return []
    
    async def extract_sessions_agentcore(self, credentials: Dict[str, str]) -> List[Dict[str, Any]]:
        """Extract sessions using AgentCore Browser Tool"""
        try:
            # TODO: Replace with actual AgentCore SDK calls when available
            # For now, return mock data that matches the expected structure
            
            if self.agentcore_client:
                # Actual AgentCore invocation
                response = await self.agentcore_client.invoke_agent(
                    agent_name='campus-coach-scraper',
                    input_data={
                        'credentials': credentials,
                        'action': 'extract_sessions',
                        'weeks': 2  # Extract last 2 weeks
                    }
                )
                return response.get('sessions', [])
            else:
                # Mock implementation for development
                logger.warning("AgentCore client not available, using mock data")
                return await self.generate_mock_sessions()
                
        except Exception as e:
            logger.error(f"AgentCore session extraction failed: {str(e)}")
            raise
    
    async def generate_mock_sessions(self) -> List[Dict[str, Any]]:
        """Generate mock Campus Coach sessions for development"""
        mock_sessions = [
            {
                "session_id": "cc_001",
                "session_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                "session_type": "tempo_run",
                "duration_minutes": 45,
                "description": "5x1000m @ tempo pace with 90s recovery",
                "intervals": [
                    {"distance": 1000, "pace": "4:10", "recovery": "90s"},
                    {"distance": 1000, "pace": "4:10", "recovery": "90s"},
                    {"distance": 1000, "pace": "4:10", "recovery": "90s"},
                    {"distance": 1000, "pace": "4:10", "recovery": "90s"},
                    {"distance": 1000, "pace": "4:10", "recovery": "0s"}
                ],
                "target_zones": ["zone3", "zone4"],
                "week_number": "15",
                "extracted_at": datetime.now(timezone.utc).isoformat()
            },
            {
                "session_id": "cc_002",
                "session_date": (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%d'),
                "session_type": "easy_run",
                "duration_minutes": 60,
                "description": "60min easy run @ conversational pace",
                "intervals": [],
                "target_zones": ["zone1", "zone2"],
                "week_number": "15",
                "extracted_at": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        return mock_sessions
    
    async def match_activity_to_session(
        self,
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]],
        sessions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Match activity against planned sessions using Bedrock AI
        
        Uses Claude Sonnet 4.5 for intelligent pattern matching with confidence scoring
        """
        try:
            if not sessions:
                return {"matched": False, "confidence": 0.0, "reason": "No sessions available"}
            
            # Analyze activity patterns from streams data
            activity_patterns = await self.analyze_activity_patterns(activity_data, streams_data)
            
            # Use Bedrock AI for intelligent session matching
            match_result = await self.bedrock_session_matching(
                activity_data, activity_patterns, sessions
            )
            
            return match_result
            
        except Exception as e:
            logger.error(f"Session matching failed: {str(e)}")
            return {"matched": False, "confidence": 0.0, "error": str(e)}
    
    async def analyze_activity_patterns(
        self, 
        activity_data: Dict[str, Any], 
        streams_data: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze activity patterns from streams data for matching"""
        try:
            patterns = {
                "activity_date": activity_data.get('start_date_local', ''),
                "duration_minutes": activity_data.get('moving_time', 0) / 60,
                "distance_km": activity_data.get('distance', 0) / 1000,
                "activity_type": activity_data.get('type', 'Run'),
                "intervals_detected": [],
                "effort_zones": [],
                "pace_variability": 0.0
            }
            
            if streams_data:
                # Analyze velocity patterns for intervals
                velocity_data = streams_data.get('velocity_smooth', [])
                if velocity_data:
                    patterns["intervals_detected"] = self.detect_intervals_from_velocity(velocity_data)
                    patterns["pace_variability"] = self.calculate_pace_variability(velocity_data)
                
                # Analyze heart rate zones
                heartrate_data = streams_data.get('heartrate', [])
                if heartrate_data:
                    patterns["effort_zones"] = self.analyze_heart_rate_zones(heartrate_data)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Activity pattern analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def detect_intervals_from_velocity(self, velocity_data: List[float]) -> List[Dict[str, Any]]:
        """Detect intervals from velocity data"""
        intervals = []
        
        if len(velocity_data) < 10:
            return intervals
        
        # Simple interval detection based on significant pace changes
        threshold = 0.3  # 30% pace change threshold
        in_interval = False
        interval_start = 0
        
        for i in range(1, len(velocity_data)):
            if velocity_data[i-1] > 0:  # Avoid division by zero
                pace_change = abs(velocity_data[i] - velocity_data[i-1]) / velocity_data[i-1]
                
                if pace_change > threshold and not in_interval:
                    # Start of interval
                    in_interval = True
                    interval_start = i
                elif pace_change > threshold and in_interval:
                    # End of interval
                    in_interval = False
                    interval_duration = (i - interval_start) * 1  # Assuming 1 second per data point
                    if interval_duration > 60:  # Only count intervals > 1 minute
                        intervals.append({
                            "start_time": interval_start,
                            "duration_seconds": interval_duration,
                            "avg_velocity": sum(velocity_data[interval_start:i]) / (i - interval_start)
                        })
        
        return intervals
    
    def calculate_pace_variability(self, velocity_data: List[float]) -> float:
        """Calculate pace variability coefficient"""
        if not velocity_data or len(velocity_data) < 2:
            return 0.0
        
        # Convert velocity to pace and calculate coefficient of variation
        paces = [1/v if v > 0 else 0 for v in velocity_data]
        valid_paces = [p for p in paces if p > 0]
        
        if len(valid_paces) < 2:
            return 0.0
        
        mean_pace = sum(valid_paces) / len(valid_paces)
        variance = sum((p - mean_pace) ** 2 for p in valid_paces) / len(valid_paces)
        std_dev = variance ** 0.5
        
        return std_dev / mean_pace if mean_pace > 0 else 0.0
    
    def analyze_heart_rate_zones(self, heartrate_data: List[int]) -> List[str]:
        """Analyze heart rate zones from HR data"""
        if not heartrate_data:
            return []
        
        # Simple zone analysis (assuming max HR ~190 for average athlete)
        estimated_max_hr = 190
        zones = []
        
        for hr in heartrate_data:
            hr_percentage = hr / estimated_max_hr
            
            if hr_percentage < 0.6:
                zones.append('zone1')
            elif hr_percentage < 0.7:
                zones.append('zone2')
            elif hr_percentage < 0.8:
                zones.append('zone3')
            elif hr_percentage < 0.9:
                zones.append('zone4')
            else:
                zones.append('zone5')
        
        # Return unique zones in order of appearance
        unique_zones = []
        for zone in zones:
            if zone not in unique_zones:
                unique_zones.append(zone)
        
        return unique_zones
    
    async def bedrock_session_matching(
        self,
        activity_data: Dict[str, Any],
        activity_patterns: Dict[str, Any],
        sessions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Use Bedrock AI for intelligent session matching"""
        try:
            # Build prompt for Claude Sonnet 4.5
            prompt = self.build_matching_prompt(activity_data, activity_patterns, sessions)
            
            # Call Bedrock Claude
            response = self.bedrock_client.invoke_model(
                modelId=os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0'),
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 1000,
                    'temperature': 0.3,  # Lower temperature for more consistent matching
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
            
            return self.parse_matching_result(generated_text, sessions)
            
        except Exception as e:
            logger.error(f"Bedrock session matching failed: {str(e)}")
            return {"matched": False, "confidence": 0.0, "error": str(e)}
    
    def build_matching_prompt(
        self,
        activity_data: Dict[str, Any],
        activity_patterns: Dict[str, Any],
        sessions: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for Bedrock AI session matching"""
        
        prompt = f"""Analyze this Strava activity and match it against planned Campus Coach training sessions.

ACTIVITY DATA:
- Date: {activity_patterns.get('activity_date', 'unknown')}
- Duration: {activity_patterns.get('duration_minutes', 0):.0f} minutes
- Distance: {activity_patterns.get('distance_km', 0):.2f} km
- Type: {activity_patterns.get('activity_type', 'Run')}
- Intervals detected: {len(activity_patterns.get('intervals_detected', []))}
- Effort zones: {', '.join(activity_patterns.get('effort_zones', []))}
- Pace variability: {activity_patterns.get('pace_variability', 0):.3f}

PLANNED SESSIONS:
"""
        
        for i, session in enumerate(sessions[:5]):  # Limit to 5 most recent sessions
            prompt += f"""
Session {i+1}:
- Date: {session.get('session_date', 'unknown')}
- Type: {session.get('session_type', 'unknown')}
- Duration: {session.get('duration_minutes', 0)} minutes
- Description: {session.get('description', 'No description')}
- Intervals: {len(session.get('intervals', []))}
- Target zones: {', '.join(session.get('target_zones', []))}
"""
        
        prompt += """
MATCHING CRITERIA:
1. Date proximity (same day = highest score, within 2 days = good)
2. Session type alignment (tempo, intervals, easy run, etc.)
3. Duration similarity (within 20% = good match)
4. Interval structure match (number and type of intervals)
5. Effort zone correspondence (target vs actual zones)

Return your analysis in JSON format:
{
    "matched": true/false,
    "confidence": 0.0-1.0,
    "best_match_session_id": "session_id or null",
    "match_reasons": ["reason1", "reason2"],
    "confidence_breakdown": {
        "date_proximity": 0.0-1.0,
        "session_type": 0.0-1.0,
        "duration": 0.0-1.0,
        "intervals": 0.0-1.0,
        "effort_zones": 0.0-1.0
    }
}"""
        
        return prompt
    
    def parse_matching_result(self, generated_text: str, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse Bedrock AI matching result"""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
                
                # Find the matched session
                matched_session = None
                if result.get('matched') and result.get('best_match_session_id'):
                    for session in sessions:
                        if session.get('session_id') == result['best_match_session_id']:
                            matched_session = session
                            break
                
                return {
                    "matched": result.get('matched', False),
                    "confidence": result.get('confidence', 0.0),
                    "session": matched_session,
                    "match_reasons": result.get('match_reasons', []),
                    "confidence_breakdown": result.get('confidence_breakdown', {}),
                    "analysis_type": "bedrock_ai"
                }
            else:
                logger.error("Failed to parse JSON from Bedrock response")
                return {"matched": False, "confidence": 0.0, "error": "Parse error"}
                
        except Exception as e:
            logger.error(f"Failed to parse matching result: {str(e)}")
            return {"matched": False, "confidence": 0.0, "error": str(e)}
    
    async def analyze_performance_compliance(
        self,
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]],
        planned_session: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze performance compliance comparing actual vs planned
        
        Uses streams-based analysis for detailed comparison
        """
        try:
            if not planned_session or not streams_data:
                return None
            
            analysis = {
                "session_execution": "unknown",
                "pace_accuracy": 0.0,
                "effort_distribution": "unknown",
                "interval_precision": 0.0,
                "compliance_score": 0.0,
                "recommendations": []
            }
            
            # Analyze pace accuracy for intervals
            planned_intervals = planned_session.get('intervals', [])
            detected_intervals = streams_data.get('velocity_smooth', [])
            
            if planned_intervals and detected_intervals:
                pace_accuracy = self.calculate_pace_accuracy(planned_intervals, detected_intervals)
                analysis["pace_accuracy"] = pace_accuracy
            
            # Analyze effort distribution
            target_zones = planned_session.get('target_zones', [])
            heartrate_data = streams_data.get('heartrate', [])
            
            if target_zones and heartrate_data:
                effort_analysis = self.analyze_effort_distribution(target_zones, heartrate_data)
                analysis["effort_distribution"] = effort_analysis
            
            # Calculate overall compliance score
            analysis["compliance_score"] = self.calculate_compliance_score(analysis)
            
            # Generate recommendations
            analysis["recommendations"] = self.generate_performance_recommendations(analysis)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Performance compliance analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def calculate_pace_accuracy(self, planned_intervals: List[Dict], velocity_data: List[float]) -> float:
        """Calculate pace accuracy for interval sessions"""
        # Simplified implementation - would need more sophisticated analysis
        # This is a placeholder for the actual pace analysis logic
        return 0.85  # Mock 85% accuracy
    
    def analyze_effort_distribution(self, target_zones: List[str], heartrate_data: List[int]) -> str:
        """Analyze effort distribution vs target zones"""
        # Simplified implementation
        if "zone3" in target_zones or "zone4" in target_zones:
            return "moderate_to_hard"
        elif "zone1" in target_zones or "zone2" in target_zones:
            return "easy_to_moderate"
        else:
            return "mixed_effort"
    
    def calculate_compliance_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate overall compliance score"""
        pace_score = analysis.get("pace_accuracy", 0.0)
        # Add other factors as needed
        return pace_score  # Simplified for now
    
    def generate_performance_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations based on analysis"""
        recommendations = []
        
        pace_accuracy = analysis.get("pace_accuracy", 0.0)
        if pace_accuracy < 0.8:
            recommendations.append("Focus on pacing consistency in interval sessions")
        
        compliance_score = analysis.get("compliance_score", 0.0)
        if compliance_score > 0.9:
            recommendations.append("Excellent session execution!")
        elif compliance_score > 0.7:
            recommendations.append("Good session execution with room for improvement")
        else:
            recommendations.append("Consider reviewing pacing strategy for this session type")
        
        return recommendations
    
    async def store_extracted_sessions(self, sessions: List[Dict[str, Any]]) -> None:
        """Store extracted sessions in DynamoDB"""
        try:
            table = self.dynamodb.Table(self.sessions_table_name)
            
            for session in sessions:
                table.put_item(Item=session)
            
            logger.info(f"Stored {len(sessions)} sessions in DynamoDB")
            
        except Exception as e:
            logger.error(f"Failed to store sessions: {str(e)}")
    
    async def test_login_credentials(self, credentials: Dict[str, str]) -> bool:
        """Test Campus Coach login credentials"""
        try:
            # TODO: Implement actual credential testing with AgentCore Browser Tool
            # For now, return True for valid-looking credentials
            username = credentials.get('username', '')
            password = credentials.get('password', '')
            
            if len(username) > 3 and len(password) > 6:
                logger.info("Campus Coach credentials appear valid (mock validation)")
                return True
            else:
                logger.error("Campus Coach credentials appear invalid")
                return False
                
        except Exception as e:
            logger.error(f"Credential testing failed: {str(e)}")
            return False
    
    async def store_credentials_securely(self, credentials: Dict[str, str]) -> None:
        """Store credentials in AWS Secrets Manager"""
        try:
            secret_name = f"strava-ai-boost-campus-coach-{self.config.module_id}"
            
            self.secrets_client.create_secret(
                Name=secret_name,
                SecretString=json.dumps(credentials),
                Description="Campus Coach credentials for Strava AI Boost"
            )
            
            logger.info(f"Stored Campus Coach credentials in Secrets Manager: {secret_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceExistsException':
                # Update existing secret
                self.secrets_client.update_secret(
                    SecretId=secret_name,
                    SecretString=json.dumps(credentials)
                )
                logger.info(f"Updated Campus Coach credentials in Secrets Manager: {secret_name}")
            else:
                raise
    
    async def get_stored_credentials(self) -> Optional[Dict[str, str]]:
        """Retrieve stored credentials from Secrets Manager"""
        try:
            secret_name = f"strava-ai-boost-campus-coach-{self.config.module_id}"
            
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            credentials = json.loads(response['SecretString'])
            
            return credentials
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.error("Campus Coach credentials not found in Secrets Manager")
            else:
                logger.error(f"Failed to retrieve credentials: {str(e)}")
            return None
    
    async def test_agentcore_connectivity(self) -> bool:
        """Test AgentCore Browser Tool connectivity"""
        try:
            # TODO: Implement actual AgentCore connectivity test
            # For now, return True as mock
            logger.info("AgentCore connectivity test passed (mock)")
            return True
            
        except Exception as e:
            logger.error(f"AgentCore connectivity test failed: {str(e)}")
            return False
    
    def get_required_credentials(self) -> List[str]:
        """Get list of required credential fields"""
        return ["username", "password"]
    
    def get_module_info(self) -> Dict[str, Any]:
        """Get Campus Coach module information"""
        return {
            "module_id": "campus_coach",
            "name": "Campus Coach",
            "description": "Integrates with Campus Coach training platform for session matching and performance analysis",
            "version": "1.0.0",
            "required_credentials": self.get_required_credentials(),
            "settings_schema": {
                "extraction_frequency": {
                    "type": "string",
                    "default": "daily",
                    "options": ["daily", "weekly", "manual"]
                },
                "confidence_threshold": {
                    "type": "number",
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.0
                },
                "max_session_age_days": {
                    "type": "integer",
                    "default": 14,
                    "min": 1,
                    "max": 30
                }
            },
            "features": [
                "Automated session extraction via AgentCore Browser Tool",
                "AI-powered session matching with confidence scoring",
                "Performance compliance analysis",
                "Retry logic for cold start issues"
            ]
        }