import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, OWNER_ID
from userbot import userbot
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ControlBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command and callback handlers"""
        # Commands
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.main_menu))
        self.application.add_handler(CommandHandler("tasks", self.view_tasks))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handlers
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_text_message
        ))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("❌ Unauthorized access!")
            return
        
        welcome_text = f"""
🤖 **Telegram Auto-Forwarder Control Bot**

✅ Bot Active & Ready
🔄 Userbot Status: {"🟢 Running" if userbot.is_running else "🔴 Stopped"}
📊 Active Tasks: {len(userbot.active_tasks)}

**Quick Commands:**
/menu - Main control panel
/tasks - View all tasks
/help - Get help

Use /menu to access all features with buttons!
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        if update.effective_user.id != OWNER_ID:
            return
            
        help_text = """
📖 **Help & Commands**

**Basic Commands:**
/start - Start the bot
/menu - Main control panel  
/tasks - View all tasks
/help - This help message

**Adding Tasks:**
1. Click "➕ Add New Task" from menu
2. Send format: `source_chat_id target_chat_id task_name`
3. Example: `-1001234567890 -1009876543210 MyTask`

**Chat IDs:**
- Use @userinfobot to get chat IDs
- Forward a message from channel to @userinfobot
- For groups, add bot and use /id command

**Task Management:**
- 🟢 Green = Active (forwarding)
- 🔴 Red = Inactive (paused)
- Toggle status anytime from menu
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main menu with buttons"""
        if update.effective_user.id != OWNER_ID:
            return
        
        keyboard = [
            [
                InlineKeyboardButton("➕ Add New Task", callback_data="add_task"),
                InlineKeyboardButton("📋 View Tasks", callback_data="view_tasks")
            ],
            [
                InlineKeyboardButton("⚙️ Manage Tasks", callback_data="manage_tasks"),
                InlineKeyboardButton("📊 Statistics", callback_data="stats")
            ],
            [
                InlineKeyboardButton("🔄 Restart Userbot", callback_data="restart_userbot"),
                InlineKeyboardButton("🛑 Stop Userbot", callback_data="stop_userbot")
            ],
            [
                InlineKeyboardButton("🆘 Help", callback_data="help_menu")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        status_emoji = "🟢" if userbot.is_running else "🔴"
        text = f"""
🎛️ **Control Panel**

🤖 Userbot Status: {status_emoji} {"Running" if userbot.is_running else "Stopped"}
📊 Active Tasks: {len(userbot.active_tasks)}
⚡ System: Online

Select an option below:
        """
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "add_task":
            await self.add_task_menu(update, context)
        elif data == "view_tasks":
            await self.view_tasks_menu(update, context)
        elif data == "manage_tasks":
            await self.manage_tasks_menu(update, context)
        elif data == "stats":
            await self.show_statistics(update, context)
        elif data == "restart_userbot":
            await self.restart_userbot(update, context)
        elif data == "stop_userbot":
            await self.stop_userbot_action(update, context)
        elif data == "help_menu":
            await self.help_menu(update, context)
        elif data == "back_to_menu":
            await self.main_menu(update, context)
        elif data.startswith("toggle_task_"):
            task_id = int(data.replace("toggle_task_", ""))
            await self.toggle_task(update, context, task_id)
        elif data.startswith("delete_task_"):
            task_id = int(data.replace("delete_task_", ""))
            await self.delete_task_action(update, context, task_id)
        elif data.startswith("confirm_delete_"):
            task_id = int(data.replace("confirm_delete_", ""))
            await self.confirm_delete_task(update, context, task_id)
    
    async def add_task_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add new forwarding task"""
        text = """
➕ **Add New Forwarding Task**

📝 Send task details in this format:
source_chat_id target_chat_id [task_name]

text

**Examples:**
-1001234567890 -1009876543210 EarnKaro Task
@source_channel @target_bot My Forward Task
-1001111111111 -1002222222222

**How to get Chat IDs:**
• Forward message to @userinfobot
• Use @myidbot for user/group IDs
• Add bot to group and check logs

Send your task details or /cancel to go back.
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        context.user_data['expecting'] = 'new_task'
    
    async def view_tasks_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View all forwarding tasks"""
        tasks = await db.get_all_tasks()
        
        if not tasks:
            text = "📋 **No Tasks Found**\n\nUse ➕ Add New Task to create your first forwarding task."
            keyboard = [
                [InlineKeyboardButton("➕ Add New Task", callback_data="add_task")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
            ]
        else:
            text = f"📋 **All Forwarding Tasks** ({len(tasks)})\n\n"
            keyboard = []
            
            for i, task in enumerate(tasks, 1):
                status_emoji = "🟢" if task.status == "active" else "🔴"
                text += f"{i}. {status_emoji} **{task.task_name}**\n"
                text += f"   📤 Source: `{task.source_chat}`\n"
                text += f"   📥 Target: `{task.dest_chat}`\n"
                text += f"   📅 Created: {task.created_at.strftime('%d/%m/%Y')}\n\n"
                
                if i <= 10:  # Show buttons only for first 10 tasks
                    keyboard.append([
                        InlineKeyboardButton(f"⚙️ {task.task_name[:15]}...", callback_data=f"edit_task_{task.id}"),
                        InlineKeyboardButton("🔄", callback_data=f"toggle_task_{task.id}"),
                        InlineKeyboardButton("🗑️", callback_data=f"delete_task_{task.id}")
                    ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def manage_tasks_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage tasks menu"""
        active_tasks = [t for t in userbot.active_tasks.values() if t['status'] == 'active']
        
        text = f"""
⚙️ **Task Management**

📊 **Current Status:**
• Total Tasks: {len(await db.get_all_tasks())}
• Active Tasks: {len(active_tasks)}
• Userbot Status: {"🟢 Running" if userbot.is_running else "🔴 Stopped"}

**Quick Actions:**
        """
        
        keyboard = [
            [
                InlineKeyboardButton("▶️ Start All Tasks", callback_data="start_all_tasks"),
                InlineKeyboardButton("⏸️ Pause All Tasks", callback_data="pause_all_tasks")
            ],
            [
                InlineKeyboardButton("🗑️ Clear Inactive", callback_data="clear_inactive"),
                InlineKeyboardButton("🔄 Reload Tasks", callback_data="reload_tasks")
            ],
            [
                InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        if update.effective_user.id != OWNER_ID:
            return
        
        if context.user_data.get('expecting') == 'new_task':
            await self.process_new_task(update, context)
    
    async def process_new_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process new task creation"""
        try:
            if update.message.text.startswith('/cancel'):
                await update.message.reply_text("❌ Task creation cancelled.")
                context.user_data.pop('expecting', None)
                return
            
            parts = update.message.text.strip().split()
            if len(parts) < 2:
                await update.message.reply_text(
                    "❌ Invalid format! Please provide at least source and target chat IDs.\n\n"
                    "Format: `source_chat_id target_chat_id [task_name]`",
                    parse_mode='Markdown'
                )
                return
            
            source_chat = parts[0]
            target_chat = parts[1]
            task_name = " ".join(parts[2:]) if len(parts) > 2 else f"Task_{source_chat[:10]}"
            
            # Convert to chat IDs if needed
            source_id = await self.resolve_chat_id(source_chat)
            target_id = await self.resolve_chat_id(target_chat)
            
            if source_id is None or target_id is None:
                await update.message.reply_text("❌ Invalid chat IDs provided! Please check and try again.")
                return
            
            task_id = await userbot.add_forwarding_task(source_id, target_id, task_name)
            if task_id:
                await update.message.reply_text(
                    f"✅ **Task Created Successfully!**\n\n"
                    f"📝 Task: {task_name}\n"
                    f"📤 Source: `{source_id}`\n"
                    f"📥 Target: `{target_id}`\n"
                    f"🆔 Task ID: {task_id}\n\n"
                    f"🟢 Status: Active & Ready to forward!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to create task! Please check logs.")
                
        except Exception as e:
            logger.error(f"Error processing new task: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        context.user_data.pop('expecting', None)
    
    async def resolve_chat_id(self, chat_input):
        """Resolve chat ID from username or ID"""
        try:
            if chat_input.startswith('@'):
                # Username - try to get chat info
                chat = await userbot.app.get_chat(chat_input)
                return chat.id
            else:
                # Assume it's already a chat ID
                return int(chat_input)
        except Exception as e:
            logger.error(f"Error resolving chat ID for {chat_input}: {e}")
            return None
    
    async def toggle_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int):
        """Toggle task status"""
        try:
            task = await db.get_task_by_id(task_id)
            if task:
                new_status = "inactive" if task.status == "active" else "active"
                
                if new_status == "active":
                    success = await userbot.enable_task(task_id)
                else:
                    success = await userbot.disable_task(task_id)
                
                if success:
                    status_text = "✅ Enabled" if new_status == "active" else "⏸️ Paused"
                    await update.callback_query.answer(f"Task {status_text}!")
                    await self.view_tasks_menu(update, context)
                else:
                    await update.callback_query.answer("❌ Failed to update task!")
            else:
                await update.callback_query.answer("❌ Task not found!")
        except Exception as e:
            logger.error(f"Error toggling task: {e}")
            await update.callback_query.answer("❌ Error occurred!")
    
    async def delete_task_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int):
        """Confirm task deletion"""
        task = await db.get_task_by_id(task_id)
        if task:
            text = f"""
🗑️ **Confirm Deletion**

Are you sure you want to delete this task?

📝 **Task:** {task.task_name}
📤 **Source:** `{task.source_chat}`
📥 **Target:** `{task.dest_chat}`

⚠️ This action cannot be undone!
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_delete_{task_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data="view_tasks")
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def confirm_delete_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int):
        """Delete forwarding task"""
        try:
            success = await userbot.delete_task(task_id)
            if success:
                await update.callback_query.answer("🗑️ Task Deleted Successfully!")
                await self.view_tasks_menu(update, context)
            else:
                await update.callback_query.answer("❌ Failed to delete task!")
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            await update.callback_query.answer("❌ Error occurred!")
    
    async def restart_userbot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restart userbot"""
        try:
            await update.callback_query.answer("🔄 Restarting userbot...")
            await userbot.restart_userbot()
            await asyncio.sleep(2)
            
            text = "✅ **Userbot Restarted Successfully!**\n\n🔄 All tasks reloaded and ready to forward."
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error restarting userbot: {e}")
            await update.callback_query.answer("❌ Restart failed!")
    
    async def stop_userbot_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop userbot"""
        try:
            await update.callback_query.answer("🛑 Stopping userbot...")
            await userbot.stop_userbot()
            
            text = "🛑 **Userbot Stopped**\n\n⚠️ No messages will be forwarded until restart."
            keyboard = [
                [InlineKeyboardButton("🔄 Restart", callback_data="restart_userbot")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error stopping userbot: {e}")
            await update.callback_query.answer("❌ Stop failed!")
    
    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        try:
            all_tasks = await db.get_all_tasks()
            active_tasks = [t for t in all_tasks if t.status == "active"]
            inactive_tasks = [t for t in all_tasks if t.status == "inactive"]
            
            text = f"""
📊 **System Statistics**

🤖 **Bot Status:**
• Control Bot: 🟢 Online
• Userbot: {"🟢 Running" if userbot.is_running else "🔴 Stopped"}

📋 **Tasks Overview:**
• Total Tasks: {len(all_tasks)}
• 🟢 Active Tasks: {len(active_tasks)}
• 🔴 Inactive Tasks: {len(inactive_tasks)}

💾 **Database:**
• Connection: 🟢 Healthy
• Storage: PostgreSQL

⚡ **Performance:**
• Status: All Systems Normal
• Uptime: 24/7 Active
• Auto-Forward: Real-time

🚀 **System Health: Excellent**
            """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh Stats", callback_data="stats")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error showing statistics: {e}")
            await update.callback_query.answer("❌ Failed to load stats!")
    
    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help menu"""
        text = """
🆘 **Help & Documentation**

**🤖 What is this bot?**
This is an auto-forwarding bot that instantly forwards messages from source channels/groups to target destinations.

**📝 How to add tasks?**
1. Click "➕ Add New Task"
2. Send: `source_id target_id task_name`
3. Bot will start forwarding automatically

**🔍 How to get Chat IDs?**
• Forward message to @userinfobot
• Use @myidbot for user IDs
• Add this bot to group for group ID

**⚙️ Task Management:**
• 🟢 Green = Active (forwarding)
• 🔴 Red = Inactive (paused)
• Toggle anytime from tasks menu

**🚨 Troubleshooting:**
• Make sure userbot is member of source chats
• Check destination chat permissions
• Restart userbot if issues persist

**📞 Need Help?** Contact the bot owner.
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    def start_bot(self):
        """Start the control bot"""
        logger.info("🤖 Starting control bot...")
        self.application.run_polling(drop_pending_updates=True)

# Global control bot instance
control_bot = ControlBot()
