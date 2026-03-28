"""
Async database connection pool using asyncpg + SQLAlchemy async engine.
Provides a FastAPI dependency `get_db` that yields an asyncpg connection.
"""
from typing import AsyncGenerator
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import structlog

logger = structlog.get_logger()

# SQLAlchemy async engine (used for ORM models)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# Bare asyncpg pool (used directly in services for raw queries)
_pool: asyncpg.Pool | None = None


async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.DATABASE_URL.replace("+asyncpg", ""),
        min_size=2,
        max_size=10,
    )
    logger.info("Database pool initialized")


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Database pool closed")


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


# FastAPI dependency — yields an asyncpg connection from the pool
async def get_db() -> AsyncGenerator[asyncpg.Connection, None]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


# FastAPI dependency — yields an SQLAlchemy AsyncSession (for ORM operations)
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
