"""
Integration Utilities for Strava AI Boost

Provides high-level integration functions that connect all utility classes
and provide comprehensive system functionality. Implements Requirements 8.1, 8.4
for proper integration of utility classes with error handling and monitoring.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, UTC
import logging
import asyncio
from contextlib import contextmanager

from .strava_client import StravaAPIClient, create_strava_client_from_env
from .oauth_handler import StravaOAuthHandler, create_oauth_handler_from_env
from .rate_limiter import StravaRateLimiter, create_rate_limiter_from_env
from .secrets_manager import StravaTokenManager, create_token_manager_from_env
from .data_transformers import (
    StravaDataTransformer, DataQualityReport, create_data_transformer,
    DataValidator, create_data_validator
)
from .monitoring import (
    CloudWatchMetrics, PerformanceTracker, create_cloudwatch_metrics,
    create_performance_tracker
)
from .monitoring import (
    CloudWatchMetrics, SystemHealthMonitor, PerformanceTracker,
    create_cloudwatch_metrics, create_health_monitor, create_performance_tracker
)
from .data_models import (
    ActivityData, StreamsData, ProcessingStatus,
    ValidationError, ProcessingError, EnhancedContent
)

logger = logging.getLogger(__name__)


class IntegratedStravaClient:
    """
    Integrated Strava client with comprehensive error handling, monitoring,
    and data transformation capabilities.
    
    Combines all utility classes into a single, easy-to-use interface.
    """
    
    def __init__(self,
                 strava_client: Optional[StravaAPIClient] = None,
                 oauth_handler: Optional[StravaOAuthHandler] = None,
                 rate_limiter: Optional[StravaRateLimiter] = None,
                 token_manager: Optional[StravaTokenManager] = None,
                 data_transformer: Optional[StravaDataTransformer] = None,
                 data_validator: Optional[Any] = None,
                 metrics: Optional[CloudWatchMetrics] = None,
                 performance_tracker: Optional[PerformanceTracker] = None,
                 user_id: str = "default"):
        """
        Initialize integrated Strava client.
        
        Args:
            strava_client: Strava API client
            oauth_handler: OAuth handler
            rate_limiter: Rate limiter
            token_manager: Token manager
            data_transformer: Data transformer
            data_validator: Data validator
            metrics: CloudWatch metrics
            performance_tracker: Performance tracker
            user_id: User identifier
        """
        self.user_id = user_id
        
        # Initialize components
        self.strava_client = strava_client or create_strava_client_from_env(user_id)
        self.oauth_handler = oauth_handler or create_oauth_handler_from_env()
        self.rate_limiter = rate_limiter or create_rate_limiter_from_env()
        self.token_manager = token_manager or create_token_manager_from_env()
        self.data_transformer = data_transformer or create_data_transformer()
        self.data_validator = data_validator or create_data_validator()
        self.metrics = metrics or create_cloudwatch_metrics()
        self.performance_tracker = performance_tracker or create_performance_tracker()
    
    @contextmanager
    def _track_operation(self, operation_name: str):
        """Context manager for tracking operation performance"""
        start_time = datetime.now(UTC)
        success = False
        error = None
        
        try:
            yield
            success = True
        except Exception as e:
            error = e
            raise
        finally:
            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Track performance
            self.performance_tracker.track_operation(
                operation_name=operation_name,
                duration_ms=duration_ms,
                success=success,
                metadata={'user_id': self.user_id, 'error': str(error) if error else None}
            )
            
            # Record metrics
            self.metrics.record_api_call(
                api_name="Strava",
                success=success,
                response_time_ms=duration_ms
            )
            
            if error:
                self.metrics.record_error(
                    component="IntegratedStravaClient",
                    error_type=type(error).__name__,
                    error_message=str(error)
                )
    
    async def get_activity(self, activity_id: str) -> Dict[str, Any]:
        """
        Get activity data with rate limiting.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Activity data dictionary
        """
        with self._track_operation("get_activity"):
            # Check rate limits and wait if needed
            self.rate_limiter.wait_if_needed()
            
            # Get activity data
            response = await self.strava_client.get_activity(activity_id)
            
            # Record the request
            self.rate_limiter.record_request()
            
            return response.data if hasattr(response, 'data') else response
    
    async def get_activity_streams(self, activity_id: str) -> Dict[str, Any]:
        """
        Get activity streams data with rate limiting.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Streams data dictionary
        """
        with self._track_operation("get_activity_streams"):
            # Check rate limits and wait if needed
            self.rate_limiter.wait_if_needed()
            
            # Get streams data
            response = await self.strava_client.get_activity_streams(activity_id)
            
            # Record the request
            self.rate_limiter.record_request()
            
            return response.data if hasattr(response, 'data') else response
    
    async def get_activity_with_retry(self, activity_id: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Get activity data with retry logic.
        
        Args:
            activity_id: Strava activity ID
            max_retries: Maximum number of retry attempts
            
        Returns:
            Activity data dictionary
        """
        for attempt in range(max_retries):
            try:
                return await self.get_activity(activity_id)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Attempt {attempt + 1} failed for activity {activity_id}: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    
    def get_activity_with_validation(self, activity_id: str) -> Tuple[ActivityData, List[ValidationError]]:
        """
        Get activity data with comprehensive validation.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Tuple of (ActivityData, validation_errors)
            
        Raises:
            Exception: If activity cannot be retrieved or transformed
        """
        with self._track_operation("get_activity_with_validation"):
            # Get raw activity data
            response = self.strava_client.get_activity(activity_id)
            raw_activity = response.data
            
            # Transform to structured data
            activity_data = self.data_transformer.transform_raw_activity(raw_activity)
            
            # Validate data
            validation_errors = self.data_validator.validate_activity_data(activity_data)
            
            logger.info(f"Retrieved and validated activity {activity_id} with {len(validation_errors)} validation errors")
            
            return activity_data, validation_errors
    
    def get_activity_with_streams_and_validation(self, 
                                               activity_id: str) -> Tuple[ActivityData, Optional[StreamsData], List[ValidationError], DataQualityReport]:
        """
        Get activity with streams data and comprehensive validation.
        
        Args:
            activity_id: Strava activity ID
            
        Returns:
            Tuple of (ActivityData, StreamsData, validation_errors, quality_report)
        """
        with self._track_operation("get_activity_with_streams_and_validation"):
            # Get activity and streams data
            combined_data = self.strava_client.get_activity_with_streams(activity_id)
            
            # Transform activity data
            activity_data = self.data_transformer.transform_raw_activity(combined_data['activity'])
            
            # Transform streams data if available
            streams_data = None
            if combined_data['streams_available']:
                streams_data = self.data_transformer.transform_raw_streams(combined_data['streams'])
            
            # Validate data
            validation_errors = self.data_validator.validate_activity_data(activity_data)
            if streams_data:
                streams_errors = self.data_validator.validate_streams_data(streams_data)
                validation_errors.extend(streams_errors)
            
            # Assess data quality
            quality_report = self.data_validator.assess_data_quality(activity_data, streams_data)
            
            logger.info(f"Retrieved activity {activity_id} with streams, {len(validation_errors)} validation errors, quality score: {quality_report.overall_score:.2f}")
            
            return activity_data, streams_data, validation_errors, quality_report
    
    def update_activity_with_validation(self, 
                                      activity_id: str,
                                      name: Optional[str] = None,
                                      description: Optional[str] = None) -> bool:
        """
        Update activity with validation and error handling.
        
        Args:
            activity_id: Strava activity ID
            name: New activity name
            description: New activity description
            
        Returns:
            True if successful, False otherwise
        """
        with self._track_operation("update_activity_with_validation"):
            try:
                # Validate inputs
                if name is not None and len(name.strip()) == 0:
                    raise ValueError("Activity name cannot be empty")
                
                if description is not None and len(description) > 10000:
                    raise ValueError("Activity description too long (max 10000 characters)")
                
                # Update activity
                response = self.strava_client.update_activity(
                    activity_id=activity_id,
                    name=name,
                    description=description
                )
                
                logger.info(f"Successfully updated activity {activity_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to update activity {activity_id}: {e}")
                return False
    
    def test_connection_comprehensive(self) -> Dict[str, Any]:
        """
        Comprehensive connection test with detailed status.
        
        Returns:
            Dictionary with detailed connection status
        """
        with self._track_operation("test_connection_comprehensive"):
            # Test basic connection
            connection_result = self.strava_client.test_connection()
            
            # Get token status
            token_status = self.token_manager.get_token_status(self.user_id)
            
            # Get rate limit status
            rate_limit_status = self.rate_limiter.get_comprehensive_status()
            
            # Get OAuth connection status
            oauth_status = self.oauth_handler.get_connection_status(self.user_id)
            
            return {
                'connection': connection_result,
                'tokens': token_status,
                'rate_limits': rate_limit_status,
                'oauth': oauth_status,
                'timestamp': datetime.now(UTC).isoformat()
            }
    
    def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get performance summary for all operations.
        
        Args:
            hours: Time window in hours
            
        Returns:
            Dictionary with performance summary
        """
        operations = [
            "get_activity_with_validation",
            "get_activity_with_streams_and_validation",
            "update_activity_with_validation",
            "test_connection_comprehensive"
        ]
        
        summary = {}
        for operation in operations:
            try:
                summary[operation] = self.performance_tracker.get_performance_summary(operation, hours)
            except Exception as e:
                summary[operation] = {'error': str(e)}
        
        return summary


class SystemMonitor:
    """
    Comprehensive system monitoring that integrates all monitoring capabilities.
    
    Provides unified system health monitoring, alerting, and status reporting.
    """
    
    def __init__(self,
                 health_monitor: Optional[SystemHealthMonitor] = None,
                 metrics: Optional[CloudWatchMetrics] = None,
                 performance_tracker: Optional[PerformanceTracker] = None,
                 integrated_client: Optional[IntegratedStravaClient] = None):
        """
        Initialize system monitor.
        
        Args:
            health_monitor: System health monitor
            metrics: CloudWatch metrics
            performance_tracker: Performance tracker
            integrated_client: Integrated Strava client
        """
        self.health_monitor = health_monitor or create_health_monitor()
        self.metrics = metrics or create_cloudwatch_metrics()
        self.performance_tracker = performance_tracker or create_performance_tracker()
        self.integrated_client = integrated_client
    
    def check_strava_connectivity(self) -> bool:
        """Check Strava API connectivity"""
        try:
            if self.integrated_client:
                result = self.integrated_client.test_connection_comprehensive()
                return result['connection']['connected']
            return False
        except Exception as e:
            logger.error(f"Error checking Strava connectivity: {e}")
            return False
    
    def check_aws_services(self) -> Dict[str, bool]:
        """Check AWS services health"""
        services_status = {}
        
        # Check DynamoDB
        try:
            import boto3
            dynamodb = boto3.client('dynamodb')
            dynamodb.list_tables()
            services_status['dynamodb'] = True
        except Exception as e:
            logger.error(f"DynamoDB health check failed: {e}")
            services_status['dynamodb'] = False
        
        # Check Secrets Manager
        try:
            import boto3
            secrets = boto3.client('secretsmanager')
            secrets.list_secrets(MaxResults=1)
            services_status['secrets_manager'] = True
        except Exception as e:
            logger.error(f"Secrets Manager health check failed: {e}")
            services_status['secrets_manager'] = False
        
        # Check CloudWatch
        try:
            import boto3
            cloudwatch = boto3.client('cloudwatch')
            cloudwatch.list_metrics(MaxRecords=1)
            services_status['cloudwatch'] = True
        except Exception as e:
            logger.error(f"CloudWatch health check failed: {e}")
            services_status['cloudwatch'] = False
        
        return services_status
    
    def _check_dynamodb_health(self) -> bool:
        """Check DynamoDB health"""
        try:
            import boto3
            dynamodb = boto3.client('dynamodb')
            dynamodb.list_tables()
            return True
        except Exception as e:
            logger.error(f"DynamoDB health check failed: {e}")
            return False
    
    def _check_secrets_manager_health(self) -> bool:
        """Check Secrets Manager health"""
        try:
            import boto3
            secrets = boto3.client('secretsmanager')
            secrets.list_secrets(MaxResults=1)
            return True
        except Exception as e:
            logger.error(f"Secrets Manager health check failed: {e}")
            return False
    
    def _check_bedrock_health(self) -> bool:
        """Check Bedrock health"""
        try:
            import boto3
            bedrock = boto3.client('bedrock-runtime')
            # Simple check - list foundation models
            bedrock.list_foundation_models()
            return True
        except Exception as e:
            logger.error(f"Bedrock health check failed: {e}")
            return False
    
    def _check_step_functions_health(self) -> bool:
        """Check Step Functions health"""
        try:
            import boto3
            stepfunctions = boto3.client('stepfunctions')
            stepfunctions.list_state_machines(maxResults=1)
            return True
        except Exception as e:
            logger.error(f"Step Functions health check failed: {e}")
            return False
    
    async def check_system_health(self) -> Dict[str, Any]:
        """
        Perform comprehensive system health check.
        
        Returns:
            Dictionary with system health status
        """
        services = {
            'dynamodb': self._check_dynamodb_health(),
            'secrets_manager': self._check_secrets_manager_health(),
            'bedrock': self._check_bedrock_health(),
            'step_functions': self._check_step_functions_health()
        }
        
        # Determine overall status
        healthy_services = sum(1 for status in services.values() if status)
        total_services = len(services)
        
        if healthy_services == total_services:
            overall_status = "healthy"
        elif healthy_services > 0:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"
        
        # Convert boolean to status strings
        service_statuses = {
            name: "healthy" if status else "unhealthy"
            for name, status in services.items()
        }
        
        from datetime import datetime, timezone
        
        return {
            "overall_status": overall_status,
            "services": service_statuses,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def collect_performance_metrics(self) -> Dict[str, Any]:
        """
        Collect system performance metrics.
        
        Returns:
            Dictionary with performance metrics
        """
        import psutil
        from datetime import datetime, timezone
        
        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "memory_usage": psutil.virtual_memory().percent,
            "cpu_usage": psutil.cpu_percent(interval=1),
        }
        
        # Try to get network connections, but handle permission errors gracefully
        try:
            metrics["active_connections"] = len(psutil.net_connections())
        except (psutil.AccessDenied, PermissionError):
            # On macOS, this requires elevated permissions
            metrics["active_connections"] = -1  # Indicate unavailable
        
        metrics["disk_usage"] = psutil.disk_usage('/').percent
        
        # Send metrics to CloudWatch if available
        if self.metrics:
            try:
                self.metrics.put_metric("SystemMemoryUsage", metrics["memory_usage"], "Percent")
                self.metrics.put_metric("SystemCPUUsage", metrics["cpu_usage"], "Percent")
                self.metrics.put_metric("ActiveConnections", metrics["active_connections"], "Count")
            except Exception as e:
                logger.error(f"Failed to send metrics to CloudWatch: {e}")
        
        return metrics
    
    def perform_comprehensive_health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive system health check.
        
        Returns:
            Dictionary with complete system status
        """
        try:
            # Check Strava connectivity
            strava_connected = self.check_strava_connectivity()
            
            # Check AWS services
            aws_services = self.check_aws_services()
            
            # Get health summary
            health_summary = self.health_monitor.get_system_health_summary()
            
            # Get performance data
            performance_summary = {}
            if self.integrated_client:
                performance_summary = self.integrated_client.get_performance_summary(24)
            
            # Create system status
            system_status = SystemStatus(
                strava_connected=strava_connected,
                agentcore_status='unknown',  # Will be updated by AgentCore checks
                lambda_functions_healthy=aws_services.get('lambda', True),
                dynamodb_healthy=aws_services.get('dynamodb', True),
                secrets_manager_healthy=aws_services.get('secrets_manager', True),
                processing_queue_depth=0,  # Will be updated by queue checks
                last_updated=datetime.now(UTC)
            )
            
            # Record health metrics
            self.metrics.put_metric(
                metric_name="SystemHealth",
                value=1 if system_status.overall_health == 'healthy' else 0,
                dimensions={"OverallHealth": system_status.overall_health}
            )
            
            return system_status
            
        except Exception as e:
            logger.error(f"Error performing health check: {e}")
            
            # Return unhealthy status
            return SystemStatus(
                strava_connected=False,
                agentcore_status='unhealthy',
                lambda_functions_healthy=False,
                dynamodb_healthy=False,
                secrets_manager_healthy=False,
                last_updated=datetime.now(UTC)
            )


