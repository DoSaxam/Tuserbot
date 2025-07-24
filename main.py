import asyncio
import threading
import logging
import signal
import sys
import time
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
        self.control_bot_thread = None
        self.start_time = time.time()
        
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
            # Retry after delay
            await asyncio.sleep(10)
            await self.start_userbot_service()
    
    def start_control_bot_service(self):
        """Start control bot in separate thread"""
        try:
            logger.info("🎛️ Starting control bot service...")
            control_bot.start_bot()
        except Exception as e:
            logger.error(f"❌ Control bot service error: {e}")
    
    def start_keep_alive_service(self):
        """Start keep-alive service"""
        try:
            logger.info("🔄 Starting keep-alive service...")
            self.flask_thread = start_keep_alive_system()
            logger.info("✅ Keep-alive service started successfully")
        except Exception as e:
            logger.error(f"❌ Keep-alive service failed: {e}")
    
    async def monitor_services(self):
        """Monitor all services and restart if needed"""
        logger.info("📊 Starting service monitoring...")
        
        while self.running:
            try:
                # Check userbot status
                if not userbot.is_running:
                    logger.warning("⚠️ Userbot is not running, attempting restart...")
                    try:
                        await self.start_userbot_service()
                    except Exception as e:
                        logger.error(f"Failed to restart userbot: {e}")
                
                # Check Flask server status
                if self.flask_thread and not self.flask_thread.is_alive():
                    logger.warning("⚠️ Flask server died, restarting...")
                    self.start_keep_alive_service()
                
                # Log periodic status
                uptime = time.time() - self.start_time
                logger.info(f"💚 System healthy - Uptime: {uptime:.0f}s, Tasks: {len(userbot.active_tasks)}")
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def start_system(self):
        """Start the complete forwarding system"""
        logger.info("🚀 Starting Telegram Auto-Forwarder System...")
        logger.info(f"📅 Start time: {time.ctime()}")
        
        try:
            # Initialize database first
            await self.initialize_database()
            
            # Start keep-alive service
            self.start_keep_alive_service()
            
            # Start userbot
            self.userbot_task = asyncio.create_task(self.start_userbot_service())
            
            # Start control bot in separate thread
            self.control_bot_thread = threading.Thread(
                target=self.start_control_bot_service, 
                daemon=True
            )
            self.control_bot_thread.start()
            
            # Wait a bit for services to initialize
            await asyncio.sleep(5)
            
            logger.info("✅ All services started successfully!")
            logger.info("🎯 System is now operational and ready to forward messages")
            
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
            # Stop userbot
            if userbot.is_running:
                await userbot.stop_userbot()
                logger.info("✅ Userbot stopped")
            
            # Cancel userbot task
            if self.userbot_task and not self.userbot_task.done():
                self.userbot_task.cancel()
                try:
                    await self.userbot_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("✅ System shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")
    
    def handle_signal(self, signum, frame):
        """Handle system signals"""
        logger.info(f"📡 Received signal {signum} - initiating shutdown")
        asyncio.create_task(self.shutdown_system())

async def main():
    """Main application entry point"""
    logger.info("=" * 50)
    logger.info("🤖 TELEGRAM AUTO-FORWARDER SYSTEM")
    logger.info("=" * 50)
    
    # Create system instance
    system = TelegramForwarderSystem()
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, system.handle_signal)
    signal.signal(signal.SIGTERM, system.handle_signal)
    
    try:
        # Start the complete system
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
        # Check Python version
        if sys.version_info < (3, 8):
            logger.error("❌ Python 3.8+ required")
            sys.exit(1)
        
        logger.info(f"🐍 Python {sys.version}")
        logger.info("🚀 Starting application...")
        
        # Run the main application
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("👋 Application interrupted by user")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
        
    finally:
        logger.info("💤 Application terminated")
