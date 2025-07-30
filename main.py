import asyncio
import os
import time
import psutil
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, ChannelPrivate
from utils import with_retry, notify_admin
from database import Database

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Client(
    "userbot",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    session_string=os.environ["SESSION_STRING"]
)

queue = asyncio.Queue()
active_tasks = {}

async def forward_message(task, message):
    try:
        await queue.put((task, message))
    except Exception as e:
        logger.error(f"Queue error: {e}")
        await notify_admin(app, f"Queue error: {e}")

async def process_queue():
    while True:
        task, message = await queue.get()
        if not task["is_active"]:
            queue.task_done()
            continue
        try:
            await with_retry(app.forward_messages)(
                chat_id=task["destination_id"],
                from_chat_id=task["source_id"],
                message_ids=message.id
            )
            logger.info(f"Forwarded message {message.id} from {task['source_id']} to {task['destination_id']}")
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.x} seconds")
            await asyncio.sleep(e.x)
        except ChannelPrivate:
            logger.error(f"Channel {task['source_id']} is private or inaccessible")
            await notify_admin(app, f"Channel {task['source_id']} is private. Task disabled.")
            async with Database() as db:
                await db.update_task_status(task["id"], False)
        except Exception as e:
            logger.error(f"Forwarding error: {e}")
            await notify_admin(app, f"Forwarding error: {e}")
        queue.task_done()

async def monitor_resources():
    while True:
        process = psutil.Process()
        mem = process.memory_info().rss / 1024 / 1024  # MB
        cpu = process.cpu_percent(interval=1)
        logger.info(f"Memory: {mem:.2f} MB, CPU: {cpu:.2f}%")
        if mem > 350:
            logger.warning("High memory usage, throttling...")
            await asyncio.sleep(5)
        if mem > 450:
            logger.error("Memory overflow, restarting...")
            await notify_admin(app, "Memory overflow, restarting...")
            os.execl(sys.executable, sys.executable, *sys.argv)
        await asyncio.sleep(300)

async def main():
    async with Database() as db:
        tasks = await db.get_tasks()
        for task in tasks:
            active_tasks[task["id"]] = task
            app.on_message(filters.chat(task["source_id"]) & filters.incoming)(forward_message)
    
    asyncio.create_task(process_queue())
    asyncio.create_task(monitor_resources())
    await app.start()
    logger.info("UserBot started")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        for var in ["API_ID", "API_HASH", "SESSION_STRING", "DB_URL", "ADMIN_ID"]:
            if not os.environ.get(var):
                logger.error(f"Missing environment variable: {var}")
                exit(1)
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        notify_admin(app, f"Fatal error: {e}")
        os.execl(sys.executable, sys.executable, *sys.argv)