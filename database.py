import asyncpg
import os
import logging
import asyncio
from utils import notify_admin

logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def initialize(self):
        for attempt in range(5):
            try:
                self.pool = await asyncpg.create_pool(os.environ["DB_URL"], min_size=3, max_size=5)
                await self.create_tables()
                logger.info("Database connected")
                return
            except Exception as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(5)
        logger.error("Failed to connect to database after 5 attempts")
        await notify_admin(None, "Failed to connect to database after 5 attempts")
        exit(1)

    async def create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    source_id BIGINT NOT NULL,
                    destination_id BIGINT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE
                );
                CREATE TABLE IF NOT EXISTS admins (
                    user_id BIGINT PRIMARY KEY
                );
            ''')
            await conn.execute('INSERT INTO admins (user_id) VALUES ($1) ON CONFLICT DO NOTHING', int(os.environ["ADMIN_ID"]))

    async def add_task(self, source_id, destination_id):
        async with self.pool.acquire() as conn:
            await conn.execute('INSERT INTO tasks (source_id, destination_id) VALUES ($1, $2)', source_id, destination_id)

    async def get_tasks(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch('SELECT * FROM tasks')

    async def get_task(self, task_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow('SELECT * FROM tasks WHERE id = $1', task_id)

    async def update_task_status(self, task_id, is_active):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE tasks SET is_active = $1 WHERE id = $2', is_active, task_id)

    async def delete_task(self, task_id):
        async with self.pool.acquire() as conn:
            await conn.execute('DELETE FROM tasks WHERE id = $1', task_id)

    async def update_all_tasks_status(self, is_active):
        async with self.pool.acquire() as conn:
            await conn.execute('UPDATE tasks SET is_active = $1', is_active)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.pool:
            await self.pool.close()            return Task(**row) if row else None  
      
    @classmethod  
    async def get_tasks_for_source(cls, source_id: int) -> list[Task]:  
        async with cls.get_conn() as conn:  
            rows = await conn.fetch(  
                "SELECT * FROM tasks WHERE source = $1 AND is_active = TRUE",   
                source_id  
            )  
            return [Task(**row) for row in rows]  
      
    @classmethod  
    async def get_all_tasks(cls) -> list[Task]:  
        async with cls.get_conn() as conn:  
            rows = await conn.fetch("SELECT * FROM tasks")  
            return [Task(**row) for row in rows]  
      
    @classmethod  
    async def toggle_task(cls, task_id: int, state: bool):  
        async with cls.get_conn() as conn:  
            await conn.execute(  
                "UPDATE tasks SET is_active = $1 WHERE id = $2",  
                state, task_id  
            )  
      
    @classmethod  
    async def delete_task(cls, task_id: int):  
        async with cls.get_conn() as conn:  
            await conn.execute(  
                "DELETE FROM tasks WHERE id = $1",  
                task_id  
            )  
      
    @classmethod  
    async def validate_tasks(cls):  
        """Check all tasks for permission issues"""  
        async with cls.get_conn() as conn:  
            invalid_tasks = await conn.fetch(  
                "SELECT id FROM tasks WHERE is_active = TRUE"  
            )  
            # Actual permission checks would be implemented here  
            # For now just simulate check  
            for task in invalid_tasks:  
                await cls.toggle_task(task[\'id\'], False)  
      
    # Admin and state management  
    @classmethod  
    async def is_admin(cls, user_id: int) -> bool:  
        async with cls.get_conn() as conn:  
            return await conn.fetchval(  
                "SELECT EXISTS(SELECT 1 FROM admins WHERE user_id = $1)",  
                user_id  
            )  
      
    @classmethod  
    async def set_state(cls, user_id: int, state: str):  
        async with cls.get_conn() as conn:  
            await conn.execute(\'\'\'  
                INSERT INTO user_state(user_id, state)  
                VALUES ($1, $2)  
                ON CONFLICT (user_id) DO UPDATE SET state = $2  
            \'\'\', user_id, state)  
      
    @classmethod  
    async def get_state(cls, user_id: int) -> str:  
        async with cls.get_conn() as conn:  
            return await conn.fetchval(  
                "SELECT state FROM user_state WHERE user_id = $1",  
                user_id  
            )  
      
    @classmethod  
    async def set_temp(cls, user_id: int, key: str, value):  
        async with cls.get_conn() as conn:  
            await conn.execute(\'\'\'  
                INSERT INTO user_state(user_id, temp)  
                VALUES ($1, jsonb_build_object($2, $3))  
                ON CONFLICT (user_id) DO UPDATE   
                SET temp = user_state.temp || jsonb_build_object($2, $3)  
            \'\'\', user_id, key, value)  
      
    @classmethod  
    async def get_temp(cls, user_id: int, key: str):  
        async with cls.get_conn() as conn:  
            return await conn.fetchval(  
                "SELECT temp->>$1 FROM user_state WHERE user_id = $2",  
                key, user_id  
            )  
      
    @classmethod  
    async def clear_state(cls, user_id: int):  
        async with cls.get_conn() as conn:  
            await conn.execute(  
                "DELETE FROM user_state WHERE user_id = $1",  
                user_id  
            )  
  
# Initialize on import  
import asyncio  
asyncio.get_event_loop().run_until_complete(DB.connect())

