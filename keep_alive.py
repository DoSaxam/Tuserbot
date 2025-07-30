from flask import Flask
import os
import logging
import threading

app = Flask(__name__)
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    try:
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Flask server error: {e}")
        from utils import notify_admin
        threading.Thread(target=lambda: asyncio.run(notify_admin(None, f"Flask server error: {e}"))).start()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()