def create_integrated_strava_client(user_id: str = "default") -> IntegratedStravaClient:
    """
    Create fully integrated Strava client with all utilities.
    
    Args:
        user_id: User identifier
        
    Returns:
        IntegratedStravaClient instance
    """
    return IntegratedStravaClient(user_id=user_id)


def create_system_monitor(integrated_client: Optional[IntegratedStravaClient] = None) -> SystemMonitor:
    """
    Create comprehensive system monitor.
    
    Args:
        integrated_client: Optional integrated Strava client
        
    Returns:
        SystemMonitor instance
    """
    return SystemMonitor(integrated_client=integrated_client)


def validate_and_transform_activity(raw_activity_data: Dict[str, Any]) -> Tuple[ActivityData, List[ValidationError]]:
    """
    Validate and transform raw activity data.
    
    Args:
        raw_activity_data: Raw activity data from Strava API
        
    Returns:
        Tuple of (ActivityData, validation_errors)
    """
    transformer = create_data_transformer()
    validator = create_data_validator()
    
    # Transform data
    activity_data = transformer.transform_raw_activity(raw_activity_data)
    
    # Validate data
    validation_errors = validator.validate_activity_data(activity_data)
    
    return activity_data, validation_errors


def get_comprehensive_system_status() -> Dict[str, Any]:
    """
    Get comprehensive system status including all components.
    
    Returns:
        Dictionary with complete system status
    """
    try:
        # Create system monitor
        monitor = create_system_monitor()
        
        # Perform health check
        system_status = monitor.perform_comprehensive_health_check()
        
        # Get additional status information
        health_summary = monitor.health_monitor.get_system_health_summary()
        
        return {
            'system_status': system_status.model_dump(),
            'health_summary': health_summary,
            'timestamp': datetime.now(UTC).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting comprehensive system status: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat()
        }


# Utility functions for common operations
def setup_logging(level: str = "INFO") -> None:
    """
    Set up logging for the utilities package.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def validate_environment() -> Dict[str, bool]:
    """
    Validate that required environment variables are set.
    
    Returns:
        Dictionary with validation results
    """
    import os
    
    required_vars = [
        'STRAVA_CLIENT_ID',
        'STRAVA_CLIENT_SECRET',
        'AWS_REGION'
    ]
    
    optional_vars = [
        'STRAVA_REDIRECT_URI',
        'OAUTH_SECRETS_NAME',
        'RATE_LIMIT_TABLE_NAME'
    ]
    
    results = {}
    
    for var in required_vars:
        results[var] = bool(os.getenv(var))
    
    for var in optional_vars:
        results[f"{var}_optional"] = bool(os.getenv(var))
    
    results['all_required_set'] = all(results[var] for var in required_vars)
    
    return results