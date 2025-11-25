"""Database session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine
import structlog

from aegis.config import get_settings

logger = structlog.get_logger(__name__)

# Global session factory and engine
_session_factory: sessionmaker | None = None
_engine: Engine | None = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using
            echo=False,  # Set to True for SQL logging during development
        )
    return _engine


def init_db() -> None:
    """Initialize database connection and create all tables."""
    from aegis.database.models import Base

    engine = get_engine()
    Base.metadata.create_all(engine)


def get_session_factory() -> sessionmaker:
    """Get or create the global session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Usage:
        with get_db_session() as session:
            project = session.query(Project).first()
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Session:
    """Get a database session (for dependency injection).

    Note: Caller is responsible for closing the session.

    Usage:
        session = get_db()
        try:
            project = session.query(Project).first()
            session.commit()
        finally:
            session.close()
    """
    factory = get_session_factory()
    return factory()


def cleanup_db_connections() -> None:
    """Clean up database connections and dispose of engine.

    This should be called during shutdown to ensure all database
    connections are properly closed.
    """
    global _session_factory, _engine

    logger.info("cleaning_up_database_connections")

    try:
        # Dispose of the engine, which closes all connections in the pool
        if _engine is not None:
            logger.debug("disposing_database_engine")
            _engine.dispose()
            logger.info("database_engine_disposed")
            _engine = None

        # Clear session factory
        _session_factory = None

    except Exception as e:
        logger.error("database_cleanup_failed", error=str(e), exc_info=True)
        raise
