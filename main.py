import os
import asyncio
import psutil
import logging
import signal
import sys
from datetime import datetime, timedelta
from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from database import Database
from utils import with_retry, log_message, notify_admin, setup_logging
from keep_alive import run_flask_server

# Environment Variables
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]  # Control bot token
SESSION_STRING = os.environ["SESSION_STRING"]  # UserBot session
ADMIN_ID = int(os.environ["ADMIN_ID"])

# Performance Settings
GLOBAL_MSG_LIMIT = 100  # messages per minute globally
CHAT_MSG_LIMIT = 25     # messages per minute per chat
QUEUE_SIZE = 500        # max queue capacity
WORKER_COUNT = 4        # concurrent workers

# Global State
message_queue = asyncio.Queue(maxsize=QUEUE_SIZE)
chat_counters = {}  # {chat_id: {'count': int, 'reset_time': datetime}}
forwarding_enabled = True
tasks_cache = {}

# Initialize clients
userbot = Client("userbot", api_id=API_ID, api_hash=API_HASH, 
                session_string=SESSION_STRING, in_memory=True)
control_bot = Client("control", api_id=API_ID, api_hash=API_HASH, 
                    bot_token=BOT_TOKEN, in_memory=True)

db = Database()

class ForwardingBot:
    def __init__(self):
        self.setup_logging()
        self.global_counter = {'count': 0, 'reset_time': datetime.now()}
    
    def setup_logging(self):
        setup_logging()
        logging.info("🚀 Telegram Forwarder Starting...")

    async def init_database(self):
        """Initialize database connection"""
        await db.connect()
        await self.load_tasks_cache()

    async def load_tasks_cache(self):
        """Load active tasks into memory for faster access"""
        global tasks_cache
        tasks = await db.get_all_tasks()
        tasks_cache = {task['source_id']: [] for task in tasks}
        for task in tasks:
            if task['is_active']:
                tasks_cache.setdefault(task['source_id'], []).append(task)
        log_message(f"Loaded {len(tasks)} tasks into cache")

    async def check_rate_limit(self, chat_id):
        """Smart rate limiting with time windows"""
        now = datetime.now()
        
        # Global rate limit check
        if now - self.global_counter['reset_time'] >= timedelta(minutes=1):
            self.global_counter = {'count': 0, 'reset_time': now}
        
        if self.global_counter['count'] >= GLOBAL_MSG_LIMIT:
            wait_time = 60 - (now - self.global_counter['reset_time']).seconds
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                self.global_counter = {'count': 0, 'reset_time': datetime.now()}
        
        # Per-chat rate limit check
        if chat_id not in chat_counters:
            chat_counters[chat_id] = {'count': 0, 'reset_time': now}
        
        chat_data = chat_counters[chat_id]
        if now - chat_data['reset_time'] >= timedelta(minutes=1):
            chat_counters[chat_id] = {'count': 0, 'reset_time': now}
        
        if chat_data['count'] >= CHAT_MSG_LIMIT:
            wait_time = 60 - (now - chat_data['reset_time']).seconds
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                chat_counters[chat_id] = {'count': 0, 'reset_time': datetime.now()}

    async def forward_worker(self):
        """Message forwarding worker"""
        while True:
            try:
                msg, dest_id = await message_queue.get()
                
                if not forwarding_enabled:
                    message_queue.task_done()
                    continue
                
                await self.check_rate_limit(dest_id)
                
                # Forward message with retry logic
                await self.forward_message_with_retry(msg, dest_id)
                
                # Update counters
                self.global_counter['count'] += 1
                chat_counters.setdefault(dest_id, {'count': 0, 'reset_time': datetime.now()})['count'] += 1
                
                message_queue.task_done()
                
            except Exception as e:
                log_message(f"Worker error: {e}")
                message_queue.task_done()

    @with_retry(attempts=3, delay=2)
    async def forward_message_with_retry(self, message, dest_id):
        """Forward message with error handling"""
        try:
            await message.copy(dest_id)
        except errors.FloodWait as e:
            log_message(f"FloodWait: {e.value}s for chat {dest_id}")
            await asyncio.sleep(e.value + 1)
            await message.copy(dest_id)
        except errors.ChannelPrivate:
            await self.disable_tasks_for_destination(dest_id)
            await notify_admin(control_bot, f"❌ Destination {dest_id} is private. Tasks disabled.")
        except errors.UserDeactivated:
            await notify_admin(control_bot, f"❌ UserBot deactivated. Please check session.")
        except Exception as e:
            log_message(f"Forward error to {dest_id}: {e}")
            raise

    async def disable_tasks_for_destination(self, dest_id):
        """Disable all tasks for a problematic destination"""
        await db.disable_tasks_by_destination(dest_id)
        await self.load_tasks_cache()

    async def resource_monitor(self):
        """Monitor system resources"""
        while True:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
                queue_size = message_queue.qsize()
                
                log_message(f"📊 Queue: {queue_size} | RAM: {memory_mb:.1f}MB | CPU: {cpu_percent:.1f}%")
                
                # Memory management
                if memory_mb > 450:
                    await notify_admin(control_bot, f"🚨 High memory usage: {memory_mb:.1f}MB. Restarting...")
                    os.execl(sys.executable, sys.executable, *sys.argv)
                elif memory_mb > 350:
                    global forwarding_enabled
                    forwarding_enabled = False
                    await asyncio.sleep(30)  # Pause forwarding
                    forwarding_enabled = True
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                log_message(f"Monitor error: {e}")

