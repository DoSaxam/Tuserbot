# control_bot.py
import telegram
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN
from database import add_task, get_tasks, toggle_task, delete_task

updater = Updater(BOT_TOKEN, use_context=True)
dp = updater.dispatcher

def start(update, context):
    keyboard = [
        [InlineKeyboardButton("Add Task", callback_data='add')],
        [InlineKeyboardButton("List Tasks", callback_data='list')],
        [InlineKeyboardButton("Toggle Task", callback_data='toggle')],
        [InlineKeyboardButton("Delete Task", callback_data='delete')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Manage tasks:', reply_markup=reply_markup)

def button(update, context):
    query = update.callback_query
    data = query.data
    if data == 'add':
        query.message.reply_text("Send /add <source_id> <target_id>")
    elif data == 'list':
        tasks = get_tasks()
        text = "Tasks:\n" + "\n".join([f"ID: {t[0]} | Source: {t[1]} | Target: {t[2]} | Active: {t[3]}" for t in tasks])
        query.message.reply_text(text or "No tasks")
    elif data == 'toggle':
        query.message.reply_text("Send /toggle <task_id>")
    elif data == 'delete':
        query.message.reply_text("Send /delete <task_id>")

def add_command(update, context):
    try:
        source, target = context.args
        add_task(source, target)
        update.message.reply_text("Task added!")
    except:
        update.message.reply_text("Usage: /add <source> <target>")

# Similar for toggle and delete
def toggle_command(update, context):
    try:
        task_id = context.args[0]
        toggle_task(task_id)
        update.message.reply_text("Task toggled!")
    except:
        update.message.reply_text("Usage: /toggle <id>")

def delete_command(update, context):
    try:
        task_id = context.args[0]
        delete_task(task_id)
        update.message.reply_text("Task deleted!")
    except:
        update.message.reply_text("Usage: /delete <id>")

dp.add_handler(CommandHandler('start', start))
dp.add_handler(CallbackQueryHandler(button))
dp.add_handler(CommandHandler('add', add_command))
dp.add_handler(CommandHandler('toggle', toggle_command))
dp.add_handler(CommandHandler('delete', delete_command))

updater.start_polling()
updater.idle()
