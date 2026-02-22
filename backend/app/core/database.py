"""Async database layer for GovContract AI.

Uses SQLAlchemy 2.x async engine with asyncpg driver, targeting Supabase PostgreSQL.
All public functions degrade gracefully if DATABASE_URL is not set — the app runs
in in-memory mode (V1) without any code changes elsewhere.
"""
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory: Optional[async_sessionmaker] = None


class Base(DeclarativeBase):
    pass


def db_enabled() -> bool:
    """Return True if DATABASE_URL is configured."""
    return bool(get_settings().database_url)


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    # Normalise driver prefix — Supabase connection strings often start with postgres://
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # If already postgresql+asyncpg:// leave it alone
    return create_async_engine(
        url,
        echo=settings.debug,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )


async def init_db() -> bool:
    """
    Create all tables (if they don't exist) and initialise the session factory.

    Returns True if the database is available, False if DATABASE_URL is not set
    or the connection failed. The app continues in in-memory mode on False.
    """
    if not db_enabled():
        logger.info("DATABASE_URL not set — running in in-memory mode (V1)")
        return False

    global _engine, _session_factory
    try:
        _engine = _make_engine()
        # Import so ORM models are registered with Base.metadata
        import app.models.db_models  # noqa: F401

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
        logger.info("Database initialised successfully")
        return True
    except Exception as e:
        logger.error(f"Database init failed — continuing in-memory: {e}")
        _engine = None
        _session_factory = None
        return False


async def get_db_session() -> Optional[AsyncSession]:
    """
    Return a new AsyncSession, or None if DB is not available.
    Caller is responsible for closing the session.
    """
    if _session_factory is None:
        return None
    return _session_factory()


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
