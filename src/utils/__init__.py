"""
Strava AI Boost Utilities Package

Comprehensive utility classes for data handling, API integration,
monitoring, and system management.
"""

from .data_models import (
    # Core data models
    ActivityData, StreamsData, ProcessingStatus, ModuleConfig,
    CampusCoachSession, EndurawData, SystemStatus,
    
    # Supporting models
    LatLng, PolylineMap, Gear, SplitMetric, Lap,
    ModuleCredentials, ValidationError, ProcessingError,
    
    # Rate limiting
    StravaRateLimit
)

from .strava_client import (
    StravaAPIClient, StravaAPIError, StravaRateLimitError,
    StravaAuthenticationError, StravaNotFoundError,
    StravaAPIResponse, StreamType,
    create_strava_client_from_env
)

from .oauth_handler import (
    StravaOAuthHandler,
    create_oauth_handler_from_env
)

from .rate_limiter import (
    StravaRateLimiter, RateLimitType, RateLimitStatus,
    create_rate_limiter_from_env
)

from .secrets_manager import (
    SecretsManagerHelper, StravaTokenManager, SecretMetadata,
    create_token_manager_from_env
)

from .data_transformers import (
    StravaDataTransformer, DataValidator, DataExporter,
    DataQualityReport,
    create_data_transformer, create_data_validator, create_data_exporter
)

from .monitoring import (
    CloudWatchMetrics, SystemHealthMonitor, PerformanceTracker,
    MetricData, Alert, AlertSeverity, MetricType,
    create_cloudwatch_metrics, create_health_monitor, create_performance_tracker
)

# Integration functions
from .integration import (
    IntegratedStravaClient, SystemMonitor,
    create_integrated_strava_client,
    create_system_monitor,
    validate_and_transform_activity,
    get_comprehensive_system_status,
    setup_logging,
    validate_environment
)

__all__ = [
    # Data models
    'ActivityData', 'StreamsData', 'ProcessingStatus', 'ModuleConfig',
    'CampusCoachSession', 'EndurawData', 'SystemStatus',
    'LatLng', 'PolylineMap', 'Gear', 'SplitMetric', 'Lap',
    'ModuleCredentials', 'ValidationError', 'ProcessingError',
    'StravaRateLimit',
    
    # API client
    'StravaAPIClient', 'StravaAPIError', 'StravaRateLimitError',
    'StravaAuthenticationError', 'StravaNotFoundError',
    'StravaAPIResponse', 'StreamType',
    'create_strava_client_from_env',
    
    # OAuth
    'StravaOAuthHandler',
    'create_oauth_handler_from_env',
    
    # Rate limiting
    'StravaRateLimiter', 'RateLimitType', 'RateLimitStatus',
    'create_rate_limiter_from_env',
    
    # Secrets management
    'SecretsManagerHelper', 'StravaTokenManager', 'SecretMetadata',
    'create_token_manager_from_env',
    
    # Data transformation
    'StravaDataTransformer', 'DataValidator', 'DataExporter',
    'DataQualityReport',
    'create_data_transformer', 'create_data_validator', 'create_data_exporter',
    
    # Monitoring
    'CloudWatchMetrics', 'SystemHealthMonitor', 'PerformanceTracker',
    'MetricData', 'Alert', 'AlertSeverity', 'MetricType',
    'create_cloudwatch_metrics', 'create_health_monitor', 'create_performance_tracker',
    
    # Integration
    'IntegratedStravaClient', 'SystemMonitor',
    'create_integrated_strava_client',
    'create_system_monitor',
    'validate_and_transform_activity',
    'get_comprehensive_system_status',
    'setup_logging',
    'validate_environment'
]