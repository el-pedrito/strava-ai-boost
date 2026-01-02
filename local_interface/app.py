"""
Local Web Interface for Strava AI Boost

Python Flask application with AWS Cloudscape components for:
- Strava OAuth configuration and app setup
- Module management (Campus Coach, Enduraw)
- Real-time dashboard with activity statistics
- Processing status monitoring

Architecture: 100% API Gateway + Lambda (no direct AWS SDK access)
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import json
import os
import sys
from typing import Dict, Any, List
import logging
import requests
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src directory to path for config imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from config.strava_config import get_strava_config, is_strava_configured
    from config.llm_config import get_bedrock_model_id
    from utils.oauth_handler import StravaOAuthHandler
except ImportError as e:
    logging.error(f"Failed to import configuration modules: {e}")
    # Fallback functions for development
    def get_strava_config():
        class MockConfig:
            def is_configured(self): return False
            def get_oauth_config(self): return {}
            def get_setup_instructions(self): return {}
        return MockConfig()
    def is_strava_configured(): return False
    def get_bedrock_model_id(): 
        import os
        return os.environ.get('BEDROCK_MODEL_ID', 'global.anthropic.claude-sonnet-4-5-20250929-v1:0')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Session configuration for OAuth state management
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)  # Extended for OAuth flow

# Configuration - All from environment variables (.env file)
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '').rstrip('/')
API_GATEWAY_KEY = os.environ.get('API_GATEWAY_KEY', '')

if not API_GATEWAY_URL or not API_GATEWAY_KEY:
    logger.error("❌ API_GATEWAY_URL or API_GATEWAY_KEY not configured!")
    logger.error("Run: ./scripts/setup_local_env.sh to configure environment variables")
    sys.exit(1)

STRAVA_OAUTH_URL = os.environ.get('STRAVA_OAUTH_URL', 'https://www.strava.com/oauth/authorize')
STRAVA_TOKEN_URL = os.environ.get('STRAVA_TOKEN_URL', 'https://www.strava.com/oauth/token')
CAMPUS_COACH_URL = os.environ.get('CAMPUS_COACH_URL', 'https://campus.coach')
ENDURAW_URL = os.environ.get('ENDURAW_URL', 'https://enduraw.com')

# API Gateway endpoints
API_ENDPOINTS = {
    'dashboard_stats': f"{API_GATEWAY_URL}/dashboard/stats",
    'dashboard_activities': f"{API_GATEWAY_URL}/dashboard/activities",
    'dashboard_system': f"{API_GATEWAY_URL}/dashboard/system",
    'oauth_status': f"{API_GATEWAY_URL}/config/oauth",
    'oauth_callback': f"{API_GATEWAY_URL}/config/oauth",
    'modules': f"{API_GATEWAY_URL}/config/modules",
    'enhancement': f"{API_GATEWAY_URL}/config/enhancement",
    'preferences': f"{API_GATEWAY_URL}/preferences",
    'agentcore_health': f"{API_GATEWAY_URL}/health/agentcore"
}

# API Gateway headers with API Key
API_HEADERS = {
    'Content-Type': 'application/json',
    'X-API-Key': API_GATEWAY_KEY
}


@app.route('/')
def index():
    """Main dashboard page - 100% server-side like config page"""
    try:
        # Load AgentCore environment variables
        load_agentcore_env()
        
        # Get all data server-side like config page does
        
        # Get OAuth status (same as config page)
        oauth_status = get_oauth_status()
        
        # Get enhancement status from DynamoDB
        enhancement_status = get_enhancement_status_local()
        
        # Get AgentCore status by checking if memory ID exists and is accessible
        agentcore_status = get_agentcore_status()
        
        # Get system status with real data
        system_status = {
            'strava_connected': oauth_status.get('connected', False),
            'agentcore_status': agentcore_status,
            'enhancement_enabled': enhancement_status.get('enhancement_enabled', True),
            'enhancement_status': 'active' if enhancement_status.get('enhancement_enabled', True) else 'paused'
        }
        
        # Get system stats from API Gateway
        try:
            response = requests.get(API_ENDPOINTS['dashboard_system'], headers=API_HEADERS, timeout=5)
            if response.status_code == 200:
                system_stats = response.json()
                system_status['total_activities'] = system_stats.get('total_activities', 0)
                system_status['success_rate_24h'] = system_stats.get('success_rate', 0)
                system_status['recent_activities_24h'] = system_stats.get('recent_activities_24h', 0)
            else:
                logger.warning(f"System stats API returned {response.status_code}")
                system_status['total_activities'] = 0
                system_status['success_rate_24h'] = 0
                system_status['recent_activities_24h'] = 0
        except Exception as e:
            logger.warning(f"Failed to get system stats from API: {e}")
            system_status['total_activities'] = 0
            system_status['success_rate_24h'] = 0
            system_status['recent_activities_24h'] = 0
        
        # Get recent activities (same function as API)
        activities = get_recent_activities()
        
        # Get module status (same as config page approach)
        modules = get_module_status()
        
        return render_template('dashboard.html', 
                             status=system_status, 
                             activities=activities,
                             modules=modules,
                             oauth_status=oauth_status,
                             enhancement_status=enhancement_status)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template('error.html', error=str(e)), 500


def load_agentcore_env():
    """Load AgentCore environment variables from .env.agentcore file"""
    try:
        env_file = os.path.join(os.path.dirname(__file__), '..', '.env.agentcore')
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value
            logger.info("Loaded AgentCore environment variables")
        else:
            logger.warning("AgentCore .env file not found")
    except Exception as e:
        logger.error(f"Failed to load AgentCore environment: {e}")


def get_agentcore_status() -> str:
    """Get AgentCore status by testing agent accessibility via API Gateway"""
    try:
        # Call AgentCore health check API
        response = requests.get(API_ENDPOINTS['agentcore_health'], headers=API_HEADERS, timeout=10)
        
        if response.status_code == 200:
            health_data = response.json()
            overall_status = health_data.get('overall_status', 'unknown')
            
            logger.info(f"AgentCore health check: {overall_status}")
            return overall_status
        else:
            logger.warning(f"AgentCore health API returned {response.status_code}")
            return 'error'
            
    except Exception as e:
        logger.error(f"AgentCore health check failed: {e}")
        return 'error'


# REMOVED: calculate_success_rate_24h() - Now using API Gateway /dashboard/system endpoint


# REMOVED: get_sqs_queue_depth() - Now using API Gateway /dashboard/system endpoint


def get_enhancement_status_local() -> Dict[str, Any]:
    """Get enhancement status from API Gateway"""
    try:
        response = requests.get(API_ENDPOINTS['enhancement'], headers=API_HEADERS, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Enhancement API returned {response.status_code}")
            return {
                'enhancement_enabled': True,
                'enhancement_paused_at': None,
                'status': 'active'
            }
    except Exception as e:
        logger.warning(f"Failed to get enhancement status: {e}")
        return {
            'enhancement_enabled': True,
            'enhancement_paused_at': None,
            'status': 'active'
        }



@app.route('/config')
def config():
    """Configuration page"""
    try:
        # Get Strava app configuration status
        strava_config = get_strava_config()
        strava_configured = strava_config.is_configured()
        
        # Get OAuth status
        oauth_status = get_oauth_status()
        
        # Get module configurations
        modules = get_module_configurations()
        
        # Get setup instructions if not configured
        setup_instructions = None
        if not strava_configured:
            setup_instructions = strava_config.get_setup_instructions()
        
        return render_template('config.html',
                             strava_configured=strava_configured,
                             oauth_status=oauth_status,
                             modules=modules,
                             setup_instructions=setup_instructions,
                             bedrock_model=get_bedrock_model_id())
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        return render_template('error.html', error=str(e)), 500


@app.route('/config/strava', methods=['POST'])
def configure_strava_app():
    """Configure Strava application credentials"""
    try:
        data = request.get_json()
        client_id = data.get('client_id', '').strip()
        client_secret = data.get('client_secret', '').strip()
        redirect_uri = data.get('redirect_uri', '').strip()
        
        # Get Strava configuration instance
        strava_config = get_strava_config()
        
        # Validate configuration
        validation = strava_config.validate_configuration(client_id, client_secret)
        
        if not validation['valid']:
            return jsonify({
                'success': False,
                'errors': validation['errors'],
                'warnings': validation.get('warnings', [])
            }), 400
        
        # Store configuration
        success = strava_config.store_configuration(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri or None
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Strava app configuration saved successfully',
                'warnings': validation.get('warnings', [])
            })
        else:
            return jsonify({
                'success': False,
                'errors': ['Failed to store configuration in AWS Secrets Manager']
            }), 500
            
    except Exception as e:
        logger.error(f"Strava app configuration error: {str(e)}")
        return jsonify({
            'success': False,
            'errors': [f'Configuration error: {str(e)}']
        }), 500


@app.route('/oauth/strava')
def strava_oauth():
    """Initiate Strava OAuth flow"""
    try:
        # Check if Strava app is configured
        strava_config = get_strava_config()
        if not strava_config.is_configured():
            flash('Please configure your Strava application first', 'error')
            return redirect(url_for('config'))
        
        # Create OAuth handler with current configuration
        oauth_config = strava_config.get_oauth_config()
        oauth_handler = StravaOAuthHandler(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            redirect_uri=oauth_config['redirect_uri']
        )
        
        # Generate OAuth URL with PKCE
        auth_url, state, code_verifier = oauth_handler.get_authorization_url()
        
        # Store state and code_verifier in session for callback
        session['oauth_state'] = state
        session['oauth_code_verifier'] = code_verifier
        session['oauth_client_id'] = oauth_config['client_id']
        session['oauth_client_secret'] = oauth_config['client_secret']
        session['oauth_redirect_uri'] = oauth_config['redirect_uri']
        session.permanent = True
        
        logger.info(f"Initiating OAuth flow with state: {state[:10]}...")
        
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"OAuth initiation error: {str(e)}")
        flash(f'OAuth error: {str(e)}', 'error')
        return redirect(url_for('config'))


@app.route('/oauth/callback')
def oauth_callback():
    """Handle Strava OAuth callback"""
    try:
        # Check for errors in callback
        error = request.args.get('error')
        if error:
            error_description = request.args.get('error_description', 'Unknown error')
            flash(f'OAuth error: {error} - {error_description}', 'error')
            return redirect(url_for('config'))
        
        # Get authorization code and state
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code:
            flash('No authorization code received from Strava', 'error')
            return redirect(url_for('config'))
        
        # Validate state parameter (CSRF protection)
        stored_state = session.get('oauth_state')
        if not stored_state:
            logger.warning("No stored state in session - attempting to recover from Strava app configuration")
            
            # Try to recover OAuth configuration from Strava config
            try:
                strava_config = get_strava_config()
                if strava_config.is_configured():
                    oauth_config = strava_config.get_oauth_config()
                    
                    # Create OAuth handler with recovered config
                    oauth_handler = StravaOAuthHandler(
                        client_id=oauth_config['client_id'],
                        client_secret=oauth_config['client_secret'],
                        redirect_uri=oauth_config['redirect_uri']
                    )
                    
                    # Exchange code directly without PKCE (fallback mode)
                    logger.info("Attempting OAuth token exchange without PKCE (fallback mode)")
                    
                    # Manual token exchange
                    token_data = {
                        'client_id': oauth_config['client_id'],
                        'client_secret': oauth_config['client_secret'],
                        'code': code,
                        'grant_type': 'authorization_code'
                    }
                    
                    response = requests.post('https://www.strava.com/oauth/token', data=token_data)
                    response.raise_for_status()
                    
                    tokens = response.json()
                    
                    # Add metadata
                    tokens['obtained_at'] = datetime.now(UTC).isoformat()
                    tokens['client_id'] = oauth_config['client_id']
                    
                    # Store tokens securely
                    if oauth_handler.store_tokens_securely(tokens, user_id="default"):
                        flash('Successfully connected to Strava! Your account is now linked.', 'success')
                        logger.info("OAuth flow completed successfully (fallback mode)")
                        return redirect(url_for('config'))
                    else:
                        flash('Failed to store OAuth tokens securely. Please try again.', 'error')
                        logger.error("Failed to store OAuth tokens")
                        return redirect(url_for('config'))
                        
                else:
                    flash('Strava application not configured. Please configure your Strava app first.', 'error')
                    return redirect(url_for('config'))
                    
            except Exception as e:
                logger.error(f"Failed to recover OAuth configuration: {e}")
                flash('OAuth session expired and recovery failed - please try connecting again', 'warning')
                return redirect(url_for('config'))
        
        if stored_state != state:
            logger.error(f"State mismatch: stored={stored_state[:10] if stored_state else 'None'}..., received={state[:10] if state else 'None'}...")
            flash('Invalid state parameter - possible security issue', 'error')
            return redirect(url_for('config'))
        
        # Get stored OAuth parameters from session
        code_verifier = session.get('oauth_code_verifier')
        client_id = session.get('oauth_client_id')
        client_secret = session.get('oauth_client_secret')
        redirect_uri = session.get('oauth_redirect_uri')
        
        if not all([code_verifier, client_id, client_secret, redirect_uri]):
            logger.warning("Missing OAuth session data - session may have expired")
            flash('OAuth session data missing - please try connecting again', 'warning')
            return redirect(url_for('config'))
        
        # Create OAuth handler
        oauth_handler = StravaOAuthHandler(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        )
        
        # Exchange authorization code for tokens
        authorization_response = request.url
        tokens = oauth_handler.exchange_code_for_tokens(
            authorization_response=authorization_response,
            code_verifier=code_verifier,
            state=state
        )
        
        # Store tokens securely in AWS Secrets Manager with default user_id
        if oauth_handler.store_tokens_securely(tokens, user_id="default"):
            # Clear OAuth session data
            session.pop('oauth_state', None)
            session.pop('oauth_code_verifier', None)
            session.pop('oauth_client_id', None)
            session.pop('oauth_client_secret', None)
            session.pop('oauth_redirect_uri', None)
            
            flash('Successfully connected to Strava! Your account is now linked.', 'success')
            logger.info("OAuth flow completed successfully")
        else:
            flash('Failed to store OAuth tokens securely. Please try again.', 'error')
            logger.error("Failed to store OAuth tokens")
        
        return redirect(url_for('config'))
        
    except ValueError as e:
        logger.error(f"OAuth callback validation error: {str(e)}")
        flash(f'OAuth validation error: {str(e)}', 'error')
        return redirect(url_for('config'))
    except requests.RequestException as e:
        logger.error(f"OAuth token exchange error: {str(e)}")
        flash(f'Failed to exchange authorization code for tokens: {str(e)}', 'error')
        return redirect(url_for('config'))
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        flash(f'OAuth callback error: {str(e)}', 'error')
        return redirect(url_for('config'))


@app.route('/api/modules', methods=['GET'])
def api_get_modules():
    """API endpoint to get module configurations"""
    try:
        modules = get_module_configurations()
        return jsonify({'modules': modules})
    except Exception as e:
        logger.error(f"Get modules error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/modules/status')
def api_get_module_status():
    """API endpoint for real-time module status monitoring"""
    try:
        # Get module configurations and status
        modules = get_module_status()
        
        # Add health checks for each enabled module
        for module_id, module_data in modules.items():
            if module_data.get('enabled'):
                health_status = check_module_health(module_id)
                module_data.update(health_status)
        
        return jsonify({
            'modules': modules,
            'last_updated': datetime.now(UTC).isoformat(),
            'system_status': 'healthy' if all(m.get('status') != 'error' for m in modules.values()) else 'degraded'
        })
        
    except Exception as e:
        logger.error(f"Module status API error: {str(e)}")
        return jsonify({
            'error': str(e),
            'modules': {},
            'system_status': 'error'
        }), 500


def check_module_health(module_id: str) -> Dict[str, Any]:
    """Check module health status via API Gateway"""
    try:
        # Get module status from API Gateway
        response = requests.get(API_ENDPOINTS['modules'], headers=API_HEADERS, timeout=5)
        if response.status_code == 200:
            data = response.json()
            modules = data.get('modules', {})
            module_data = modules.get(module_id, {})
            
            return {
                'health_status': module_data.get('status', 'unknown'),
                'health_message': module_data.get('message', ''),
                'last_health_check': datetime.now(UTC).isoformat(),
                'last_successful_extraction': module_data.get('last_extraction')
            }
        else:
            logger.warning(f"Modules API returned {response.status_code}")
            return {
                'health_status': 'unknown',
                'health_message': 'API Gateway unavailable',
                'last_health_check': datetime.now(UTC).isoformat()
            }
        
    except Exception as e:
        logger.error(f"Module health check error for {module_id}: {e}")
        return {
            'health_status': 'error',
            'health_message': f'Health check failed: {str(e)}',
            'last_health_check': datetime.now(UTC).isoformat()
        }



@app.route('/api/modules/<module_id>', methods=['POST'])
def api_configure_module(module_id: str):
    """API endpoint to configure a module"""
    try:
        config_data = request.get_json()
        
        # Validate module ID
        if module_id not in ['campus_coach', 'enduraw']:
            return jsonify({
                'success': False,
                'error': 'Invalid module ID. Supported modules: campus_coach, enduraw'
            }), 400
        
        # Validate request data
        if not config_data:
            return jsonify({
                'success': False,
                'error': 'Missing configuration data'
            }), 400
        
        # Validate enabled field
        enabled = config_data.get('enabled')
        if enabled is None:
            return jsonify({
                'success': False,
                'error': 'Missing "enabled" field in configuration'
            }), 400
        
        if not isinstance(enabled, bool):
            return jsonify({
                'success': False,
                'error': '"enabled" field must be a boolean'
            }), 400
        
        # No validation needed here - let the Lambda/API Gateway handle it
        # This allows enabling Campus Coach without credentials if already configured
        # (same behavior as Enduraw)
        
        # Configure module with validation and error handling
        result = configure_module(module_id, config_data)
        
        if result['success']:
            return jsonify({
                'success': True,
                'status': 'configured',
                'module_id': module_id,
                'enabled': enabled,
                'message': result['message']
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 500
            
    except json.JSONDecodeError:
        return jsonify({
            'success': False,
            'error': 'Invalid JSON in request body'
        }), 400
    except Exception as e:
        logger.error(f"Configure module error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Configuration error: {str(e)}'
        }), 500


@app.route('/oauth/disconnect', methods=['POST'])
def oauth_disconnect():
    """Disconnect and revoke Strava OAuth tokens"""
    try:
        # Check if Strava app is configured
        strava_config = get_strava_config()
        if not strava_config.is_configured():
            flash('Strava application not configured', 'error')
            return redirect(url_for('config'))
        
        # Create OAuth handler
        oauth_config = strava_config.get_oauth_config()
        oauth_handler = StravaOAuthHandler(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            redirect_uri=oauth_config['redirect_uri']
        )
        
        # Revoke tokens
        if oauth_handler.revoke_tokens():
            flash('Successfully disconnected from Strava. Your tokens have been revoked.', 'success')
            logger.info("OAuth tokens revoked successfully")
        else:
            flash('Failed to revoke tokens. Please try again.', 'error')
            logger.error("Failed to revoke OAuth tokens")
        
        return redirect(url_for('config'))
        
    except Exception as e:
        logger.error(f"OAuth disconnect error: {str(e)}")
        flash(f'Disconnect error: {str(e)}', 'error')
        return redirect(url_for('config'))


@app.route('/api/dashboard/stats')
def api_dashboard_stats():
    """API endpoint for dashboard statistics"""
    try:
        # Call AWS API Gateway for dashboard stats
        api_url = f"{API_GATEWAY_URL}/dashboard/stats"
        
        try:
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                logger.warning(f"Dashboard API returned status {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Failed to call Dashboard API: {e}")
        
        # Fallback to local data
        stats = {
            'activity_stats': {
                'total_activities': 0,
                'completed_activities': 0,
                'failed_activities': 0,
                'success_rate': 0
            },
            'performance_metrics': {
                'avg_processing_time': '0s',
                'system_health': 'unknown'
            },
            'module_stats': {
                'campus_coach_usage': 0,
                'enduraw_usage': 0
            },
            'last_updated': datetime.now(UTC).isoformat()
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/activities')
def api_get_activities():
    """API endpoint to get recent activities for dashboard"""
    try:
        activities = get_recent_activities()
        return jsonify(activities)
    except Exception as e:
        logger.error(f"Get activities API error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhancement', methods=['GET'])
def api_get_enhancement_status():
    """API endpoint to get enhancement status"""
    try:
        # Call AWS API Gateway to get enhancement status
        response = requests.get(API_ENDPOINTS['enhancement'], headers=API_HEADERS, timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            logger.error(f"Enhancement API returned status {response.status_code}: {response.text}")
            return jsonify({
                'error': 'Failed to get enhancement status from API',
                'status_code': response.status_code
            }), response.status_code
            
    except requests.RequestException as e:
        logger.error(f"Failed to call Enhancement API: {e}")
        return jsonify({
            'error': 'API Gateway unavailable',
            'message': str(e)
        }), 503
    except Exception as e:
        logger.error(f"Get enhancement status error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhancement', methods=['POST'])
def api_toggle_enhancement():
    """API endpoint to pause/resume enhancement - supports both JSON and form data"""
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            action = data.get('action')
        else:
            action = request.form.get('action')
        
        if action not in ['pause', 'resume']:
            if request.is_json:
                return jsonify({'error': 'Invalid action. Use "pause" or "resume"'}), 400
            else:
                flash('Invalid action. Use "pause" or "resume"', 'error')
                return redirect(url_for('index'))
        
        # Call AWS API Gateway to toggle enhancement status
        try:
            response = requests.post(
                API_ENDPOINTS['enhancement'], 
                json={'action': action},
                timeout=10,
                headers=API_HEADERS
            )
            if response.status_code == 200:
                result = response.json()
                
                # Show user-friendly message
                if action == 'pause':
                    message = 'Enhancement has been paused. New activities will not be processed.'
                    flash_type = 'info'
                else:
                    message = 'Enhancement has been resumed. New activities will be processed automatically.'
                    flash_type = 'success'
                
                if request.is_json:
                    return jsonify(result)
                else:
                    flash(message, flash_type)
                    return redirect(url_for('index'))
            else:
                logger.error(f"Enhancement API returned status {response.status_code}: {response.text}")
                if request.is_json:
                    return jsonify({
                        'error': 'Failed to toggle enhancement',
                        'status_code': response.status_code
                    }), response.status_code
                else:
                    flash('Failed to toggle enhancement. Please try again.', 'error')
                    return redirect(url_for('index'))
        except requests.RequestException as e:
            logger.error(f"Failed to call API Gateway: {e}")
            if request.is_json:
                return jsonify({
                    'error': 'API Gateway unavailable',
                    'message': str(e)
                }), 503
            else:
                flash('API Gateway unavailable. Please try again.', 'error')
                return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Toggle enhancement error: {str(e)}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('index'))
            return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Toggle enhancement error: {str(e)}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'Enhancement toggle error: {str(e)}', 'error')
            return redirect(url_for('index'))


@app.route('/api/test-connection')
def api_test_connection():
    """API endpoint to test Strava connection"""
    try:
        # Check if Strava app is configured
        strava_config = get_strava_config()
        if not strava_config.is_configured():
            return jsonify({
                'success': False,
                'error': 'Strava application not configured'
            }), 400
        
        # Get OAuth configuration
        oauth_config = strava_config.get_oauth_config()
        oauth_handler = StravaOAuthHandler(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            redirect_uri=oauth_config['redirect_uri']
        )
        
        # Get valid access token (will refresh if needed)
        access_token = oauth_handler.get_valid_access_token(user_id="default")
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'No valid access token available. Please reconnect to Strava.'
            }), 401
        
        # Test Strava API call - get athlete profile
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers, timeout=10)
        
        if response.status_code == 200:
            athlete_data = response.json()
            return jsonify({
                'success': True,
                'message': 'Connection test successful',
                'athlete': {
                    'id': athlete_data.get('id'),
                    'firstname': athlete_data.get('firstname'),
                    'lastname': athlete_data.get('lastname'),
                    'city': athlete_data.get('city'),
                    'country': athlete_data.get('country')
                },
                'api_usage': {
                    'daily_limit': response.headers.get('X-RateLimit-Limit'),
                    'daily_usage': response.headers.get('X-RateLimit-Usage'),
                    'short_term_limit': response.headers.get('X-RateLimit-Limit'),
                    'short_term_usage': response.headers.get('X-RateLimit-Usage')
                }
            })
        elif response.status_code == 401:
            return jsonify({
                'success': False,
                'error': 'Authentication failed. Please reconnect to Strava.'
            }), 401
        elif response.status_code == 403:
            return jsonify({
                'success': False,
                'error': 'Access forbidden. Check your Strava application permissions.'
            }), 403
        elif response.status_code == 429:
            return jsonify({
                'success': False,
                'error': 'Rate limit exceeded. Please try again later.'
            }), 429
        else:
            return jsonify({
                'success': False,
                'error': f'Strava API returned status {response.status_code}: {response.text}'
            }), 500
            
    except requests.RequestException as e:
        logger.error(f"Connection test network error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Network error: {str(e)}'
        }), 500
    except Exception as e:
        logger.error(f"Connection test error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Connection test failed: {str(e)}'
        }), 500



def get_recent_activities() -> List[Dict[str, Any]]:
    """Get recent processed activities from API Gateway"""
    try:
        # Get activities from API Gateway
        response = requests.get(API_ENDPOINTS['dashboard_activities'], headers=API_HEADERS, timeout=5)
        if response.status_code == 200:
            data = response.json()
            raw_activities = data.get('activities', [])
            
            # Transform to template format
            activities = []
            for act in raw_activities[:10]:  # Top 10
                # Calculate processing time
                created_at = act.get('created_at', '')
                updated_at = act.get('updated_at', '')
                processing_time = 'N/A'
                
                if created_at and updated_at:
                    try:
                        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        delta = updated - created
                        processing_time = f"{int(delta.total_seconds())}s"
                    except:
                        pass
                
                # Format date
                date_str = 'N/A'
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        date_str = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass
                
                activities.append({
                    'name': act.get('enhanced_title') or act.get('original_name', 'Unknown'),
                    'date': date_str,
                    'processing_time': processing_time,
                    'status': act.get('processing_status', 'unknown'),
                    'modules_used': act.get('modules_used', [])
                })
            
            logger.info(f"Transformed {len(activities)} activities for dashboard")
            return activities
        else:
            logger.error(f"Activities API returned {response.status_code}: {response.text}")
            return []
        
    except Exception as e:
        logger.error(f"Get activities error: {str(e)}")
        return []


def get_module_status() -> Dict[str, Any]:
    """Get module status for dashboard"""
    try:
        # Try to get module status from API Gateway first
        try:
            response = requests.get(API_ENDPOINTS['modules'], headers=API_HEADERS, timeout=5)
            if response.status_code == 200:
                data = response.json()
                modules = data.get('modules', {})
                
                # Transform API response to dashboard format
                status = {}
                for module_id, module_data in modules.items():
                    status[module_id] = {
                        'enabled': module_data.get('enabled', False),
                        'configured': module_data.get('configured', False),
                        'status': module_data.get('status', 'unknown'),
                        'last_extraction': module_data.get('last_extraction'),
                        'wait_time': module_data.get('wait_time', '2 minutes') if module_id == 'enduraw' else None
                    }
                
                return status
            else:
                logger.warning(f"Modules API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to get module status from API Gateway: {e}")
        
        # API Gateway failed, return error
        logger.error("Failed to get module status from API Gateway")
        return {
            'campus_coach': {
                'enabled': False,
                'configured': False,
                'last_extraction': None,
                'status': 'error',
                'error': 'API Gateway unavailable'
            },
            'enduraw': {
                'enabled': False,
                'configured': True,
                'wait_time': '2 minutes',
                'status': 'error',
                'error': 'API Gateway unavailable'
            }
        }
        
    except Exception as e:
        logger.error(f"Module status error: {str(e)}")
        return {
            'campus_coach': {
                'enabled': False,
                'configured': False,
                'last_extraction': None,
                'status': 'error',
                'error': str(e)
            },
            'enduraw': {
                'enabled': False,
                'configured': True,
                'wait_time': '2 minutes',
                'status': 'error',
                'error': str(e)
            }
        }


def get_oauth_status() -> Dict[str, Any]:
    """Get Strava OAuth connection status"""
    try:
        # Check if Strava app is configured first
        strava_config = get_strava_config()
        if not strava_config.is_configured():
            return {
                'connected': False,
                'configured': False,
                'message': 'Strava application not configured'
            }
        
        # Create OAuth handler and check connection status
        oauth_config = strava_config.get_oauth_config()
        oauth_handler = StravaOAuthHandler(
            client_id=oauth_config['client_id'],
            client_secret=oauth_config['client_secret'],
            redirect_uri=oauth_config['redirect_uri']
        )
        
        # Get connection status from OAuth handler
        status = oauth_handler.get_connection_status()
        
        # Add configuration status
        status['configured'] = True
        
        return status
        
    except Exception as e:
        logger.error(f"OAuth status error: {str(e)}")
        return {
            'connected': False,
            'configured': False,
            'error': str(e)
        }


def get_module_configurations() -> Dict[str, Any]:
    """Get module configurations with enhanced status information"""
    try:
        # Get module configs from API Gateway
        response = requests.get(API_ENDPOINTS['modules'], headers=API_HEADERS, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('modules', {})
        else:
            logger.error(f"Modules API returned status {response.status_code}: {response.text}")
            return {}
            
    except requests.RequestException as e:
        logger.error(f"Failed to get modules from API Gateway: {e}")
        return {}
    except Exception as e:
        logger.error(f"Module configurations error: {str(e)}")
        return {}


def configure_module(module_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Configure a module with comprehensive validation and error handling"""
    try:
        enabled = config_data.get('enabled', False)
        config = config_data.get('config', {})
        
        # Try to configure module via API Gateway first
        try:
            payload = {
                'module_id': module_id,
                'enabled': enabled,
                'config': config
            }
            
            response = requests.post(
                API_ENDPOINTS['modules'],
                json=payload,
                timeout=10,
                headers=API_HEADERS
            )
            
            if response.status_code == 200:
                logger.info(f"Module {module_id} configured successfully via API Gateway")
                return {
                    'success': True,
                    'message': f'{module_id.replace("_", " ").title()} {"enabled" if enabled else "disabled"} successfully'
                }
            else:
                logger.error(f"Module API returned status {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'error': f'API returned status {response.status_code}'
                }
                
        except requests.RequestException as e:
            logger.error(f"Failed to configure module via API Gateway: {e}")
            return {
                'success': False,
                'error': f'API Gateway unavailable: {str(e)}'
            }
        
    except Exception as e:
        logger.error(f"Module configuration error: {str(e)}")
        return {
            'success': False,
            'error': f'Module configuration error: {str(e)}'
        }


