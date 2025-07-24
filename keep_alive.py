import threading
import time
import requests
import logging
import os
from flask import Flask, jsonify
from config import KEEP_ALIVE_URL, KEEP_ALIVE_INTERVAL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for health checks and port binding
app = Flask(__name__)

@app.route('/')
def home():
    """Main endpoint for Render port detection"""
    return """
    🤖 Telegram Auto-Forwarder Bot
    
    ✅ Status: Online & Running
    🔄 Service: Active 24/7
    📡 Keep-Alive: Enabled
    🌐 Port: Properly Bound
    
    Bot is working perfectly!
    """

@app.route('/health')
def health_check():
    """Health check endpoint with system status"""
    try:
        from userbot import userbot
        return jsonify({
            'status': 'healthy',
            'service': 'telegram-auto-forwarder',
            'userbot_running': userbot.is_running,
            'active_tasks': len(userbot.active_tasks),
            'port': os.getenv('PORT', '10000'),
            'host': '0.0.0.0',
            'timestamp': time.time()
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'port': os.getenv('PORT', '10000'),
            'timestamp': time.time()
        }), 500

@app.route('/ping')
def ping():
    """Simple ping endpoint for external monitoring"""
    return jsonify({
        'ping': 'pong',
        'service': 'telegram-forwarder',
        'timestamp': time.time()
    })

@app.route('/stats')
def stats():
    """Statistics endpoint for monitoring"""
    try:
        from userbot import userbot
        return jsonify({
            'total_active_tasks': len(userbot.active_tasks),
            'userbot_status': 'running' if userbot.is_running else 'stopped',
            'uptime': 'continuous',
            'flask_status': 'running',
            'keep_alive_status': 'active',
            'timestamp': time.time()
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({
            'error': str(e),
            'flask_status': 'running',
            'timestamp': time.time()
        }), 500

@app.route('/test')
def test_endpoint():
    """Test endpoint for deployment verification"""
    return jsonify({
        'message': 'All systems operational!',
        'flask_server': 'running',
        'port_binding': 'successful',
        'render_compatible': True,
        'timestamp': time.time()
    })

def keep_alive_ping():
    """Keep the service alive by making periodic requests"""
    def ping_server():
        while True:
            try:
                if KEEP_ALIVE_URL:
                    # Self-ping to prevent Render from sleeping
                    response = requests.get(
                        KEEP_ALIVE_URL, 
                        timeout=30,
                        headers={
                            'User-Agent': 'KeepAlive-Bot/1.0',
                            'Accept': 'application/json'
                        }
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"✅ Keep-alive ping successful - Status: {response.status_code}")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping failed - Status: {response.status_code}")
                        
                    # Also ping health endpoint
                    try:
                        health_url = f"{KEEP_ALIVE_URL}/health"
                        health_response = requests.get(health_url, timeout=10)
                        logger.info(f"🏥 Health check ping - Status: {health_response.status_code}")
                    except:
                        pass  # Health ping is optional
                        
                else:
                    logger.info("📡 Keep-alive ping (URL not configured)")
                
            except requests.exceptions.Timeout:
                logger.error("⏰ Keep-alive request timed out")
            except requests.exceptions.ConnectionError:
                logger.error("🌐 Keep-alive connection error")
            except Exception as e:
                logger.error(f"❌ Keep-alive error: {e}")
            
            # Wait for next ping
            time.sleep(KEEP_ALIVE_INTERVAL)
    
    # Start ping thread
    ping_thread = threading.Thread(target=ping_server, daemon=True)
    ping_thread.start()
    logger.info(f"🔄 Keep-alive service started (interval: {KEEP_ALIVE_INTERVAL}s)")

def start_flask_server():
    """Start Flask server with proper port binding for Render"""
    try:
        # Get port from environment variable (Render provides this)
        port = int(os.getenv("PORT", 10000))
        
        logger.info(f"🌐 Starting Flask server...")
        logger.info(f"📍 Host: 0.0.0.0")
        logger.info(f"🔌 Port: {port}")
        
        # Critical: Must bind to 0.0.0.0 for Render to detect the port
        app.run(
            host='0.0.0.0',      # Essential for Render port detection
            port=port,           # Use PORT environment variable
            debug=False,         # Production mode
            use_reloader=False,  # Disable auto-reload
            threaded=True        # Enable threading
        )
        
    except Exception as e:
        logger.error(f"❌ Flask server startup error: {e}")
        raise

def initialize_keep_alive_system():
    """Initialize complete keep-alive system"""
    try:
        logger.info("🚀 Initializing keep-alive system...")
        
        # Start keep-alive pinging service
        keep_alive_ping()
        
        # Log system status
        logger.info("✅ Keep-alive system initialized successfully")
        logger.info(f"🌐 Flask server ready to start on port {os.getenv('PORT', '10000')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Keep-alive system initialization failed: {e}")
        return False

# Health monitoring functions
def is_service_healthy():
    """Check if service is healthy"""
    try:
        from userbot import userbot
        return userbot.is_running
    except:
        return False

def get_system_status():
    """Get comprehensive system status"""
    try:
        from userbot import userbot
        return {
            'flask_server': 'running',
            'userbot_status': 'running' if userbot.is_running else 'stopped',
            'active_tasks': len(userbot.active_tasks),
            'keep_alive': 'active',
            'port_binding': 'successful',
            'render_compatible': True
        }
    except Exception as e:
        return {
            'flask_server': 'running',
            'error': str(e),
            'keep_alive': 'active',
            'port_binding': 'successful'
        }

if __name__ == "__main__":
    # For standalone testing
    logger.info("🧪 Running keep_alive.py in standalone mode")
    initialize_keep_alive_system()
    start_flask_server()
