"""
Monitoring and Alerting Integration

Provides comprehensive monitoring, alerting, and observability utilities
for the Strava AI Boost system. Implements Requirements 8.1, 8.4 for
monitoring and alerting integration.
"""

import boto3
from botocore.exceptions import ClientError
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta, UTC
import json
import logging
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """CloudWatch metric types"""
    COUNT = "Count"
    GAUGE = "None"
    RATE = "Count/Second"
    DURATION = "Milliseconds"
    BYTES = "Bytes"
    PERCENT = "Percent"


@dataclass
class MetricData:
    """CloudWatch metric data point"""
    metric_name: str
    value: float
    unit: MetricType
    timestamp: Optional[datetime] = None
    dimensions: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)


@dataclass
class Alert:
    """System alert information"""
    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    component: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class CloudWatchMetrics:
    """
    CloudWatch metrics publisher for system monitoring.
    
    Publishes custom metrics for tracking system performance,
    errors, and business metrics.
    """
    
    def __init__(self, 
                 namespace: str = "StravaAIBoost",
                 region_name: str = "eu-west-1"):
        """
        Initialize CloudWatch metrics publisher.
        
        Args:
            namespace: CloudWatch namespace for metrics
            region_name: AWS region
        """
        self.namespace = namespace
        self.region_name = region_name
        self.cloudwatch = boto3.client('cloudwatch', region_name=region_name)
        self._metric_buffer = []
        self._buffer_size = 20  # CloudWatch limit
    
    def put_metric(self, 
                   metric_name: str,
                   value: float,
                   unit: MetricType = MetricType.COUNT,
                   dimensions: Optional[Dict[str, str]] = None,
                   timestamp: Optional[datetime] = None) -> bool:
        """
        Put a single metric to CloudWatch.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Metric unit type
            dimensions: Metric dimensions
            timestamp: Metric timestamp (defaults to now)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            metric_data = MetricData(
                metric_name=metric_name,
                value=value,
                unit=unit,
                dimensions=dimensions or {},
                timestamp=timestamp
            )
            
            self._metric_buffer.append(metric_data)
            
            # Flush buffer if full
            if len(self._metric_buffer) >= self._buffer_size:
                return self.flush_metrics()
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding metric {metric_name}: {e}")
            return False
    
    def put_metrics_batch(self, metrics: List[MetricData]) -> bool:
        """
        Put multiple metrics to CloudWatch in batch.
        
        Args:
            metrics: List of MetricData objects
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._metric_buffer.extend(metrics)
            return self.flush_metrics()
            
        except Exception as e:
            logger.error(f"Error adding metrics batch: {e}")
            return False
    
    def flush_metrics(self) -> bool:
        """
        Flush buffered metrics to CloudWatch.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._metric_buffer:
            return True
        
        try:
            # Prepare metric data for CloudWatch
            metric_data = []
            
            for metric in self._metric_buffer:
                data_point = {
                    'MetricName': metric.metric_name,
                    'Value': metric.value,
                    'Unit': metric.unit.value,
                    'Timestamp': metric.timestamp
                }
                
                if metric.dimensions:
                    data_point['Dimensions'] = [
                        {'Name': k, 'Value': v} 
                        for k, v in metric.dimensions.items()
                    ]
                
                metric_data.append(data_point)
            
            # Send to CloudWatch in batches
            batch_size = 20  # CloudWatch limit
            for i in range(0, len(metric_data), batch_size):
                batch = metric_data[i:i + batch_size]
                
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
            
            logger.debug(f"Flushed {len(self._metric_buffer)} metrics to CloudWatch")
            self._metric_buffer.clear()
            return True
            
        except ClientError as e:
            logger.error(f"Error flushing metrics to CloudWatch: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error flushing metrics: {e}")
            return False
    
    def record_activity_processed(self, 
                                 success: bool,
                                 processing_time_ms: int,
                                 modules_used: List[str]) -> bool:
        """
        Record activity processing metrics.
        
        Args:
            success: Whether processing was successful
            processing_time_ms: Processing time in milliseconds
            modules_used: List of modules that were used
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Record processing count
            self.put_metric(
                metric_name="ActivityProcessed",
                value=1,
                unit=MetricType.COUNT,
                dimensions={"Status": "Success" if success else "Failed"}
            )
            
            # Record processing time
            self.put_metric(
                metric_name="ProcessingTime",
                value=processing_time_ms,
                unit=MetricType.DURATION
            )
            
            # Record module usage
            for module in modules_used:
                self.put_metric(
                    metric_name="ModuleUsage",
                    value=1,
                    unit=MetricType.COUNT,
                    dimensions={"Module": module}
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording activity processing metrics: {e}")
            return False
    
    def record_api_call(self, 
                       api_name: str,
                       success: bool,
                       response_time_ms: int,
                       status_code: Optional[int] = None) -> bool:
        """
        Record API call metrics.
        
        Args:
            api_name: Name of the API (e.g., "Strava", "Bedrock")
            success: Whether the call was successful
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code if applicable
            
        Returns:
            True if successful, False otherwise
        """
        try:
            dimensions = {
                "API": api_name,
                "Status": "Success" if success else "Failed"
            }
            
            if status_code:
                dimensions["StatusCode"] = str(status_code)
            
            # Record API call count
            self.put_metric(
                metric_name="APICall",
                value=1,
                unit=MetricType.COUNT,
                dimensions=dimensions
            )
            
            # Record response time
            self.put_metric(
                metric_name="APIResponseTime",
                value=response_time_ms,
                unit=MetricType.DURATION,
                dimensions={"API": api_name}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording API call metrics: {e}")
            return False
    
    def record_error(self, 
                    component: str,
                    error_type: str,
                    error_message: str) -> bool:
        """
        Record error metrics.
        
        Args:
            component: Component where error occurred
            error_type: Type of error
            error_message: Error message
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.put_metric(
                metric_name="Error",
                value=1,
                unit=MetricType.COUNT,
                dimensions={
                    "Component": component,
                    "ErrorType": error_type
                }
            )
            
            logger.error(f"Recorded error metric: {component}/{error_type} - {error_message}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording error metrics: {e}")
            return False
    
    def record_cost_estimate(self, 
                           service: str,
                           cost_usd: float) -> bool:
        """
        Record cost estimation metrics.
        
        Args:
            service: AWS service name
            cost_usd: Estimated cost in USD
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.put_metric(
                metric_name="EstimatedCost",
                value=cost_usd,
                unit=MetricType.GAUGE,
                dimensions={"Service": service}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error recording cost metrics: {e}")
            return False


class SystemHealthMonitor:
    """
    System health monitoring and alerting.
    
    Monitors system components and generates alerts for issues.
    """
    
    def __init__(self, 
                 metrics: Optional[CloudWatchMetrics] = None,
                 alert_topic_arn: Optional[str] = None):
        """
        Initialize system health monitor.
        
        Args:
            metrics: CloudWatch metrics publisher
            alert_topic_arn: SNS topic ARN for alerts
        """
        self.metrics = metrics or CloudWatchMetrics()
        self.alert_topic_arn = alert_topic_arn
        self.sns = boto3.client('sns') if alert_topic_arn else None
        self.active_alerts: Dict[str, Alert] = {}
    
    def check_component_health(self, 
                             component: str,
                             health_check_func,
                             *args, **kwargs) -> bool:
        """
        Check health of a system component.
        
        Args:
            component: Component name
            health_check_func: Function to check component health
            *args, **kwargs: Arguments for health check function
            
        Returns:
            True if healthy, False otherwise
        """
        try:
            start_time = datetime.now(UTC)
            is_healthy = health_check_func(*args, **kwargs)
            end_time = datetime.now(UTC)
            
            check_duration = (end_time - start_time).total_seconds() * 1000
            
            # Record health check metrics
            self.metrics.put_metric(
                metric_name="HealthCheck",
                value=1 if is_healthy else 0,
                unit=MetricType.GAUGE,
                dimensions={"Component": component}
            )
            
            self.metrics.put_metric(
                metric_name="HealthCheckDuration",
                value=check_duration,
                unit=MetricType.DURATION,
                dimensions={"Component": component}
            )
            
            # Generate alert if unhealthy
            if not is_healthy:
                self.create_alert(
                    alert_id=f"health_{component}",
                    severity=AlertSeverity.ERROR,
                    title=f"{component} Health Check Failed",
                    message=f"Health check for {component} returned unhealthy status",
                    component=component
                )
            else:
                # Resolve alert if component is now healthy
                self.resolve_alert(f"health_{component}")
            
            return is_healthy
            
        except Exception as e:
            logger.error(f"Error checking health for {component}: {e}")
            
            # Record error and create alert
            self.metrics.record_error(component, "HealthCheckError", str(e))
            self.create_alert(
                alert_id=f"health_error_{component}",
                severity=AlertSeverity.CRITICAL,
                title=f"{component} Health Check Error",
                message=f"Health check for {component} failed with error: {str(e)}",
                component=component
            )
            
            return False
    
    def create_alert(self, 
                    alert_id: str,
                    severity: AlertSeverity,
                    title: str,
                    message: str,
                    component: str,
                    metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Create a system alert.
        
        Args:
            alert_id: Unique alert identifier
            severity: Alert severity level
            title: Alert title
            message: Alert message
            component: Component that generated the alert
            metadata: Additional alert metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            alert = Alert(
                alert_id=alert_id,
                severity=severity,
                title=title,
                message=message,
                component=component,
                timestamp=datetime.now(UTC),
                metadata=metadata or {}
            )
            
            # Store active alert
            self.active_alerts[alert_id] = alert
            
            # Send SNS notification if configured
            if self.sns and self.alert_topic_arn:
                self._send_alert_notification(alert)
            
            # Record alert metric
            self.metrics.put_metric(
                metric_name="Alert",
                value=1,
                unit=MetricType.COUNT,
                dimensions={
                    "Severity": severity.value,
                    "Component": component
                }
            )
            
            logger.warning(f"Created alert {alert_id}: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating alert {alert_id}: {e}")
            return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """
        Resolve an active alert.
        
        Args:
            alert_id: Alert identifier to resolve
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.now(UTC)
                
                # Remove from active alerts
                del self.active_alerts[alert_id]
                
                # Record resolution metric
                self.metrics.put_metric(
                    metric_name="AlertResolved",
                    value=1,
                    unit=MetricType.COUNT,
                    dimensions={
                        "Severity": alert.severity.value,
                        "Component": alert.component
                    }
                )
                
                logger.info(f"Resolved alert {alert_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            return False
    
    def _send_alert_notification(self, alert: Alert) -> bool:
        """
        Send alert notification via SNS.
        
        Args:
            alert: Alert to send
            
        Returns:
            True if successful, False otherwise
        """
        try:
            message = {
                "alert_id": alert.alert_id,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "component": alert.component,
                "timestamp": alert.timestamp.isoformat(),
                "metadata": alert.metadata
            }
            
            self.sns.publish(
                TopicArn=self.alert_topic_arn,
                Subject=f"[{alert.severity.value.upper()}] {alert.title}",
                Message=json.dumps(message, indent=2)
            )
            
            return True
            
        except ClientError as e:
            logger.error(f"Error sending alert notification: {e}")
            return False
    
    def get_active_alerts(self) -> List[Alert]:
        """
        Get list of active alerts.
        
        Returns:
            List of active Alert objects
        """
        return list(self.active_alerts.values())
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """
        Get system health summary.
        
        Returns:
            Dictionary with health summary
        """
        active_alerts = self.get_active_alerts()
        
        # Count alerts by severity
        alert_counts = {severity.value: 0 for severity in AlertSeverity}
        for alert in active_alerts:
            alert_counts[alert.severity.value] += 1
        
        # Determine overall health
        if alert_counts['critical'] > 0:
            overall_health = 'critical'
        elif alert_counts['error'] > 0:
            overall_health = 'unhealthy'
        elif alert_counts['warning'] > 0:
            overall_health = 'degraded'
        else:
            overall_health = 'healthy'
        
        return {
            'overall_health': overall_health,
            'active_alerts_count': len(active_alerts),
            'alerts_by_severity': alert_counts,
            'active_alerts': [asdict(alert) for alert in active_alerts],
            'last_updated': datetime.now(UTC).isoformat()
        }


class PerformanceTracker:
    """
    Performance tracking and analysis utilities.
    
    Tracks system performance metrics and provides analysis.
    """
    
    def __init__(self, metrics: Optional[CloudWatchMetrics] = None):
        """
        Initialize performance tracker.
        
        Args:
            metrics: CloudWatch metrics publisher
        """
        self.metrics = metrics or CloudWatchMetrics()
        self.performance_data = {}
    
    def track_operation(self, 
                       operation_name: str,
                       duration_ms: int,
                       success: bool,
                       metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Track performance of an operation.
        
        Args:
            operation_name: Name of the operation
            duration_ms: Operation duration in milliseconds
            success: Whether operation was successful
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Record metrics
            self.metrics.put_metric(
                metric_name="OperationDuration",
                value=duration_ms,
                unit=MetricType.DURATION,
                dimensions={"Operation": operation_name}
            )
            
            self.metrics.put_metric(
                metric_name="OperationCount",
                value=1,
                unit=MetricType.COUNT,
                dimensions={
                    "Operation": operation_name,
                    "Status": "Success" if success else "Failed"
                }
            )
            
            # Store performance data
            if operation_name not in self.performance_data:
                self.performance_data[operation_name] = []
            
            self.performance_data[operation_name].append({
                'timestamp': datetime.now(UTC),
                'duration_ms': duration_ms,
                'success': success,
                'metadata': metadata or {}
            })
            
            # Keep only recent data (last 1000 entries)
            if len(self.performance_data[operation_name]) > 1000:
                self.performance_data[operation_name] = self.performance_data[operation_name][-1000:]
            
            return True
            
        except Exception as e:
            logger.error(f"Error tracking operation {operation_name}: {e}")
            return False
    
    def get_performance_summary(self, 
                              operation_name: str,
                              time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Get performance summary for an operation.
        
        Args:
            operation_name: Name of the operation
            time_window_hours: Time window for analysis in hours
            
        Returns:
            Dictionary with performance summary
        """
        if operation_name not in self.performance_data:
            return {'error': f'No data for operation: {operation_name}'}
        
        # Filter data by time window
        cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)
        recent_data = [
            entry for entry in self.performance_data[operation_name]
            if entry['timestamp'] >= cutoff_time
        ]
        
        if not recent_data:
            return {'error': f'No recent data for operation: {operation_name}'}
        
        # Calculate statistics
        durations = [entry['duration_ms'] for entry in recent_data]
        successes = [entry['success'] for entry in recent_data]
        
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)
        success_rate = sum(successes) / len(successes) * 100
        
        # Calculate percentiles
        sorted_durations = sorted(durations)
        p50 = sorted_durations[len(sorted_durations) // 2]
        p95 = sorted_durations[int(len(sorted_durations) * 0.95)]
        p99 = sorted_durations[int(len(sorted_durations) * 0.99)]
        
        return {
            'operation': operation_name,
            'time_window_hours': time_window_hours,
            'total_operations': len(recent_data),
            'success_rate_percent': round(success_rate, 2),
            'duration_stats': {
                'average_ms': round(avg_duration, 2),
                'min_ms': min_duration,
                'max_ms': max_duration,
                'p50_ms': p50,
                'p95_ms': p95,
                'p99_ms': p99
            },
            'last_updated': datetime.now(UTC).isoformat()
        }


def create_cloudwatch_metrics(namespace: str = "StravaAIBoost") -> CloudWatchMetrics:
    """Create CloudWatch metrics publisher"""
    return CloudWatchMetrics(namespace=namespace)


def create_health_monitor(alert_topic_arn: Optional[str] = None) -> SystemHealthMonitor:
    """Create system health monitor"""
    return SystemHealthMonitor(alert_topic_arn=alert_topic_arn)


def create_performance_tracker() -> PerformanceTracker:
    """Create performance tracker"""
    return PerformanceTracker()