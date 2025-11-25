"""SQLAlchemy database models for Aegis."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class Project(Base, TimestampMixin):
    """Tracks Asana projects that Aegis monitors."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    asana_gid = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code_path = Column(Text)
    portfolio_gid = Column(String(50), nullable=False, index=True)
    workspace_gid = Column(String(50), nullable=False)
    team_gid = Column(String(50))

    # Metadata
    asana_permalink_url = Column(Text)
    notes = Column(Text)
    archived = Column(Boolean, default=False)

    # Tracking
    last_synced_at = Column(DateTime)

    # Settings
    settings = Column(JSON, default=dict)

    # Relationships
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Task(Base, TimestampMixin):
    """Tracks all Asana tasks that Aegis processes."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    asana_gid = Column(String(50), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))

    # Task Details
    name = Column(String(500), nullable=False)
    description = Column(Text)
    html_notes = Column(Text)

    # Status
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    due_on = Column(String(50))  # Date as string YYYY-MM-DD
    due_at = Column(DateTime)

    # Assignment
    assignee_gid = Column(String(50))
    assignee_name = Column(String(255))
    assigned_to_aegis = Column(Boolean, default=False, index=True)

    # Hierarchy
    parent_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    num_subtasks = Column(Integer, default=0)

    # Metadata
    asana_permalink_url = Column(Text)
    tags = Column(JSON, default=list)
    custom_fields = Column(JSON, default=dict)

    # Tracking
    last_synced_at = Column(DateTime)
    modified_at = Column(DateTime)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    executions = relationship(
        "TaskExecution", back_populates="task", cascade="all, delete-orphan"
    )
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    parent = relationship("Task", remote_side=[id], backref="subtasks")

    __table_args__ = (
        Index("idx_tasks_project", "project_id"),
        Index("idx_tasks_assigned", "assigned_to_aegis", "completed"),
    )


class TaskExecution(Base, TimestampMixin):
    """Tracks each time Aegis attempts to process a task."""

    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Execution Details
    status = Column(
        String(50), nullable=False
    )  # 'pending', 'in_progress', 'completed', 'failed', 'blocked'
    agent_type = Column(String(100))

    # Timing
    started_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)

    # Results
    success = Column(Boolean)
    error_message = Column(Text)
    output = Column(Text)

    # Resources
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Numeric(10, 6))

    # Context
    context = Column(JSON, default=dict)
    execution_metadata = Column(JSON, default=dict)

    # Relationships
    task = relationship("Task", back_populates="executions")
    events = relationship(
        "AgentEvent", back_populates="task_execution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_executions_task", "task_id"),
        Index("idx_executions_status", "status"),
    )


class Agent(Base, TimestampMixin):
    """Tracks agent instances and their lifecycle."""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)

    # Agent Identity
    agent_type = Column(String(100), nullable=False, index=True)
    agent_id = Column(String(100), unique=True, nullable=False)

    # Status
    status = Column(
        String(50), nullable=False, index=True
    )  # 'idle', 'busy', 'stopped', 'error'
    current_task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"))

    # Performance
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    total_execution_time_seconds = Column(Integer, default=0)
    total_tokens_used = Column(Integer, default=0)
    total_cost_usd = Column(Numeric(10, 6), default=Decimal("0"))

    # Lifecycle
    started_at = Column(DateTime)
    stopped_at = Column(DateTime)
    last_active_at = Column(DateTime)

    # Configuration
    config = Column(JSON, default=dict)

    # Relationships
    events = relationship("AgentEvent", back_populates="agent", cascade="all, delete-orphan")


class AgentEvent(Base):
    """Detailed event log for debugging and analysis."""

    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    task_execution_id = Column(Integer, ForeignKey("task_executions.id", ondelete="SET NULL"))

    # Event Details
    event_type = Column(String(100), nullable=False, index=True)
    message = Column(Text)
    level = Column(String(20), default="INFO")  # 'DEBUG', 'INFO', 'WARNING', 'ERROR'

    # Context
    data = Column(JSON, default=dict)

    # Timing
    occurred_at = Column(DateTime, nullable=False, default=func.now())

    # Relationships
    agent = relationship("Agent", back_populates="events")
    task_execution = relationship("TaskExecution", back_populates="events")

    __table_args__ = (
        Index("idx_events_agent_occurred", "agent_id", "occurred_at"),
        Index("idx_events_execution", "task_execution_id"),
    )


class Comment(Base):
    """Tracks comments/communications on tasks."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    asana_gid = Column(String(50), unique=True, nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Comment Details
    text = Column(Text, nullable=False)
    created_by_gid = Column(String(50))
    created_by_name = Column(String(255))

    # Metadata
    is_from_aegis = Column(Boolean, default=False)
    comment_type = Column(String(50))  # 'response', 'question', 'status_update', 'error'

    # Timing
    created_at = Column(DateTime, nullable=False)

    # Relationships
    task = relationship("Task", back_populates="comments")

    __table_args__ = (Index("idx_comments_task_created", "task_id", "created_at"),)


class PromptTemplate(Base, TimestampMixin):
    """Versioned prompt storage for agent instructions."""

    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True)

    # Template Identity
    name = Column(String(100), nullable=False)
    agent_type = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1)

    # Content
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text, nullable=False)

    # Status
    active = Column(Boolean, default=True)

    # Metadata
    description = Column(Text)
    tags = Column(JSON, default=list)
    variables = Column(JSON, default=list)  # List of template variables

    # Performance Tracking
    usage_count = Column(Integer, default=0)
    success_rate = Column(Numeric(5, 4))
    avg_tokens_used = Column(Integer)

    # Versioning
    created_by = Column(String(255))

    __table_args__ = (
        Index("idx_prompts_active", "agent_type", "active"),
        Index("idx_prompts_unique", "name", "agent_type", "version", unique=True),
    )


class SystemState(Base):
    """Singleton table for global system state."""

    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, default=1)

    # Orchestrator Status
    orchestrator_status = Column(
        String(50), default="stopped"
    )  # 'running', 'stopped', 'paused'
    orchestrator_pid = Column(Integer)
    orchestrator_started_at = Column(DateTime)

    # Last Sync Info
    last_portfolio_sync_at = Column(DateTime)
    last_tasks_sync_at = Column(DateTime)

    # Statistics
    total_tasks_processed = Column(Integer, default=0)
    total_tasks_pending = Column(Integer, default=0)
    active_agents_count = Column(Integer, default=0)

    # Configuration
    config = Column(JSON, default=dict)

    # Metadata
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (CheckConstraint("id = 1", name="singleton_check"),)


class Webhook(Base):
    """Track webhook deliveries and processing (Future)."""

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True)

    # Webhook Details
    source = Column(String(50), nullable=False)  # 'asana'
    event_type = Column(String(100), nullable=False)
    resource_gid = Column(String(50))
    resource_type = Column(String(50))

    # Payload
    payload = Column(JSON, nullable=False)

    # Processing
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime)
    error_message = Column(Text)

    # Timing
    received_at = Column(DateTime, nullable=False, default=func.now())

    __table_args__ = (
        Index("idx_webhooks_processed_received", "processed", "received_at"),
        Index("idx_webhooks_resource", "resource_type", "resource_gid"),
    )
