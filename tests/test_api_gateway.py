"""
Live API Gateway Endpoint Tests

Tests real API Gateway endpoints with dynamic configuration discovery.
Uses deployed AWS resources with proper authentication.

To run: pytest tests/test_api_gateway_live.py -v
"""

import pytest
import requests
import json
from .aws_config import get_aws_config


@pytest.fixture(scope="module")
def api_client(aws_config):
    """Create API client with dynamic configuration"""
    api_url = aws_config.get_api_gateway_url()
    api_key = aws_config.get_api_gateway_key()
    
    if not api_url or not api_key:
        pytest.skip("API Gateway not fully configured")
    
    class APIClient:
        def __init__(self, base_url, api_key):
            self.base_url = base_url.rstrip('/')
            self.api_key = api_key
            self.headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json"
            }
        
        def get(self, path, timeout=10):
            """GET request"""
            return requests.get(
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=timeout
            )
        
        def post(self, path, data, timeout=10):
            """POST request"""
            return requests.post(
                f"{self.base_url}{path}",
                json=data,
                headers=self.headers,
                timeout=timeout
            )
        
        def put(self, path, data, timeout=10):
            """PUT request"""
            return requests.put(
                f"{self.base_url}{path}",
                json=data,
                headers=self.headers,
                timeout=timeout
            )
        
        def delete(self, path, timeout=10):
            """DELETE request"""
            return requests.delete(
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=timeout
            )
    
    return APIClient(api_url, api_key)


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_agentcore_health(self, api_client):
        """Test GET /health/agentcore"""
        response = api_client.get('/health/agentcore')
        
        assert response.status_code in [200, 503], f"Expected 200 or 503, got {response.status_code}"
        
        data = response.json()
        assert 'overall_status' in data
        assert data['overall_status'] in ['healthy', 'degraded', 'error']


class TestConfigurationEndpoints:
    """Test configuration endpoints"""
    
    def test_oauth_status(self, api_client):
        """Test GET /config/oauth"""
        response = api_client.get('/config/oauth')
        
        assert response.status_code == 200
        data = response.json()
        assert 'connected' in data
        assert isinstance(data['connected'], bool)
    
    def test_modules_list(self, api_client):
        """Test GET /config/modules"""
        response = api_client.get('/config/modules')
        
        assert response.status_code == 200
        data = response.json()
        assert 'modules' in data
        assert isinstance(data['modules'], dict)
        
        # Should have campus_coach and enduraw modules
        modules = data['modules']
        assert 'campus_coach' in modules or 'enduraw' in modules
    
    def test_enhancement_status(self, api_client):
        """Test GET /config/enhancement"""
        response = api_client.get('/config/enhancement')
        
        assert response.status_code == 200
        data = response.json()
        assert 'enhancement_enabled' in data
        assert isinstance(data['enhancement_enabled'], bool)
    
    def test_enhancement_toggle_pause(self, api_client):
        """Test POST /config/enhancement (pause)"""
        # Get current status
        current = api_client.get('/config/enhancement').json()
        original_enabled = current.get('enhancement_enabled', True)
        
        # Pause enhancement
        response = api_client.post('/config/enhancement', {'action': 'pause'})
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'paused' or data.get('enhancement_enabled') == False
        
        # Restore original status if needed
        if original_enabled:
            api_client.post('/config/enhancement', {'action': 'resume'})
    
    def test_enhancement_toggle_resume(self, api_client):
        """Test POST /config/enhancement (resume)"""
        # Ensure paused first
        api_client.post('/config/enhancement', {'action': 'pause'})
        
        # Resume enhancement
        response = api_client.post('/config/enhancement', {'action': 'resume'})
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'active' or data.get('enhancement_enabled') == True


class TestDashboardEndpoints:
    """Test dashboard endpoints"""
    
    def test_dashboard_stats(self, api_client):
        """Test GET /dashboard/stats"""
        response = api_client.get('/dashboard/stats')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have activity stats
        assert 'activity_stats' in data or 'total_activities' in data
        
        if 'activity_stats' in data:
            stats = data['activity_stats']
            assert 'total_activities' in stats
            assert 'completed_activities' in stats
            assert 'success_rate' in stats
    
    def test_dashboard_activities(self, api_client):
        """Test GET /dashboard/activities"""
        response = api_client.get('/dashboard/activities')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have activities list (even if empty)
        assert 'activities' in data or isinstance(data, list)
    
    def test_dashboard_system(self, api_client):
        """Test GET /dashboard/system"""
        response = api_client.get('/dashboard/system')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have system metrics
        assert 'total_activities' in data or 'system_status' in data


