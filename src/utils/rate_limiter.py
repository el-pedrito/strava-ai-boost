"""
Strava API Rate Limiter with DynamoDB Persistence

Implements rate limiting for Strava API calls with 100/15min and 1000/day limits.
Handles Requirements 10.1, 10.2, 10.3, 10.4, 10.5 for API rate compliance.
"""

import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta, UTC
import time
import math
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RateLimitType(Enum):
    """Rate limit types for Strava API"""
    SHORT_TERM = "short_term"  # 100 requests per 15 minutes
    DAILY = "daily"           # 1000 requests per day


@dataclass
class RateLimitStatus:
    """Rate limit status information"""
    limit_type: RateLimitType
    current_usage: int
    limit: int
    reset_time: datetime
    usage_percentage: float
    is_near_limit: bool
    is_exceeded: bool
    wait_time_seconds: float = 0.0
    
    @property
    def remaining(self) -> int:
        """Get remaining requests"""
        return max(0, self.limit - self.current_usage)


class StravaRateLimiter:
    """
    Rate limiter for Strava API calls with DynamoDB persistence.
    
    Tracks both short-term (100/15min) and daily (1000/day) limits
    with exponential backoff and cross-Lambda persistence.
    """
    
    # Strava API rate limits
    SHORT_TERM_LIMIT = 100      # requests per 15 minutes
    DAILY_LIMIT = 1000          # requests per day
    SHORT_TERM_WINDOW = 15 * 60  # 15 minutes in seconds
    DAILY_WINDOW = 24 * 60 * 60  # 24 hours in seconds
    
    # Safety thresholds
    NEAR_LIMIT_THRESHOLD = 0.8  # 80% of limit
    CRITICAL_THRESHOLD = 0.95   # 95% of limit
    
    def __init__(self, 
                 table_name: str = "strava-ai-boost-rate-limits",
                 region_name: str = "eu-west-1"):
        """
        Initialize rate limiter.
        
        Args:
            table_name: DynamoDB table name for rate limit storage
            region_name: AWS region
        """
        self.table_name = table_name
        self.region_name = region_name
        self.dynamodb = boto3.resource('dynamodb', region_name=region_name)
        self.table = self.dynamodb.Table(table_name)
    
    def _get_current_time(self) -> datetime:
        """Get current UTC time"""
        return datetime.now(UTC)
    
    def _get_reset_time(self, limit_type: RateLimitType) -> datetime:
        """
        Calculate reset time for a rate limit type.
        
        Args:
            limit_type: Type of rate limit
            
        Returns:
            DateTime when the limit resets
        """
        now = self._get_current_time()
        
        if limit_type == RateLimitType.SHORT_TERM:
            # Reset every 15 minutes at :00, :15, :30, :45
            minutes = now.minute
            reset_minute = ((minutes // 15) + 1) * 15
            if reset_minute >= 60:
                reset_time = now.replace(hour=now.hour + 1, minute=0, second=0, microsecond=0)
            else:
                reset_time = now.replace(minute=reset_minute, second=0, microsecond=0)
        else:  # DAILY
            # Reset at midnight UTC
            reset_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        return reset_time
    
    def _get_rate_limit_key(self, limit_type: RateLimitType) -> str:
        """
        Get DynamoDB key for rate limit type.
        
        Args:
            limit_type: Type of rate limit
            
        Returns:
            DynamoDB partition key
        """
        return limit_type.value
    
    def _get_rate_limit_data(self, limit_type: RateLimitType) -> Dict:
        """
        Get current rate limit data from DynamoDB.
        
        Args:
            limit_type: Type of rate limit
            
        Returns:
            Rate limit data dictionary
        """
        try:
            key = self._get_rate_limit_key(limit_type)
            response = self.table.get_item(Key={'limit_type': key})
            
            if 'Item' in response:
                item = response['Item']
                
                # Convert timestamps back to datetime
                reset_time = datetime.fromisoformat(item['reset_time'])
                last_request = datetime.fromisoformat(item['last_request'])
                
                return {
                    'current_usage': int(item['current_usage']),
                    'reset_time': reset_time,
                    'last_request': last_request
                }
            else:
                # Initialize new rate limit data
                reset_time = self._get_reset_time(limit_type)
                return {
                    'current_usage': 0,
                    'reset_time': reset_time,
                    'last_request': self._get_current_time()
                }
                
        except ClientError as e:
            logger.error(f"Error getting rate limit data for {limit_type.value}: {e}")
            # Return safe defaults
            return {
                'current_usage': 0,
                'reset_time': self._get_reset_time(limit_type),
                'last_request': self._get_current_time()
            }
    
    def _update_rate_limit_data(self, 
                               limit_type: RateLimitType, 
                               current_usage: int, 
                               reset_time: datetime) -> bool:
        """
        Update rate limit data in DynamoDB.
        
        Args:
            limit_type: Type of rate limit
            current_usage: Current usage count
            reset_time: When the limit resets
            
        Returns:
            True if successful, False otherwise
        """
        try:
            key = self._get_rate_limit_key(limit_type)
            now = self._get_current_time()
            
            self.table.put_item(
                Item={
                    'limit_type': key,
                    'current_usage': current_usage,
                    'reset_time': reset_time.isoformat(),
                    'last_request': now.isoformat(),
                    'updated_at': now.isoformat()
                }
            )
            
            logger.debug(f"Updated rate limit data for {limit_type.value}: {current_usage}")
            return True
            
        except ClientError as e:
            logger.error(f"Error updating rate limit data for {limit_type.value}: {e}")
            return False
    
    def _check_and_reset_if_needed(self, limit_type: RateLimitType) -> Dict:
        """
        Check if rate limit window has reset and update if needed.
        
        Args:
            limit_type: Type of rate limit
            
        Returns:
            Current rate limit data
        """
        data = self._get_rate_limit_data(limit_type)
        now = self._get_current_time()
        
        # Check if we need to reset the counter
        if now >= data['reset_time']:
            logger.info(f"Rate limit window reset for {limit_type.value}")
            
            # Calculate new reset time
            new_reset_time = self._get_reset_time(limit_type)
            
            # Reset usage counter
            data['current_usage'] = 0
            data['reset_time'] = new_reset_time
            
            # Update in DynamoDB
            self._update_rate_limit_data(limit_type, 0, new_reset_time)
        
        return data
    
    def get_rate_limit_status(self, limit_type: RateLimitType) -> RateLimitStatus:
        """
        Get current rate limit status.
        
        Args:
            limit_type: Type of rate limit to check
            
        Returns:
            RateLimitStatus object with current status
        """
        data = self._check_and_reset_if_needed(limit_type)
        
        # Get limit value
        limit = self.SHORT_TERM_LIMIT if limit_type == RateLimitType.SHORT_TERM else self.DAILY_LIMIT
        
        # Calculate usage percentage
        usage_percentage = (data['current_usage'] / limit) * 100
        
        # Check thresholds
        is_near_limit = usage_percentage >= (self.NEAR_LIMIT_THRESHOLD * 100)
        is_exceeded = data['current_usage'] >= limit
        
        # Calculate wait time if exceeded
        wait_time_seconds = 0.0
        if is_exceeded:
            now = self._get_current_time()
            wait_time_seconds = (data['reset_time'] - now).total_seconds()
            wait_time_seconds = max(0, wait_time_seconds)
        
        return RateLimitStatus(
            limit_type=limit_type,
            current_usage=data['current_usage'],
            limit=limit,
            reset_time=data['reset_time'],
            usage_percentage=usage_percentage,
            is_near_limit=is_near_limit,
            is_exceeded=is_exceeded,
            wait_time_seconds=wait_time_seconds
        )
    
    def can_make_request(self) -> Tuple[bool, List[RateLimitStatus]]:
        """
        Check if a request can be made without exceeding limits.
        
        Returns:
            Tuple of (can_make_request, [status_list])
        """
        short_term_status = self.get_rate_limit_status(RateLimitType.SHORT_TERM)
        daily_status = self.get_rate_limit_status(RateLimitType.DAILY)
        
        can_make = not (short_term_status.is_exceeded or daily_status.is_exceeded)
        
        return can_make, [short_term_status, daily_status]
    
    def record_request(self) -> Tuple[bool, List[RateLimitStatus]]:
        """
        Record a new API request and update counters.
        
        Returns:
            Tuple of (success, [status_list])
        """
        # Check current status
        can_make, statuses = self.can_make_request()
        
        if not can_make:
            logger.warning("Request blocked due to rate limit")
            return False, statuses
        
        # Update both counters
        success = True
        
        for limit_type in [RateLimitType.SHORT_TERM, RateLimitType.DAILY]:
            data = self._check_and_reset_if_needed(limit_type)
            new_usage = data['current_usage'] + 1
            
            if not self._update_rate_limit_data(limit_type, new_usage, data['reset_time']):
                success = False
        
        # Get updated statuses
        _, updated_statuses = self.can_make_request()
        
        if success:
            logger.debug("Request recorded successfully")
        else:
            logger.error("Failed to record request in DynamoDB")
        
        return success, updated_statuses
    
    def get_wait_time(self) -> float:
        """
        Get recommended wait time before next request.
        
        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        can_make, statuses = self.can_make_request()
        
        if can_make:
            return 0.0
        
        # Return the minimum wait time needed
        wait_times = [status.wait_time_seconds for status in statuses if status.is_exceeded]
        return min(wait_times) if wait_times else 0.0
    
    def wait_if_needed(self, max_wait_seconds: float = 900.0) -> bool:
        """
        Wait if rate limits are exceeded.
        
        Args:
            max_wait_seconds: Maximum time to wait (default 15 minutes)
            
        Returns:
            True if ready to proceed, False if wait time exceeds maximum
        """
        wait_time = self.get_wait_time()
        
        if wait_time <= 0:
            return True
        
        if wait_time > max_wait_seconds:
            logger.warning(f"Wait time {wait_time:.1f}s exceeds maximum {max_wait_seconds:.1f}s")
            return False
        
        logger.info(f"Rate limit exceeded, waiting {wait_time:.1f} seconds")
        time.sleep(wait_time)
        return True
    
    def get_exponential_backoff_delay(self, attempt: int, base_delay: float = 1.0) -> float:
        """
        Calculate exponential backoff delay.
        
        Args:
            attempt: Attempt number (0-based)
            base_delay: Base delay in seconds
            
        Returns:
            Delay in seconds with jitter
        """
        # Exponential backoff: base_delay * 2^attempt
        delay = base_delay * (2 ** attempt)
        
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * (time.time() % 1) - 1)  # Random between -25% and +25%
        
        # Cap at 5 minutes
        final_delay = min(delay + jitter, 300.0)
        
        return max(0.1, final_delay)  # Minimum 100ms
    
    def execute_with_rate_limiting(self, 
                                  func, 
                                  *args, 
                                  max_retries: int = 3,
                                  max_wait_seconds: float = 900.0,
                                  **kwargs):
        """
        Execute a function with automatic rate limiting and retries.
        
        Args:
            func: Function to execute
            *args: Function arguments
            max_retries: Maximum retry attempts
            max_wait_seconds: Maximum wait time for rate limits
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all retries exhausted or rate limits exceeded
        """
        for attempt in range(max_retries + 1):
            try:
                # Check rate limits
                if not self.wait_if_needed(max_wait_seconds):
                    raise Exception(f"Rate limit wait time exceeds maximum ({max_wait_seconds}s)")
                
                # Record the request
                success, statuses = self.record_request()
                if not success:
                    logger.warning("Failed to record request, proceeding anyway")
                
                # Execute the function
                result = func(*args, **kwargs)
                
                # Log successful execution
                short_term = next(s for s in statuses if s.limit_type == RateLimitType.SHORT_TERM)
                daily = next(s for s in statuses if s.limit_type == RateLimitType.DAILY)
                
                logger.info(f"API call successful. Usage: {short_term.current_usage}/{short_term.limit} (15min), "
                           f"{daily.current_usage}/{daily.limit} (daily)")
                
                return result
                
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"All retry attempts exhausted: {e}")
                    raise
                
                # Calculate backoff delay
                delay = self.get_exponential_backoff_delay(attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
                time.sleep(delay)
    
    def get_comprehensive_status(self) -> Dict:
        """
        Get comprehensive rate limiting status.
        
        Returns:
            Dictionary with detailed status information
        """
        short_term_status = self.get_rate_limit_status(RateLimitType.SHORT_TERM)
        daily_status = self.get_rate_limit_status(RateLimitType.DAILY)
        
        can_make, _ = self.can_make_request()
        wait_time = self.get_wait_time()
        
        return {
            'can_make_request': can_make,
            'wait_time_seconds': wait_time,
            'short_term': {
                'current_usage': short_term_status.current_usage,
                'limit': short_term_status.limit,
                'remaining': short_term_status.remaining,
                'usage_percentage': short_term_status.usage_percentage,
                'reset_time': short_term_status.reset_time.isoformat(),
                'is_near_limit': short_term_status.is_near_limit,
                'is_exceeded': short_term_status.is_exceeded
            },
            'daily': {
                'current_usage': daily_status.current_usage,
                'limit': daily_status.limit,
                'remaining': daily_status.remaining,
                'usage_percentage': daily_status.usage_percentage,
                'reset_time': daily_status.reset_time.isoformat(),
                'is_near_limit': daily_status.is_near_limit,
                'is_exceeded': daily_status.is_exceeded
            },
            'timestamp': self._get_current_time().isoformat()
        }
    
    def reset_rate_limits(self, limit_type: Optional[RateLimitType] = None) -> bool:
        """
        Reset rate limits (for testing or emergency use).
        
        Args:
            limit_type: Specific limit to reset, or None for all
            
        Returns:
            True if successful, False otherwise
        """
        try:
            types_to_reset = [limit_type] if limit_type else [RateLimitType.SHORT_TERM, RateLimitType.DAILY]
            
            for lt in types_to_reset:
                reset_time = self._get_reset_time(lt)
                success = self._update_rate_limit_data(lt, 0, reset_time)
                if not success:
                    return False
                
                logger.info(f"Reset rate limit for {lt.value}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting rate limits: {e}")
            return False


def create_rate_limiter_from_env() -> StravaRateLimiter:
    """
    Create rate limiter from environment variables.
    
    Expected environment variables:
    - RATE_LIMIT_TABLE_NAME: DynamoDB table name (optional)
    - AWS_REGION: AWS region (optional)
    
    Returns:
        Configured StravaRateLimiter instance
    """
    import os
    
    table_name = os.getenv('RATE_LIMIT_TABLE_NAME', 'strava-ai-boost-rate-limits')
    region = os.getenv('AWS_REGION', 'eu-west-1')
    
    return StravaRateLimiter(table_name=table_name, region_name=region)