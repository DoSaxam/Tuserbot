# userbot.py
from pyrogram import Client, filters, errors
import asyncio
from config import API_ID, API_HASH
from database import init_db, get_tasks

init_db()  # Initialize DB
app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.chat(lambda _, __, msg: True))  # Listen to all
async def forward_message(client, message):
    try:
        tasks = get_tasks()  # Load from DB
        for task in tasks:
            task_id, source, target, active = task
            if active and message.chat.id == int(source):
                await message.forward(int(target))
    except errors.FloodWait as e:
        await asyncio.sleep(e.x)  # Handle rate limits
    except Exception as e:
        print(f"Error: {e}")  # Log and continue

async def main():
    while True:  # Auto-reconnect loop
        try:
            await app.start()
            print("Userbot running...")
            await asyncio.Future()  # Run forever
        except Exception as e:
            print(f"Reconnecting: {e}")
            await asyncio.sleep(5)  # Wait and retry

if __name__ == '__main__':
    asyncio.run(main())
