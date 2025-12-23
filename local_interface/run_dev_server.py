#!/usr/bin/env python3
"""
Development server runner for Strava AI Boost local interface

Starts the Flask application with proper configuration for development testing.
"""

import os
import sys
from datetime import datetime

# Add src directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def setup_environment():
    """Setup development environment variables"""
    
    # Set development environment variables
    os.environ.setdefault('SECRET_KEY', 'dev-secret-key-for-testing-only')
    os.environ.setdefault('FLASK_ENV', 'development')
    os.environ.setdefault('FLASK_DEBUG', 'True')
    
    # AWS configuration (will use fallback if API Gateway not available)
    os.environ.setdefault('AWS_DEFAULT_REGION', 'eu-west-1')
    os.environ.setdefault('API_GATEWAY_URL', 'https://your-api-gateway-id.execute-api.eu-west-1.amazonaws.com/prod')
    
    # External service URLs - all configurable via environment
    os.environ.setdefault('STRAVA_OAUTH_URL', 'https://www.strava.com/oauth/authorize')
    os.environ.setdefault('STRAVA_TOKEN_URL', 'https://www.strava.com/oauth/token')
    os.environ.setdefault('CAMPUS_COACH_URL', 'https://campus.coach')
    os.environ.setdefault('ENDURAW_URL', 'https://enduraw.com')
    
    print("🔧 Development Environment Setup")
    print("-" * 40)
    print(f"Secret Key: {'*' * 20} (development)")
    print(f"AWS Region: {os.environ.get('AWS_DEFAULT_REGION')}")
    print(f"API Gateway: {os.environ.get('API_GATEWAY_URL')}")
    print(f"Strava OAuth: {os.environ.get('STRAVA_OAUTH_URL')}")
    print(f"Campus Coach: {os.environ.get('CAMPUS_COACH_URL')}")
    print(f"Enduraw: {os.environ.get('ENDURAW_URL')}")
    print(f"Flask Debug: {os.environ.get('FLASK_DEBUG')}")
    print()


def check_dependencies():
    """Check if required dependencies are available"""
    
    print("📦 Checking Dependencies")
    print("-" * 25)
    
    required_packages = [
        'flask',
        'boto3',
        'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - MISSING")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install flask boto3 requests")
        return False
    
    print("✅ All dependencies available")
    return True


def main():
    """Main function to start development server"""
    
    print(f"🚀 Strava AI Boost - Local Development Server")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Setup environment
    setup_environment()
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Cannot start server - missing dependencies")
        return 1
    
    print("\n🌐 Starting Flask Development Server")
    print("-" * 35)
    print("URL: http://127.0.0.1:3000")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        # Import and run Flask app
        from app import app
        
        # Run development server
        app.run(
            host='127.0.0.1',
            port=3000,
            debug=True,
            use_reloader=True
        )
        
    except ImportError as e:
        print(f"❌ Failed to import Flask app: {e}")
        print("Make sure app.py is in the same directory")
        return 1
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())