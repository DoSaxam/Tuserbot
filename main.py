import asyncio
import logging
import os
import time
import psutil
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, ChannelPrivate, ChatAdminRequired, UserNotParticipant, SessionExpired

from database import Database
from utils import setup_logging, retry_on_failure, send_admin_notification, ResourceMonitor, RateLimiter, MessageValidator, ConfigValidator
from keep_alive import start_keep_alive_thread

# Setup logging
logger = setup_logging()

class TelegramForwarder:
    def __init__(self):
        # Validate environment variables first
        validation_results = ConfigValidator.validate_env_vars()
        missing_vars = ConfigValidator.get_missing_vars(validation_results)
        
        if missing_vars:
            raise ValueError(f"Missing or invalid environment variables: {', '.join(missing_vars)}")
        
        self.API_ID = int(os.environ.get('API_ID'))
        self.API_HASH = os.environ.get('API_HASH')
        self.BOT_TOKEN = os.environ.get('BOT_TOKEN')
        self.SESSION_STRING = os.environ.get('SESSION_STRING')
        self.ADMIN_ID = int(os.environ.get('ADMIN_ID'))
        
        # Initialize clients
        self.userbot = Client(
            "userbot",
            api_id=self.API_ID,
            api_hash=self.API_HASH,
            session_string=self.SESSION_STRING
        )
        
        self.control_bot = Client(
            "control_bot",
            api_id=self.API_ID,
            api_hash=self.API_HASH,
            bot_token=self.BOT_TOKEN
        )
        
        # Initialize components
        self.db = Database()
        self.resource_monitor = ResourceMonitor()
        self.rate_limiter = RateLimiter()
        
        # Message queue and workers
        self.message_queue = asyncio.Queue(maxsize=500)
        self.is_running = True
        self.worker_tasks = []
        self.user_states = {}
        
        # Statistics
        self.stats = {
            'messages_forwarded': 0,
            'errors': 0,
            'start_time': time.time(),
            'queue_size': 0
        }
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup message and callback handlers"""
        
        @self.control_bot.on_message(filters.command("start") & filters.user(self.ADMIN_ID))
        async def start_command(client, message):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Task", callback_data="add_task")],
                [InlineKeyboardButton("📋 List Tasks", callback_data="list_tasks")],
                [InlineKeyboardButton("📊 System Status", callback_data="system_status")],
                [InlineKeyboardButton("⏸️ Pause All", callback_data="pause_all"),
                 InlineKeyboardButton("▶️ Resume All", callback_data="resume_all")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_main")]
            ])
            
            await message.reply_text(
                "🤖 **Telegram Auto-Forwarder Control Panel**\n\n"
                "Select an option below to manage your forwarding tasks:",
                reply_markup=keyboard
            )
        
        @self.control_bot.on_message(filters.command("tasks") & filters.user(self.ADMIN_ID))
        async def tasks_command(client, message):
            await self._send_tasks_list(message)
        
        @self.control_bot.on_message(filters.command("test") & filters.user(self.ADMIN_ID))
        async def test_command(client, message):
            try:
                userbot_me = await self.userbot.get_me()
                control_bot_me = await self.control_bot.get_me()
                db_status = await self.db.test_connection()
                
                status_text = (
                    "✅ **Connection Test Results**\n\n"
                    f"UserBot: ✅ Connected as {userbot_me.first_name}\n"
                    f"Control Bot: ✅ Connected as {control_bot_me.first_name}\n"
                    f"Database: {'✅ Connected' if db_status else '❌ Failed'}\n"
                    f"Queue Size: {self.message_queue.qsize()}\n"
                    f"Memory Usage: {self.resource_monitor.get_memory_usage():.1f}MB"
                )
                await message.reply_text(status_text)
            except Exception as e:
                await message.reply_text(f"❌ Test failed: {str(e)}")
        
        @self.control_bot.on_message(filters.text & filters.user(self.ADMIN_ID))
        async def text_handler(client, message):
            user_id = message.from_user.id
            if user_id in self.user_states:
                await self._handle_add_task_input(message)
        
        @self.control_bot.on_callback_query()
        async def callback_handler(client, callback_query):
            await self._handle_callback_query(callback_query)
        
        @self.userbot.on_message(filters.all)
        async def message_handler(client, message):
            await self._handle_incoming_message(message)
    
    async def _handle_callback_query(self, query: CallbackQuery):
        """Handle callback queries from inline keyboards"""
        data = query.data
        user_id = query.from_user.id
        
        try:
            if data == "add_task":
                await self._start_add_task_flow(query)
            elif data == "list_tasks":
                await self._send_tasks_list_callback(query)
            elif data == "system_status":
                await self._send_system_status(query)
            elif data == "pause_all":
                await self._pause_all_tasks(query)
            elif data == "resume_all":
                await self._resume_all_tasks(query)
            elif data == "refresh_main":
                await self._refresh_main_panel(query)
            elif data.startswith("toggle_task_"):
                task_id = int(data.replace("toggle_task_", ""))
                await self._toggle_task(query, task_id)
            elif data.startswith("delete_task_"):
                task_id = int(data.replace("delete_task_", ""))
                await self._delete_task(query, task_id)
            elif data == "back_to_main":
                await self._back_to_main(query)
                
        except Exception as e:
            logger.error(f"Callback handler error: {e}")
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    async def _start_add_task_flow(self, query: CallbackQuery):
        """Start the add task flow"""
        self.user_states[query.from_user.id] = {'step': 'waiting_source'}
        await query.edit_message_text(
            "📝 **Add New Forwarding Task**\n\n"
            "Please send me the **source channel/chat ID** or username\n"
            "Example: `-1001234567890` or `@channel_username`",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
            ]])
        )
        await query.answer()
    
    async def _handle_add_task_input(self, message: Message):
        """Handle text input during add task flow"""
        user_id = message.from_user.id
        state = self.user_states.get(user_id, {})
        
        try:
            if state.get('step') == 'waiting_source':
                # Validate source ID
                source_id = MessageValidator.validate_chat_id(message.text)
                if source_id is None:
                    await message.reply_text(
                        "❌ Invalid chat ID format!\n\n"
                        "Please send a valid chat ID like:\n"
                        "• `-1001234567890` (for channels/groups)\n"
                        "• `@username` (will be resolved)\n"
                        "• Or use /start to cancel"
                    )
                    return
                
                # Try to get chat info to validate
                try:
                    chat = await self.userbot.get_chat(source_id)
                    self.user_states[user_id] = {
                        'step': 'waiting_destination',
                        'source_id': source_id if isinstance(source_id, int) else chat.id,
                        'source_title': chat.title or chat.first_name or "Unknown"
                    }
                    
                    await message.reply_text(
                        f"✅ Source chat validated: **{chat.title or chat.first_name}**\n\n"
                        "Now send me the **destination channel/chat ID** where messages should be forwarded:",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
                        ]])
                    )
                except Exception as e:
                    await message.reply_text(
                        f"❌ Cannot access source chat: {str(e)}\n\n"
                        "Make sure:\n"
                        "• The UserBot is a member of this chat\n"
                        "• The chat ID is correct\n"
                        "• The chat is not private"
                    )
            
            elif state.get('step') == 'waiting_destination':
                # Validate destination ID
                dest_id = MessageValidator.validate_chat_id(message.text)
                if dest_id is None:
                    await message.reply_text(
                        "❌ Invalid destination chat ID format!\n\n"
                        "Please send a valid chat ID or use /start to cancel"
                    )
                    return
                
                # Try to get destination chat info
                try:
                    dest_chat = await self.userbot.get_chat(dest_id)
                    final_dest_id = dest_id if isinstance(dest_id, int) else dest_chat.id
                    
                    # Create the task
                    success = await self.db.add_task(state['source_id'], final_dest_id)
                    
                    if success:
                        await message.reply_text(
                            f"✅ **Task Created Successfully!**\n\n"
                            f"📥 **From:** {state['source_title']}\n"
                            f"📤 **To:** {dest_chat.title or dest_chat.first_name}\n\n"
                            "The forwarding task is now active and will start processing messages immediately.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("📋 View All Tasks", callback_data="list_tasks"),
                                InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_main")
                            ]])
                        )
                        
                        # Clear user state
                        del self.user_states[user_id]
                        
                        # Send admin notification
                        await send_admin_notification(
                            self.control_bot, self.ADMIN_ID,
                            f"📝 New forwarding task created:\n"
                            f"From: {state['source_title']}\n"
                            f"To: {dest_chat.title or dest_chat.first_name}"
                        )
                    else:
                        await message.reply_text("❌ Failed to create task. Please try again.")
                        
                except Exception as e:
                    await message.reply_text(
                        f"❌ Cannot access destination chat: {str(e)}\n\n"
                        "Make sure the UserBot has permission to send messages to this chat."
                    )
                    
        except Exception as e:
            logger.error(f"Add task input error: {e}")
            await message.reply_text(f"❌ Error: {str(e)}")
    
    async def _send_tasks_list(self, message: Message):
        """Send tasks list via message"""
        tasks = await self.db.get_all_tasks()
        
        if not tasks:
            await message.reply_text(
                "📋 **No forwarding tasks found**\n\n"
                "Use /start and click ➕ Add Task to create your first forwarding task."
            )
            return
        
        text = "📋 **Your Forwarding Tasks**\n\n"
        
        for task in tasks:
            status_icon = "✅ Active" if task['is_active'] else "❌ Inactive"
            text += f"**Task #{task['id']}** - {status_icon}\n"
            text += f"📥 From: `{task['source_id']}`\n"
            text += f"📤 To: `{task['destination_id']}`\n"
            text += f"📅 Created: {task['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
        
        await message.reply_text(text)
    
    async def _send_tasks_list_callback(self, query: CallbackQuery):
        """Send tasks list via callback"""
        tasks = await self.db.get_all_tasks()
        
        if not tasks:
            await query.edit_message_text(
                "📋 **No forwarding tasks found**\n\n"
                "Use ➕ Add Task to create your first forwarding task.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
                ]])
            )
            await query.answer()
            return
        
        keyboard = []
        text = "📋 **Active Forwarding Tasks**\n\n"
        
        for task in tasks:
            status_icon = "✅" if task['is_active'] else "❌"
            text += f"{status_icon} Task #{task['id']}\n"
            text += f"   📥 From: `{task['source_id']}`\n"
            text += f"   📤 To: `{task['destination_id']}`\n\n"
            
            keyboard.append([
                InlineKeyboardButton(f"{status_icon} Toggle #{task['id']}", 
                                   callback_data=f"toggle_task_{task['id']}"),
                InlineKeyboardButton("🗑️ Delete", 
                                   callback_data=f"delete_task_{task['id']}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_main")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()
    
    async def _send_system_status(self, query: CallbackQuery):
        """Send system status"""
        memory_usage = self.resource_monitor.get_memory_usage()
        cpu_usage = self.resource_monitor.get_cpu_usage()
        uptime = time.time() - self.stats['start_time']
        uptime_str = str(timedelta(seconds=int(uptime)))
        
        status_text = (
            "📊 **System Status**\n\n"
            f"🔄 Uptime: {uptime_str}\n"
            f"💾 Memory: {memory_usage:.1f}MB / 400MB\n"
            f"⚡ CPU: {cpu_usage:.1f}%\n"
            f"📨 Queue Size: {self.message_queue.qsize()}/500\n"
            f"✅ Messages Forwarded: {self.stats['messages_forwarded']}\n"
            f"❌ Errors: {self.stats['errors']}\n"
            f"🔧 Workers: {len(self.worker_tasks)} active\n"
            f"🛠️ Status: {'🟢 Running' if self.is_running else '🔴 Paused'}"
        )
        
        await query.edit_message_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Refresh", callback_data="system_status"),
                InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
            ]])
        )
        await query.answer()
    
    async def _pause_all_tasks(self, query: CallbackQuery):
        """Pause all forwarding tasks"""
        try:
            success = await self.db.pause_all_tasks()
            if success:
                await query.edit_message_text(
                    "⏸️ **All tasks paused successfully!**\n\n"
                    "No messages will be forwarded until you resume the tasks.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("▶️ Resume All", callback_data="resume_all"),
                        InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
                    ]])
                )
                await send_admin_notification(
                    self.control_bot, self.ADMIN_ID,
                    "⏸️ All forwarding tasks have been paused"
                )
            else:
                await query.answer("❌ Failed to pause tasks", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    async def _resume_all_tasks(self, query: CallbackQuery):
        """Resume all forwarding tasks"""
        try:
            success = await self.db.resume_all_tasks()
            if success:
                await query.edit_message_text(
                    "▶️ **All tasks resumed successfully!**\n\n"
                    "Message forwarding is now active for all tasks.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⏸️ Pause All", callback_data="pause_all"),
                        InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
                    ]])
                )
                await send_admin_notification(
                    self.control_bot, self.ADMIN_ID,
                    "▶️ All forwarding tasks have been resumed"
                )
            else:
                await query.answer("❌ Failed to resume tasks", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    async def _toggle_task(self, query: CallbackQuery, task_id: int):
        """Toggle task status"""
        try:
            tasks = await self.db.get_all_tasks()
            task = next((t for t in tasks if t['id'] == task_id), None)
            
            if not task:
                await query.answer("❌ Task not found", show_alert=True)
                return
            
            new_status = not task['is_active']
            success = await self.db.update_task_status(task_id, new_status)
            
            if success:
                status_text = "activated" if new_status else "deactivated"
                await query.answer(f"✅ Task #{task_id} {status_text}")
                # Refresh the task list
                await self._send_tasks_list_callback(query)
            else:
                await query.answer("❌ Failed to update task", show_alert=True)
                
        except Exception as e:
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    async def _delete_task(self, query: CallbackQuery, task_id: int):
        """Delete a task"""
        try:
            success = await self.db.delete_task(task_id)
            if success:
                await query.answer(f"🗑️ Task #{task_id} deleted")
                # Refresh the task list
                await self._send_tasks_list_callback(query)
                
                await send_admin_notification(
                    self.control_bot, self.ADMIN_ID,
                    f"🗑️ Forwarding task #{task_id} has been deleted"
                )
            else:
                await query.answer("❌ Failed to delete task", show_alert=True)
                
        except Exception as e:
            await query.answer(f"❌ Error: {str(e)}", show_alert=True)
    
    async def _back_to_main(self, query: CallbackQuery):
        """Return to main menu"""
        # Clear user state
        if query.from_user.id in self.user_states:
            del self.user_states[query.from_user.id]
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Task", callback_data="add_task")],
            [InlineKeyboardButton("📋 List Tasks", callback_data="list_tasks")],
            [InlineKeyboardButton("📊 System Status", callback_data="system_status")],
            [InlineKeyboardButton("⏸️ Pause All", callback_data="pause_all"),
             InlineKeyboardButton("▶️ Resume All", callback_data="resume_all")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_main")]
        ])
        
        await query.edit_message_text(
            "🤖 **Telegram Auto-Forwarder Control Panel**\n\n"
            "Select an option below to manage your forwarding tasks:",
            reply_markup=keyboard
        )
        await query.answer()
    
    async def _refresh_main_panel(self, query: CallbackQuery):
        """Refresh main panel"""
        await self._back_to_main(query)
    
    async def _handle_incoming_message(self, message: Message):
        """Handle incoming messages for forwarding"""
        if not self.is_running:
            return
        
        try:
            # Check if message is from a source chat
            tasks = await self.db.get_tasks_by_source(message.chat.id)
            
            for task in tasks:
                if task['is_active']:
                    # Add to queue for processing
                    if self.message_queue.qsize() < 500:
                        await self.message_queue.put({
                            'message': message,
                            'task': task,
                            'timestamp': time.time()
                        })
                        self.stats['queue_size'] = self.message_queue.qsize()
                    else:
                        logger.warning("Message queue full, dropping message")
                        await send_admin_notification(
                            self.control_bot, self.ADMIN_ID,
                            "⚠️ Message queue full! Some messages may be lost."
                        )
        
        except Exception as e:
            logger.error(f"Error handling incoming message: {e}")
            self.stats['errors'] += 1
    
    async def _process_message_queue(self):
        """Process messages from the queue"""
        while self.is_running:
            try:
                # Get message from queue with timeout
                queue_item = await asyncio.wait_for(
                    self.message_queue.get(), timeout=1.0
                )
                
                message = queue_item['message']
                task = queue_item['task']
                
                # Check rate limits
                if not self.rate_limiter.can_send(task['destination_id']):
                    # Put message back in queue and wait
                    await asyncio.sleep(1)
                    await self.message_queue.put(queue_item)
                    continue
                
                # Forward message
                success = await self._forward_message(message, task)
                
                if success:
                    self.stats['messages_forwarded'] += 1
                    self.rate_limiter.record_message(task['destination_id'])
                else:
                    self.stats['errors'] += 1
                
                self.stats['queue_size'] = self.message_queue.qsize()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(1)
    
    @retry_on_failure(max_retries=3, delay=2)
    async def _forward_message(self, message: Message, task: dict) -> bool:
        """Forward a single message"""
        try:
            destination_id = task['destination_id']
            
            # Forward based on message type
            if message.text:
                await self.userbot.send_message(destination_id, message.text)
            elif message.photo:
                await self.userbot.send_photo(
                    destination_id, message.photo.file_id,
                    caption=message.caption or ""
                )
            elif message.video:
                await self.userbot.send_video(
                    destination_id, message.video.file_id,
                    caption=message.caption or ""
                )
            elif message.document:
                await self.userbot.send_document(
                    destination_id, message.document.file_id,
                    caption=message.caption or ""
                )
            elif message.audio:
                await self.userbot.send_audio(
                    destination_id, message.audio.file_id,
                    caption=message.caption or ""
                )
            elif message.voice:
                await self.userbot.send_voice(
                    destination_id, message.voice.file_id,
                    caption=message.caption or ""
                )
            elif message.video_note:
                await self.userbot.send_video_note(
                    destination_id, message.video_note.file_id
                )
            elif message.sticker:
                await self.userbot.send_sticker(
                    destination_id, message.sticker.file_id
                )
            elif message.poll:
                await self.userbot.forward_messages(
                    destination_id, message.chat.id, message.id
                )
            else:
                # Fallback: forward message
                await self.userbot.forward_messages(
                    destination_id, message.chat.id, message.id
                )
            
            return True
            
        except FloodWait as e:
            logger.warning(f"FloodWait: waiting {e.value} seconds")
            self.rate_limiter.set_flood_wait(task['destination_id'], e.value)
            await asyncio.sleep(e.value)
            raise
        except (ChannelPrivate, ChatAdminRequired, UserNotParticipant) as e:
            logger.error(f"Permission error for task {task['id']}: {e}")
            await self.db.update_task_status(task['id'], False)
            await send_admin_notification(
                self.control_bot, self.ADMIN_ID,
                f"❌ Task #{task['id']} disabled due to permission error: {str(e)}"
            )
            return False
        except Exception as e:
            logger.error(f"Forward error: {e}")
            raise
    
    async def _monitor_resources(self):
        """Monitor system resources and take action if needed"""
        while self.is_running:
            try:
                memory_usage = self.resource_monitor.get_memory_usage()
                
                if memory_usage > 450:  # 450MB threshold
                    logger.warning(f"High memory usage: {memory_usage}MB")
                    await send_admin_notification(
                        self.control_bot, self.ADMIN_ID,
                        f"⚠️ High memory usage: {memory_usage}MB. Restarting process..."
                    )
                    # Graceful shutdown and restart
                    await self._graceful_restart()
                
                elif memory_usage > 400:  # 400MB warning
                    logger.warning(f"Memory warning: {memory_usage}MB")
                    # Force garbage collection
                    import gc
                    gc.collect()
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _graceful_restart(self):
        """Gracefully restart the system"""
        try:
            logger.info("Initiating graceful restart...")
            
            # Stop accepting new messages
            self.is_running = False
            
            # Wait for queue to empty (max 30 seconds)
            wait_time = 0
            while self.message_queue.qsize() > 0 and wait_time < 30:
                await asyncio.sleep(1)
                wait_time += 1
            
            # Cancel all worker tasks
            for task in self.worker_tasks:
                if not task.done():
                    task.cancel()
            
            # Close database connections
            await self.db.close()
            
            # Stop clients
            await self.userbot.stop()
            await self.control_bot.stop()
            
            logger.info("Graceful restart completed")
            
            # Exit the process - Render will restart it
            import sys
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Error during graceful restart: {e}")
            import sys
            sys.exit(1)
    
    async def start(self):
        """Start the forwarder system"""
        try:
            logger.info("Starting Telegram Forwarder...")
            
            # Start Flask keep-alive server
            start_keep_alive_thread()
            
            # Initialize database
            await self.db.connect()
            
            # Start clients
            await self.userbot.start()
            await self.control_bot.start()
            
            logger.info("Bots started successfully")
            
            # Start worker tasks
            for i in range(4):  # 4 concurrent workers
                task = asyncio.create_task(self._process_message_queue())
                self.worker_tasks.append(task)
            
            # Start resource monitor
            monitor_task = asyncio.create_task(self._monitor_resources())
            self.worker_tasks.append(monitor_task)
            
            # Send startup notification
            await send_admin_notification(
                self.control_bot, self.ADMIN_ID,
                "✅ Telegram Auto-Forwarder started successfully!\n"
                "Use /start to access the control panel."
            )
            
            logger.info("System started successfully")
            
            # Keep running
            await asyncio.gather(*self.worker_tasks)
            
        except Exception as e:
            logger.error(f"Startup error: {e}")
            await send_admin_notification(
                self.control_bot, self.ADMIN_ID,
                f"❌ Startup failed: {str(e)}"
            )
            raise
    
    async def stop(self):
        """Stop the forwarder system gracefully"""
        try:
            logger.info("Stopping Telegram Forwarder...")
            
            # Stop accepting new messages
            self.is_running = False
            
            # Send shutdown notification
            await send_admin_notification(
                self.control_bot, self.ADMIN_ID,
                "🛑 Telegram Auto-Forwarder is shutting down..."
            )
            
            # Cancel all worker tasks
            for task in self.worker_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
            
            # Close database connections
            await self.db.close()
            
            # Stop clients
            await self.userbot.stop()
            await self.control_bot.stop()
            
            logger.info("Telegram Forwarder stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

if __name__ == "__main__":
    forwarder = TelegramForwarder()
    
    try:
        asyncio.run(forwarder.start())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        asyncio.run(forwarder.stop())
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        asyncio.run(forwarder.stop())
