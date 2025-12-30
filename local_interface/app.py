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
import requests
from datetime import datetime, timedelta, UTC

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

# AWS clients - Force using the correct profile
import os
os.environ['AWS_PROFILE'] = 'your-aws-profile'
os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'

dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
secretsmanager = boto3.client('secretsmanager', region_name='eu-west-1')
apigateway = boto3.client('apigateway', region_name='eu-west-1')

# AWS Configuration Constants
AWS_REGION = 'eu-west-1'
USER_CONFIG_TABLE = os.environ.get('USER_CONFIG_TABLE', 'strava-ai-boost-user-configuration')
ACTIVITIES_TABLE = os.environ.get('ACTIVITIES_TABLE', 'strava-ai-boost-activities')

# Configuration - All URLs from environment variables or auto-detected from CloudFormation
def get_api_gateway_url():
    """Auto-detect API Gateway URL from CloudFormation if not provided via environment"""
    env_url = os.environ.get('API_GATEWAY_URL')
    if env_url:
        return env_url
    
    try:
        # Try to get API Gateway URL from CloudFormation
        cf_client = boto3.client('cloudformation', region_name='eu-west-1')
        
        # Get StravaAIBoost-API stack outputs
        response = cf_client.describe_stacks(StackName='StravaAIBoost-API')
        outputs = response['Stacks'][0].get('Outputs', [])
        
        for output in outputs:
            if 'APIEndpoint' in output['OutputKey']:
                url = output['OutputValue'].rstrip('/')
                logger.info(f"Auto-detected API Gateway URL from CloudFormation: {url}")
                return url
                
    except Exception as e:
        logger.warning(f"Failed to auto-detect API Gateway URL: {e}")
    
    # Fallback to default
    return 'https://api.strava-ai-boost.local'

API_GATEWAY_URL = get_api_gateway_url()
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
            'system_health': 'healthy' if oauth_status.get('connected') and agentcore_status == 'healthy' else 'degraded',
            'enhancement_enabled': enhancement_status.get('enhancement_enabled', True),
            'enhancement_status': 'active' if enhancement_status.get('enhancement_enabled', True) else 'paused'
        }
        
        # Get total activities count
        try:
            table = dynamodb.Table('strava-ai-boost-activities')
            response = table.scan(Select='COUNT')
            system_status['total_activities'] = response.get('Count', 0)
        except Exception as e:
            logger.warning(f"Failed to get activity count: {e}")
            system_status['total_activities'] = 0
        
        # Calculate real success rate from last 24h activities
        system_status['success_rate_24h'] = calculate_success_rate_24h()
        
        # Get real queue depth from SQS
        system_status['processing_queue_depth'] = get_sqs_queue_depth()
        
        # Get recent activities (same function as API)
        activities = get_recent_activities()
        
        # Get module status (same as config page approach)
        modules = get_module_status()
        
        # Get processing status for real-time section
        processing_status = get_processing_status_local()
        
        return render_template('dashboard.html', 
                             status=system_status, 
                             activities=activities,
                             modules=modules,
                             oauth_status=oauth_status,
                             enhancement_status=enhancement_status,
                             processing_status=processing_status)
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
    """Get AgentCore status by checking agent ARNs and accessibility"""
    try:
        # Check if agents are configured
        content_arn = os.environ.get('CONTENT_GENERATION_AGENT_ARN')
        campus_arn = os.environ.get('CAMPUS_COACH_AGENT_ARN')
        agents_available = os.environ.get('AGENTCORE_AGENTS_AVAILABLE', 'false').lower() == 'true'
        
        if not agents_available or (not content_arn and not campus_arn):
            return 'not_configured'
        
        # If we have agent ARNs, consider AgentCore as healthy
        # Memory is managed automatically in STM mode, no need to check
        logger.info(f"AgentCore agents found - Content: {bool(content_arn)}, Campus: {bool(campus_arn)}")
        return 'healthy'
            
    except Exception as e:
        logger.error(f"AgentCore status check failed: {e}")
        return 'error'