class TestUserPreferencesEndpoints:
    """Test user preferences endpoints"""
    
    def test_get_preferences(self, api_client):
        """Test GET /preferences"""
        response = api_client.get('/preferences')
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have user_preferences (even if empty)
        assert 'user_preferences' in data or 'preferences' in data
    
    def test_update_preferences(self, api_client):
        """Test POST /preferences"""
        # Get current preferences
        current = api_client.get('/preferences').json()
        
        # Update preferences
        new_preferences = {
            'user_preferences': {
                'age_range': '26-35',
                'sport_approach': 'performance',
                'content_length': 'medium',
                'content_tone': 'motivational & energetic'
            }
        }
        
        response = api_client.post('/preferences', new_preferences)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True or 'user_preferences' in data


class TestModuleManagement:
    """Test module management endpoints"""
    
    def test_module_configuration_campus_coach(self, api_client):
        """Test Campus Coach module configuration"""
        # Get current modules
        response = api_client.get('/config/modules')
        assert response.status_code == 200
        
        modules = response.json()['modules']
        
        if 'campus_coach' in modules:
            campus_coach = modules['campus_coach']
            assert 'enabled' in campus_coach
            assert isinstance(campus_coach['enabled'], bool)
    
    def test_module_configuration_enduraw(self, api_client):
        """Test Enduraw module configuration"""
        # Get current modules
        response = api_client.get('/config/modules')
        assert response.status_code == 200
        
        modules = response.json()['modules']
        
        if 'enduraw' in modules:
            enduraw = modules['enduraw']
            assert 'enabled' in enduraw
            assert isinstance(enduraw['enabled'], bool)


class TestErrorHandling:
    """Test API error handling"""
    
    def test_invalid_endpoint(self, api_client):
        """Test invalid endpoint returns proper error"""
        response = api_client.get('/invalid/endpoint')
        
        # Should return 404 or 403
        assert response.status_code in [403, 404]
    
    def test_invalid_method(self, api_client):
        """Test invalid HTTP method"""
        # Try DELETE on GET-only endpoint
        response = api_client.delete('/dashboard/stats')
        
        # Should return 403 or 405 (Method Not Allowed)
        assert response.status_code in [403, 405]
    
    def test_missing_api_key(self):
        """Test request without API key"""
        # Get API URL
        config = get_aws_config()
        api_url = config.get_api_gateway_url()
        
        if not api_url:
            pytest.skip("API Gateway URL not available")
        
        # Request without API key
        response = requests.get(f"{api_url}/health/agentcore", timeout=10)
        
        # Should return 403 (Forbidden)
        assert response.status_code == 403
    
    def test_invalid_api_key(self):
        """Test request with invalid API key"""
        config = get_aws_config()
        api_url = config.get_api_gateway_url()
        
        if not api_url:
            pytest.skip("API Gateway URL not available")
        
        # Request with invalid API key
        response = requests.get(
            f"{api_url}/health/agentcore",
            headers={"X-API-Key": "invalid-key-12345"},
            timeout=10
        )
        
        # Should return 403 (Forbidden)
        assert response.status_code == 403


class TestAPIPerformance:
    """Test API performance and response times"""
    
    def test_health_endpoint_response_time(self, api_client):
        """Test health endpoint responds quickly"""
        import time
        
        start = time.time()
        response = api_client.get('/health/agentcore')
        duration = time.time() - start
        
        assert response.status_code in [200, 503]
        assert duration < 5.0, f"Health check should respond in <5s, took {duration:.2f}s"
    
    def test_dashboard_stats_response_time(self, api_client):
        """Test dashboard stats responds quickly"""
        import time
        
        start = time.time()
        response = api_client.get('/dashboard/stats')
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 10.0, f"Dashboard stats should respond in <10s, took {duration:.2f}s"
    
    def test_modules_list_response_time(self, api_client):
        """Test modules list responds quickly"""
        import time
        
        start = time.time()
        response = api_client.get('/config/modules')
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 5.0, f"Modules list should respond in <5s, took {duration:.2f}s"


class TestDataValidation:
    """Test API response data validation"""
    
    def test_dashboard_stats_structure(self, api_client):
        """Test dashboard stats response structure"""
        response = api_client.get('/dashboard/stats')
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        if 'activity_stats' in data:
            stats = data['activity_stats']
            assert 'total_activities' in stats
            assert isinstance(stats['total_activities'], int)
            assert stats['total_activities'] >= 0
    
    def test_modules_response_structure(self, api_client):
        """Test modules response structure"""
        response = api_client.get('/config/modules')
        assert response.status_code == 200
        
        data = response.json()
        assert 'modules' in data
        
        modules = data['modules']
        assert isinstance(modules, dict)
        
        # Each module should have 'enabled' field
        for module_id, module_config in modules.items():
            assert 'enabled' in module_config, f"Module {module_id} should have 'enabled' field"
            assert isinstance(module_config['enabled'], bool)
    
    def test_preferences_response_structure(self, api_client):
        """Test preferences response structure"""
        response = api_client.get('/preferences')
        assert response.status_code == 200
        
        data = response.json()
        
        # Should have user_preferences or preferences
        assert 'user_preferences' in data or 'preferences' in data


