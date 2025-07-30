import asyncio
import functools
import logging
import os
from datetime import datetime
from pyrogram.errors import FloodWait

def setup_logging():
    """Configure logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )

def log_message(message: str):
    """Log message with timestamp"""
    logging.info(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def with_retry(attempts=3, delay=2):
    """Retry decorator with exponential backoff"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(attempts):
                try:
                    return await func(*args, **kwargs)
                except FloodWait as e:
                    wait_time = e.value + 1
                    log_message(f"FloodWait: {wait_time}s on attempt {attempt + 1}")
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    last_exception = e
                    if attempt < attempts - 1:
                        wait_time = delay * (2 ** attempt)
                        log_message(f"Retry {attempt + 1}/{attempts} after {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        log_message(f"Final attempt failed: {e}")
            
            raise last_exception
        return wrapper
    return decorator

async def notify_admin(client, message: str):
    """Send notification to admin"""
    try:
        admin_id = int(os.environ["ADMIN_ID"])
        await client.send_message(admin_id, f"🤖 **Bot Alert**\n\n{message}")
    except Exception as e:
        log_message(f"Failed to notify admin: {e}")

def validate_chat_id(chat_id_str: str) -> int:
    """Validate and convert chat ID"""
    try:
        chat_id = int(chat_id_str)
        if abs(chat_id) < 1000000000:  # Basic validation
            raise ValueError("Invalid chat ID format")
        return chat_id
    except ValueError:
        raise ValueError("Chat ID must be a valid integer")

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