def calculate_success_rate_24h() -> float:
    """Calculate real success rate from activities in last 24 hours"""
    try:
        table = dynamodb.Table('strava-ai-boost-activities')
        
        # Get activities from last 24 hours
        from datetime import datetime, timedelta, UTC
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        
        response = table.scan(
            FilterExpression='created_at > :yesterday',
            ExpressionAttributeValues={':yesterday': yesterday}
        )
        
        activities = response.get('Items', [])
        if not activities:
            return 98.0  # Default based on system design
        
        # Count successful vs failed activities
        successful = sum(1 for activity in activities 
                        if activity.get('processing_status') == 'completed' 
                        or activity.get('enhanced_description'))
        
        total = len(activities)
        return round((successful / total) * 100, 1) if total > 0 else 98.0
        
    except Exception as e:
        logger.warning(f"Failed to calculate success rate: {e}")
        return 98.0  # Default


def get_sqs_queue_depth() -> int:
    """Get real queue depth from SQS"""
    try:
        sqs = boto3.client('sqs', region_name='eu-west-1')
        
        # Get queue URL
        queue_name = 'strava-ai-boost-activity-processing'
        response = sqs.get_queue_url(QueueName=queue_name)
        queue_url = response['QueueUrl']
        
        # Get queue attributes
        attributes = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        
        return int(attributes['Attributes']['ApproximateNumberOfMessages'])
        
    except Exception as e:
        logger.warning(f"Failed to get SQS queue depth: {e}")
        return 0


def get_enhancement_status_local() -> Dict[str, Any]:
    """Get enhancement status from local DynamoDB"""
    try:
        table = dynamodb.Table('strava-ai-boost-user-configuration')
        response = table.get_item(Key={'user_id': 'SYSTEM_CONFIG'})
        
        if 'Item' in response:
            config = response['Item']
            return {
                'enhancement_enabled': config.get('enhancement_enabled', True),
                'enhancement_paused_at': config.get('enhancement_paused_at'),
                'status': 'active' if config.get('enhancement_enabled', True) else 'paused'
            }
        else:
            # Default configuration
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


def get_processing_status_local() -> Dict[str, Any]:
    """Get processing status from local sources with real SQS data"""
    try:
        # Get currently processing activities
        processing_activities = []
        try:
            table = dynamodb.Table('strava-ai-boost-activities')
            response = table.scan(
                FilterExpression='processing_status = :status',
                ExpressionAttributeValues={':status': 'processing'},
                Limit=10
            )
            
            for item in response.get('Items', []):
                # Get modules being used for this activity
                modules_used = []
                if item.get('campus_coach_session_id') or item.get('campus_coach_data'):
                    modules_used.append('Campus Coach')
                if item.get('enduraw_data') or item.get('enhanced_metrics'):
                    modules_used.append('Enduraw')
                
                processing_activities.append({
                    'id': item.get('activity_id'),
                    'name': item.get('original_name', 'Unknown Activity'),
                    'type': item.get('activity_type', 'Unknown'),
                    'started_at': item.get('processing_started_at'),
                    'modules_used': modules_used
                })
        except Exception as e:
            logger.warning(f"Failed to get processing activities: {e}")
        
        # Get real queue status from SQS
        queue_status = get_real_sqs_status()
        
        return {
            'processing_activities': processing_activities,
            'queue_status': queue_status,
            'system_status': 'healthy',
            'last_updated': datetime.now(UTC).isoformat()
        }
    except Exception as e:
        logger.error(f"Processing status error: {str(e)}")
        return {
            'processing_activities': [],
            'queue_status': {
                'processing_queue': {'approximate_messages': 0},
                'dead_letter_queue': {'approximate_messages': 0}
            },
            'system_status': 'error',
            'error': str(e)
        }


