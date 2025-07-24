# main.py (Run this on Render)
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from userbot import main as userbot_main
from control_bot import updater
from config import RENDER_URL

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def ping_self():
    try:
        requests.get(RENDER_URL)
    except Exception:
        pass  # Error handling

scheduler = BackgroundScheduler()
scheduler.add_job(ping_self, 'interval', minutes=5)
scheduler.start()

if __name__ == '__main__':
    import threading
    threading.Thread(target=userbot_main).start()  # Run userbot
    threading.Thread(target=updater.start_polling).start()  # Run control bot
    app.run(host='0.0.0.0', port=8080)  # Flask for Render
