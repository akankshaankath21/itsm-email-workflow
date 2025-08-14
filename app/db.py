from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Database engine
engine = create_async_engine(
    settings.database_url,
    echo=False,  # Set to True for SQL query logging
    future=True
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
class Base(DeclarativeBase):
    pass

# Dependency for FastAPI routes
async def get_session() -> AsyncSession:
    """Database session dependency for FastAPI routes."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

# Initialize database tables
async def init_models() -> None:
    """Create all database tables."""
    async with engine.begin() as conn:
        # Import all models to ensure they're registered
        from app.models import GmailNode, RawEmail, EmailRecord, WorkflowExecution
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully")