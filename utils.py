import asyncio
import logging
import functools
from pyrogram.errors import FloodWait

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def with_retry(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return await func(*args, **kwargs)
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.x} seconds")
                await asyncio.sleep(e.x)
            except Exception as e:
                logger.error(f"Retry {attempt + 1} failed: {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    return wrapper

async def notify_admin(client, message):
    if client:
        try:
            await client.send_message(int(os.environ["ADMIN_ID"]), f"Error: {message}")
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")off  
    return wrapper  
  
# FloodWait handler  
def handle_floodwait(func):  
    async def wrapper(*args, **kwargs):  
        try:  
            return await func(*args, **kwargs)  
        except Exception as e:  
            if "FloodWait" in str(e):  
                wait_time = int(str(e).split()[-1])  
                logger.warning(f"FloodWait detected, sleeping {wait_time}s")  
                await asyncio.sleep(wait_time + 5)  
                return await func(*args, **kwargs)  
            raise  
    return wrapper  
  
# Admin notifications  
async def notify_admin(message: str):  
    try:  
        async with Client(  
            "notify",  
            api_id=os.getenv("API_ID"),  
            api_hash=os.getenv("API_HASH"),  
            bot_token=os.getenv("BOT_TOKEN")  
        ) as bot:  
            await bot.send_message(  
                chat_id=int(os.getenv("ADMIN_ID")),  
                text=message  
            )  
    except Exception as e:  
        logger.error(f"Failed to notify admin: {str(e)}")  
  
# Resource monitor  
async def resource_monitor():  
    while True:  
        mem = psutil.virtual_memory()  
        cpu = psutil.cpu_percent()  
          
        if mem.percent > 80:  
            logger.warning(f"High memory usage: {mem.percent}%")  
            await notify_admin(f"🚨 High memory usage: {mem.percent}%")  
          
        if cpu > 90:  
            logger.warning(f"High CPU usage: {cpu}%")  
            await notify_admin(f"🚨 High CPU usage: {cpu}%")  
          
        await asyncio.sleep(300)  # Check every 5 minutes  
  
# Health endpoint for web process  
async def health_handler(request):  
    return web.Response(text="OK")  
  
# Sanitization helpers  
def sanitize_id(value):  
    try:  
        return abs(int(value))  
    except:  
        return None  
  
def validate_source(source):  
    if not source:  
        return False  
    # Add more validation as needed  
    return True