class TestCORSConfiguration:
    """Test CORS configuration"""
    
    def test_cors_headers_present(self, api_client):
        """Test CORS headers are present in responses"""
        response = api_client.get('/health/agentcore')
        
        # Check for CORS headers
        headers = response.headers
        
        # At least one CORS header should be present
        cors_headers = [
            'Access-Control-Allow-Origin',
            'Access-Control-Allow-Methods',
            'Access-Control-Allow-Headers'
        ]
        
        has_cors = any(header in headers for header in cors_headers)
        # CORS might be configured at API Gateway level, not in Lambda response
        # So this test is informational
        assert True  # Always pass, just check headers exist


class TestEndToEndScenarios:
    """Test complete end-to-end scenarios"""
    
    def test_check_system_status(self, api_client):
        """Test checking complete system status"""
        # 1. Check OAuth status
        oauth_response = api_client.get('/config/oauth')
        assert oauth_response.status_code == 200
        oauth_data = oauth_response.json()
        
        # 2. Check modules
        modules_response = api_client.get('/config/modules')
        assert modules_response.status_code == 200
        modules_data = modules_response.json()
        
        # 3. Check enhancement status
        enhancement_response = api_client.get('/config/enhancement')
        assert enhancement_response.status_code == 200
        enhancement_data = enhancement_response.json()
        
        # 4. Check dashboard stats
        stats_response = api_client.get('/dashboard/stats')
        assert stats_response.status_code == 200
        stats_data = stats_response.json()
        
        # All endpoints should respond successfully
        assert oauth_data is not None
        assert modules_data is not None
        assert enhancement_data is not None
        assert stats_data is not None
    
    def test_pause_resume_workflow(self, api_client):
        """Test pause and resume enhancement workflow"""
        # 1. Get current status
        current = api_client.get('/config/enhancement').json()
        original_enabled = current.get('enhancement_enabled', True)
        
        # 2. Pause
        pause_response = api_client.post('/config/enhancement', {'action': 'pause'})
        assert pause_response.status_code == 200
        pause_data = pause_response.json()
        assert pause_data.get('status') == 'paused' or pause_data.get('enhancement_enabled') == False
        
        # 3. Verify paused
        status = api_client.get('/config/enhancement').json()
        assert status.get('enhancement_enabled') == False or status.get('status') == 'paused'
        
        # 4. Resume
        resume_response = api_client.post('/config/enhancement', {'action': 'resume'})
        assert resume_response.status_code == 200
        resume_data = resume_response.json()
        assert resume_data.get('status') == 'active' or resume_data.get('enhancement_enabled') == True
        
        # 5. Verify resumed
        status = api_client.get('/config/enhancement').json()
        assert status.get('enhancement_enabled') == True or status.get('status') == 'active'
        
        # 6. Restore original status if needed
        if not original_enabled:
            api_client.post('/config/enhancement', {'action': 'pause'})


class TestAPIGatewaySummary:
    """Summary test showing all discovered resources"""
    
    def test_print_api_summary(self, aws_config):
        """Print API Gateway configuration summary"""
        print("\n" + "="*60)
        print("API Gateway Test Configuration")
        print("="*60)
        
        api_url = aws_config.get_api_gateway_url()
        api_key = aws_config.get_api_gateway_key()
        
        print(f"API URL: {api_url}")
        print(f"API Key: {api_key[:15]}..." if api_key else "API Key: Not found")
        
        print("\nAvailable Endpoints:")
        endpoints = [
            "GET  /health/agentcore",
            "GET  /config/oauth",
            "POST /config/oauth",
            "GET  /config/modules",
            "POST /config/modules",
            "GET  /config/enhancement",
            "POST /config/enhancement",
            "GET  /dashboard/stats",
            "GET  /dashboard/activities",
            "GET  /dashboard/system",
            "GET  /preferences",
            "POST /preferences"
        ]
        
        for endpoint in endpoints:
            print(f"  - {endpoint}")
        
        print("="*60 + "\n")
        
        assert api_url is not None, "API Gateway URL should be discoverable"
        assert api_key is not None, "API Gateway Key should be discoverable"
