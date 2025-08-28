from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.database.session import init_db
from app.bot.telegram_bot import telegram_bot
from app.scanner.scanner import token_scanner
from app.services.redis_client import redis_client
from app.core.logging_config import setup_logging
from app.services.result_tracker import run_tracking_loop, run_cleanup_loop
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting DexScanner Bot...")

    # Initialize database
    try:
        if settings.DATABASE_URL:
            await init_db()
            print("✅ Database connected successfully")
        else:
            print("⚠️ Database URL not configured - running in memory mode")
    except Exception as e:
        print(f"⚠️ Database connection failed: {str(e)[:50]}... - running in memory mode")

    # Initialize Redis
    await redis_client.connect()

    # Start Telegram bot
    if settings.BOT_TOKEN and settings.BOT_TOKEN != "your_bot_token_here":
        asyncio.create_task(telegram_bot.start_polling())
        print("✅ Telegram bot started")
    else:
        print("⚠️ BOT_TOKEN not configured, skipping Telegram bot")

    # Start token scanner
    asyncio.create_task(token_scanner.start_scanning())
    print("✅ Token scanner started")
    # Start result tracking jobs
    asyncio.create_task(run_tracking_loop())
    asyncio.create_task(run_cleanup_loop())
    print("✅ Result tracking jobs started")


    yield

    # Shutdown
    print("🛑 Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="DexScanner Bot",
    description="Advanced Solana Token Analysis Bot",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {"message": "DexScanner Bot is running!", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    from app.database.session import get_db
    from app.database.models import User
    from sqlalchemy import select, text
    import datetime
    
    # Check database
    db_status = "healthy"
    try:
        async for session in get_db():
            await session.execute(text("SELECT 1"))
            break
    except:
        db_status = "error"
    
    # Count active users
    user_count = 0
    try:
        async for session in get_db():
            result = await session.execute(select(User).where(User.is_subscribed == True))
            user_count = len(result.scalars().all())
            break
    except:
        pass
    
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "services": {
            "telegram": bool(settings.BOT_TOKEN),
            "database": db_status,
            "redis": redis_client.connected
        },
        "metrics": {
            "active_users": user_count,
            "scanner_interval": settings.SCAN_INTERVAL
        }
    }

@app.get("/trending")
async def get_trending():
    """Test endpoint for trending tokens"""
    from app.scanner.data_provider import data_provider
    tokens = await data_provider.fetch_trending_tokens(limit=10)
    return {"trending_tokens": tokens}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
