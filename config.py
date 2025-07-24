import os
from dotenv import load_dotenv

load_dotenv()

# Telegram API credentials
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

# Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

# Database
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

# Keep alive settings
KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL")
KEEP_ALIVE_INTERVAL = 300  # 5 minutes

# Forwarding settings
MAX_RETRIES = 3
RETRY_DELAY = 2
