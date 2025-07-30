import asyncpg
import os
import asyncio
import logging
from typing import List, Dict, Optional

class Database:
    def __init__(self):
        self.pool = None
        self.db_url = os.environ["DB_URL"]
    
    async def connect(self):
        """Establish database connection with retry logic"""
        for attempt in range(5):
            try:
                self.pool = await asyncpg.create_pool(
                    self.db_url,
                    min_size=3,
                    max_size=5,
                    max_queries=50000,
                    max_inactive_connection_lifetime=300
                )
                await self.create_tables()
                logging.info("✅ Database connected successfully")
                return
            except Exception as e:
                logging.error(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < 4:
                    await asyncio.sleep(5)
                else:
                    raise
    
    async def create_tables(self):
        """Create necessary tables"""
        async with self.pool.acquire() as conn:
            # Tasks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    source_id BIGINT NOT NULL,
                    destination_id BIGINT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User states table for control bot
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_states (
                    user_id BIGINT PRIMARY KEY,
                    state TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_source ON tasks(source_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(is_active)")
    
    async def add_task(self, source_id: int, destination_id: int) -> int:
        """Add a new forwarding task"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO tasks (source_id, destination_id) VALUES ($1, $2) RETURNING id",
                source_id, destination_id
            )
            return row['id']
    
    async def get_all_tasks(self) -> List[Dict]:
        """Get all tasks"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tasks ORDER BY id")
            return [dict(row) for row in rows]
    
    async def get_active_tasks(self) -> List[Dict]:
        """Get only active tasks"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tasks WHERE is_active = TRUE")
            return [dict(row) for row in rows]
    
    async def toggle_task(self, task_id: int):
        """Toggle task active status"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET is_active = NOT is_active WHERE id = $1",
                task_id
            )
    
    async def delete_task(self, task_id: int):
        """Delete a task"""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    
    async def disable_tasks_by_destination(self, dest_id: int):
        """Disable all tasks for a specific destination"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET is_active = FALSE WHERE destination_id = $1",
                dest_id
            )
    
    async def set_user_state(self, user_id: int, state: Optional[str]):
        """Set user state for control bot interactions"""
        async with self.pool.acquire() as conn:
            if state is None:
                await conn.execute("DELETE FROM user_states WHERE user_id = $1", user_id)
            else:
                await conn.execute(
                    """INSERT INTO user_states (user_id, state) 
                       VALUES ($1, $2) 
                       ON CONFLICT (user_id) 
                       DO UPDATE SET state = $2, updated_at = CURRENT_TIMESTAMP""",
                    user_id, state
                )
    
    async def get_user_state(self, user_id: int) -> Optional[str]:
        """Get user state"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state FROM user_states WHERE user_id = $1", user_id)
            return row['state'] if row else None
