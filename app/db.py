from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True
)


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass

async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_models() -> None:
    async with engine.begin() as conn:
        from app.models import GmailNode, RawEmail, EmailRecord, WorkflowExecution
        
        from app.workflow_models import (
            WorkflowTemplate, WorkflowNode, WorkflowEdge, 
            WorkflowInstance, NodeExecution
        )
        
        await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully")