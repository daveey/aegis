"""SQLAlchemy models for the Master Process state."""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class WorkQueueItem(Base):
    """Represents a unit of work in the master queue."""

    __tablename__ = "work_queue"

    id = Column(Integer, primary_key=True)

    # Work Definition
    agent_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(String(100), nullable=False) # e.g. Task GID or Project GID
    resource_type = Column(String(50), nullable=False) # 'task' or 'project'

    # Priority and Scheduling
    priority = Column(Integer, default=0, index=True) # Higher is more urgent
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Status
    status = Column(String(50), default="pending", index=True) # pending, assigned, completed, failed
    assigned_to_agent_id = Column(String(100), nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Context
    payload = Column(JSON, default=dict) # Any extra data needed

    __table_args__ = (
        Index("idx_queue_pending", "status", "priority"),
    )


class AgentState(Base):
    """Tracks the state of running agents in the pool."""

    __tablename__ = "agent_pool"

    id = Column(Integer, primary_key=True)

    # Identity
    agent_id = Column(String(100), unique=True, nullable=False)
    agent_type = Column(String(100), nullable=False) # 'worker', 'syncer', etc. (though syncers might be separate)

    # Status
    status = Column(String(50), default="idle", index=True) # idle, busy, offline
    current_work_item_id = Column(Integer, nullable=True)

    # Heartbeat
    last_heartbeat_at = Column(DateTime, nullable=False, default=func.now())

    # Metadata
    pid = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False, default=func.now())
