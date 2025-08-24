from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.config import settings
from app.database.session import init_db
from app.bot.telegram_bot import telegram_bot
from app.scanner.scanner import token_scanner
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

    # Start Telegram bot
    if settings.BOT_TOKEN and settings.BOT_TOKEN != "your_bot_token_here":
        asyncio.create_task(telegram_bot.start_polling())
        print("✅ Telegram bot started")
    else:
        print("⚠️ BOT_TOKEN not configured, skipping Telegram bot")

    # Start token scanner
    asyncio.create_task(token_scanner.start_scanning())
    print("✅ Token scanner started")

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
    return {"status": "healthy", "telegram_configured": bool(settings.BOT_TOKEN)}

@app.get("/trending")
async def get_trending():
    """Test endpoint for trending tokens"""
    from app.scanner.data_provider import data_provider
    tokens = await data_provider.fetch_trending_tokens(limit=10)
    return {"trending_tokens": tokens}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
