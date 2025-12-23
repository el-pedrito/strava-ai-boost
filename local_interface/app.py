"""
Local Web Interface for Strava AI Boost

Python Flask application with AWS Cloudscape components for:
- Strava OAuth configuration and app setup
- Module management (Campus Coach, Enduraw)
- Real-time dashboard with activity statistics
- Processing status monitoring
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import boto3
import json
import os
import sys
from typing import Dict, Any, List
import logging
import requests
from datetime import datetime, timedelta

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
    def get_bedrock_model_id(): return "anthropic.claude-3-5-sonnet-20241022-v2:0"

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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
secretsmanager = boto3.client('secretsmanager', region_name='eu-west-1')
apigateway = boto3.client('apigateway', region_name='eu-west-1')

# Configuration - All URLs from environment variables
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', 'https://api.strava-ai-boost.local')
STRAVA_OAUTH_URL = os.environ.get('STRAVA_OAUTH_URL', 'https://www.strava.com/oauth/authorize')
STRAVA_TOKEN_URL = os.environ.get('STRAVA_TOKEN_URL', 'https://www.strava.com/oauth/token')
CAMPUS_COACH_URL = os.environ.get('CAMPUS_COACH_URL', 'https://campus.coach')
ENDURAW_URL = os.environ.get('ENDURAW_URL', 'https://enduraw.com')

# API Gateway endpoints
API_ENDPOINTS = {
    'dashboard_stats': f"{API_GATEWAY_URL}/dashboard/stats",
    'dashboard_activities': f"{API_GATEWAY_URL}/dashboard/activities", 
    'status': f"{API_GATEWAY_URL}/status",
    'oauth_status': f"{API_GATEWAY_URL}/config/oauth",
    'oauth_callback': f"{API_GATEWAY_URL}/config/oauth",
    'modules': f"{API_GATEWAY_URL}/config/modules",
    'enhancement': f"{API_GATEWAY_URL}/config/enhancement"
}


@app.route('/')
def index():
    """Main dashboard page"""
    try:
        # Get system status
        status = get_system_status()
        
        # Get recent activities
        activities = get_recent_activities()
        
        # Get module status
        modules = get_module_status()
        
        return render_template('dashboard.html', 
                             status=status, 
                             activities=activities,
                             modules=modules)
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return render_template('error.html', error=str(e)), 500


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
        if not stored_state or stored_state != state:
            flash('Invalid state parameter - possible security issue', 'error')
            return redirect(url_for('config'))
        
        # Get stored OAuth parameters from session
        code_verifier = session.get('oauth_code_verifier')
        client_id = session.get('oauth_client_id')
        client_secret = session.get('oauth_client_secret')
        redirect_uri = session.get('oauth_redirect_uri')
        
        if not all([code_verifier, client_id, client_secret, redirect_uri]):
            flash('Missing OAuth session data - please try again', 'error')
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
        
        # Store tokens securely in AWS Secrets Manager
        if oauth_handler.store_tokens_securely(tokens):
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
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}")
        flash(f'OAuth callback error: {str(e)}', 'error')
        return redirect(url_for('config'))


@app.route('/api/modules', methods=['GET'])
def api_get_modules():
    """API endpoint to get module status"""
    try:
        modules = get_module_configurations()
        return jsonify(modules)
    except Exception as e:
        logger.error(f"Get modules error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/modules/<module_id>', methods=['POST'])
def api_configure_module(module_id: str):
    """API endpoint to configure a module"""
    try:
        config_data = request.get_json()
        
        # Validate module ID
        if module_id not in ['campus_coach', 'enduraw']:
            return jsonify({'error': 'Invalid module ID'}), 400
        
        # TODO: Configure module
        success = configure_module(module_id, config_data)
        
        if success:
            return jsonify({'status': 'configured'})
        else:
            return jsonify({'error': 'Configuration failed'}), 500
            
    except Exception as e:
        logger.error(f"Configure module error: {str(e)}")
        return jsonify({'error': str(e)}), 500


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
            'last_updated': datetime.utcnow().isoformat()
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/processing/status')
def api_processing_status():
    """API endpoint for real-time processing status"""
    try:
        # Call AWS API Gateway for processing status
        api_url = f"{API_GATEWAY_URL}/status"
        
        try:
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                logger.warning(f"Status API returned status {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Failed to call Status API: {e}")
        
        # Fallback to local data
        status = {
            'system_status': 'unknown',
            'recent_activities': [],
            'queue_status': {
                'processing_queue': {'approximate_messages': 0},
                'dead_letter_queue': {'approximate_messages': 0}
            },
            'last_updated': datetime.utcnow().isoformat()
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Processing status error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhancement', methods=['GET'])
def api_get_enhancement_status():
    """API endpoint to get enhancement status"""
    try:
        # Call AWS API Gateway to get enhancement status
        try:
            response = requests.get(API_ENDPOINTS['enhancement'], timeout=10)
            if response.status_code == 200:
                return jsonify(response.json())
            else:
                logger.warning(f"Enhancement API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to call API Gateway: {e}")
        
        # Fallback to local DynamoDB query
        table = dynamodb.Table('strava-ai-boost-user-configuration')
        response = table.get_item(Key={'user_id': 'SYSTEM_CONFIG'})
        
        if 'Item' in response:
            config = response['Item']
            enhancement_enabled = config.get('enhancement_enabled', True)
            paused_at = config.get('enhancement_paused_at')
            
            return jsonify({
                'enhancement_enabled': enhancement_enabled,
                'enhancement_paused_at': paused_at,
                'status': 'active' if enhancement_enabled else 'paused',
                'fallback': True
            })
        else:
            # Default configuration
            return jsonify({
                'enhancement_enabled': True,
                'enhancement_paused_at': None,
                'status': 'active',
                'fallback': True
            })
            
    except Exception as e:
        logger.error(f"Get enhancement status error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhancement', methods=['POST'])
def api_toggle_enhancement():
    """API endpoint to pause/resume enhancement"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'pause' or 'resume'
        
        if action not in ['pause', 'resume']:
            return jsonify({'error': 'Invalid action. Use "pause" or "resume"'}), 400
        
        # Call AWS API Gateway to toggle enhancement status
        try:
            response = requests.post(
                API_ENDPOINTS['enhancement'], 
                json={'action': action},
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 200:
                result = response.json()
                
                # Show user-friendly message
                if action == 'pause':
                    flash('Enhancement has been paused. New activities will not be processed.', 'info')
                else:
                    flash('Enhancement has been resumed. New activities will be processed automatically.', 'success')
                
                return jsonify(result)
            else:
                logger.warning(f"Enhancement API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to call API Gateway: {e}")
        
        # Fallback to local DynamoDB update
        table = dynamodb.Table('strava-ai-boost-user-configuration')
        
        if action == 'pause':
            paused_at = datetime.utcnow().isoformat()
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': False,
                    'enhancement_paused_at': paused_at,
                    'updated_at': paused_at
                }
            )
            flash('Enhancement has been paused. New activities will not be processed.', 'info')
            return jsonify({
                'status': 'paused',
                'paused_at': paused_at,
                'message': 'Enhancement paused',
                'fallback': True
            })
        else:  # resume
            resumed_at = datetime.utcnow().isoformat()
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'enhancement_resumed_at': resumed_at,
                    'updated_at': resumed_at
                }
            )
            flash('Enhancement has been resumed. New activities will be processed automatically.', 'success')
            return jsonify({
                'status': 'active',
                'resumed_at': resumed_at,
                'message': 'Enhancement resumed',
                'fallback': True
            })
        
    except Exception as e:
        logger.error(f"Toggle enhancement error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_system_status() -> Dict[str, Any]:
    """Get overall system status"""
    try:
        # Try to get status from API Gateway first
        try:
            response = requests.get(API_ENDPOINTS['status'], timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Status API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to get status from API Gateway: {e}")
        
        # Fallback to local status checks
        oauth_status = get_oauth_status()
        
        return {
            'strava_connected': oauth_status.get('connected', False),
            'agentcore_status': 'unknown',
            'processing_queue_depth': 0,
            'last_activity_processed': None,
            'success_rate_24h': 0,
            'enhancement_status': 'unknown',
            'system_health': 'unknown',
            'fallback': True
        }
    except Exception as e:
        logger.error(f"System status error: {str(e)}")
        return {'error': str(e)}


def get_recent_activities() -> List[Dict[str, Any]]:
    """Get recent processed activities"""
    try:
        # Try to get activities from API Gateway first
        try:
            response = requests.get(API_ENDPOINTS['dashboard_activities'], timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('activities', [])
            else:
                logger.warning(f"Dashboard API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to get activities from API Gateway: {e}")
        
        # Fallback to local DynamoDB query
        try:
            table = dynamodb.Table('strava-ai-boost-activities')
            response = table.scan(Limit=10)
            
            activities = []
            for item in response.get('Items', []):
                activities.append({
                    'id': item.get('activity_id'),
                    'name': item.get('original_name', 'Unknown Activity'),
                    'date': item.get('created_at', ''),
                    'status': item.get('processing_status', 'unknown'),
                    'modules_used': item.get('modules_used', []),
                    'processing_time': 'unknown'
                })
            
            return activities
            
        except Exception as e:
            logger.warning(f"Failed to query DynamoDB: {e}")
            return []
        
    except Exception as e:
        logger.error(f"Get activities error: {str(e)}")
        return []


def get_module_status() -> Dict[str, Any]:
    """Get module status for dashboard"""
    try:
        # TODO: Get module status from DynamoDB
        
        return {
            'campus_coach': {
                'enabled': False,
                'configured': False,
                'last_extraction': None
            },
            'enduraw': {
                'enabled': False,
                'configured': True,
                'wait_time': '2-7 minutes'
            }
        }
    except Exception as e:
        logger.error(f"Module status error: {str(e)}")
        return {}


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
    """Get module configurations"""
    try:
        # Try to get module configs from API Gateway first
        try:
            response = requests.get(API_ENDPOINTS['modules'], timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('modules', {})
            else:
                logger.warning(f"Modules API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to get modules from API Gateway: {e}")
        
        # Fallback to local DynamoDB query
        try:
            table = dynamodb.Table('strava-ai-boost-user-configuration')
            response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
            stored_config = response.get('Item', {})
            
            return {
                'campus_coach': {
                    'id': 'campus_coach',
                    'name': 'Campus Coach',
                    'description': 'Training session matching and analysis',
                    'enabled': stored_config.get('campus_coach_enabled', False),
                    'configured': stored_config.get('campus_coach_configured', False),
                    'requires_credentials': True
                },
                'enduraw': {
                    'id': 'enduraw',
                    'name': 'Enduraw Integration',
                    'description': 'Enhanced analytics with weather and wind data',
                    'enabled': stored_config.get('enduraw_enabled', False),
                    'configured': True,
                    'requires_credentials': False
                }
            }
        except Exception as e:
            logger.warning(f"Failed to query DynamoDB for modules: {e}")
            
        # Final fallback
        return {
            'campus_coach': {
                'id': 'campus_coach',
                'name': 'Campus Coach',
                'description': 'Training session matching and analysis',
                'enabled': False,
                'configured': False,
                'requires_credentials': True
            },
            'enduraw': {
                'id': 'enduraw',
                'name': 'Enduraw Integration',
                'description': 'Enhanced analytics with weather and wind data',
                'enabled': False,
                'configured': True,
                'requires_credentials': False
            }
        }
    except Exception as e:
        logger.error(f"Module configurations error: {str(e)}")
        return {}


def configure_module(module_id: str, config_data: Dict[str, Any]) -> bool:
    """Configure a module"""
    try:
        # Try to configure module via API Gateway first
        try:
            payload = {
                'module_id': module_id,
                'enabled': config_data.get('enabled', False),
                'config': config_data.get('config', {})
            }
            
            response = requests.post(
                API_ENDPOINTS['modules'],
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info(f"Module {module_id} configured successfully via API Gateway")
                return True
            else:
                logger.warning(f"Module API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to configure module via API Gateway: {e}")
        
        # Fallback to local DynamoDB update
        try:
            table = dynamodb.Table('strava-ai-boost-user-configuration')
            
            # Get existing config
            response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
            module_config = response.get('Item', {'user_id': 'MODULE_CONFIG'})
            
            # Update module configuration
            enabled = config_data.get('enabled', False)
            module_config[f'{module_id}_enabled'] = enabled
            module_config[f'{module_id}_configured'] = True
            module_config[f'{module_id}_updated_at'] = datetime.utcnow().isoformat()
            
            # Store updated configuration
            table.put_item(Item=module_config)
            
            logger.info(f"Module {module_id} configured locally: enabled={enabled}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to configure module locally: {e}")
            return False
        
    except Exception as e:
        logger.error(f"Module configuration error: {str(e)}")
        return False


if __name__ == '__main__':
    # Development server
    app.run(host='127.0.0.1', port=3000, debug=True)