# Control Bot Handlers
@control_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def start_command(client, message):
    """Start command with main menu"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Tasks", callback_data="list_tasks")],
        [InlineKeyboardButton("➕ Add Task", callback_data="add_task")],
        [InlineKeyboardButton("⏸️ Pause All", callback_data="pause_all"),
         InlineKeyboardButton("▶️ Resume All", callback_data="resume_all")],
        [InlineKeyboardButton("📊 Status", callback_data="status")]
    ])
    await message.reply("🤖 **Telegram Forwarder Control Panel**\n\nChoose an option:", reply_markup=keyboard)

@control_bot.on_message(filters.command("tasks") & filters.user(ADMIN_ID))
async def list_tasks_command(client, message):
    """List all tasks"""
    await show_tasks_list(client, message)

@control_bot.on_callback_query(filters.user(ADMIN_ID))
async def callback_handler(client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    data = callback_query.data
    
    if data == "list_tasks":
        await show_tasks_list(client, callback_query.message)
    elif data == "add_task":
        await callback_query.message.edit_text(
            "➕ **Add New Task**\n\n"
            "Send source and destination IDs in this format:\n"
            "`source_id destination_id`\n\n"
            "Example: `-1001234567890 -1009876543210`"
        )
        # Set user state for next message
        await db.set_user_state(ADMIN_ID, "waiting_task_ids")
    elif data == "pause_all":
        global forwarding_enabled
        forwarding_enabled = False
        await callback_query.answer("⏸️ All forwarding paused")
        await callback_query.message.edit_text("⏸️ **All forwarding has been paused**")
    elif data == "resume_all":
        forwarding_enabled = True
        await callback_query.answer("▶️ All forwarding resumed")
        await callback_query.message.edit_text("▶️ **All forwarding has been resumed**")
    elif data == "status":
        await show_status(client, callback_query.message)
    elif data.startswith("toggle_"):
        task_id = int(data.split("_")[1])
        await toggle_task(task_id)
        await callback_query.answer("✅ Task toggled")
        await show_tasks_list(client, callback_query.message)
    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        await db.delete_task(task_id)
        await bot.load_tasks_cache()
        await callback_query.answer("🗑️ Task deleted")
        await show_tasks_list(client, callback_query.message)

async def show_tasks_list(client, message):
    """Display all tasks with buttons"""
    tasks = await db.get_all_tasks()
    
    if not tasks:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add First Task", callback_data="add_task")]
        ])
        await message.edit_text("📋 **No tasks found**\n\nAdd your first forwarding task!", reply_markup=keyboard)
        return
    
    text = "📋 **Active Forwarding Tasks**\n\n"
    keyboard_buttons = []
    
    for task in tasks:
        status = "✅" if task['is_active'] else "❌"
        text += f"{status} **Task #{task['id']}**\n"
        text += f"   Source: `{task['source_id']}`\n"
        text += f"   Destination: `{task['destination_id']}`\n\n"
        
        # Add buttons for each task
        keyboard_buttons.append([
            InlineKeyboardButton(f"{status} Toggle #{task['id']}", callback_data=f"toggle_{task['id']}"),
            InlineKeyboardButton(f"🗑️ Delete #{task['id']}", callback_data=f"delete_{task['id']}")
        ])
    
    # Add control buttons
    keyboard_buttons.append([InlineKeyboardButton("➕ Add Task", callback_data="add_task")])
    keyboard_buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="list_tasks")])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    await message.edit_text(text, reply_markup=keyboard)

async def show_status(client, message):
    """Show system status"""
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent()
    queue_size = message_queue.qsize()
    
    tasks = await db.get_all_tasks()
    active_tasks = sum(1 for task in tasks if task['is_active'])
    
    status_text = f"""
