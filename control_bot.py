import asyncio
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
from utils import with_retry, notify_admin

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Client(
    "control_bot",
    api_id=int(os.environ["API_ID"]),
    api_hash=os.environ["API_HASH"],
    bot_token=os.environ["BOT_TOKEN"]
)

admin_id = int(os.environ["ADMIN_ID"])

async def validate_chat(client, chat_id):
    try:
        chat = await with_retry(client.get_chat)(chat_id)
        return True
    except Exception as e:
        logger.error(f"Chat validation error for {chat_id}: {e}")
        return False

@app.on_message(filters.command("start") & filters.user(admin_id))
async def start(client, message):
    buttons = [
        [InlineKeyboardButton("Add Task", callback_data="add_task")],
        [InlineKeyboardButton("List Tasks", callback_data="list_tasks")],
        [InlineKeyboardButton("Pause All", callback_data="pause_all")],
        [InlineKeyboardButton("Resume All", callback_data="resume_all")]
    ]
    await message.reply("Welcome to Control Bot!", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_message(filters.command("add") & filters.user(admin_id))
async def add_task(client, message):
    await message.reply("Enter source chat ID:")
    client.storage.set_state(message.from_user.id, "awaiting_source")

@app.on_message(filters.text & filters.user(admin_id))
async def handle_input(client, message):
    state = client.storage.get_state(message.from_user.id)
    if state == "awaiting_source":
        try:
            source_id = int(message.text)
            if await validate_chat(client, source_id):
                client.storage.set_state(message.from_user.id, "awaiting_destination")
                client.storage.set_source_id(message.from_user.id, source_id)
                await message.reply("Enter destination chat ID:")
            else:
                await message.reply("Invalid source chat ID.")
        except ValueError:
            await message.reply("Please enter a valid numeric chat ID.")
    elif state == "awaiting_destination":
        try:
            destination_id = int(message.text)
            if await validate_chat(client, destination_id):
                async with Database() as db:
                    await db.add_task(client.storage.get_source_id(message.from_user.id), destination_id)
                await message.reply("Task added successfully!")
                client.storage.set_state(message.from_user.id, None)
            else:
                await message.reply("Invalid destination chat ID.")
        except ValueError:
            await message.reply("Please enter a valid numeric chat ID.")

@app.on_callback_query(filters.user(admin_id))
async def handle_callback(client, callback_query):
    data = callback_query.data
    if data == "add_task":
        await callback_query.message.reply("Enter source chat ID:")
        client.storage.set_state(callback_query.from_user.id, "awaiting_source")
    elif data == "list_tasks":
        async with Database() as db:
            tasks = await db.get_tasks()
        if not tasks:
            await callback_query.message.reply("No tasks found.")
            return
        buttons = []
        for task in tasks:
            status = "✅" if task["is_active"] else "❌"
            buttons.append([
                InlineKeyboardButton(f"Task {task['id']} ({status})", callback_data=f"task_{task['id']}"),
                InlineKeyboardButton("Toggle", callback_data=f"toggle_{task['id']}"),
                InlineKeyboardButton("Delete", callback_data=f"delete_{task['id']}")
            ])
        await callback_query.message.reply("Tasks:", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("toggle_"):
        task_id = int(data.split("_")[1])
        async with Database() as db:
            task = await db.get_task(task_id)
            await db.update_task_status(task_id, not task["is_active"])
        await callback_query.message.reply(f"Task {task_id} toggled.")
    elif data.startswith("delete_"):
        task_id = int(data.split("_")[1])
        async with Database() as db:
            await db.delete_task(task_id)
        await callback_query.message.reply(f"Task {task_id} deleted.")
    elif data == "pause_all":
        async with Database() as db:
            await db.update_all_tasks_status(False)
        await callback_query.message.reply("All tasks paused.")
    elif data == "resume_all":
        async with Database() as db:
            await db.update_all_tasks_status(True)
        await callback_query.message.reply("All tasks resumed.")

async def main():
    try:
        for var in ["API_ID", "API_HASH", "BOT_TOKEN", "DB_URL", "ADMIN_ID"]:
            if not os.environ.get(var):
                logger.error(f"Missing environment variable: {var}")
                exit(1)
        async with Database() as db:
            await db.initialize()
        await app.start()
        logger.info("Control Bot started")
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Control Bot fatal error: {e}")
        await notify_admin(app, f"Control Bot fatal error: {e}")
        os.execl(sys.executable, sys.executable, *sys.argv)

if __name__ == "__main__":
    asyncio.run(main())