import threading
import time
import requests
import logging
from flask import Flask, jsonify
from config import KEEP_ALIVE_URL, KEEP_ALIVE_INTERVAL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    """Main endpoint"""
    return """
    🤖 Telegram Auto-Forwarder Bot
    
    ✅ Status: Online & Running
    🔄 Service: Active 24/7
    📡 Keep-Alive: Enabled
    
    Bot is working perfectly!
    """

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        from userbot import userbot
        return jsonify({
            'status': 'healthy',
            'service': 'telegram-auto-forwarder',
            'userbot_running': userbot.is_running,
            'active_tasks': len(userbot.active_tasks),
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': time.time()
        }), 500

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return jsonify({
        'ping': 'pong',
        'timestamp': time.time()
    })

@app.route('/stats')
def stats():
    """Statistics endpoint"""
    try:
        from userbot import userbot
        return jsonify({
            'total_active_tasks': len(userbot.active_tasks),
            'userbot_status': 'running' if userbot.is_running else 'stopped',
            'uptime': 'continuous',
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def keep_alive():
    """Keep the service alive by making periodic requests"""
    def ping_server():
        while True:
            try:
                if KEEP_ALIVE_URL:
                    # Self-ping to prevent Render from sleeping
                    response = requests.get(
                        KEEP_ALIVE_URL, 
                        timeout=30,
                        headers={'User-Agent': 'KeepAlive-Bot/1.0'}
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"✅ Keep-alive ping successful - Status: {response.status_code}")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping failed - Status: {response.status_code}")
                        
                    # Also ping health endpoint
                    health_url = f"{KEEP_ALIVE_URL}/health"
                    health_response = requests.get(health_url, timeout=10)
                    logger.info(f"🏥 Health check - Status: {health_response.status_code}")
                    
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
    """Start Flask server in production mode"""
    try:
        logger.info("🌐 Starting Flask server...")
        app.run(
            host='0.0.0.0', 
            port=8080, 
            debug=False, 
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"❌ Flask server error: {e}")
        
def start_keep_alive_system():
    """Start complete keep-alive system"""
    # Start keep-alive pinging
    keep_alive()
    
    # Start Flask server in separate thread
    flask_thread = threading.Thread(target=start_flask_server, daemon=True)
    flask_thread.start()
    
    logger.info("🚀 Keep-alive system fully initialized")
    return flask_thread

# Health monitoring functions
def is_service_healthy():
    """Check if service is healthy"""
    try:
        from userbot import userbot
        return userbot.is_running
    except:
        return False

def get_system_stats():
    """Get system statistics"""
    try:
        from userbot import userbot
        return {
            'userbot_running': userbot.is_running,
            'active_tasks': len(userbot.active_tasks),
            'flask_server': 'running',
            'keep_alive': 'active'
        }
    except Exception as e:
        return {'error': str(e)}

if __name__ == "__main__":
    # For testing
    start_keep_alive_system()
    logger.info("Keep-alive system running in standalone mode")