📊 **System Status**

🤖 **Bot Status**: {'🟢 Online' if forwarding_enabled else '🔴 Paused'}
📋 **Tasks**: {active_tasks}/{len(tasks)} active
📨 **Queue**: {queue_size} messages
💾 **Memory**: {memory_mb:.1f} MB
⚡ **CPU**: {cpu_percent:.1f}%
⏱️ **Uptime**: {datetime.now().strftime('%H:%M:%S')}

🔄 **Rate Limits**:
• Global: {GLOBAL_MSG_LIMIT} msg/min
• Per Chat: {CHAT_MSG_LIMIT} msg/min
"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="status")],
        [InlineKeyboardButton("📋 View Tasks", callback_data="list_tasks")]
    ])
    
    await message.edit_text(status_text, reply_markup=keyboard)

async def toggle_task(task_id):
    """Toggle task active status"""
    await db.toggle_task(task_id)
    await bot.load_tasks_cache()

@control_bot.on_message(filters.text & filters.user(ADMIN_ID))
async def handle_text_input(client, message):
    """Handle text input for adding tasks"""
    user_state = await db.get_user_state(ADMIN_ID)
    
    if user_state == "waiting_task_ids":
        try:
            # Parse source and destination IDs
            ids = message.text.strip().split()
            if len(ids) != 2:
                await message.reply("❌ Please send exactly 2 IDs: `source_id destination_id`")
                return
            
            source_id = int(ids[0])
            dest_id = int(ids[1])
            
            # Add task to database
            task_id = await db.add_task(source_id, dest_id)
            await bot.load_tasks_cache()
            
            # Clear user state
            await db.set_user_state(ADMIN_ID, None)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View All Tasks", callback_data="list_tasks")]
            ])
            
            await message.reply(
                f"✅ **Task #{task_id} Added Successfully**\n\n"
                f"Source: `{source_id}`\n"
                f"Destination: `{dest_id}`\n"
                f"Status: ✅ Active",
                reply_markup=keyboard
            )
            
        except ValueError:
            await message.reply("❌ Invalid IDs. Please send numeric IDs only.")
        except Exception as e:
            await message.reply(f"❌ Error adding task: {e}")

# UserBot Message Handler
@userbot.on_message(group=-1)
async def handle_incoming_message(client, message):
    """Handle all incoming messages for forwarding"""
    if not forwarding_enabled:
        return
    
    source_id = message.chat.id
    if source_id not in tasks_cache:
        return
    
    # Queue messages for forwarding
    for task in tasks_cache[source_id]:
        if task['is_active']:
            try:
                message_queue.put_nowait((message, task['destination_id']))
            except asyncio.QueueFull:
                log_message("⚠️ Message queue full, dropping message")

# Main Application
async def main():
    """Main application entry point"""
    global bot
    bot = ForwardingBot()
    
    # Start Flask server for keep-alive
    run_flask_server()
    
    # Initialize database
    await bot.init_database()
    
    # Start worker tasks
    for _ in range(WORKER_COUNT):
        asyncio.create_task(bot.forward_worker())
    
    # Start monitoring
    asyncio.create_task(bot.resource_monitor())
    
    # Start both bots
    await userbot.start()
    await control_bot.start()
    
    log_message("🚀 Telegram Forwarder is now running!")
    await notify_admin(control_bot, "🚀 **Bot Started Successfully**\n\nType /start to access the control panel.")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
