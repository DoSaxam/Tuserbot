import os
import logging
from flask import Flask, jsonify
from threading import Thread
import psutil
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def home():
    """Basic home endpoint"""
    return jsonify({
        "status": "online",
        "service": "telegram-forwarder",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Health check endpoint for monitoring"""
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent()
        
        return jsonify({
            "status": "healthy",
            "memory_mb": round(memory_mb, 2),
            "cpu_percent": round(cpu_percent, 2),
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/stats')
def stats():
    """Detailed stats endpoint"""
    try:
        process = psutil.Process()
        return jsonify({
            "memory": {
                "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "vms_mb": round(process.memory_info().vms / 1024 / 1024, 2)
            },
            "cpu_percent": round(process.cpu_percent(), 2),
            "threads": process.num_threads(),
            "uptime": str(datetime.now() - datetime.fromtimestamp(process.create_time())),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask_server():
    """Run Flask server in a separate thread"""
    def run():
        port = int(os.environ.get('PORT', 8080))
        logging.info(f"🌐 Flask server starting on port {port}")
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
    
    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread

if __name__ == '__main__':
    run_flask_server()
