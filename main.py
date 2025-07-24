import asyncio
import threading
import logging
import signal
import sys
import time
import os
from userbot import userbot
from control_bot import control_bot
from keep_alive import start_keep_alive_system
from database import db

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class TelegramForwarderSystem:
    def __init__(self):
        self.running = True
        self.userbot_task = None
        self.flask_thread = None
        self.start_time = time.time()
        
    def check_environment_variables(self):
        """Check all required environment variables"""
        logger.info("🔍 Checking environment variables...")
        
        required_vars = [
            'API_ID', 'API_HASH', 'SESSION_STRING', 
            'BOT_TOKEN', 'OWNER_ID', 'POSTGRES_DSN'
        ]
        
        missing_vars = []
        for var in required_vars:
            value = os.getenv(var)
            if value:
                if var in ['SESSION_STRING', 'BOT_TOKEN', 'POSTGRES_DSN']:
                    logger.info(f"✅ {var}: {'*' * 20}")
                else:
                    logger.info(f"✅ {var}: {value}")
            else:
                missing_vars.append(var)
                logger.error(f"❌ {var}: MISSING!")
        
        port = os.getenv("PORT", "10000")
        keep_alive_url = os.getenv("KEEP_ALIVE_URL", "Not set")
        logger.info(f"🔌 PORT: {port}")
        logger.info(f"🌐 KEEP_ALIVE_URL: {keep_alive_url}")
        
        if missing_vars:
            logger.error(f"❌ Missing required environment variables: {missing_vars}")
            return False
        
        logger.info("✅ All required environment variables are properly set")
        return True
        
    async def initialize_database(self):
        """Initialize database connection and tables"""
        try:
            logger.info("🗄️ Initializing database...")
            await db.init_db()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    async def start_userbot_service(self):
        """Start userbot service with error handling"""
        try:
            logger.info("🤖 Starting userbot service...")
            await userbot.start_userbot()
            logger.info("✅ Userbot service started successfully")
        except Exception as e:
            logger.error(f"❌ Userbot service failed to start: {e}")
            logger.info("⏳ Retrying userbot start in 10 seconds...")
            await asyncio.sleep(10)
            await self.start_userbot_service()
    
    def start_control_bot_service(self):
        """Start control bot with proper event loop handling"""
        try:
            logger.info("🎛️ Starting control bot service...")
            
            # 🔥 FIX: Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Start control bot in this thread's event loop
            control_bot.start_bot()
            
        except Exception as e:
            logger.error(f"❌ Control bot service error: {e}")
    
    def start_keep_alive_service(self):
        """Start keep-alive service with Flask server"""
        try:
            logger.info("🔄 Starting keep-alive service...")
            logger.info("🌐 Initializing Flask server for port detection...")
            
            self.flask_thread = start_keep_alive_system()
            
            # Wait for Flask to initialize properly
            time.sleep(4)
            
            if self.flask_thread and self.flask_thread.is_alive():
                logger.info("✅ Keep-alive service started successfully")
                logger.info("✅ Flask server is running and port should be detected")
            else:
                logger.error("❌ Keep-alive service failed to start properly")
                raise Exception("Flask server failed to start")
                
        except Exception as e:
            logger.error(f"❌ Keep-alive service failed: {e}")
            raise
    
    async def monitor_services(self):
        """Monitor all services and restart if needed"""
        logger.info("📊 Starting service monitoring...")
        
        while self.running:
            try:
                # Check userbot status
                if hasattr(userbot, 'is_running') and not userbot.is_running:
                    logger.warning("⚠️ Userbot is not running, attempting restart...")
                    try:
                        await self.start_userbot_service()
                    except Exception as e:
                        logger.error(f"Failed to restart userbot: {e}")
                
                # Check Flask server status
                if self.flask_thread and not self.flask_thread.is_alive():
                    logger.warning("⚠️ Flask server died, restarting...")
                    try:
                        self.start_keep_alive_service()
                    except Exception as e:
                        logger.error(f"Failed to restart Flask server: {e}")
                
                # Log periodic status
                uptime = time.time() - self.start_time
                active_tasks = len(userbot.active_tasks) if hasattr(userbot, 'active_tasks') else 0
                logger.info(f"💚 System healthy - Uptime: {uptime:.0f}s, Tasks: {active_tasks}")
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def start_system(self):
        """Start the complete forwarding system"""
        logger.info("🚀 Starting Telegram Auto-Forwarder System...")
        logger.info(f"📅 Start time: {time.ctime()}")
        logger.info(f"🐍 Python version: {sys.version}")
        
        try:
            # Step 1: Check environment variables
            logger.info("🔍 Step 1: Environment validation...")
            if not self.check_environment_variables():
                logger.error("❌ Environment check failed! Stopping deployment.")
                sys.exit(1)
            
            # Step 2: Start Flask server FIRST
            logger.info("🌐 Step 2: Starting Flask server (CRITICAL for port detection)...")
            self.start_keep_alive_service()
            
            # Step 3: Initialize database
            logger.info("🗄️ Step 3: Database initialization...")
            await self.initialize_database()
            
            # Step 4: Start userbot
            logger.info("🤖 Step 4: Starting userbot service...")
            self.userbot_task = asyncio.create_task(self.start_userbot_service())
            
            # Step 5: Start control bot in separate thread with event loop
            logger.info("🎛️ Step 5: Starting control bot...")
            control_bot_thread = threading.Thread(
                target=self.start_control_bot_service, 
                daemon=True
            )
            control_bot_thread.start()
            
            # Wait for services to initialize
            await asyncio.sleep(8)
            
            logger.info("✅ All services started successfully!")
            logger.info("🎯 System is now operational and ready to forward messages")
            logger.info(f"🌐 Service available at: {os.getenv('KEEP_ALIVE_URL', 'URL not configured')}")
            logger.info(f"🔌 Running on port: {os.getenv('PORT', '10000')}")
            
            # Start monitoring services
            await self.monitor_services()
            
        except Exception as e:
            logger.error(f"❌ System startup error: {e}")
            await self.shutdown_system()
            raise
    
    async def shutdown_system(self):
        """Gracefully shutdown the system"""
        logger.info("🛑 Initiating system shutdown...")
        self.running = False
        
        try:
            if hasattr(userbot, 'is_running') and userbot.is_running:
                await userbot.stop_userbot()
                logger.info("✅ Userbot stopped")
            
            if self.userbot_task and not self.userbot_task.done():
                self.userbot_task.cancel()
                try:
                    await self.userbot_task
                except asyncio.CancelledError:
                    logger.info("✅ Userbot task cancelled")
            
            logger.info("✅ System shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    def handle_signal(self, signum, frame):
        """Handle system signals"""
        logger.info(f"📡 Received signal {signum} - initiating shutdown")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.shutdown_system())

async def main():
    """Main application entry point"""
    logger.info("=" * 60)
    logger.info("🤖 TELEGRAM AUTO-FORWARDER SYSTEM")
    logger.info("🚀 RENDER DEPLOYMENT VERSION")
    logger.info("=" * 60)
    
    system = TelegramForwarderSystem()
    
    signal.signal(signal.SIGINT, system.handle_signal)
    signal.signal(signal.SIGTERM, system.handle_signal)
    
    try:
        await system.start_system()
        
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt")
        await system.shutdown_system()
        
    except Exception as e:
        logger.error(f"❌ Critical system error: {e}")
        await system.shutdown_system()
        sys.exit(1)

if __name__ == "__main__":
    try:
        if sys.version_info < (3, 8):
            logger.error("❌ Python 3.8+ required")
            sys.exit(1)
        
        logger.info(f"🐍 Python {sys.version}")
        logger.info("🚀 Starting application...")
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("👋 Application interrupted by user")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
        
    finally:
        logger.info("💤 Application terminated")
