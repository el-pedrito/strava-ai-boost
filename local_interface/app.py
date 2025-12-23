"""
Local Web Interface for Strava AI Boost

Python Flask application with AWS Cloudscape components for:
- Strava OAuth configuration and app setup
- Module management (Campus Coach, Enduraw)
- Real-time dashboard with activity statistics
- Processing status monitoring
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import boto3
import json
import os
import sys
from typing import Dict, Any, List
import logging

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

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
secretsmanager = boto3.client('secretsmanager', region_name='eu-west-1')
apigateway = boto3.client('apigateway', region_name='eu-west-1')

# Configuration
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', 'https://api.strava-ai-boost.local')


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
        # In production, use secure session storage
        # For now, we'll use a simple approach
        
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
        
        # Get authorization code
        code = request.args.get('code')
        state = request.args.get('state')
        
        if not code:
            flash('No authorization code received from Strava', 'error')
            return redirect(url_for('config'))
        
        # TODO: Complete OAuth token exchange
        # This requires implementing session storage for state and code_verifier
        # For now, show success message
        
        flash('OAuth callback received successfully. Token exchange implementation pending.', 'info')
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


@app.route('/api/status')
def api_get_status():
    """API endpoint for real-time status"""
    try:
        status = get_system_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Get status error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/activities')
def api_get_activities():
    """API endpoint for activity history"""
    try:
        activities = get_recent_activities()
        return jsonify(activities)
    except Exception as e:
        logger.error(f"Get activities error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/enhancement', methods=['GET'])
def api_get_enhancement_status():
    """API endpoint to get enhancement status"""
    try:
        # TODO: Call AWS API Gateway to get enhancement status
        # For now, return placeholder data
        return jsonify({
            'enhancement_enabled': True,
            'enhancement_paused_at': None,
            'status': 'active'
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
            return jsonify({'error': 'Invalid action'}), 400
        
        # TODO: Call AWS API Gateway to toggle enhancement status
        # For now, return success
        status = 'paused' if action == 'pause' else 'active'
        message = f'Enhancement has been {action}d'
        
        return jsonify({
            'status': status,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Toggle enhancement error: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_system_status() -> Dict[str, Any]:
    """Get overall system status"""
    try:
        # TODO: Implement system status checks
        # - Check DynamoDB tables
        # - Check Lambda functions
        # - Check Step Functions
        # - Check AgentCore agents
        
        return {
            'strava_connected': True,  # Placeholder
            'agentcore_status': 'healthy',
            'processing_queue_depth': 0,
            'last_activity_processed': '2024-12-18T10:00:00Z',
            'success_rate_24h': 98.5
        }
    except Exception as e:
        logger.error(f"System status error: {str(e)}")
        return {'error': str(e)}


def get_recent_activities() -> List[Dict[str, Any]]:
    """Get recent processed activities"""
    try:
        # TODO: Query DynamoDB for recent activities
        
        # Placeholder data
        return [
            {
                'id': '12345',
                'name': 'Morning Run',
                'date': '2024-12-18',
                'status': 'completed',
                'modules_used': ['campus_coach'],
                'processing_time': '15s'
            }
        ]
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
        if not is_strava_configured():
            return {
                'connected': False,
                'configured': False,
                'message': 'Strava application not configured'
            }
        
        # Check for OAuth tokens in Secrets Manager
        try:
            secret_name = "strava-ai-boost-oauth-tokens"
            response = secretsmanager.get_secret_value(SecretId=secret_name)
            tokens = json.loads(response['SecretString'])
            
            return {
                'connected': True,
                'configured': True,
                'expires_at': tokens.get('expires_at'),
                'scopes': tokens.get('scope', '').split(','),
                'obtained_at': tokens.get('obtained_at')
            }
            
        except secretsmanager.exceptions.ResourceNotFoundException:
            return {
                'connected': False,
                'configured': True,
                'message': 'No OAuth tokens found - please connect to Strava'
            }
        
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
        # TODO: Get module configs from DynamoDB
        
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
        # TODO: Implement module configuration
        # - Validate credentials if required
        # - Store configuration in DynamoDB
        # - Test module connectivity
        
        logger.info(f"Configuring module {module_id} with data: {config_data}")
        return True
    except Exception as e:
        logger.error(f"Module configuration error: {str(e)}")
        return False


if __name__ == '__main__':
    # Development server
    app.run(host='127.0.0.1', port=3000, debug=True)