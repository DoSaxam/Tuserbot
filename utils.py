import asyncio
import logging
import os
import time
import psutil
import functools
from typing import Dict, Optional, Any
from collections import defaultdict, deque
from datetime import datetime, timedelta
import json

def setup_logging():
    """Setup comprehensive logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce pyrogram logging noise
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=1, exponential_backoff=True):
    """Decorator for retrying failed operations"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logging.error(f"Function {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    wait_time = delay * (2 ** attempt) if exponential_backoff else delay
                    logging.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            raise last_exception
        
        return wrapper
    return decorator

async def send_admin_notification(bot_client, admin_id: int, message: str, parse_mode: str = None):
    """Send notification to admin with error handling"""
    try:
        # Truncate message if too long
        if len(message) > 4000:
            message = message[:3900] + "\n\n... (message truncated)"
        
        await bot_client.send_message(
            admin_id, 
            message,
            parse_mode=parse_mode
        )
        
    except Exception as e:
        logging.error(f"Failed to send admin notification: {e}")

class ResourceMonitor:
    """Enhanced system resource monitoring"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.cpu_history = deque(maxlen=30)  # Store last 30 readings
        self.memory_history = deque(maxlen=30)
        
        # Baseline measurements
        self.start_time = time.time()
        self.initial_memory = self.get_memory_usage()
        
        # Warning thresholds
        self.memory_warning_threshold = 350.0  # MB
        self.memory_critical_threshold = 450.0  # MB
        self.cpu_warning_threshold = 70.0      # %
        self.cpu_critical_threshold = 90.0     # %
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            self.memory_history.append({
                'value': memory_mb,
                'timestamp': time.time()
            })
            return memory_mb
        except Exception as e:
            logging.error(f"Error getting memory usage: {e}")
            return 0.0
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
            self.cpu_history.append({
                'value': cpu_percent,
                'timestamp': time.time()
            })
            return cpu_percent
        except Exception as e:
            logging.error(f"Error getting CPU usage: {e}")
            return 0.0
    
    def get_average_memory(self, minutes: int = 5) -> float:
        """Get average memory usage over specified minutes"""
        if not self.memory_history:
            return 0.0
        
        cutoff_time = time.time() - (minutes * 60)
        recent_values = [
            entry['value'] for entry in self.memory_history 
            if entry['timestamp'] >= cutoff_time
        ]
        
        return sum(recent_values) / len(recent_values) if recent_values else 0.0
    
    def get_average_cpu(self, minutes: int = 5) -> float:
        """Get average CPU usage over specified minutes"""
        if not self.cpu_history:
            return 0.0
        
        cutoff_time = time.time() - (minutes * 60)
        recent_values = [
            entry['value'] for entry in self.cpu_history 
            if entry['timestamp'] >= cutoff_time
        ]
        
        return sum(recent_values) / len(recent_values) if recent_values else 0.0
    
    def is_memory_critical(self) -> bool:
        """Check if memory usage is at critical level"""
        current_memory = self.get_memory_usage()
        return current_memory > self.memory_critical_threshold
    
    def is_memory_warning(self) -> bool:
        """Check if memory usage is at warning level"""
        current_memory = self.get_memory_usage()
        return current_memory > self.memory_warning_threshold
    
    def is_cpu_critical(self) -> bool:
        """Check if CPU usage is at critical level"""
        avg_cpu = self.get_average_cpu(minutes=2)
        return avg_cpu > self.cpu_critical_threshold
    
    def is_cpu_warning(self) -> bool:
        """Check if CPU usage is at warning level"""
        avg_cpu = self.get_average_cpu(minutes=2)
        return avg_cpu > self.cpu_warning_threshold
    
    def get_uptime(self) -> str:
        """Get system uptime in human readable format"""
        uptime_seconds = time.time() - self.start_time
        return format_duration(uptime_seconds)

class RateLimiter:
    """Enhanced rate limiting for message forwarding"""
    
    def __init__(self):
        self.global_limit = 100  # messages per minute globally
        self.chat_limit = 30     # messages per minute per chat
        self.window_size = 60    # 1 minute window
        
        self.global_counter = deque()
        self.chat_counters = defaultdict(lambda: deque())
        
        self.flood_wait_until = {}  # Track flood wait times
        
        # Statistics
        self.total_messages_sent = 0
        self.total_messages_blocked = 0
        self.total_flood_waits = 0
    
    def can_send(self, chat_id: int) -> bool:
        """Check if we can send a message to this chat"""
        current_time = time.time()
        
        # Check flood wait
        if chat_id in self.flood_wait_until:
            if current_time < self.flood_wait_until[chat_id]:
                return False
            else:
                del self.flood_wait_until[chat_id]
        
        # Clean old entries
        self._clean_old_entries(current_time)
        
        # Check global limit
        if len(self.global_counter) >= self.global_limit:
            self.total_messages_blocked += 1
            return False
        
        # Check per-chat limit
        if len(self.chat_counters[chat_id]) >= self.chat_limit:
            self.total_messages_blocked += 1
            return False
        
        return True
    
    def record_message(self, chat_id: int, success: bool = True):
        """Record a sent message"""
        current_time = time.time()
        self.global_counter.append(current_time)
        self.chat_counters[chat_id].append(current_time)
        self.total_messages_sent += 1
    
    def set_flood_wait(self, chat_id: int, wait_time: int):
        """Set flood wait for a specific chat"""
        self.flood_wait_until[chat_id] = time.time() + wait_time
        self.total_flood_waits += 1
        logging.warning(f"Flood wait set for chat {chat_id}: {wait_time} seconds")
    
    def _clean_old_entries(self, current_time: float):
        """Remove entries older than the window"""
        cutoff_time = current_time - self.window_size
        
        # Clean global counter
        while self.global_counter and self.global_counter[0] < cutoff_time:
            self.global_counter.popleft()
        
        # Clean chat counters
        for chat_id in list(self.chat_counters.keys()):
            counter = self.chat_counters[chat_id]
            while counter and counter[0] < cutoff_time:
                counter.popleft()
            
            # Remove empty counters
            if not counter:
                del self.chat_counters[chat_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics"""
        current_time = time.time()
        self._clean_old_entries(current_time)
        
        return {
            'global_count': len(self.global_counter),
            'global_limit': self.global_limit,
            'active_chats': len(self.chat_counters),
            'flood_waits_active': len(self.flood_wait_until),
            'total_messages_sent': self.total_messages_sent,
            'total_messages_blocked': self.total_messages_blocked,
            'total_flood_waits': self.total_flood_waits,
            'success_rate_overall': (
                (self.total_messages_sent - self.total_messages_blocked) / 
                max(1, self.total_messages_sent)
            ) * 100
        }

class MessageValidator:
    """Enhanced input validation and sanitization"""
    
    @staticmethod
    def validate_chat_id(chat_id_str: str) -> Optional[Any]:
        """Validate and convert chat ID or username"""
        try:
            # Remove whitespace and common prefixes
            chat_id_str = chat_id_str.strip()
            
            if not chat_id_str:
                return None
            
            # Handle username format
            if chat_id_str.startswith('@'):
                username = chat_id_str[1:].strip()
                if MessageValidator._is_valid_username(username):
                    return chat_id_str  # Return username as string
                return None
            
            # Handle numeric ID
            try:
                chat_id = int(chat_id_str)
                
                # Basic validation for chat ID ranges
                if abs(chat_id) < 1000:  # Too small to be a valid chat ID
                    return None
                
                # Check for common invalid patterns
                if chat_id == 0 or str(chat_id) in ['123456789', '987654321']:
                    return None
                
                return chat_id
                
            except ValueError:
                return None
                
        except (ValueError, TypeError, AttributeError):
            return None
    
    @staticmethod
    def _is_valid_username(username: str) -> bool:
        """Validate Telegram username format"""
        if len(username) < 5 or len(username) > 32:
            return False
        
        # Username should start with a letter
        if not username[0].isalpha():
            return False
        
        # Username should only contain letters, numbers, and underscores
        if not all(c.isalnum() or c == '_' for c in username):
            return False
        
        # Username shouldn't end with underscore
        if username.endswith('_'):
            return False
        
        # Username shouldn't have consecutive underscores
        if '__' in username:
            return False
        
        return True
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 4000) -> str:
        """Enhanced text sanitization"""
        if not text:
            return ""
        
        # Remove null bytes and dangerous control characters
        text = ''.join(
            char for char in text 
            if ord(char) >= 32 or char in '\n\r\t'
        )
        
        # Remove excessive whitespace
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Remove excessive spaces
            cleaned_line = ' '.join(line.split())
            if cleaned_line or len(cleaned_lines) == 0:  # Keep first empty line
                cleaned_lines.append(cleaned_line)
        
        text = '\n'.join(cleaned_lines)
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length-3] + "..."
        
        return text.strip()
    
    @staticmethod
    def validate_environment_variable(var_name: str, var_value: str) -> bool:
        """Validate specific environment variables"""
        if not var_value:
            return False
        
        validations = {
            'API_ID': lambda x: x.isdigit() and len(x) >= 6,
            'API_HASH': lambda x: len(x) == 32 and all(c.isalnum() for c in x),
            'BOT_TOKEN': lambda x: ':' in x and len(x.split(':')[0]) >= 8,
            'SESSION_STRING': lambda x: len(x) > 300,
            'ADMIN_ID': lambda x: x.isdigit() and len(x) >= 8,
            'DB_URL': lambda x: x.startswith(('postgresql://', 'postgres://'))
        }
        
        validator = validations.get(var_name)
        if validator:
            return validator(var_value)
        
        return len(var_value) > 0

