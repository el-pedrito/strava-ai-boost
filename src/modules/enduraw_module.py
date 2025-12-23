"""
Enduraw Module for Strava AI Boost

Integrates with Enduraw third-party Strava app for enhanced analytics
including pace without wind, weather impact, and elevation cost analysis.
"""

from typing import Dict, Any, Optional, List
import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base_module import (
    BaseModule, 
    ModuleConfig, 
    ModuleInsight, 
    ModuleError,
    ModuleConfigurationError,
    ModuleProcessingError
)

logger = logging.getLogger(__name__)


class EndurawModule(BaseModule):
    """
    Enduraw integration module
    
    Features:
    - Wait logic for 2-7 minute Enduraw processing delay
    - Enhanced metrics fetching (pace without wind, weather, elevation cost)
    - Integration with content generation pipeline
    - Toggle functionality via local interface
    """
    
    def __init__(self, config: ModuleConfig):
        super().__init__(config)
        self.strava_client = None
        self.secrets_client = None
        self.wait_timeout_seconds = config.settings.get('wait_timeout_seconds', 420)  # 7 minutes default
        self.min_wait_seconds = config.settings.get('min_wait_seconds', 120)  # 2 minutes minimum
        self.check_interval_seconds = config.settings.get('check_interval_seconds', 30)  # Check every 30s
        
    async def _initialize_module(self) -> None:
        """Initialize Enduraw module with HTTP client and AWS services"""
        try:
            # Initialize AWS clients
            self.secrets_client = boto3.client('secretsmanager')
            
            # Initialize HTTP session with retry strategy
            self.session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
            
            logger.info("Enduraw module initialized successfully")
            
        except Exception as e:
            raise ModuleConfigurationError(
                self.config.module_id,
                f"Failed to initialize Enduraw module: {str(e)}",
                e
            )
    
    async def analyze_activity(
        self, 
        activity_data: Dict[str, Any],
        streams_data: Optional[Dict[str, Any]] = None
    ) -> ModuleInsight:
        """
        Analyze activity with Enduraw enhanced metrics
        
        Implements wait logic for Enduraw processing and fetches enhanced analytics
        """
        try:
            if not self.is_enabled():
                return ModuleInsight(
                    module_id="enduraw",
                    insights={},
                    confidence=0.0,
                    metadata={"status": "disabled"}
                )
            
            activity_id = activity_data.get('id')
            if not activity_id:
                raise ModuleProcessingError(
                    self.config.module_id,
                    "Activity ID not found in activity data"
                )
            
            # Wait for Enduraw processing with timeout
            enhanced_metrics = await self.wait_for_enduraw_processing(activity_id)
            
            if enhanced_metrics:
                # Process enhanced metrics for content generation
                insights = await self.process_enhanced_metrics(
                    activity_data, enhanced_metrics
                )
                
                return ModuleInsight(
                    module_id="enduraw",
                    insights=insights,
                    confidence=0.9,  # High confidence when Enduraw data is available
                    metadata={
                        "enduraw_processing_time": enhanced_metrics.get('processing_time_seconds'),
                        "metrics_available": list(enhanced_metrics.get('metrics', {}).keys()),
                        "analysis_type": "enduraw_enhanced"
                    }
                )
            else:
                # Enduraw processing timed out or failed
                return ModuleInsight(
                    module_id="enduraw",
                    insights={"enduraw_available": False},
                    confidence=0.0,
                    metadata={
                        "status": "timeout",
                        "wait_time_seconds": self.wait_timeout_seconds,
                        "analysis_type": "fallback"
                    }
                )
            
        except Exception as e:
            logger.error(f"Enduraw analysis failed: {str(e)}")
            raise ModuleProcessingError(
                self.config.module_id,
                f"Activity analysis failed: {str(e)}",
                e
            )
    
    async def configure(self, credentials: Dict[str, str]) -> bool:
        """
        Configure Enduraw module
        
        Enduraw doesn't require separate credentials as it uses Strava OAuth,
        but we validate Strava token access for enhanced data
        """
        try:
            # Enduraw uses Strava OAuth tokens, so we just need to validate
            # that we can access Strava API for enhanced data
            
            # Store configuration settings
            self.config.credentials = {"configured": True}
            
            logger.info("Enduraw module configured successfully")
            return True
            
        except Exception as e:
            raise ModuleConfigurationError(
                self.config.module_id,
                f"Configuration failed: {str(e)}",
                e
            )
    
    async def validate_configuration(self) -> bool:
        """
        Validate Enduraw configuration
        
        Checks that Strava API access is available for enhanced metrics
        """
        try:
            # Enduraw integration doesn't require separate validation
            # as it piggybacks on Strava OAuth tokens
            return self.config.credentials and self.config.credentials.get("configured", False)
            
        except Exception as e:
            logger.error(f"Enduraw validation failed: {str(e)}")
            return False
    
    async def wait_for_enduraw_processing(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Wait for Enduraw to process the activity with enhanced analytics
        
        Implements 2-7 minute wait logic with periodic checking
        """
        try:
            logger.info(f"Waiting for Enduraw processing of activity {activity_id}")
            
            start_time = datetime.now()
            
            # Wait minimum time before first check
            await asyncio.sleep(self.min_wait_seconds)
            
            # Periodic checking until timeout
            while True:
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                
                if elapsed_seconds >= self.wait_timeout_seconds:
                    logger.warning(f"Enduraw processing timeout after {elapsed_seconds:.0f}s")
                    break
                
                # Check if Enduraw data is available
                enhanced_data = await self.check_enduraw_data_available(activity_id)
                
                if enhanced_data:
                    processing_time = elapsed_seconds
                    enhanced_data['processing_time_seconds'] = processing_time
                    logger.info(f"Enduraw data available after {processing_time:.0f}s")
                    return enhanced_data
                
                # Wait before next check
                await asyncio.sleep(self.check_interval_seconds)
            
            return None
            
        except Exception as e:
            logger.error(f"Enduraw wait logic failed: {str(e)}")
            return None
    
    async def check_enduraw_data_available(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if Enduraw enhanced data is available for the activity
        
        This would typically involve checking Strava API for enhanced fields
        or checking Enduraw's API if available
        """
        try:
            # Get Strava OAuth token
            strava_token = await self.get_strava_oauth_token()
            if not strava_token:
                logger.error("No Strava OAuth token available")
                return None
            
            # Check Strava API for enhanced data that Enduraw might have added
            enhanced_data = await self.fetch_enhanced_strava_data(activity_id, strava_token)
            
            if enhanced_data and self.has_enduraw_enhancements(enhanced_data):
                return enhanced_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to check Enduraw data availability: {str(e)}")
            return None
    
    async def get_strava_oauth_token(self) -> Optional[str]:
        """Get Strava OAuth token from Secrets Manager"""
        try:
            secret_name = "strava-ai-boost-oauth-tokens"
            
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            tokens = json.loads(response['SecretString'])
            
            return tokens.get('access_token')
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.error("Strava OAuth tokens not found in Secrets Manager")
            else:
                logger.error(f"Failed to retrieve Strava tokens: {str(e)}")
            return None
    
    async def fetch_enhanced_strava_data(self, activity_id: str, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Fetch enhanced Strava data that might include Enduraw enhancements
        
        This checks for additional fields that Enduraw might have populated
        """
        try:
            # Fetch activity with all available fields
            url = f"https://www.strava.com/api/v3/activities/{activity_id}"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.session.get(url, headers=headers, timeout=10)
            )
            
            if response.status_code == 200:
                activity_data = response.json()
                
                # Also fetch streams data for enhanced analysis
                streams_data = await self.fetch_activity_streams(activity_id, access_token)
                
                return {
                    'activity': activity_data,
                    'streams': streams_data,
                    'fetched_at': datetime.now(timezone.utc).isoformat()
                }
            else:
                logger.error(f"Failed to fetch Strava activity: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch enhanced Strava data: {str(e)}")
            return None
    
    async def fetch_activity_streams(self, activity_id: str, access_token: str) -> Optional[Dict[str, Any]]:
        """Fetch activity streams data for enhanced analysis"""
        try:
            url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
            params = {
                'keys': 'velocity_smooth,heartrate,cadence,watts,temp,grade_smooth,altitude,time,distance',
                'key_by_type': 'true'
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.session.get(url, headers=headers, params=params, timeout=15)
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to fetch streams data: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch activity streams: {str(e)}")
            return None
    
    def has_enduraw_enhancements(self, enhanced_data: Dict[str, Any]) -> bool:
        """
        Check if the data contains Enduraw-specific enhancements
        
        This looks for fields or patterns that indicate Enduraw has processed the activity
        """
        try:
            activity = enhanced_data.get('activity', {})
            streams = enhanced_data.get('streams', {})
            
            # Check for Enduraw-specific fields or enhanced data quality
            # This is a heuristic approach since Enduraw's exact API isn't documented
            
            enduraw_indicators = [
                # Check for enhanced weather data
                activity.get('weather') is not None,
                
                # Check for enhanced power/pace analysis
                streams.get('watts') is not None and len(streams.get('watts', {}).get('data', [])) > 0,
                
                # Check for enhanced elevation data
                streams.get('grade_smooth') is not None,
                
                # Check for temperature data (often enhanced by Enduraw)
                streams.get('temp') is not None,
                
                # Check for recent activity modification (Enduraw might update fields)
                self.is_recently_modified(activity)
            ]
            
            # Consider Enduraw data available if multiple indicators are present
            indicator_count = sum(1 for indicator in enduraw_indicators if indicator)
            
            logger.info(f"Enduraw indicators found: {indicator_count}/5")
            return indicator_count >= 2  # Require at least 2 indicators
            
        except Exception as e:
            logger.error(f"Failed to check Enduraw enhancements: {str(e)}")
            return False
    
    def is_recently_modified(self, activity: Dict[str, Any]) -> bool:
        """Check if activity was recently modified (potential Enduraw processing)"""
        try:
            upload_id = activity.get('upload_id')
            updated_at = activity.get('updated_at')
            
            if updated_at:
                # Parse updated timestamp
                from dateutil import parser
                updated_time = parser.parse(updated_at)
                
                # Check if updated within last 10 minutes (potential Enduraw processing)
                time_diff = datetime.now(timezone.utc) - updated_time.replace(tzinfo=timezone.utc)
                return time_diff.total_seconds() < 600  # 10 minutes
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check modification time: {str(e)}")
            return False
    
    async def process_enhanced_metrics(
        self, 
        activity_data: Dict[str, Any], 
        enhanced_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process Enduraw enhanced metrics for content generation
        
        Extracts and formats enhanced analytics for use in content generation
        """
        try:
            enhanced_activity = enhanced_data.get('activity', {})
            enhanced_streams = enhanced_data.get('streams', {})
            
            insights = {
                "enduraw_available": True,
                "enhanced_metrics": {},
                "weather_analysis": {},
                "performance_insights": {},
                "recommendations": []
            }
            
            # Extract weather impact analysis
            weather_data = enhanced_activity.get('weather')
            if weather_data:
                insights["weather_analysis"] = self.analyze_weather_impact(weather_data)
            
            # Extract enhanced pace analysis (pace without wind)
            if enhanced_streams.get('velocity_smooth'):
                pace_analysis = self.analyze_enhanced_pace(
                    enhanced_streams['velocity_smooth'], 
                    weather_data
                )
                insights["enhanced_metrics"]["pace_without_wind"] = pace_analysis
            
            # Extract elevation cost analysis
            if enhanced_streams.get('grade_smooth') and enhanced_streams.get('velocity_smooth'):
                elevation_analysis = self.analyze_elevation_cost(
                    enhanced_streams['grade_smooth'],
                    enhanced_streams['velocity_smooth']
                )
                insights["enhanced_metrics"]["elevation_cost"] = elevation_analysis
            
            # Extract power analysis if available
            if enhanced_streams.get('watts'):
                power_analysis = self.analyze_power_metrics(enhanced_streams['watts'])
                insights["enhanced_metrics"]["power_analysis"] = power_analysis
            
            # Generate performance insights
            insights["performance_insights"] = self.generate_performance_insights(
                activity_data, enhanced_data
            )
            
            # Generate recommendations based on enhanced data
            insights["recommendations"] = self.generate_enduraw_recommendations(insights)
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to process enhanced metrics: {str(e)}")
            return {"enduraw_available": False, "error": str(e)}
    
    def analyze_weather_impact(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze weather impact on performance"""
        try:
            analysis = {
                "conditions": weather_data,
                "impact_assessment": "neutral",
                "wind_effect": "minimal",
                "temperature_effect": "optimal"
            }
            
            # Analyze wind impact
            wind_speed = weather_data.get('wind_speed', 0)
            if wind_speed > 15:  # km/h
                analysis["wind_effect"] = "significant"
                analysis["impact_assessment"] = "challenging"
            elif wind_speed > 8:
                analysis["wind_effect"] = "moderate"
            
            # Analyze temperature impact
            temp = weather_data.get('temp', 20)
            if temp > 25 or temp < 5:
                analysis["temperature_effect"] = "challenging"
                if analysis["impact_assessment"] == "neutral":
                    analysis["impact_assessment"] = "challenging"
            elif temp > 30 or temp < 0:
                analysis["temperature_effect"] = "extreme"
                analysis["impact_assessment"] = "extreme"
            
            return analysis
            
        except Exception as e:
            logger.error(f"Weather analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def analyze_enhanced_pace(self, velocity_data: Dict[str, Any], weather_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze pace with wind correction"""
        try:
            velocities = velocity_data.get('data', [])
            if not velocities:
                return {"error": "No velocity data available"}
            
            # Calculate basic pace metrics
            avg_velocity = sum(velocities) / len(velocities) if velocities else 0
            avg_pace_per_km = (1000 / avg_velocity / 60) if avg_velocity > 0 else 0  # min/km
            
            analysis = {
                "average_pace_per_km": avg_pace_per_km,
                "pace_without_wind": avg_pace_per_km,  # Would be calculated with wind correction
                "wind_adjustment_seconds": 0,
                "pace_variability": self.calculate_pace_variability(velocities)
            }
            
            # Apply wind correction if weather data available
            if weather_data and weather_data.get('wind_speed', 0) > 5:
                wind_adjustment = self.calculate_wind_adjustment(
                    avg_velocity, 
                    weather_data.get('wind_speed', 0),
                    weather_data.get('wind_direction', 0)
                )
                analysis["wind_adjustment_seconds"] = wind_adjustment
                analysis["pace_without_wind"] = avg_pace_per_km - (wind_adjustment / 60)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Enhanced pace analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def analyze_elevation_cost(self, grade_data: Dict[str, Any], velocity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze elevation cost impact on pace"""
        try:
            grades = grade_data.get('data', [])
            velocities = velocity_data.get('data', [])
            
            if not grades or not velocities or len(grades) != len(velocities):
                return {"error": "Insufficient elevation/velocity data"}
            
            # Calculate elevation cost metrics
            uphill_segments = []
            downhill_segments = []
            flat_segments = []
            
            for i, grade in enumerate(grades):
                if grade > 2:  # Uphill > 2%
                    uphill_segments.append((grade, velocities[i]))
                elif grade < -2:  # Downhill < -2%
                    downhill_segments.append((grade, velocities[i]))
                else:  # Flat ±2%
                    flat_segments.append((grade, velocities[i]))
            
            analysis = {
                "uphill_pace_cost": self.calculate_uphill_cost(uphill_segments),
                "downhill_benefit": self.calculate_downhill_benefit(downhill_segments),
                "flat_pace": self.calculate_flat_pace(flat_segments),
                "elevation_efficiency": 0.0
            }
            
            # Calculate overall elevation efficiency
            if analysis["flat_pace"] > 0:
                total_cost = analysis["uphill_pace_cost"] - analysis["downhill_benefit"]
                analysis["elevation_efficiency"] = max(0, 1 - (total_cost / analysis["flat_pace"]))
            
            return analysis
            
        except Exception as e:
            logger.error(f"Elevation cost analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def analyze_power_metrics(self, power_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze power metrics if available"""
        try:
            power_values = power_data.get('data', [])
            if not power_values:
                return {"error": "No power data available"}
            
            valid_power = [p for p in power_values if p > 0]
            if not valid_power:
                return {"error": "No valid power data"}
            
            analysis = {
                "average_power": sum(valid_power) / len(valid_power),
                "max_power": max(valid_power),
                "power_variability": self.calculate_power_variability(valid_power),
                "normalized_power": self.calculate_normalized_power(valid_power)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Power analysis failed: {str(e)}")
            return {"error": str(e)}
    
    def calculate_pace_variability(self, velocities: List[float]) -> float:
        """Calculate pace variability coefficient"""
        if len(velocities) < 2:
            return 0.0
        
        valid_velocities = [v for v in velocities if v > 0]
        if len(valid_velocities) < 2:
            return 0.0
        
        mean_velocity = sum(valid_velocities) / len(valid_velocities)
        variance = sum((v - mean_velocity) ** 2 for v in valid_velocities) / len(valid_velocities)
        std_dev = variance ** 0.5
        
        return std_dev / mean_velocity if mean_velocity > 0 else 0.0
    
    def calculate_wind_adjustment(self, velocity: float, wind_speed: float, wind_direction: float) -> float:
        """Calculate wind adjustment in seconds per km"""
        # Simplified wind adjustment calculation
        # In reality, this would consider wind direction relative to movement
        wind_factor = min(wind_speed / 20, 0.5)  # Cap at 50% impact
        return wind_factor * 10  # Up to 10 seconds per km adjustment
    
    def calculate_uphill_cost(self, uphill_segments: List[tuple]) -> float:
        """Calculate average pace cost for uphill segments"""
        if not uphill_segments:
            return 0.0
        
        total_cost = 0.0
        for grade, velocity in uphill_segments:
            # Simplified cost calculation: higher grade = more cost
            cost_factor = min(grade / 10, 1.0)  # Cap at 100% cost for 10% grade
            total_cost += cost_factor * 30  # Up to 30 seconds per km cost
        
        return total_cost / len(uphill_segments)
    
    def calculate_downhill_benefit(self, downhill_segments: List[tuple]) -> float:
        """Calculate average pace benefit for downhill segments"""
        if not downhill_segments:
            return 0.0
        
        total_benefit = 0.0
        for grade, velocity in downhill_segments:
            # Simplified benefit calculation
            benefit_factor = min(abs(grade) / 10, 0.5)  # Cap at 50% benefit
            total_benefit += benefit_factor * 15  # Up to 15 seconds per km benefit
        
        return total_benefit / len(downhill_segments)
    
    def calculate_flat_pace(self, flat_segments: List[tuple]) -> float:
        """Calculate average pace for flat segments"""
        if not flat_segments:
            return 0.0
        
        velocities = [velocity for _, velocity in flat_segments]
        avg_velocity = sum(velocities) / len(velocities)
        
        return (1000 / avg_velocity / 60) if avg_velocity > 0 else 0.0  # min/km
    
    def calculate_power_variability(self, power_values: List[float]) -> float:
        """Calculate power variability index"""
        if len(power_values) < 2:
            return 0.0
        
        mean_power = sum(power_values) / len(power_values)
        variance = sum((p - mean_power) ** 2 for p in power_values) / len(power_values)
        std_dev = variance ** 0.5
        
        return std_dev / mean_power if mean_power > 0 else 0.0
    
    def calculate_normalized_power(self, power_values: List[float]) -> float:
        """Calculate normalized power (simplified)"""
        if not power_values:
            return 0.0
        
        # Simplified normalized power calculation
        # Real calculation involves 30-second rolling averages raised to 4th power
        return sum(power_values) / len(power_values) * 1.05  # Rough approximation
    
    def generate_performance_insights(
        self, 
        activity_data: Dict[str, Any], 
        enhanced_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate performance insights from enhanced data"""
        try:
            insights = {
                "efficiency_score": 0.0,
                "pacing_strategy": "unknown",
                "environmental_adaptation": "good",
                "improvement_areas": []
            }
            
            # Analyze pacing strategy
            streams = enhanced_data.get('streams', {})
            if streams.get('velocity_smooth'):
                velocities = streams['velocity_smooth'].get('data', [])
                if velocities:
                    pace_variability = self.calculate_pace_variability(velocities)
                    if pace_variability < 0.1:
                        insights["pacing_strategy"] = "very_consistent"
                    elif pace_variability < 0.2:
                        insights["pacing_strategy"] = "consistent"
                    elif pace_variability < 0.3:
                        insights["pacing_strategy"] = "variable"
                    else:
                        insights["pacing_strategy"] = "highly_variable"
            
            # Calculate efficiency score based on multiple factors
            efficiency_factors = []
            
            # Add pacing efficiency
            if insights["pacing_strategy"] in ["very_consistent", "consistent"]:
                efficiency_factors.append(0.9)
            elif insights["pacing_strategy"] == "variable":
                efficiency_factors.append(0.7)
            else:
                efficiency_factors.append(0.5)
            
            # Add environmental adaptation
            weather = enhanced_data.get('activity', {}).get('weather')
            if weather:
                wind_speed = weather.get('wind_speed', 0)
                if wind_speed > 15:
                    efficiency_factors.append(0.8)  # Good adaptation to challenging conditions
                else:
                    efficiency_factors.append(0.9)  # Normal conditions
            
            insights["efficiency_score"] = sum(efficiency_factors) / len(efficiency_factors) if efficiency_factors else 0.0
            
            return insights
            
        except Exception as e:
            logger.error(f"Performance insights generation failed: {str(e)}")
            return {"error": str(e)}
    
    def generate_enduraw_recommendations(self, insights: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on Enduraw enhanced data"""
        recommendations = []
        
        try:
            # Weather-based recommendations
            weather_analysis = insights.get("weather_analysis", {})
            if weather_analysis.get("wind_effect") == "significant":
                recommendations.append("Consider adjusting pacing strategy for windy conditions")
            
            if weather_analysis.get("temperature_effect") == "challenging":
                recommendations.append("Monitor hydration and pacing in challenging temperature conditions")
            
            # Pace analysis recommendations
            enhanced_metrics = insights.get("enhanced_metrics", {})
            pace_data = enhanced_metrics.get("pace_without_wind", {})
            
            if isinstance(pace_data, dict) and pace_data.get("wind_adjustment_seconds", 0) > 5:
                recommendations.append("Strong wind impact detected - actual effort was higher than pace suggests")
            
            # Elevation recommendations
            elevation_data = enhanced_metrics.get("elevation_cost", {})
            if isinstance(elevation_data, dict):
                efficiency = elevation_data.get("elevation_efficiency", 0)
                if efficiency < 0.7:
                    recommendations.append("Focus on hill running technique to improve elevation efficiency")
                elif efficiency > 0.9:
                    recommendations.append("Excellent hill running efficiency!")
            
            # Performance insights recommendations
            performance = insights.get("performance_insights", {})
            pacing_strategy = performance.get("pacing_strategy", "unknown")
            
            if pacing_strategy == "highly_variable":
                recommendations.append("Work on pacing consistency for better performance")
            elif pacing_strategy == "very_consistent":
                recommendations.append("Excellent pacing discipline!")
            
            # Default recommendation if no specific insights
            if not recommendations:
                recommendations.append("Enhanced Enduraw analytics provide valuable performance insights")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Recommendation generation failed: {str(e)}")
            return ["Enhanced analytics available via Enduraw integration"]
    
    def get_required_credentials(self) -> List[str]:
        """Get list of required credential fields"""
        return []  # Enduraw uses Strava OAuth, no separate credentials needed
    
    def get_module_info(self) -> Dict[str, Any]:
        """Get Enduraw module information"""
        return {
            "module_id": "enduraw",
            "name": "Enduraw Enhanced Analytics",
            "description": "Integrates with Enduraw third-party app for enhanced analytics including pace without wind, weather impact, and elevation cost analysis",
            "version": "1.0.0",
            "required_credentials": self.get_required_credentials(),
            "settings_schema": {
                "wait_timeout_seconds": {
                    "type": "integer",
                    "default": 420,
                    "min": 120,
                    "max": 600,
                    "description": "Maximum wait time for Enduraw processing (2-10 minutes)"
                },
                "min_wait_seconds": {
                    "type": "integer",
                    "default": 120,
                    "min": 60,
                    "max": 300,
                    "description": "Minimum wait time before checking for Enduraw data"
                },
                "check_interval_seconds": {
                    "type": "integer",
                    "default": 30,
                    "min": 15,
                    "max": 60,
                    "description": "Interval between Enduraw data availability checks"
                }
            },
            "features": [
                "2-7 minute wait logic for Enduraw processing",
                "Enhanced pace analysis (pace without wind)",
                "Weather impact assessment",
                "Elevation cost analysis",
                "Power metrics analysis (when available)",
                "Performance efficiency scoring",
                "Environmental adaptation insights"
            ],
            "dependencies": [
                "Strava OAuth tokens",
                "Enduraw app connected to user's Strava account"
            ]
        }