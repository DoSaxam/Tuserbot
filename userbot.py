import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, ChatWriteForbidden, UserDeactivated, SessionPasswordNeeded
from config import API_ID, API_HASH, SESSION_STRING, MAX_RETRIES, RETRY_DELAY
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramUserbot:
    def __init__(self):
        self.app = Client(
            "userbot_session",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=SESSION_STRING
        )
        self.active_tasks = {}
        self.is_running = False
    
    async def start_userbot(self):
        """Start the userbot"""
        try:
            await self.app.start()
            self.is_running = True
            logger.info("✅ Userbot started successfully!")
            
            # Load existing tasks
            await self.load_tasks()
            
            # Set up message handler
            @self.app.on_message()
            async def message_handler(client, message):
                try:
                    await self.handle_new_message(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
                    
        except SessionPasswordNeeded:
            logger.error("❌ 2FA Password required. Please disable 2FA or provide password.")
            raise
        except Exception as e:
            logger.error(f"❌ Error starting userbot: {e}")
            await asyncio.sleep(5)
            await self.restart_userbot()
    
    async def restart_userbot(self):
        """Restart userbot"""
        try:
            if self.is_running:
                await self.stop_userbot()
            await asyncio.sleep(3)
            await self.start_userbot()
        except Exception as e:
            logger.error(f"Error restarting userbot: {e}")
    
    async def load_tasks(self):
        """Load all active tasks from database"""
        try:
            tasks = await db.get_all_active_tasks()
            self.active_tasks = {}
            for task in tasks:
                self.active_tasks[task.id] = {
                    'source_chat': task.source_chat,
                    'dest_chat': task.dest_chat,
                    'task_name': task.task_name,
                    'status': task.status
                }
            logger.info(f"📋 Loaded {len(tasks)} active forwarding tasks")
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
    
    async def handle_new_message(self, message):
        """Handle incoming messages and forward if needed"""
        try:
            source_chat = message.chat.id
            
            # Check all active tasks for this source
            for task_id, task in self.active_tasks.items():
                if (task["source_chat"] == source_chat and 
                    task["status"] == "active"):
                    
                    await self.forward_message(message, task)
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def forward_message(self, message, task):
        """Forward message to destination with retry logic"""
        for attempt in range(MAX_RETRIES):
            try:
                # Get destination chat ID
                dest_chat = task["dest_chat"]
                
                # Forward the message
                await self.app.forward_messages(
                    chat_id=dest_chat,
                    from_chat_id=message.chat.id,
                    message_ids=message.id
                )
                
                logger.info(f"✅ Message forwarded: {message.chat.id} → {dest_chat}")
                break
                
            except FloodWait as e:
                logger.warning(f"⏳ Flood wait: {e.value} seconds")
                await asyncio.sleep(e.value)
                
            except ChatWriteForbidden:
                logger.error(f"❌ Cannot write to destination chat: {task['dest_chat']}")
                break
                
            except Exception as e:
                logger.error(f"❌ Forward attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    logger.error(f"❌ Failed to forward after {MAX_RETRIES} attempts")
    
    async def add_forwarding_task(self, source_chat_id, destination_chat_id, task_name=""):
        """Add new forwarding task"""
        try:
            task_name = task_name or f"Task_{source_chat_id}→{destination_chat_id}"
            
            task_id = await db.add_task(source_chat_id, destination_chat_id, task_name)
            if task_id:
                self.active_tasks[task_id] = {
                    'source_chat': source_chat_id,
                    'dest_chat': destination_chat_id,
                    'task_name': task_name,
                    'status': 'active'
                }
                logger.info(f"✅ Added forwarding task: {task_name}")
                return task_id
            return None
            
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            return None
    
    async def disable_task(self, task_id):
        """Disable forwarding task"""
        try:
            success = await db.update_task_status(task_id, "inactive")
            if success and task_id in self.active_tasks:
                self.active_tasks[task_id]['status'] = 'inactive'
            return success
        except Exception as e:
            logger.error(f"Error disabling task: {e}")
            return False
    
    async def enable_task(self, task_id):
        """Enable forwarding task"""
        try:
            success = await db.update_task_status(task_id, "active")
            if success:
                task = await db.get_task_by_id(task_id)
                if task:
                    self.active_tasks[task_id] = {
                        'source_chat': task.source_chat,
                        'dest_chat': task.dest_chat,
                        'task_name': task.task_name,
                        'status': 'active'
                    }
            return success
        except Exception as e:
            logger.error(f"Error enabling task: {e}")
            return False
    
    async def delete_task(self, task_id):
        """Delete forwarding task"""
        try:
            success = await db.delete_task(task_id)
            if success and task_id in self.active_tasks:
                del self.active_tasks[task_id]
            return success
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return False
    
    async def stop_userbot(self):
        """Stop the userbot"""
        try:
            if self.is_running:
                await self.app.stop()
                self.is_running = False
                logger.info("🛑 Userbot stopped")
        except Exception as e:
            logger.error(f"Error stopping userbot: {e}")

# Global userbot instance
userbot = TelegramUserbot()
