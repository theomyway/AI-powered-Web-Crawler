"""
Database session management with async support.

Provides connection pooling and session factory for Azure Cosmos DB PostgreSQL.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global engine instance
_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async database engine.
    
    Uses connection pooling optimized for Azure Cosmos DB PostgreSQL.
    
    Returns:
        AsyncEngine: SQLAlchemy async engine
    """
    global _engine
    
    if _engine is None:
        settings = get_settings()

        # Remove sslmode from URL - asyncpg uses ssl parameter instead
        db_url = str(settings.database_url).replace("?sslmode=require", "")

        _engine = create_async_engine(
            db_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=300,    # Recycle connections after 5 minutes
            echo=settings.database_echo,
            # Azure Cosmos DB for PostgreSQL settings
            connect_args={
                "ssl": True,  # Enable SSL for Azure Cosmos DB
                "server_settings": {
                    "application_name": settings.app_name,
                },
            },
        )
        
        logger.info(
            "Database engine created",
            pool_size=settings.database_pool_size,
            environment=settings.environment,
        )
    
    return _engine


# Alias for backward compatibility
engine = property(get_engine)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get async session factory.
    
    Returns:
        async_sessionmaker: Factory for creating async sessions
    """
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Global session factory
async_session_factory = get_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Yields:
        AsyncSession: Database session
        
    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside of request context.
    
    Example:
        async with get_db_context() as db:
            result = await db.execute(select(Item))
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Close the database engine and all connections."""
    global _engine
    
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine closed")