class ConfigValidator:
    """Enhanced configuration validation"""
    
    @staticmethod
    def validate_env_vars() -> Dict[str, bool]:
        """Validate all required environment variables"""
        required_vars = {
            'API_ID': os.environ.get('API_ID'),
            'API_HASH': os.environ.get('API_HASH'),
            'BOT_TOKEN': os.environ.get('BOT_TOKEN'),
            'SESSION_STRING': os.environ.get('SESSION_STRING'),
            'ADMIN_ID': os.environ.get('ADMIN_ID'),
            'DB_URL': os.environ.get('DB_URL')
        }
        
        validation_results = {}
        
        for var_name, var_value in required_vars.items():
            validation_results[var_name] = MessageValidator.validate_environment_variable(
                var_name, var_value or ""
            )
        
        return validation_results
    
    @staticmethod
    def get_missing_vars(validation_results: Dict[str, bool]) -> list:
        """Get list of missing or invalid environment variables"""
        return [var for var, valid in validation_results.items() if not valid]
    
    @staticmethod
    def get_config_summary() -> Dict[str, Any]:
        """Get configuration summary for debugging"""
        env_vars = {
            'API_ID': bool(os.environ.get('API_ID')),
            'API_HASH': bool(os.environ.get('API_HASH')),
            'BOT_TOKEN': bool(os.environ.get('BOT_TOKEN')),
            'SESSION_STRING': bool(os.environ.get('SESSION_STRING')),
            'ADMIN_ID': bool(os.environ.get('ADMIN_ID')),
            'DB_URL': bool(os.environ.get('DB_URL')),
            'PORT': os.environ.get('PORT', '8080')
        }
        
        return {
            'environment_variables': env_vars,
            'python_version': os.sys.version,
            'working_directory': os.getcwd(),
            'timestamp': datetime.now().isoformat()
        }

def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f}{unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f}TB"

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"

def get_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.now().isoformat()
