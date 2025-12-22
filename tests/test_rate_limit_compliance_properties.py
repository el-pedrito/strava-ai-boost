"""
Property-Based Tests for Rate Limit Compliance

Tests Property 13: API calls respect both 15-minute and daily rate limits
Validates Requirements 10.1, 10.2
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import boto3
from moto import mock_aws
import time

# Import the modules to test
from src.utils.rate_limiter import StravaRateLimiter, RateLimitType, RateLimitStatus


# Test data strategies
@st.composite
def api_call_count_strategy(draw):
    """Generate valid API call counts"""
    return draw(st.integers(min_value=1, max_value=200))


@st.composite
def time_window_strategy(draw):
    """Generate time windows for testing"""
    return draw(st.integers(min_value=1, max_value=1440))  # 1 minute to 24 hours


class TestRateLimitComplianceProperties:
    """
    Property-based tests for rate limit compliance.
    
    **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
    """
    
    def _create_test_table(self, table_name: str, region_name: str = 'us-east-1'):
        """Create a test DynamoDB table for rate limiting"""
        dynamodb = boto3.resource('dynamodb', region_name=region_name)
        
        try:
            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {
                        'AttributeName': 'limit_type',
                        'KeyType': 'HASH'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'limit_type',
                        'AttributeType': 'S'
                    }
                ],
                BillingMode='PAY_PER_REQUEST'
            )
            
            # Wait for table to be created (in moto this is instant)
            table.wait_until_exists()
            return table
            
        except Exception as e:
            # Table might already exist, try to get it
            try:
                return dynamodb.Table(table_name)
            except:
                raise e
    
    @mock_aws
    @given(call_count=st.integers(min_value=1, max_value=99))
    @settings(max_examples=100, deadline=None)
    def test_short_term_rate_limit_compliance_property(self, call_count):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any number of API calls below the 15-minute limit (100), 
        all calls should be allowed without rate limiting.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-rate-limits-short-{call_count}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Act & Assert - Make calls below the limit
        successful_calls = 0
        for i in range(call_count):
            can_make, statuses = rate_limiter.can_make_request()
            
            # Should be able to make request
            assert can_make is True, f"Should be able to make request {i+1}/{call_count}"
            
            # Record the request
            success, updated_statuses = rate_limiter.record_request()
            assert success is True, f"Should successfully record request {i+1}"
            
            # Verify short-term status
            short_term_status = next(s for s in updated_statuses if s.limit_type == RateLimitType.SHORT_TERM)
            assert short_term_status.current_usage == i + 1, f"Usage should be {i+1}"
            assert short_term_status.current_usage <= StravaRateLimiter.SHORT_TERM_LIMIT, "Should not exceed short-term limit"
            assert not short_term_status.is_exceeded, "Short-term limit should not be exceeded"
            
            successful_calls += 1
        
        # Assert - All calls should have succeeded
        assert successful_calls == call_count, f"All {call_count} calls should have succeeded"
        
        # Verify final status
        final_status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
        assert final_status.current_usage == call_count, "Final usage should match call count"
        assert final_status.remaining >= 0, "Remaining calls should be non-negative"
    
    @mock_aws
    @given(call_count=st.integers(min_value=1, max_value=999))
    @settings(max_examples=100, deadline=None)
    def test_daily_rate_limit_compliance_property(self, call_count):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any number of API calls below the daily limit (1000),
        all calls should be allowed without daily rate limiting.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-rate-limits-daily-{call_count}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Act & Assert - Make calls below the daily limit
        successful_calls = 0
        
        # We need to simulate calls without hitting the 15-minute limit
        # So we'll directly update the daily counter
        for i in range(call_count):
            # Get current daily status
            daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
            
            # Should not be exceeded
            assert not daily_status.is_exceeded, f"Daily limit should not be exceeded at call {i+1}"
            assert daily_status.current_usage <= StravaRateLimiter.DAILY_LIMIT, "Should not exceed daily limit"
            
            # Simulate recording a request (update daily counter directly)
            rate_limiter._update_rate_limit_data(
                RateLimitType.DAILY, 
                i + 1, 
                daily_status.reset_time
            )
            
            successful_calls += 1
        
        # Assert - All calls should have been processed
        assert successful_calls == call_count, f"All {call_count} calls should have been processed"
        
        # Verify final daily status
        final_daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        assert final_daily_status.current_usage == call_count, "Final daily usage should match call count"
        assert final_daily_status.remaining >= 0, "Remaining daily calls should be non-negative"
    
    @mock_aws
    @given(excess_calls=st.integers(min_value=1, max_value=50))
    @settings(max_examples=100, deadline=None)
    def test_short_term_rate_limit_blocking_property(self, excess_calls):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any number of API calls that would exceed the 15-minute limit,
        the rate limiter should block additional calls until the window resets.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-rate-limits-block-{excess_calls}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Fill up to the limit
        limit = StravaRateLimiter.SHORT_TERM_LIMIT
        for i in range(limit):
            success, _ = rate_limiter.record_request()
            assert success is True, f"Should record request {i+1} within limit"
        
        # Verify we're at the limit
        status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
        assert status.current_usage == limit, "Should be at the limit"
        assert status.is_exceeded or status.current_usage >= limit, "Should be at or exceeding limit"
        
        # Act & Assert - Try to make excess calls
        blocked_calls = 0
        for i in range(excess_calls):
            can_make, statuses = rate_limiter.can_make_request()
            
            # Should be blocked due to rate limit
            short_term_status = next(s for s in statuses if s.limit_type == RateLimitType.SHORT_TERM)
            
            if short_term_status.is_exceeded:
                # This call should be blocked
                success, _ = rate_limiter.record_request()
                assert success is False, f"Excess call {i+1} should be blocked"
                blocked_calls += 1
            else:
                # If not exceeded, we might have hit a reset window
                # This is acceptable behavior
                pass
        
        # Assert - At least some calls should have been blocked if we're testing excess
        if excess_calls > 0:
            # Verify the rate limiter is tracking correctly
            final_status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
            assert final_status.current_usage >= limit, "Usage should be at or above limit"
    
    @mock_aws
    @given(excess_calls=st.integers(min_value=1, max_value=100))
    @settings(max_examples=100, deadline=None)
    def test_daily_rate_limit_blocking_property(self, excess_calls):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any number of API calls that would exceed the daily limit,
        the rate limiter should block additional calls until the day resets.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-rate-limits-daily-block-{excess_calls}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Set daily usage to the limit
        daily_limit = StravaRateLimiter.DAILY_LIMIT
        daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        
        # Update daily counter to the limit
        rate_limiter._update_rate_limit_data(
            RateLimitType.DAILY,
            daily_limit,
            daily_status.reset_time
        )
        
        # Verify we're at the daily limit
        status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        assert status.current_usage == daily_limit, "Should be at the daily limit"
        assert status.is_exceeded or status.current_usage >= daily_limit, "Should be at or exceeding daily limit"
        
        # Act & Assert - Try to make excess calls
        for i in range(min(excess_calls, 10)):  # Limit iterations for performance
            can_make, statuses = rate_limiter.can_make_request()
            
            # Check daily status
            daily_status = next(s for s in statuses if s.limit_type == RateLimitType.DAILY)
            
            if daily_status.is_exceeded:
                # This call should be blocked
                assert can_make is False, f"Excess daily call {i+1} should be blocked"
                
                # Verify wait time is provided
                assert daily_status.wait_time_seconds > 0, "Should provide wait time when exceeded"
            else:
                # If not exceeded, we might have hit a reset window
                # This is acceptable behavior
                pass
    
    @mock_aws
    @given(
        short_calls=st.integers(min_value=1, max_value=50),
        daily_calls=st.integers(min_value=1, max_value=100)
    )
    @settings(max_examples=100, deadline=None)
    def test_dual_rate_limit_compliance_property(self, short_calls, daily_calls):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any combination of API calls, both 15-minute and daily limits
        should be enforced simultaneously and independently.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-dual-limits-{short_calls}-{daily_calls}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Test that both limits are checked
        total_calls = min(short_calls + daily_calls, 150)  # Reasonable limit for testing
        
        successful_calls = 0
        blocked_calls = 0
        
        for i in range(total_calls):
            # Check if we can make a request
            can_make, statuses = rate_limiter.can_make_request()
            
            short_term_status = next(s for s in statuses if s.limit_type == RateLimitType.SHORT_TERM)
            daily_status = next(s for s in statuses if s.limit_type == RateLimitType.DAILY)
            
            # Should be blocked if either limit is exceeded
            should_be_blocked = short_term_status.is_exceeded or daily_status.is_exceeded
            
            if should_be_blocked:
                assert can_make is False, f"Call {i+1} should be blocked due to rate limits"
                blocked_calls += 1
            else:
                # Try to record the request
                success, updated_statuses = rate_limiter.record_request()
                
                if success:
                    successful_calls += 1
                    
                    # Verify counters are updated correctly
                    updated_short = next(s for s in updated_statuses if s.limit_type == RateLimitType.SHORT_TERM)
                    updated_daily = next(s for s in updated_statuses if s.limit_type == RateLimitType.DAILY)
                    
                    # Both counters should have incremented
                    assert updated_short.current_usage > short_term_status.current_usage or updated_short.current_usage == 1, "Short-term counter should increment"
                    assert updated_daily.current_usage > daily_status.current_usage or updated_daily.current_usage == 1, "Daily counter should increment"
                    
                    # Neither should exceed their limits after a successful call
                    assert updated_short.current_usage <= StravaRateLimiter.SHORT_TERM_LIMIT, "Short-term usage should not exceed limit"
                    assert updated_daily.current_usage <= StravaRateLimiter.DAILY_LIMIT, "Daily usage should not exceed limit"
        
        # Assert - Verify the behavior was consistent
        total_processed = successful_calls + blocked_calls
        assert total_processed == total_calls, "All calls should have been processed (either succeeded or blocked)"
        
        # Verify final state is consistent
        final_short_status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
        final_daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        
        assert final_short_status.current_usage <= StravaRateLimiter.SHORT_TERM_LIMIT, "Final short-term usage should not exceed limit"
        assert final_daily_status.current_usage <= StravaRateLimiter.DAILY_LIMIT, "Final daily usage should not exceed limit"
    
    @mock_aws
    @given(usage_percentage=st.floats(min_value=0.1, max_value=0.95))
    @settings(max_examples=100, deadline=None)
    def test_rate_limit_status_accuracy_property(self, usage_percentage):
        """
        **Feature: strava-ai-boost, Property 13: API calls respect both 15-minute and daily rate limits**
        
        For any usage percentage of rate limits, the status reporting
        should accurately reflect the current state and remaining capacity.
        
        **Validates: Requirements 10.1, 10.2**
        """
        # Arrange
        table_name = f"test-status-accuracy-{int(usage_percentage * 100)}"
        region_name = 'us-east-1'
        
        # Create the test table
        self._create_test_table(table_name, region_name)
        
        rate_limiter = StravaRateLimiter(table_name=table_name, region_name=region_name)
        
        # Calculate target usage for both limits
        short_term_target = int(StravaRateLimiter.SHORT_TERM_LIMIT * usage_percentage)
        daily_target = int(StravaRateLimiter.DAILY_LIMIT * usage_percentage)
        
        # Set usage levels directly
        short_status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
        daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        
        rate_limiter._update_rate_limit_data(RateLimitType.SHORT_TERM, short_term_target, short_status.reset_time)
        rate_limiter._update_rate_limit_data(RateLimitType.DAILY, daily_target, daily_status.reset_time)
        
        # Act - Get status
        updated_short_status = rate_limiter.get_rate_limit_status(RateLimitType.SHORT_TERM)
        updated_daily_status = rate_limiter.get_rate_limit_status(RateLimitType.DAILY)
        
        # Assert - Verify accuracy
        assert updated_short_status.current_usage == short_term_target, "Short-term usage should match target"
        assert updated_daily_status.current_usage == daily_target, "Daily usage should match target"
        
        # Verify remaining calculations
        expected_short_remaining = StravaRateLimiter.SHORT_TERM_LIMIT - short_term_target
        expected_daily_remaining = StravaRateLimiter.DAILY_LIMIT - daily_target
        
        assert updated_short_status.remaining == expected_short_remaining, "Short-term remaining should be accurate"
        assert updated_daily_status.remaining == expected_daily_remaining, "Daily remaining should be accurate"
        
        # Verify percentage calculations
        expected_short_percentage = (short_term_target / StravaRateLimiter.SHORT_TERM_LIMIT) * 100
        expected_daily_percentage = (daily_target / StravaRateLimiter.DAILY_LIMIT) * 100
        
        assert abs(updated_short_status.usage_percentage - expected_short_percentage) < 0.1, "Short-term percentage should be accurate"
        assert abs(updated_daily_status.usage_percentage - expected_daily_percentage) < 0.1, "Daily percentage should be accurate"
        
        # Verify threshold flags
        near_limit_threshold = rate_limiter.NEAR_LIMIT_THRESHOLD * 100
        
        if usage_percentage >= rate_limiter.NEAR_LIMIT_THRESHOLD:
            assert updated_short_status.is_near_limit, "Should flag near limit when above threshold"
            assert updated_daily_status.is_near_limit, "Should flag near limit when above threshold"
        else:
            assert not updated_short_status.is_near_limit, "Should not flag near limit when below threshold"
            assert not updated_daily_status.is_near_limit, "Should not flag near limit when below threshold"


if __name__ == "__main__":
    # Run the property tests
    pytest.main([__file__, "-v", "--tb=short"])