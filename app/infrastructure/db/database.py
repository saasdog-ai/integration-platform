"""Async database engine and session management."""

import hashlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global engine instance (initialized on first use)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine

    if _engine is None:
        settings = get_settings()

        # Configure statement timeout to prevent long-running queries from
        # exhausting the connection pool. This is critical for production stability.
        connect_args = {
            "server_settings": {
                "statement_timeout": str(settings.database_statement_timeout_ms),
            },
            # Command timeout for asyncpg (connection-level timeout)
            "command_timeout": settings.database_statement_timeout_ms / 1000,
        }

        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_recycle=settings.database_pool_recycle,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            connect_args=connect_args,
            echo=settings.is_development and settings.log_level.upper() == "DEBUG",
        )
        logger.info(
            "Database engine created",
            extra={
                "pool_size": settings.database_pool_size,
                "max_overflow": settings.database_max_overflow,
                "statement_timeout_ms": settings.database_statement_timeout_ms,
            },
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for getting a database session (for non-FastAPI use)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database connection and verify connectivity."""
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error("Database connection failed", extra={"error": str(e)})
        raise


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


def _compute_lock_id(client_id: UUID, integration_id: UUID) -> int:
    """
    Compute a stable advisory lock ID from client_id and integration_id.

    PostgreSQL advisory locks use int8 (bigint) for lock IDs.
    We hash the UUIDs to get a stable, reproducible lock ID.
    """
    combined = f"{client_id}:{integration_id}".encode()
    hash_bytes = hashlib.sha256(combined).digest()[:8]
    return int.from_bytes(hash_bytes, byteorder="big", signed=True)


@asynccontextmanager
async def advisory_lock(
    session: AsyncSession, client_id: UUID, integration_id: UUID
) -> AsyncGenerator[None, None]:
    """
    Context manager for PostgreSQL advisory lock.

    Uses pg_advisory_xact_lock which is automatically released at transaction end.
    This lock is blocking - it waits until the lock is available.

    Args:
        session: The database session (must be within a transaction).
        client_id: The client ID for the lock.
        integration_id: The integration ID for the lock.
    """
    lock_id = _compute_lock_id(client_id, integration_id)
    # pg_advisory_xact_lock is transaction-scoped and automatically released
    await session.execute(text(f"SELECT pg_advisory_xact_lock({lock_id})"))
    logger.debug(
        "Advisory lock acquired",
        extra={"lock_id": lock_id, "client_id": str(client_id)},
    )
    try:
        yield
    finally:
        # Lock is automatically released when transaction ends
        logger.debug(
            "Advisory lock will be released on transaction end",
            extra={"lock_id": lock_id},
        )