@app.route('/api/user-preferences', methods=['GET', 'POST'])
def api_user_preferences():
    """API endpoint to get or update user preferences for content personalization"""
    try:
        user_id = get_current_user_id()
        
        if request.method == 'GET':
            # Get preferences from API Gateway
            response = requests.get(
                f"{API_ENDPOINTS['preferences']}?user_id={user_id}",
                headers=API_HEADERS,
                timeout=10
            )
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                logger.error(f"Preferences API returned status {response.status_code}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to get preferences'
                }), response.status_code
        
        elif request.method == 'POST':
            # Update preferences via API Gateway
            data = request.get_json()
            data['user_id'] = user_id
            
            response = requests.post(
                API_ENDPOINTS['preferences'],
                json=data,
                headers=API_HEADERS,
                timeout=10
            )
            
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                logger.error(f"Preferences API returned status {response.status_code}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to update preferences'
                }), response.status_code
            
    except requests.RequestException as e:
        logger.error(f"API Gateway error: {e}")
        return jsonify({
            'success': False,
            'error': 'API Gateway unavailable'
        }), 503
    except Exception as e:
        logger.error(f"User preferences error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/preferences')
def preferences():
    """User preferences page for content personalization"""
    try:
        return render_template('preferences.html')
    except Exception as e:
        logger.error(f"Preferences page error: {str(e)}")
        return render_template('error.html', error=str(e)), 500


def get_current_user_id() -> str:
    """Get current user ID (for single-user app, returns default)"""
    # For single-user application, use default user ID
    # In multi-user setup, this would come from session/auth
    return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')


if __name__ == '__main__':
    # Development server
    app.run(host='127.0.0.1', port=3000, debug=True)
