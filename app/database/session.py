from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Check if DATABASE_URL is configured
if settings.DATABASE_URL and settings.DATABASE_URL != "":
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://") if "postgresql://" in settings.DATABASE_URL else settings.DATABASE_URL,
        echo=False
    )
    
    SessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
else:
    engine = None
    SessionLocal = None

async def init_db():
    """Initialize database tables"""
    if engine is None:
        raise Exception("Database URL not configured")
        
    from app.database.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    """Get database session"""
    if SessionLocal is None:
        raise Exception("Database not configured")
        
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
