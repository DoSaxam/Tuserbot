import asyncio
import asyncpg
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)

def retry_on_failure(max_retries=3, delay=2):
    """Simple retry decorator for database operations"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Database operation {func.__name__} failed after {max_retries} retries: {e}")
                        raise e
                    
                    wait_time = delay * (2 ** attempt)
                    logger.warning(f"Database attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
            
            raise last_exception
        return wrapper
    return decorator

class Database:
    def __init__(self):
        self.db_url = os.environ.get('DB_URL')
        if not self.db_url:
            raise ValueError("DB_URL environment variable not set")
        
        self.pool = None
        self._connection_retries = 0
        self.max_retries = 5
    
    @retry_on_failure(max_retries=5, delay=5)
    async def connect(self):
        """Initialize database connection pool"""
        try:
            # Parse SSL requirements for PostgreSQL
            ssl_require = 'require' if 'sslmode=require' in self.db_url else None
            
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=3,
                max_size=5,
                command_timeout=60,
                server_settings={
                    'application_name': 'telegram_forwarder',
                },
                ssl=ssl_require
            )
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute('SELECT 1')
            
            # Initialize tables
            await self._init_tables()
            logger.info("Database connected successfully")
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    async def _init_tables(self):
        """Initialize database tables"""
        async with self.pool.acquire() as conn:
            try:
                # Tasks table with better structure
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        source_id BIGINT NOT NULL,
                        destination_id BIGINT NOT NULL,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        messages_forwarded INTEGER DEFAULT 0,
                        last_message_at TIMESTAMP,
                        error_count INTEGER DEFAULT 0,
                        last_error TEXT,
                        UNIQUE(source_id, destination_id)
                    )
                ''')
                
                # User states table for control bot
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id BIGINT PRIMARY KEY,
                        state_data JSONB DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # System stats table for monitoring
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS system_stats (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        messages_forwarded INTEGER DEFAULT 0,
                        errors INTEGER DEFAULT 0,
                        memory_usage FLOAT DEFAULT 0.0,
                        cpu_usage FLOAT DEFAULT 0.0,
                        queue_size INTEGER DEFAULT 0,
                        active_tasks INTEGER DEFAULT 0
                    )
                ''')
                
                # Create indexes for better performance
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_tasks_source_id ON tasks(source_id);
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_tasks_destination_id ON tasks(destination_id);
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_tasks_is_active ON tasks(is_active);
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_system_stats_timestamp ON system_stats(timestamp);
                ''')
                
                # Create trigger to update updated_at automatically
                await conn.execute('''
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql';
                ''')
                
                await conn.execute('''
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_tasks_updated_at') THEN
                            CREATE TRIGGER update_tasks_updated_at 
                            BEFORE UPDATE ON tasks 
                            FOR EACH ROW 
                            EXECUTE FUNCTION update_updated_at_column();
                        END IF;
                    END $$;
                ''')
                
                logger.info("Database tables initialized successfully")
                
            except Exception as e:
                logger.error(f"Error initializing database tables: {e}")
                raise
    
    @retry_on_failure(max_retries=3, delay=2)
    async def add_task(self, source_id: int, destination_id: int) -> bool:
        """Add a new forwarding task"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    '''INSERT INTO tasks (source_id, destination_id, is_active) 
                       VALUES ($1, $2, TRUE) 
                       ON CONFLICT (source_id, destination_id) 
                       DO UPDATE SET 
                           is_active = TRUE, 
                           updated_at = CURRENT_TIMESTAMP,
                           error_count = 0,
                           last_error = NULL
                       RETURNING id''',
                    source_id, destination_id
                )
                
                logger.info(f"Added/Updated task: {source_id} -> {destination_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=2)
    async def get_all_tasks(self) -> List[Dict]:
        """Get all forwarding tasks"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    '''SELECT id, source_id, destination_id, is_active, created_at, 
                              updated_at, messages_forwarded, last_message_at, 
                              error_count, last_error
                       FROM tasks ORDER BY id DESC'''
                )
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching tasks: {e}")
            return []
    
    @retry_on_failure(max_retries=3, delay=2)
    async def get_tasks_by_source(self, source_id: int) -> List[Dict]:
        """Get active tasks by source ID"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    '''SELECT id, source_id, destination_id, is_active, created_at,
                              messages_forwarded, last_message_at, error_count
                       FROM tasks 
                       WHERE source_id = $1 AND is_active = TRUE''',
                    source_id
                )
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching tasks by source: {e}")
            return []
    
    @retry_on_failure(max_retries=3, delay=2)
    async def update_task_status(self, task_id: int, is_active: bool) -> bool:
        """Update task status"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    '''UPDATE tasks 
                       SET is_active = $1, updated_at = CURRENT_TIMESTAMP 
                       WHERE id = $2''',
                    is_active, task_id
                )
                
                # Check if any row was updated
                rows_affected = result.split()[-1] if isinstance(result, str) else 0
                success = str(rows_affected) == "1"
                
                if success:
                    logger.info(f"Updated task {task_id} status to {is_active}")
                
                return success
                
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=2)
    async def delete_task(self, task_id: int) -> bool:
        """Delete a task"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    'DELETE FROM tasks WHERE id = $1', task_id
                )
                
                rows_affected = result.split()[-1] if isinstance(result, str) else 0
                success = str(rows_affected) == "1"
                
                if success:
                    logger.info(f"Deleted task {task_id}")
                
                return success
                
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=2)
    async def pause_all_tasks(self) -> bool:
        """Pause all tasks"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    '''UPDATE tasks 
                       SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP 
                       WHERE is_active = TRUE'''
                )
                
                rows_affected = result.split()[-1] if isinstance(result, str) else 0
                logger.info(f"Paused {rows_affected} tasks")
                return True
                
        except Exception as e:
            logger.error(f"Error pausing all tasks: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=2)
    async def resume_all_tasks(self) -> bool:
        """Resume all tasks"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    '''UPDATE tasks 
                       SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP,
                           error_count = 0, last_error = NULL
                       WHERE is_active = FALSE'''
                )
                
                rows_affected = result.split()[-1] if isinstance(result, str) else 0
                logger.info(f"Resumed {rows_affected} tasks")
                return True
                
        except Exception as e:
            logger.error(f"Error resuming all tasks: {e}")
            return False
    
    @retry_on_failure(max_retries=3, delay=2)
    async def update_task_stats(self, task_id: int, success: bool = True, error_msg: str = None):
        """Update task statistics after message forwarding"""
        try:
            async with self.pool.acquire() as conn:
                if success:
                    await conn.execute(
                        '''UPDATE tasks 
                           SET messages_forwarded = messages_forwarded + 1,
                               last_message_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = $1''',
                        task_id
                    )
                else:
                    await conn.execute(
                        '''UPDATE tasks 
                           SET error_count = error_count + 1,
                               last_error = $2,
                               updated_at = CURRENT_TIMESTAMP
                           WHERE id = $1''',
                        task_id, error_msg
                    )
                    
        except Exception as e:
            logger.error(f"Error updating task stats: {e}")
    
    @retry_on_failure(max_retries=3, delay=2)
    async def save_user_state(self, user_id: int, state_data: dict):
        """Save user state for control bot"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''INSERT INTO user_states (user_id, state_data, updated_at) 
                       VALUES ($1, $2, CURRENT_TIMESTAMP) 
                       ON CONFLICT (user_id) 
                       DO UPDATE SET 
                           state_data = $2, 
                           updated_at = CURRENT_TIMESTAMP''',
                    user_id, json.dumps(state_data)
                )
                
        except Exception as e:
            logger.error(f"Error saving user state: {e}")
    
    @retry_on_failure(max_retries=3, delay=2)
    async def get_user_state(self, user_id: int) -> dict:
        """Get user state for control bot"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT state_data FROM user_states WHERE user_id = $1',
                    user_id
                )
                
                if row and row['state_data']:
                    return json.loads(row['state_data']) if isinstance(row['state_data'], str) else row['state_data']
                return {}
                
        except Exception as e:
            logger.error(f"Error getting user state: {e}")
            return {}
    
    @retry_on_failure(max_retries=3, delay=2)
    async def clear_user_state(self, user_id: int):
        """Clear user state"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    'DELETE FROM user_states WHERE user_id = $1',
                    user_id
                )
                
        except Exception as e:
            logger.error(f"Error clearing user state: {e}")
    
    @retry_on_failure(max_retries=3, delay=2)
    async def log_system_stats(self, messages_forwarded: int, errors: int, 
                              memory_usage: float, cpu_usage: float, 
                              queue_size: int, active_tasks: int):
        """Log system statistics"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    '''INSERT INTO system_stats 
                       (messages_forwarded, errors, memory_usage, cpu_usage, queue_size, active_tasks)
                       VALUES ($1, $2, $3, $4, $5, $6)''',
                    messages_forwarded, errors, memory_usage, cpu_usage, queue_size, active_tasks
                )
                
        except Exception as e:
            logger.error(f"Error logging system stats: {e}")
    
    @retry_on_failure(max_retries=3, delay=2)
    async def get_system_stats(self, hours: int = 24) -> List[Dict]:
        """Get system statistics for the last N hours"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    '''SELECT * FROM system_stats 
                       WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '%d hours'
                       ORDER BY timestamp DESC''',
                    hours
                )
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Error fetching system stats: {e}")
            return []
    
    @retry_on_failure(max_retries=3, delay=2)
    async def cleanup_old_stats(self, days: int = 7):
        """Clean up old statistics to save space"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    '''DELETE FROM system_stats 
                       WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '%d days' ''',
                    days
                )
                
                rows_affected = result.split()[-1] if isinstance(result, str) else 0
                if int(rows_affected) > 0:
                    logger.info(f"Cleaned up {rows_affected} old stat records")
                    
        except Exception as e:
            logger.error(f"Error cleaning up old stats: {e}")
    
    @retry_on_failure(max_retries=3, delay=1)
    async def test_connection(self) -> bool:
        """Test database connection"""
        try:
            if not self.pool:
                return False
                
            async with self.pool.acquire() as conn:
                result = await conn.fetchval('SELECT 1')
                return result == 1
                
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    async def get_task_statistics(self) -> Dict:
        """Get overall task statistics"""
        try:
            async with self.pool.acquire() as conn:
                # Get task counts
                task_counts = await conn.fetchrow(
                    '''SELECT 
                           COUNT(*) as total_tasks,
                           COUNT(*) FILTER (WHERE is_active = TRUE) as active_tasks,
                           COUNT(*) FILTER (WHERE is_active = FALSE) as inactive_tasks,
                           SUM(messages_forwarded) as total_messages,
                           SUM(error_count) as total_errors
                       FROM tasks'''
                )
                
                # Get most active task
                most_active = await conn.fetchrow(
                    '''SELECT source_id, destination_id, messages_forwarded 
                       FROM tasks 
                       WHERE messages_forwarded > 0 
                       ORDER BY messages_forwarded DESC 
                       LIMIT 1'''
                )
                
                # Get recent activity
                recent_activity = await conn.fetchrow(
                    '''SELECT COUNT(*) as recent_tasks
                       FROM tasks 
                       WHERE last_message_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' '''
                )
                
                return {
                    'total_tasks': task_counts['total_tasks'] or 0,
                    'active_tasks': task_counts['active_tasks'] or 0,
                    'inactive_tasks': task_counts['inactive_tasks'] or 0,
                    'total_messages': task_counts['total_messages'] or 0,
                    'total_errors': task_counts['total_errors'] or 0,
                    'most_active_task': dict(most_active) if most_active else None,
                    'recent_activity': recent_activity['recent_tasks'] or 0
                }
                
        except Exception as e:
            logger.error(f"Error getting task statistics: {e}")
            return {
                'total_tasks': 0,
                'active_tasks': 0,
                'inactive_tasks': 0,
                'total_messages': 0,
                'total_errors': 0,
                'most_active_task': None,
                'recent_activity': 0
            }
    
    async def close(self):
        """Close database connection pool"""
        try:
            if self.pool:
                await self.pool.close()
                logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
