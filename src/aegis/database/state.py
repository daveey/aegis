"""System state management for tracking orchestrator status."""

import os
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from aegis.database.models import SystemState
from aegis.database.session import get_db_session

logger = structlog.get_logger(__name__)


def get_or_create_system_state(session: Session) -> SystemState:
    """Get or create the singleton system state record.

    Args:
        session: Database session

    Returns:
        SystemState instance
    """
    state = session.query(SystemState).filter_by(id=1).first()
    if state is None:
        state = SystemState(id=1)
        session.add(state)
        session.commit()
        logger.info("created_system_state")
    return state


def update_orchestrator_status(
    status: str,
    pid: Optional[int] = None,
    session: Optional[Session] = None
) -> None:
    """Update orchestrator status in database.

    Args:
        status: New status ('running', 'stopped', 'paused')
        pid: Process ID (optional)
        session: Database session (optional, will create if not provided)
    """
    should_close_session = False

    try:
        if session is None:
            session = get_db()
            should_close_session = True

        state = get_or_create_system_state(session)
        state.orchestrator_status = status
        state.orchestrator_pid = pid

        if status == "running":
            state.orchestrator_started_at = datetime.now()
        elif status == "stopped":
            state.orchestrator_started_at = None
            state.orchestrator_pid = None

        session.commit()
        logger.info("updated_orchestrator_status", status=status, pid=pid)

    except Exception as e:
        logger.error("failed_to_update_orchestrator_status", error=str(e), exc_info=True)
        if session:
            session.rollback()
        raise
    finally:
        if should_close_session and session:
            session.close()


def mark_orchestrator_stopped(session: Optional[Session] = None) -> None:
    """Mark orchestrator as stopped in database.

    Args:
        session: Database session (optional)
    """
    update_orchestrator_status(status="stopped", pid=None, session=session)
    logger.info("orchestrator_marked_stopped")


def mark_orchestrator_running(session: Optional[Session] = None) -> None:
    """Mark orchestrator as running in database.

    Args:
        session: Database session (optional)
    """
    pid = os.getpid()
    update_orchestrator_status(status="running", pid=pid, session=session)
    logger.info("orchestrator_marked_running", pid=pid)


async def mark_orchestrator_stopped_async() -> None:
    """Mark orchestrator as stopped (async version for cleanup callbacks)."""
    try:
        mark_orchestrator_stopped()
    except Exception as e:
        logger.error("failed_to_mark_stopped_async", error=str(e), exc_info=True)


def update_system_stats(
    total_tasks_processed: Optional[int] = None,
    total_tasks_pending: Optional[int] = None,
    active_agents_count: Optional[int] = None,
    session: Optional[Session] = None
) -> None:
    """Update system statistics in database.

    Args:
        total_tasks_processed: Total tasks completed
        total_tasks_pending: Total tasks waiting
        active_agents_count: Number of active agents
        session: Database session (optional)
    """
    should_close_session = False

    try:
        if session is None:
            session = get_db()
            should_close_session = True

        state = get_or_create_system_state(session)

        if total_tasks_processed is not None:
            state.total_tasks_processed = total_tasks_processed
        if total_tasks_pending is not None:
            state.total_tasks_pending = total_tasks_pending
        if active_agents_count is not None:
            state.active_agents_count = active_agents_count

        session.commit()
        logger.debug("updated_system_stats")

    except Exception as e:
        logger.error("failed_to_update_system_stats", error=str(e), exc_info=True)
        if session:
            session.rollback()
        raise
    finally:
        if should_close_session and session:
            session.close()
