import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text, Integer, String, BigInteger, Column, TIMESTAMP, select, update, delete
from sqlalchemy.orm import declarative_base
from config import POSTGRES_DSN

logger = logging.getLogger(__name__)
Base = declarative_base()

class ForwardTask(Base):
    __tablename__ = "forward_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_chat = Column(BigInteger, nullable=False)
    dest_chat = Column(BigInteger, nullable=False)
    task_name = Column(String(120), nullable=False)
    status = Column(String(10), default="active")
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))

# Database engine and session
engine = create_async_engine(POSTGRES_DSN, pool_size=10, max_overflow=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Database:
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
    
    async def init_db(self):
        """Initialize database tables"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
            raise
    
    async def add_task(self, source_chat, dest_chat, task_name):
        """Add new forwarding task"""
        try:
            async with self.SessionLocal() as session:
                new_task = ForwardTask(
                    source_chat=source_chat,
                    dest_chat=dest_chat,
                    task_name=task_name,
                    status="active"
                )
                session.add(new_task)
                await session.commit()
                await session.refresh(new_task)
                logger.info(f"✅ Task added: {task_name}")
                return new_task.id
        except Exception as e:
            logger.error(f"❌ Error adding task: {e}")
            return None
    
    async def get_all_active_tasks(self):
        """Get all active forwarding tasks"""
        try:
            async with self.SessionLocal() as session:
                result = await session.execute(
                    select(ForwardTask).where(ForwardTask.status == "active")
                )
                tasks = result.scalars().all()
                return tasks
        except Exception as e:
            logger.error(f"❌ Error getting tasks: {e}")
            return []
    
    async def get_all_tasks(self):
        """Get all tasks"""
        try:
            async with self.SessionLocal() as session:
                result = await session.execute(select(ForwardTask))
                tasks = result.scalars().all()
                return tasks
        except Exception as e:
            logger.error(f"❌ Error getting all tasks: {e}")
            return []
    
    async def update_task_status(self, task_id, status):
        """Update task status"""
        try:
            async with self.SessionLocal() as session:
                await session.execute(
                    update(ForwardTask)
                    .where(ForwardTask.id == task_id)
                    .values(status=status)
                )
                await session.commit()
                logger.info(f"✅ Task {task_id} status updated to {status}")
                return True
        except Exception as e:
            logger.error(f"❌ Error updating task status: {e}")
            return False
    
    async def delete_task(self, task_id):
        """Delete task"""
        try:
            async with self.SessionLocal() as session:
                await session.execute(
                    delete(ForwardTask).where(ForwardTask.id == task_id)
                )
                await session.commit()
                logger.info(f"✅ Task {task_id} deleted")
                return True
        except Exception as e:
            logger.error(f"❌ Error deleting task: {e}")
            return False
    
    async def get_task_by_id(self, task_id):
        """Get task by ID"""
        try:
            async with self.SessionLocal() as session:
                result = await session.execute(
                    select(ForwardTask).where(ForwardTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                return task
        except Exception as e:
            logger.error(f"❌ Error getting task by ID: {e}")
            return None

# Global database instance
db = Database()
