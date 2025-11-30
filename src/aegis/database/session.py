"""Database session management."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aegis.config import get_settings

logger = structlog.get_logger(__name__)

# Cache for engines to avoid recreating them
_engines: dict[str, Engine] = {}
_session_factories: dict[str, sessionmaker] = {}


def get_db_url(project_gid: str | None = None) -> str:
    """Get database URL.

    If project_gid is None, returns the Master DB URL.
    If project_gid is provided, returns the Project DB URL.
    """
    settings = get_settings()

    if project_gid is None:
        # Master DB
        # Use a local sqlite file for the master process
        # We can put this in the .aegis directory in the repo root or user home
        # For now, let's assume it's in the .aegis directory of the current repo
        # or defined in settings.
        # If settings.database_url is set (e.g. postgres), we use that as master?
        # The prompt asked for "each project should have a .sqlite database".
        # It didn't explicitly say the master must be sqlite, but implied a separation.
        # Let's use a dedicated master.sqlite in the .aegis dir.

        # We need a place to store these. Let's use the .aegis directory.
        # Ideally we'd know the repo root.
        # For now, let's use a default location or rely on settings.
        # Let's assume we run from the repo root or have access to it.
        # But `get_db_url` might be called from anywhere.

        # Let's stick to a simple convention:
        # Master DB: .aegis/master.sqlite
        # Project DB: .aegis/projects/{gid}.sqlite

        base_dir = Path.cwd() / ".aegis"
        base_dir.mkdir(exist_ok=True)
        return f"sqlite:///{base_dir}/master.sqlite"
    else:
        # Project DB
        base_dir = Path.cwd() / ".aegis" / "projects"
        base_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{base_dir}/{project_gid}.sqlite"


def get_engine(db_url: str) -> Engine:
    """Get or create database engine for a specific URL."""
    global _engines

    if db_url not in _engines:
        logger.debug("creating_db_engine", url=db_url)
        _engines[db_url] = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        )
    return _engines[db_url]


def get_session_factory(db_url: str) -> sessionmaker:
    """Get or create session factory for a specific URL."""
    global _session_factories

    if db_url not in _session_factories:
        engine = get_engine(db_url)
        _session_factories[db_url] = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _session_factories[db_url]


def init_db(project_gid: str | None = None) -> None:
    """Initialize database tables.

    Args:
        project_gid: If None, initializes Master DB. If set, initializes Project DB.
    """
    db_url = get_db_url(project_gid)
    engine = get_engine(db_url)

    if project_gid is None:
        # Initialize Master models
        from aegis.database.master_models import Base as MasterBase
        MasterBase.metadata.create_all(engine)
    else:
        # Initialize Project models
        from aegis.database.models import Base as ProjectBase
        ProjectBase.metadata.create_all(engine)


@contextmanager
def get_db_session(project_gid: str | None = None) -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Args:
        project_gid: If None, connects to Master DB. If set, connects to Project DB.

    Usage:
        # Master DB
        with get_db_session() as session:
            ...

        # Project DB
        with get_db_session("12345") as session:
            ...
    """
    db_url = get_db_url(project_gid)
    factory = get_session_factory(db_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def cleanup_db_connections() -> None:
    """Clean up all database connections."""
    global _engines, _session_factories

    logger.info("cleaning_up_database_connections")

    try:
        for url, engine in _engines.items():
            logger.debug("disposing_database_engine", url=url)
            engine.dispose()

        _engines.clear()
        _session_factories.clear()

        logger.info("database_connections_cleaned_up")

    except Exception as e:
        logger.error("database_cleanup_failed", error=str(e), exc_info=True)
        raise