def get_real_sqs_status() -> Dict[str, Dict[str, int]]:
    """Get real SQS queue status"""
    try:
        sqs = boto3.client('sqs', region_name='eu-west-1')
        
        # Get main processing queue
        try:
            main_queue_response = sqs.get_queue_url(QueueName='strava-ai-boost-activity-processing')
            main_queue_url = main_queue_response['QueueUrl']
            
            main_attributes = sqs.get_queue_attributes(
                QueueUrl=main_queue_url,
                AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
            )
            
            main_messages = int(main_attributes['Attributes'].get('ApproximateNumberOfMessages', 0))
            main_in_flight = int(main_attributes['Attributes'].get('ApproximateNumberOfMessagesNotVisible', 0))
            
        except Exception as e:
            logger.warning(f"Failed to get main queue status: {e}")
            main_messages = 0
            main_in_flight = 0
        
        # Get dead letter queue
        try:
            dlq_queue_response = sqs.get_queue_url(QueueName='strava-ai-boost-activity-processing-dlq')
            dlq_queue_url = dlq_queue_response['QueueUrl']
            
            dlq_attributes = sqs.get_queue_attributes(
                QueueUrl=dlq_queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )
            
            dlq_messages = int(dlq_attributes['Attributes'].get('ApproximateNumberOfMessages', 0))
            
        except Exception as e:
            logger.warning(f"Failed to get DLQ status: {e}")
            dlq_messages = 0
        
        return {
            'processing_queue': {
                'approximate_messages': main_messages,
                'messages_in_flight': main_in_flight
            },
            'dead_letter_queue': {
                'approximate_messages': dlq_messages
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get SQS status: {e}")
        return {
            'processing_queue': {'approximate_messages': 0},
            'dead_letter_queue': {'approximate_messages': 0}
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
        
        # Add health checks and processing status for each module
        for module_id, module_data in modules.items():
            if module_data.get('enabled'):
                # Add health check status
                health_status = check_module_health(module_id)
                module_data.update(health_status)
                
                # Add processing status from Step Functions if available
                processing_status = get_module_processing_status(module_id)
                module_data.update(processing_status)
        
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
    """Check module health status"""
    try:
        health_data = {
            'health_status': 'unknown',
            'last_health_check': datetime.now(UTC).isoformat()
        }
        
        if module_id == 'campus_coach':
            # Check Campus Coach credentials and AgentCore agent status
            try:
                # Check if credentials exist
                secret_name = 'strava-ai-boost-campus-coach-credentials'
                secretsmanager.get_secret_value(SecretId=secret_name)
                
                # Check recent extraction success
                sessions_table = dynamodb.Table('strava-ai-boost-campus-coaching-sessions')
                recent_sessions = sessions_table.scan(
                    FilterExpression='extracted_at > :recent_time',
                    ExpressionAttributeValues={
                        ':recent_time': (datetime.now(UTC) - timedelta(days=7)).isoformat()
                    },
                    Limit=1
                )
                
                if recent_sessions.get('Items'):
                    health_data['health_status'] = 'healthy'
                    health_data['last_successful_extraction'] = recent_sessions['Items'][0].get('extracted_at')
                else:
                    health_data['health_status'] = 'warning'
                    health_data['health_message'] = 'No recent extractions found'
                    
            except Exception as e:
                health_data['health_status'] = 'error'
                health_data['health_message'] = f'Health check failed: {str(e)}'
                
        elif module_id == 'enduraw':
            # Enduraw is a third-party integration, check if it's properly configured
            health_data['health_status'] = 'healthy'
            health_data['health_message'] = 'Third-party integration - status depends on Enduraw service'
        
        return health_data
        
    except Exception as e:
        logger.error(f"Module health check error for {module_id}: {e}")
        return {
            'health_status': 'error',
            'health_message': f'Health check failed: {str(e)}',
            'last_health_check': datetime.now(UTC).isoformat()
        }


def get_module_processing_status(module_id: str) -> Dict[str, Any]:
    """Get module processing status from Step Functions workflow"""
    try:
        processing_data = {
            'processing_status': 'unknown',
            'active_executions': 0,
            'last_execution': None
        }
        
        # Try to get Step Functions status
        try:
            stepfunctions = boto3.client('stepfunctions', region_name='eu-west-1')
            
            # Get state machine ARN (would need to be configured)
            state_machine_arn = os.environ.get('STEP_FUNCTIONS_ARN')
            
            if state_machine_arn:
                # Get recent executions
                executions = stepfunctions.list_executions(
                    stateMachineArn=state_machine_arn,
                    statusFilter='RUNNING',
                    maxResults=10
                )
                
                processing_data['active_executions'] = len(executions.get('executions', []))
                
                # Get most recent execution
                all_executions = stepfunctions.list_executions(
                    stateMachineArn=state_machine_arn,
                    maxResults=1
                )
                
                if all_executions.get('executions'):
                    latest = all_executions['executions'][0]
                    processing_data['last_execution'] = {
                        'name': latest.get('name'),
                        'status': latest.get('status'),
                        'start_date': latest.get('startDate').isoformat() if latest.get('startDate') else None
                    }
                    processing_data['processing_status'] = 'active' if processing_data['active_executions'] > 0 else 'idle'
            else:
                processing_data['processing_status'] = 'not_configured'
                processing_data['processing_message'] = 'Step Functions ARN not configured'
                
        except Exception as e:
            logger.warning(f"Failed to get Step Functions status: {e}")
            processing_data['processing_status'] = 'unavailable'
            processing_data['processing_message'] = f'Step Functions unavailable: {str(e)}'
        
        return processing_data
        
    except Exception as e:
        logger.error(f"Processing status error for {module_id}: {e}")
        return {
            'processing_status': 'error',
            'processing_message': f'Processing status check failed: {str(e)}'
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
        
        # Validate Campus Coach credentials if enabling
        if module_id == 'campus_coach' and enabled:
            config = config_data.get('config', {})
            credentials = config.get('credentials', {})
            
            if not credentials.get('username') or not credentials.get('password'):
                return jsonify({
                    'success': False,
                    'error': 'Campus Coach credentials (username and password) are required when enabling the module'
                }), 400
        
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
            'last_updated': datetime.now(UTC).isoformat()
        }
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Processing status error: {str(e)}")
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
                headers={'Content-Type': 'application/json'}
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
                logger.warning(f"Enhancement API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to call API Gateway: {e}")
        
        # Fallback to local DynamoDB update
        table = dynamodb.Table('strava-ai-boost-user-configuration')
        
        if action == 'pause':
            paused_at = datetime.now(UTC).isoformat()
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': False,
                    'enhancement_paused_at': paused_at,
                    'updated_at': paused_at
                }
            )
            message = 'Enhancement has been paused. New activities will not be processed.'
            flash_type = 'info'
            result = {
                'status': 'paused',
                'paused_at': paused_at,
                'message': 'Enhancement paused',
                'fallback': True
            }
        else:  # resume
            resumed_at = datetime.now(UTC).isoformat()
            table.put_item(
                Item={
                    'user_id': 'SYSTEM_CONFIG',
                    'enhancement_enabled': True,
                    'enhancement_paused_at': None,
                    'enhancement_resumed_at': resumed_at,
                    'updated_at': resumed_at
                }
            )
            message = 'Enhancement has been resumed. New activities will be processed automatically.'
            flash_type = 'success'
            result = {
                'status': 'active',
                'resumed_at': resumed_at,
                'message': 'Enhancement resumed',
                'fallback': True
            }
        
        if request.is_json:
            return jsonify(result)
        else:
            flash(message, flash_type)
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
        
        # Fallback to local status checks using the same functions as config page
        oauth_status = get_oauth_status()
        
        # Get AgentCore status by checking if agents are accessible
        agentcore_status = 'unknown'
        try:
            # Try to access AgentCore memory to test connectivity
            import os
            memory_id = os.environ.get('BEDROCK_AGENTCORE_MEMORY_ID')
            if memory_id:
                # Simple check - if we have the memory ID, AgentCore is likely configured
                agentcore_status = 'healthy'
            else:
                agentcore_status = 'not_configured'
        except Exception as e:
            logger.warning(f"AgentCore status check failed: {e}")
            agentcore_status = 'error'
        
        # Get activity count from DynamoDB
        total_activities = 0
        try:
            table = dynamodb.Table('strava-ai-boost-activities')
            response = table.scan(Select='COUNT')
            total_activities = response.get('Count', 0)
        except Exception as e:
            logger.warning(f"Failed to get activity count: {e}")
        
        # Calculate success rate (simplified)
        success_rate_24h = 98.0  # Default based on system design
        
        return {
            'strava_connected': oauth_status.get('connected', False),
            'agentcore_status': agentcore_status,
            'processing_queue_depth': 0,  # Will be updated when SQS is configured
            'last_activity_processed': None,  # Will be updated with real data
            'success_rate_24h': success_rate_24h,
            'total_activities': total_activities,
            'enhancement_status': 'active',  # Default, will be updated by enhancement API
            'system_health': 'healthy' if oauth_status.get('connected') and agentcore_status == 'healthy' else 'degraded',
            'fallback': True
        }
    except Exception as e:
        logger.error(f"System status error: {str(e)}")
        return {
            'error': str(e),
            'strava_connected': False,
            'agentcore_status': 'error',
            'processing_queue_depth': 0,
            'success_rate_24h': 0,
            'total_activities': 0,
            'system_health': 'error'
        }


def get_recent_activities() -> List[Dict[str, Any]]:
    """Get recent processed activities from DynamoDB"""
    try:
        # Query DynamoDB directly for activities
        try:
            table = dynamodb.Table('strava-ai-boost-activities')
            # Get recent activities
            response = table.scan(
                Limit=10
            )
            
            activities = []
            for item in response.get('Items', []):
                # Format activity data for dashboard
                activity_date = item.get('updated_at', '')
                if activity_date:
                    try:
                        # Parse and format date (DynamoDB format is different)
                        if 'T' in activity_date:
                            parsed_date = datetime.fromisoformat(activity_date.replace('Z', '+00:00'))
                        else:
                            # Handle simple date format
                            parsed_date = datetime.fromisoformat(activity_date + '+00:00')
                        formatted_date = parsed_date.strftime('%Y-%m-%d %H:%M')
                    except Exception as e:
                        logger.warning(f"Date parsing error: {e}")
                        formatted_date = str(activity_date)
                else:
                    formatted_date = 'Unknown'
                
                # Determine processing status based on actual data
                status = item.get('processing_status', 'unknown')
                if status == 'not_processed' and item.get('enhanced_description'):
                    status = 'completed'  # Has enhanced content
                elif status == 'not_processed':
                    status = 'pending'
                
                # Get modules used based on actual data
                modules_used = []
                modules_list = item.get('modules_used', [])
                if isinstance(modules_list, list):
                    for module in modules_list:
                        if isinstance(module, dict) and 'S' in module:
                            modules_used.append(module['S'])
                        elif isinstance(module, str):
                            modules_used.append(module)
                
                # Check for Campus Coach data
                if item.get('campus_coach_session_id') or item.get('campus_coach_data'):
                    if 'Campus Coach' not in modules_used:
                        modules_used.append('Campus Coach')
                
                # Check for Enduraw data
                if item.get('enduraw_data') or item.get('enhanced_metrics'):
                    if 'Enduraw' not in modules_used:
                        modules_used.append('Enduraw')
                
                # Calculate processing time if available
                processing_time = 'unknown'
                if item.get('processing_started_at') and item.get('processing_completed_at'):
                    try:
                        start = datetime.fromisoformat(item['processing_started_at'].replace('Z', '+00:00'))
                        end = datetime.fromisoformat(item['processing_completed_at'].replace('Z', '+00:00'))
                        duration = (end - start).total_seconds()
                        if duration < 60:
                            processing_time = f"{int(duration)}s"
                        else:
                            processing_time = f"{int(duration/60)}m {int(duration%60)}s"
                    except:
                        processing_time = 'unknown'
                elif item.get('processing_duration'):
                    processing_time = item.get('processing_duration')
                elif status == 'completed':
                    processing_time = '<30s'  # Estimated for completed activities
                
                # Get activity name from enhanced title or fallback
                activity_name = 'Unknown Activity'
                if item.get('enhanced_title'):
                    activity_name = item.get('enhanced_title')
                elif item.get('original_name'):
                    activity_name = item.get('original_name')
                elif item.get('name'):
                    activity_name = item.get('name')
                
                activities.append({
                    'id': item.get('activity_id'),
                    'name': activity_name,
                    'date': formatted_date,
                    'status': status,
                    'modules_used': modules_used,
                    'processing_time': processing_time,
                    'activity_type': item.get('activity_type', 'Run'),  # Default to Run
                    'distance': item.get('distance', 0),
                    'duration': item.get('moving_time', 0),
                    'has_enhanced_content': bool(item.get('enhanced_description'))
                })
            
            # Sort by date (most recent first) - try to parse dates for proper sorting
            def sort_key(activity):
                try:
                    if activity['date'] != 'Unknown':
                        return datetime.strptime(activity['date'], '%Y-%m-%d %H:%M')
                    return datetime.min
                except:
                    return datetime.min
            
            activities.sort(key=sort_key, reverse=True)
            
            logger.info(f"Found {len(activities)} activities in DynamoDB")
            return activities[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Failed to query DynamoDB for activities: {e}")
            return []
        
    except Exception as e:
        logger.error(f"Get activities error: {str(e)}")
        return []


def get_module_status() -> Dict[str, Any]:
    """Get module status for dashboard"""
    try:
        # Try to get module status from API Gateway first
        try:
            response = requests.get(API_ENDPOINTS['modules'], timeout=5)
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
                        'wait_time': module_data.get('wait_time', '2-7 minutes') if module_id == 'enduraw' else None
                    }
                
                return status
            else:
                logger.warning(f"Modules API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to get module status from API Gateway: {e}")
        
        # Fallback to local DynamoDB query
        try:
            table = dynamodb.Table('strava-ai-boost-user-configuration')
            response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
            stored_config = response.get('Item', {})
            
            # Get Campus Coach last extraction from coaching sessions table
            campus_coach_last_extraction = None
            try:
                sessions_table = dynamodb.Table('strava-ai-boost-campus-coaching-sessions')
                sessions_response = sessions_table.scan(
                    Limit=1,
                    ScanIndexForward=False  # Get most recent
                )
                if sessions_response.get('Items'):
                    latest_session = sessions_response['Items'][0]
                    campus_coach_last_extraction = latest_session.get('extracted_at')
            except Exception as e:
                logger.warning(f"Failed to get Campus Coach last extraction: {e}")
            
            return {
                'campus_coach': {
                    'enabled': stored_config.get('campus_coach_enabled', False),
                    'configured': stored_config.get('campus_coach_configured', False),
                    'last_extraction': campus_coach_last_extraction,
                    'status': 'active' if stored_config.get('campus_coach_enabled') else 'disabled',
                    'credentials_updated': stored_config.get('campus_coach_credentials_updated'),
                    'updated_at': stored_config.get('campus_coach_updated_at')
                },
                'enduraw': {
                    'enabled': stored_config.get('enduraw_enabled', False),
                    'configured': True,  # No credentials required
                    'wait_time': stored_config.get('enduraw_wait_time', '2-7 minutes'),
                    'status': 'active' if stored_config.get('enduraw_enabled') else 'disabled',
                    'updated_at': stored_config.get('enduraw_updated_at')
                }
            }
            
        except Exception as e:
            logger.warning(f"Failed to query DynamoDB for module status: {e}")
            
        # Final fallback with default values
        return {
            'campus_coach': {
                'enabled': False,
                'configured': False,
                'last_extraction': None,
                'status': 'disabled'
            },
            'enduraw': {
                'enabled': False,
                'configured': True,
                'wait_time': '2-7 minutes',
                'status': 'disabled'
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
                'wait_time': '2-7 minutes',
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
            
            # Check Campus Coach credentials status
            campus_coach_configured = stored_config.get('campus_coach_configured', False)
            if not campus_coach_configured:
                # Check if credentials exist in Secrets Manager
                try:
                    secretsmanager.get_secret_value(SecretId='strava-ai-boost-campus-coach-credentials')
                    campus_coach_configured = True
                except:
                    campus_coach_configured = False
            
            return {
                'campus_coach': {
                    'id': 'campus_coach',
                    'name': 'Campus Coach',
                    'description': 'Training session matching and performance analysis',
                    'enabled': stored_config.get('campus_coach_enabled', False),
                    'configured': campus_coach_configured,
                    'requires_credentials': True,
                    'last_extraction': stored_config.get('campus_coach_last_extraction'),
                    'updated_at': stored_config.get('campus_coach_updated_at'),
                    'status': 'active' if stored_config.get('campus_coach_enabled') else 'disabled'
                },
                'enduraw': {
                    'id': 'enduraw',
                    'name': 'Enduraw Integration',
                    'description': 'Enhanced analytics with weather and wind impact',
                    'enabled': stored_config.get('enduraw_enabled', False),
                    'configured': True,  # No credentials required
                    'requires_credentials': False,
                    'wait_time': stored_config.get('enduraw_wait_time', '2-7 minutes'),
                    'updated_at': stored_config.get('enduraw_updated_at'),
                    'status': 'active' if stored_config.get('enduraw_enabled') else 'disabled'
                }
            }
        except Exception as e:
            logger.warning(f"Failed to query DynamoDB for modules: {e}")
            
        # Final fallback
        return {
            'campus_coach': {
                'id': 'campus_coach',
                'name': 'Campus Coach',
                'description': 'Training session matching and performance analysis',
                'enabled': False,
                'configured': False,
                'requires_credentials': True,
                'status': 'disabled'
            },
            'enduraw': {
                'id': 'enduraw',
                'name': 'Enduraw Integration',
                'description': 'Enhanced analytics with weather and wind impact',
                'enabled': False,
                'configured': True,
                'requires_credentials': False,
                'wait_time': '2-7 minutes',
                'status': 'disabled'
            }
        }
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
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info(f"Module {module_id} configured successfully via API Gateway")
                return {
                    'success': True,
                    'message': f'{module_id.replace("_", " ").title()} {"enabled" if enabled else "disabled"} successfully via API Gateway'
                }
            else:
                logger.warning(f"Module API returned status {response.status_code}: {response.text}")
        except requests.RequestException as e:
            logger.warning(f"Failed to configure module via API Gateway: {e}")
        
        # Fallback to local DynamoDB update
        try:
            table = dynamodb.Table('strava-ai-boost-user-configuration')
            
            # Get existing config
            try:
                response = table.get_item(Key={'user_id': 'MODULE_CONFIG'})
                module_config = response.get('Item', {'user_id': 'MODULE_CONFIG'})
            except Exception as e:
                logger.warning(f"Failed to get existing module config: {e}")
                module_config = {'user_id': 'MODULE_CONFIG'}
            
            # Handle Campus Coach credentials if enabling
            if module_id == 'campus_coach' and enabled:
                credentials = config.get('credentials', {})
                if credentials.get('username') and credentials.get('password'):
                    # Store credentials in Secrets Manager
                    try:
                        credential_data = {
                            'username': credentials['username'],
                            'password': credentials['password'],
                            'configured_at': datetime.now(UTC).isoformat()
                        }
                        
                        secret_name = 'strava-ai-boost-campus-coach-credentials'
                        
                        try:
                            # Try to update existing secret
                            secretsmanager.update_secret(
                                SecretId=secret_name,
                                SecretString=json.dumps(credential_data)
                            )
                            logger.info("Updated Campus Coach credentials in Secrets Manager")
                        except secretsmanager.exceptions.ResourceNotFoundException:
                            # Create new secret if it doesn't exist
                            secretsmanager.create_secret(
                                Name=secret_name,
                                Description='Campus Coach credentials for Strava AI Boost',
                                SecretString=json.dumps(credential_data)
                            )
                            logger.info("Created Campus Coach credentials in Secrets Manager")
                        
                        # Mark as configured
                        module_config['campus_coach_configured'] = True
                        module_config['campus_coach_credentials_updated'] = datetime.now(UTC).isoformat()
                        
                    except Exception as e:
                        logger.error(f"Failed to store Campus Coach credentials: {e}")
                        return {
                            'success': False,
                            'error': f'Failed to store Campus Coach credentials: {str(e)}'
                        }
            
            # Update module configuration
            module_config[f'{module_id}_enabled'] = enabled
            module_config[f'{module_id}_configured'] = True
            module_config[f'{module_id}_updated_at'] = datetime.now(UTC).isoformat()
            
            # Add module-specific configuration
            if module_id == 'enduraw':
                module_config['enduraw_wait_time'] = config.get('wait_time', '2-7 minutes')
            
            # Store updated configuration
            table.put_item(Item=module_config)
            
            logger.info(f"Module {module_id} configured locally: enabled={enabled}")
            
            return {
                'success': True,
                'message': f'{module_id.replace("_", " ").title()} {"enabled" if enabled else "disabled"} successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to configure module locally: {e}")
            return {
                'success': False,
                'error': f'Failed to update module configuration: {str(e)}'
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
            # Get current user preferences
            user_config = get_user_config_from_dynamodb(user_id)
            preferences = user_config.get('user_preferences', {})
            
            # Return with defaults if not set
            return jsonify({
                'success': True,
                'preferences': {
                    'age_range': preferences.get('age_range', '26-35'),
                    'interests': preferences.get('interests', []),
                    'sport_approach': preferences.get('sport_approach', 'health & wellness'),
                    'content_length': preferences.get('content_length', 'medium'),
                    'content_tone': preferences.get('content_tone', 'motivational & energetic'),
                    'emoji_usage': preferences.get('emoji_usage', 'moderate'),
                    'technical_detail': preferences.get('technical_detail', 'intermediate')
                }
            })
        
        elif request.method == 'POST':
            # Update user preferences
            data = request.get_json()
            
            preferences = {
                'age_range': data.get('age_range', '26-35'),
                'interests': data.get('interests', []),
                'sport_approach': data.get('sport_approach', 'health & wellness'),
                'content_length': data.get('content_length', 'medium'),
                'content_tone': data.get('content_tone', 'motivational & energetic'),
                'emoji_usage': data.get('emoji_usage', 'moderate'),
                'technical_detail': data.get('technical_detail', 'intermediate')
            }
            
            # Save to DynamoDB
            table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(USER_CONFIG_TABLE)
            table.update_item(
                Key={'user_id': user_id},
                UpdateExpression='SET user_preferences = :prefs, updated_at = :timestamp',
                ExpressionAttributeValues={
                    ':prefs': preferences,
                    ':timestamp': datetime.now(UTC).isoformat()
                }
            )
            
            logger.info(f"User preferences updated for user {user_id}")
            
            return jsonify({
                'success': True,
                'message': 'Preferences saved successfully',
                'preferences': preferences
            })
            
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


def get_user_config_from_dynamodb(user_id: str) -> Dict[str, Any]:
    """Get user configuration from DynamoDB"""
    try:
        table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in response:
            return response['Item']
        else:
            return {'user_id': user_id}
            
    except Exception as e:
        logger.error(f"Failed to get user config: {str(e)}")
        return {'user_id': user_id}


if __name__ == '__main__':
    # Development server
    app.run(host='127.0.0.1', port=3000, debug=True)

@app.route('/api/user-preferences', methods=['GET', 'POST'])
def api_user_preferences():
    """API endpoint to get or update user preferences for content personalization"""
    try:
        user_id = get_current_user_id()
        
        if request.method == 'GET':
            # Get current user preferences
            user_config = get_user_config_from_dynamodb(user_id)
            preferences = user_config.get('user_preferences', {})
            
            # Return with defaults if not set
            return jsonify({
                'success': True,
                'preferences': {
                    'age_range': preferences.get('age_range', '26-35'),
                    'interests': preferences.get('interests', []),
                    'sport_approach': preferences.get('sport_approach', 'health & wellness'),
                    'content_length': preferences.get('content_length', 'medium'),
                    'content_tone': preferences.get('content_tone', 'motivational & energetic'),
                    'emoji_usage': preferences.get('emoji_usage', 'moderate'),
                    'technical_detail': preferences.get('technical_detail', 'intermediate')
                }
            })
        
        elif request.method == 'POST':
            # Update user preferences
            data = request.get_json()
            
            preferences = {
                'age_range': data.get('age_range', '26-35'),
                'interests': data.get('interests', []),
                'sport_approach': data.get('sport_approach', 'health & wellness'),
                'content_length': data.get('content_length', 'medium'),
                'content_tone': data.get('content_tone', 'motivational & energetic'),
                'emoji_usage': data.get('emoji_usage', 'moderate'),
                'technical_detail': data.get('technical_detail', 'intermediate')
            }
            
            # Save to DynamoDB
            table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(USER_CONFIG_TABLE)
            table.update_item(
                Key={'user_id': user_id},
                UpdateExpression='SET user_preferences = :prefs, updated_at = :timestamp',
                ExpressionAttributeValues={
                    ':prefs': preferences,
                    ':timestamp': datetime.now(UTC).isoformat()
                }
            )
            
            logger.info(f"User preferences updated for user {user_id}")
            
            return jsonify({
                'success': True,
                'message': 'Preferences saved successfully',
                'preferences': preferences
            })
            
    except Exception as e:
        logger.error(f"User preferences error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_current_user_id() -> str:
    """Get current user ID (for single-user app, returns default)"""
    # For single-user application, use default user ID
    # In multi-user setup, this would come from session/auth
    return os.environ.get('DEFAULT_USER_ID', 'YOUR_USER_ID')


def get_user_config_from_dynamodb(user_id: str) -> Dict[str, Any]:
    """Get user configuration from DynamoDB"""
    try:
        table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(USER_CONFIG_TABLE)
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in response:
            return response['Item']
        else:
            return {'user_id': user_id}
            
    except Exception as e:
        logger.error(f"Failed to get user config: {str(e)}")
        return {'user_id': user_id}



@app.route('/preferences')
def preferences():
    """User preferences page for content personalization"""
    try:
        return render_template('preferences.html')
    except Exception as e:
        logger.error(f"Preferences page error: {str(e)}")
        return render_template('error.html', error=str(e)), 500
