import os
import logging
import threading
import time
import requests
from flask import Flask, jsonify, request
from datetime import datetime
import signal
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global stats for monitoring
stats = {
    'start_time': time.time(),
    'health_checks': 0,
    'last_health_check': None,
    'status': 'starting',
    'bot_status': 'unknown',
    'restart_count': 0,
    'last_restart': None,
    'maintenance_mode': False,
    'continue_requests': 0
}

# Global control variables
bot_process = None
should_restart = False

def update_bot_status(status):
    """Update bot status from external process"""
    stats['bot_status'] = status
    logger.info(f"Bot status updated to: {status}")

@app.route('/')
def index():
    """Root endpoint with comprehensive system info"""
    uptime = time.time() - stats['start_time']
    return jsonify({
        'service': 'Telegram Auto-Forwarder',
        'status': stats['status'],
        'bot_status': stats['bot_status'],
        'uptime_seconds': int(uptime),
        'uptime_formatted': format_uptime(uptime),
        'health_checks': stats['health_checks'],
        'last_health_check': stats['last_health_check'],
        'restart_count': stats['restart_count'],
        'last_restart': stats['last_restart'],
        'maintenance_mode': stats['maintenance_mode'],
        'continue_requests': stats['continue_requests'],
        'endpoints': {
            'health': '/health',
            'stats': '/stats',
            'status': '/status',
            'continue': '/continue',
            'restart': '/restart',
            'maintenance': '/maintenance',
            'ping': '/ping',
            'logs': '/logs',
            'webhook': '/webhook'
        },
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/health')
def health_check():
    """Health check endpoint for monitoring services"""
    stats['health_checks'] += 1
    stats['last_health_check'] = datetime.utcnow().isoformat()
    
    # Update status based on uptime
    uptime = time.time() - stats['start_time']
    if uptime > 60:  # Running for more than 1 minute
        stats['status'] = 'running'
    
    # Check if in maintenance mode
    if stats['maintenance_mode']:
        return jsonify({
            'status': 'maintenance',
            'message': 'System is in maintenance mode',
            'uptime': int(uptime),
            'checks': stats['health_checks'],
            'timestamp': stats['last_health_check']
        }), 503
    
    return jsonify({
        'status': 'healthy',
        'uptime': int(uptime),
        'checks': stats['health_checks'],
        'bot_status': stats['bot_status'],
        'timestamp': stats['last_health_check']
    }), 200

@app.route('/continue', methods=['POST', 'GET'])
def continue_operation():
    """Continue/Resume bot operation endpoint"""
    try:
        stats['continue_requests'] += 1
        
        # Check if maintenance mode is active
        if stats['maintenance_mode']:
            stats['maintenance_mode'] = False
            stats['status'] = 'running'
            stats['bot_status'] = 'resuming'
            
            logger.info("System resumed from maintenance mode")
            
            return jsonify({
                'status': 'success',
                'message': 'System resumed from maintenance mode',
                'action': 'maintenance_mode_disabled',
                'timestamp': datetime.utcnow().isoformat(),
                'continue_requests': stats['continue_requests']
            }), 200
        
        # Check if bot needs to be restarted
        if should_restart or stats['bot_status'] in ['stopped', 'failed', 'error']:
            stats['bot_status'] = 'restarting'
            stats['restart_count'] += 1
            stats['last_restart'] = datetime.utcnow().isoformat()
            
            logger.info("Bot restart initiated via continue endpoint")
            
            # Trigger restart (in production, this would restart the worker process)
            global bot_process
            if bot_process:
                try:
                    bot_process.terminate()
                except:
                    pass
            
            return jsonify({
                'status': 'success',
                'message': 'Bot restart initiated',
                'action': 'restart_triggered',
                'restart_count': stats['restart_count'],
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        
        # If system is already running
        if stats['status'] == 'running' and stats['bot_status'] in ['running', 'active']:
            return jsonify({
                'status': 'info',
                'message': 'System is already running normally',
                'action': 'no_action_needed',
                'current_status': stats['status'],
                'bot_status': stats['bot_status'],
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        
        # Force resume if status is unclear
        stats['status'] = 'running'
        stats['bot_status'] = 'active'
        
        return jsonify({
            'status': 'success',
            'message': 'System status updated to running',
            'action': 'status_updated',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Continue endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to continue operation: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/restart', methods=['POST'])
def restart_system():
    """Restart the entire system"""
    try:
        stats['restart_count'] += 1
        stats['last_restart'] = datetime.utcnow().isoformat()
        stats['bot_status'] = 'restarting'
        
        logger.info("System restart requested via API")
        
        # Set restart flag
        global should_restart
        should_restart = True
        
        return jsonify({
            'status': 'success',
            'message': 'System restart initiated',
            'restart_count': stats['restart_count'],
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Restart endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to restart system: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/maintenance', methods=['POST', 'GET'])
def maintenance_mode():
    """Toggle maintenance mode"""
    try:
        if request.method == 'POST':
            # Toggle maintenance mode
            stats['maintenance_mode'] = not stats['maintenance_mode']
            action = 'enabled' if stats['maintenance_mode'] else 'disabled'
            
            if stats['maintenance_mode']:
                stats['status'] = 'maintenance'
                stats['bot_status'] = 'paused'
            else:
                stats['status'] = 'running'
                stats['bot_status'] = 'active'
            
            logger.info(f"Maintenance mode {action}")
            
            return jsonify({
                'status': 'success',
                'message': f'Maintenance mode {action}',
                'maintenance_mode': stats['maintenance_mode'],
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        
        else:
            # GET request - return current maintenance status
            return jsonify({
                'maintenance_mode': stats['maintenance_mode'],
                'status': stats['status'],
                'bot_status': stats['bot_status'],
                'timestamp': datetime.utcnow().isoformat()
            }), 200
            
    except Exception as e:
        logger.error(f"Maintenance endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Maintenance mode error: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/stats')
def get_stats():
    """Get detailed statistics"""
    uptime = time.time() - stats['start_time']
    
    return jsonify({
        'service_info': {
            'name': 'Telegram Auto-Forwarder',
            'status': stats['status'],
            'bot_status': stats['bot_status'],
            'uptime_seconds': int(uptime),
            'uptime_formatted': format_uptime(uptime),
            'maintenance_mode': stats['maintenance_mode']
        },
        'monitoring': {
            'health_checks': stats['health_checks'],
            'last_health_check': stats['last_health_check'],
            'avg_checks_per_minute': stats['health_checks'] / max(uptime / 60, 1),
            'continue_requests': stats['continue_requests']
        },
        'system': {
            'restart_count': stats['restart_count'],
            'last_restart': stats['last_restart'],
            'python_version': sys.version,
            'flask_env': os.environ.get('FLASK_ENV', 'production'),
            'port': os.environ.get('PORT', '8080')
        },
        'environment': {
            'api_id_set': bool(os.environ.get('API_ID')),
            'api_hash_set': bool(os.environ.get('API_HASH')),
            'bot_token_set': bool(os.environ.get('BOT_TOKEN')),
            'session_string_set': bool(os.environ.get('SESSION_STRING')),
            'admin_id_set': bool(os.environ.get('ADMIN_ID')),
            'db_url_set': bool(os.environ.get('DB_URL'))
        }
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return jsonify({
        'pong': True,
        'timestamp': datetime.utcnow().isoformat(),
        'status': stats['status'],
        'maintenance_mode': stats['maintenance_mode']
    })

@app.route('/status')
def status():
    """Detailed status endpoint"""
    uptime = time.time() - stats['start_time']
    
    # Check if main bot process should be running
    bot_status = 'unknown'
    if uptime > 30:  # Give bot 30 seconds to start
        bot_status = 'should_be_running'
    
    return jsonify({
        'web_server': 'online',
        'bot_process': bot_status,
        'current_status': stats['status'],
        'bot_status': stats['bot_status'],
        'uptime': int(uptime),
        'uptime_formatted': format_uptime(uptime),
        'maintenance_mode': stats['maintenance_mode'],
        'restart_count': stats['restart_count'],
        'port': os.environ.get('PORT', 'not_set'),
        'environment_check': {
            'api_id_set': bool(os.environ.get('API_ID')),
            'api_hash_set': bool(os.environ.get('API_HASH')),
            'bot_token_set': bool(os.environ.get('BOT_TOKEN')),
            'session_string_set': bool(os.environ.get('SESSION_STRING')),
            'admin_id_set': bool(os.environ.get('ADMIN_ID')),
            'db_url_set': bool(os.environ.get('DB_URL'))
        }
    })

@app.route('/logs')
def get_logs():
    """Get recent system logs"""
    try:
        log_lines = []
        if os.path.exists('bot.log'):
            with open('bot.log', 'r') as f:
                log_lines = f.readlines()[-100:]  # Last 100 lines
        
        return jsonify({
            'logs': log_lines,
            'log_count': len(log_lines),
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Failed to read logs: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for external services"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Handle different webhook types
        webhook_type = data.get('type', 'unknown')
        
        if webhook_type == 'restart':
            stats['restart_count'] += 1
            stats['last_restart'] = datetime.utcnow().isoformat()
            stats['bot_status'] = 'restarting'
            global should_restart
            should_restart = True
            
            logger.info("Restart triggered via webhook")
            
            return jsonify({
                'status': 'success',
                'message': 'Restart triggered via webhook',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        elif webhook_type == 'continue':
            stats['continue_requests'] += 1
            stats['maintenance_mode'] = False
            stats['status'] = 'running'
            stats['bot_status'] = 'active'
            
            logger.info("Continue triggered via webhook")
            
            return jsonify({
                'status': 'success',
                'message': 'Continue triggered via webhook',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        else:
            return jsonify({
                'status': 'error',
                'message': f'Unknown webhook type: {webhook_type}',
                'timestamp': datetime.utcnow().isoformat()
            }), 400
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Webhook processing failed: {str(e)}',
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested endpoint was not found',
        'available_endpoints': {
            'main': '/',
            'health': '/health',
            'stats': '/stats',
            'status': '/status',
            'continue': '/continue',
            'restart': '/restart',
            'maintenance': '/maintenance',
            'ping': '/ping',
            'logs': '/logs',
            'webhook': '/webhook'
        },
        'timestamp': datetime.utcnow().isoformat()
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred',
        'timestamp': datetime.utcnow().isoformat()
    }), 500

@app.errorhandler(503)
def service_unavailable(error):
    """Handle 503 errors"""
    return jsonify({
        'error': 'Service Unavailable',
        'message': 'System is temporarily unavailable',
        'maintenance_mode': stats['maintenance_mode'],
        'timestamp': datetime.utcnow().isoformat()
    }), 503

def format_uptime(seconds):
    """Format uptime in human readable format"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def run_keep_alive():
    """Run the Flask app to keep the service alive"""
    port = int(os.environ.get('PORT', 8080))
    
    # Set status to starting
    stats['status'] = 'starting'
    stats['bot_status'] = 'initializing'
    
    logger.info(f"Starting keep-alive server on port {port}")
    
    try:
        # Run Flask app
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True
        )
    except Exception as e:
        logger.error(f"Flask server error: {e}")
        stats['status'] = 'error'
        stats['bot_status'] = 'failed'

def start_keep_alive_thread():
    """Start keep-alive server in a separate thread"""
    def run_server():
        run_keep_alive()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info("Keep-alive thread started")
    
    # Update status after delay
    def update_status():
        time.sleep(5)
        stats['status'] = 'running'
        stats['bot_status'] = 'active'
    
    status_thread = threading.Thread(target=update_status, daemon=True)
    status_thread.start()
    
    return thread

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    stats['status'] = 'shutting_down'
    stats['bot_status'] = 'stopping'
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# For direct execution
if __name__ == '__main__':
    run_keep_alive()
