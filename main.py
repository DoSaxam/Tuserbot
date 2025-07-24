import asyncio
import threading
import logging
import signal
import sys
import time
import os
from datetime import datetime

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
        self.system_healthy = False
        
    def check_environment_variables(self):
        """Check all required environment variables"""
        required_vars = {
            'API_ID': 'Telegram API ID',
            'API_HASH': 'Telegram API Hash',
            'SESSION_STRING': 'Pyrogram Session String',
            'BOT_TOKEN': 'Telegram Bot Token',
            'OWNER_ID': 'Telegram User ID',
            'POSTGRES_DSN': 'PostgreSQL Database URL'
        }
        
        missing_vars = []
        
        for var, description in required_vars.items():
            value = os.getenv(var)
            if value:
                # Mask sensitive data in logs
                if var in ['SESSION_STRING', 'BOT_TOKEN', 'POSTGRES_DSN']:
                    masked_value = f"{value[:10]}..." if len(value) > 10 else "***"
                    logger.info(f"✅ {var}: {masked_value} ({description})")
                else:
                    logger.info(f"✅ {var}: {value} ({description})")
            else:
                logger.error(f"❌ {var}: MISSING! ({description})")
                missing_vars.append(var)
        
        # Optional variables
        optional_vars = ['KEEP_ALIVE_URL', 'PORT']
        for var in optional_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"✅ {var}: {value} (Optional)")
            else:
                logger.warning(f"⚠️ {var}: Not set (Optional)")
        
        return len(missing_vars) == 0, missing_vars
    
    def start_flask_server(self):
        """Start Flask server in separate thread"""
        try:
            logger.info("🌐 Starting Flask server thread...")
            
            from keep_alive import initialize_keep_alive_system, start_flask_server
            
            # Initialize keep-alive system first
            if initialize_keep_alive_system():
                logger.info("✅ Keep-alive system initialized")
                
                # Start Flask server
                start_flask_server()
            else:
                logger.error("❌ Keep-alive system initialization failed")
                raise Exception("Keep-alive system failed to initialize")
                
        except Exception as e:
            logger.error(f"❌ Flask server thread error: {e}")
            raise
    
    async def initialize_database(self):
        """Initialize database connection and tables"""
        try:
            logger.info("🗄️ Initializing database connection...")
            
            from database import db
            await db.init_db()
            
            logger.info("✅ Database initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False
    
    async def start_userbot_service(self):
        """Start userbot service with comprehensive error handling"""
        try:
            logger.info("🤖 Starting userbot service...")
            
            from userbot import userbot
            await userbot.start_userbot()
            
            if userbot.is_running:
                logger.info("✅ Userbot service started successfully")
                return True
            else:
                logger.error("❌ Userbot failed to start properly")
                return False
                
        except Exception as e:
            logger.error(f"❌ Userbot service startup error: {e}")
            # Retry logic
            logger.info("🔄 Retrying userbot startup in 10 seconds...")
            await asyncio.sleep(10)
            try:
                from userbot import userbot
                await userbot.start_userbot()
                return userbot.is_running
            except Exception as retry_error:
                logger.error(f"❌ Userbot retry failed: {retry_error}")
                return False
    
    def start_control_bot_service(self):
        """Start control bot in separate thread"""
        try:
            logger.info("🎛️ Starting control bot service...")
            
            from control_bot import control_bot
            control_bot.start_bot()
            
        except Exception as e:
            logger.error(f"❌ Control bot service error: {e}")
            raise
    
    async def monitor_system_health(self):
        """Monitor all services and restart if needed"""
        logger.info("📊 Starting system health monitoring...")
        
        while self.running:
            try:
                # Check userbot status
                from userbot import userbot
                
                if not userbot.is_running:
                    logger.warning("⚠️ Userbot is not running, attempting restart...")
                    restart_success = await self.start_userbot_service()
                    if restart_success:
                        logger.info("✅ Userbot restarted successfully")
                    else:
                        logger.error("❌ Failed to restart userbot")
                
                # Check Flask server status
                if self.flask_thread and not self.flask_thread.is_alive():
                    logger.warning("⚠️ Flask server thread died, attempting restart...")
                    try:
                        self.flask_thread = threading.Thread(target=self.start_flask_server, daemon=True)
                        self.flask_thread.start()
                        logger.info("✅ Flask server thread restarted")
                    except Exception as e:
                        logger.error(f"❌ Failed to restart Flask server: {e}")
                
                # Log periodic health status
                uptime = time.time() - self.start_time
                uptime_str = str(datetime.fromtimestamp(uptime) - datetime.fromtimestamp(0))[:-7]
                
                logger.info(f"💚 System Health Check - Uptime: {uptime_str}, Tasks: {len(userbot.active_tasks)}")
                
                self.system_healthy = True
                
                # Wait before next health check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"❌ Health monitoring error: {e}")
                self.system_healthy = False
                await asyncio.sleep(30)  # Shorter interval if errors
    
    async def start_complete_system(self):
        """Start the complete forwarding system with proper sequencing"""
        logger.info("=" * 60)
        logger.info("🚀 TELEGRAM AUTO-FORWARDER SYSTEM STARTUP")
        logger.info("=" * 60)
        logger.info(f"📅 Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"🐍 Python Version: {sys.version}")
        logger.info(f"🌍 Environment: {os.getenv('RENDER_SERVICE_NAME', 'Local Development')}")
        
        try:
            # Step 1: Environment Variables Check
            logger.info("🔍 Step 1: Checking environment variables...")
            env_check, missing_vars = self.check_environment_variables()
            
            if not env_check:
                logger.error(f"❌ Missing required environment variables: {missing_vars}")
                logger.error("💡 Please set all required environment variables in Render dashboard")
                sys.exit(1)
            
            logger.info("✅ Step 1 Complete: All environment variables verified")
            
            # Step 2: Start Flask Server (Critical for Render port detection)
            logger.info("🌐 Step 2: Starting Flask server for port binding...")
            self.flask_thread = threading.Thread(target=self.start_flask_server, daemon=True)
            self.flask_thread.start()
            
            # Wait for Flask server to bind to port
            await asyncio.sleep(5)
            
            if self.flask_thread.is_alive():
                logger.info("✅ Step 2 Complete: Flask server started and port bound")
            else:
                logger.error("❌ Step 2 Failed: Flask server failed to start")
                sys.exit(1)
            
            # Step 3: Database Initialization
            logger.info("🗄️ Step 3: Initializing database...")
            db_success = await self.initialize_database()
            
            if not db_success:
                logger.error("❌ Step 3 Failed: Database initialization failed")
                sys.exit(1)
            
            logger.info("✅ Step 3 Complete: Database initialized successfully")
            
            # Step 4: Start Userbot Service
            logger.info("🤖 Step 4: Starting userbot service...")
            userbot_success = await self.start_userbot_service()
            
            if not userbot_success:
                logger.error("❌ Step 4 Failed: Userbot service failed to start")
                sys.exit(1)
            
            logger.info("✅ Step 4 Complete: Userbot service started")
            
            # Step 5: Start Control Bot
            logger.info("🎛️ Step 5: Starting control bot service...")
            self.control_bot_thread = threading.Thread(target=self.start_control_bot_service, daemon=True)
            self.control_bot_thread.start()
            
            # Wait for control bot to initialize
            await asyncio.sleep(3)
            
            if self.control_bot_thread.is_alive():
                logger.info("✅ Step 5 Complete: Control bot service started")
            else:
                logger.error("❌ Step 5 Failed: Control bot failed to start")
                sys.exit(1)
            
            # System Startup Complete
            logger.info("=" * 60)
            logger.info("🎉 SYSTEM STARTUP COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            logger.info("📊 System Status:")
            logger.info("   • Flask Server: ✅ Running")
            logger.info("   • Database: ✅ Connected")
            logger.info("   • Userbot: ✅ Active")
            logger.info("   • Control Bot: ✅ Online")
            logger.info("   • Keep-Alive: ✅ Active")
            logger.info("=" * 60)
            logger.info("🌐 Service URLs:")
            logger.info(f"   • Main: {os.getenv('KEEP_ALIVE_URL', 'Not configured')}")
            logger.info(f"   • Health: {os.getenv('KEEP_ALIVE_URL', 'Not configured')}/health")
            logger.info(f"   • Stats: {os.getenv('KEEP_ALIVE_URL', 'Not configured')}/stats")
            logger.info("=" * 60)
            
            # Start system monitoring
            await self.monitor_system_health()
            
        except KeyboardInterrupt:
            logger.info("👋 Received keyboard interrupt")
            await self.shutdown_system()
            
        except Exception as e:
            logger.error(f"❌ Critical system startup error: {e}")
            logger.error("💡 Check logs above for specific error details")
            await self.shutdown_system()
            raise
    
    async def shutdown_system(self):
        """Gracefully shutdown the system"""
        logger.info("🛑 Initiating graceful system shutdown...")
        self.running = False
        
        try:
            # Stop userbot
            from userbot import userbot
            if userbot.is_running:
                await userbot.stop_userbot()
                logger.info("✅ Userbot stopped")
            
            # Cancel any running tasks
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
        """Handle system signals for graceful shutdown"""
        logger.info(f"📡 Received system signal {signum} - initiating shutdown")
        asyncio.create_task(self.shutdown_system())

async def main():
    """Main application entry point"""
    # ASCII Art Banner
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                                                            ║
    ║        🤖 TELEGRAM AUTO-FORWARDER SYSTEM 🤖                ║
    ║                                                            ║
    ║        ⚡ Real-time Message Forwarding                     ║
    ║        🔄 24/7 Operation on Render                         ║
    ║        🛡️  Session String Authentication                   ║
    ║        💾 PostgreSQL Database                              ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    
    # Create system instance
    system = TelegramForwarderSystem()
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, system.handle_signal)
    signal.signal(signal.SIGTERM, system.handle_signal)
    
    try:
        # Check Python version compatibility
        if sys.version_info < (3, 8):
            logger.error("❌ Python 3.8+ required for this application")
            sys.exit(1)
        
        # Start the complete system
        await system.start_complete_system()
        
    except KeyboardInterrupt:
        logger.info("👋 Application interrupted by user")
        await system.shutdown_system()
        
    except Exception as e:
        logger.error(f"❌ Fatal application error: {e}")
        await system.shutdown_system()
        sys.exit(1)
        
    finally:
        logger.info("💤 Application terminated")

if __name__ == "__main__":
    try:
        logger.info("🎯 Starting main application...")
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("👋 Main interrupted by user")
        
    except Exception as e:
        logger.error(f"❌ Main execution error: {e}")
        sys.exit(1)
