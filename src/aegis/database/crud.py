"""Database CRUD operations for Aegis core models.

This module provides Create, Read, Update, and Delete operations for the main
database models: Project, Task, and TaskExecution.

All operations use the session context manager pattern and include proper error
handling and structured logging.
"""

from datetime import datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aegis.database.models import Project, Task, TaskExecution
from aegis.database.session import get_db_session

logger = structlog.get_logger(__name__)


# ============================================================================
# Exceptions
# ============================================================================


class NotFoundError(Exception):
    """Raised when a database record is not found."""

    pass


class DuplicateError(Exception):
    """Raised when trying to create a duplicate record."""

    pass


# ============================================================================
# Project CRUD Operations
# ============================================================================


def create_project(
    asana_gid: str,
    name: str,
    portfolio_gid: str,
    workspace_gid: str,
    code_path: str | None = None,
    team_gid: str | None = None,
    asana_permalink_url: str | None = None,
    notes: str | None = None,
    archived: bool = False,
    settings: dict | None = None,
    session: Session | None = None,
) -> Project:
    """Create a new project.

    Args:
        asana_gid: Asana project GID (must be unique)
        name: Project name
        portfolio_gid: Asana portfolio GID
        workspace_gid: Asana workspace GID
        code_path: Path to code repository (optional)
        team_gid: Asana team GID (optional)
        asana_permalink_url: Asana permalink URL (optional)
        notes: Project notes (optional)
        archived: Whether project is archived (default: False)
        settings: Project settings dict (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Created Project instance

    Raises:
        DuplicateError: If a project with this asana_gid already exists
        ValueError: If required fields are missing
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        # Create project instance
        project = Project(
            asana_gid=asana_gid,
            name=name,
            portfolio_gid=portfolio_gid,
            workspace_gid=workspace_gid,
            code_path=code_path,
            team_gid=team_gid,
            asana_permalink_url=asana_permalink_url,
            notes=notes,
            archived=archived,
            settings=settings or {},
        )

        session.add(project)
        session.commit()
        session.refresh(project)

        logger.info(
            "project_created",
            project_id=project.id,
            asana_gid=asana_gid,
            name=name,
        )

        return project

    except IntegrityError as e:
        if session:
            session.rollback()
        logger.error("duplicate_project", asana_gid=asana_gid, error=str(e))
        raise DuplicateError(f"Project with asana_gid '{asana_gid}' already exists")
    except Exception as e:
        if session:
            session.rollback()
        logger.error("project_creation_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_project_by_gid(
    asana_gid: str, session: Session | None = None
) -> Project | None:
    """Get a project by its Asana GID.

    Args:
        asana_gid: Asana project GID
        session: Database session (optional, will create if not provided)

    Returns:
        Project instance or None if not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        project = session.query(Project).filter_by(asana_gid=asana_gid).first()

        if project:
            logger.debug("project_found", asana_gid=asana_gid, project_id=project.id)
        else:
            logger.debug("project_not_found", asana_gid=asana_gid)

        return project

    except Exception as e:
        logger.error("project_fetch_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_all_projects(
    portfolio_gid: str | None = None,
    archived: bool = False,
    session: Session | None = None,
) -> list[Project]:
    """Get all projects, optionally filtered by portfolio and archived status.

    Args:
        portfolio_gid: Filter by portfolio GID (optional)
        archived: Include archived projects (default: False)
        session: Database session (optional, will create if not provided)

    Returns:
        List of Project instances
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        query = session.query(Project)

        if portfolio_gid:
            query = query.filter_by(portfolio_gid=portfolio_gid)

        if not archived:
            query = query.filter_by(archived=False)

        projects = query.order_by(Project.name).all()

        logger.debug(
            "projects_fetched",
            count=len(projects),
            portfolio_gid=portfolio_gid,
            include_archived=archived,
        )

        return projects

    except Exception as e:
        logger.error("projects_fetch_failed", error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def update_project(
    asana_gid: str,
    name: str | None = None,
    code_path: str | None = None,
    notes: str | None = None,
    archived: bool | None = None,
    settings: dict | None = None,
    last_synced_at: datetime | None = None,
    session: Session | None = None,
) -> Project:
    """Update a project's fields.

    Args:
        asana_gid: Asana project GID
        name: New name (optional)
        code_path: New code path (optional)
        notes: New notes (optional)
        archived: New archived status (optional)
        settings: New settings dict (optional)
        last_synced_at: New last synced timestamp (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Updated Project instance

    Raises:
        NotFoundError: If project not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        project = session.query(Project).filter_by(asana_gid=asana_gid).first()

        if not project:
            raise NotFoundError(f"Project with asana_gid '{asana_gid}' not found")

        # Update fields that were provided
        if name is not None:
            project.name = name
        if code_path is not None:
            project.code_path = code_path
        if notes is not None:
            project.notes = notes
        if archived is not None:
            project.archived = archived
        if settings is not None:
            project.settings = settings
        if last_synced_at is not None:
            project.last_synced_at = last_synced_at

        session.commit()
        session.refresh(project)

        logger.info("project_updated", project_id=project.id, asana_gid=asana_gid)

        return project

    except NotFoundError:
        if session:
            session.rollback()
        logger.error("project_not_found_for_update", asana_gid=asana_gid)
        raise
    except Exception as e:
        if session:
            session.rollback()
        logger.error("project_update_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


# ============================================================================
# Task CRUD Operations
# ============================================================================


def create_task(
    asana_gid: str,
    project_id: int,
    name: str,
    description: str | None = None,
    html_notes: str | None = None,
    completed: bool = False,
    completed_at: datetime | None = None,
    due_on: str | None = None,
    due_at: datetime | None = None,
    assignee_gid: str | None = None,
    assignee_name: str | None = None,
    assigned_to_aegis: bool = False,
    parent_task_id: int | None = None,
    num_subtasks: int = 0,
    asana_permalink_url: str | None = None,
    tags: list | None = None,
    custom_fields: dict | None = None,
    modified_at: datetime | None = None,
    session: Session | None = None,
) -> Task:
    """Create a new task.

    Args:
        asana_gid: Asana task GID (must be unique)
        project_id: Database ID of parent project
        name: Task name
        description: Task description (optional)
        html_notes: Task notes as HTML (optional)
        completed: Task completion status (default: False)
        completed_at: Completion timestamp (optional)
        due_on: Due date as string YYYY-MM-DD (optional)
        due_at: Due datetime (optional)
        assignee_gid: Asana assignee GID (optional)
        assignee_name: Assignee name (optional)
        assigned_to_aegis: Whether assigned to Aegis (default: False)
        parent_task_id: Parent task database ID (optional)
        num_subtasks: Number of subtasks (default: 0)
        asana_permalink_url: Asana permalink URL (optional)
        tags: List of tags (optional)
        custom_fields: Custom fields dict (optional)
        modified_at: Last modified timestamp (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Created Task instance

    Raises:
        DuplicateError: If a task with this asana_gid already exists
        ValueError: If required fields are missing
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        # Create task instance
        task = Task(
            asana_gid=asana_gid,
            project_id=project_id,
            name=name,
            description=description,
            html_notes=html_notes,
            completed=completed,
            completed_at=completed_at,
            due_on=due_on,
            due_at=due_at,
            assignee_gid=assignee_gid,
            assignee_name=assignee_name,
            assigned_to_aegis=assigned_to_aegis,
            parent_task_id=parent_task_id,
            num_subtasks=num_subtasks,
            asana_permalink_url=asana_permalink_url,
            tags=tags or [],
            custom_fields=custom_fields or {},
            modified_at=modified_at,
        )

        session.add(task)
        session.commit()
        session.refresh(task)

        logger.info(
            "task_created",
            task_id=task.id,
            asana_gid=asana_gid,
            name=name,
            project_id=project_id,
        )

        return task

    except IntegrityError as e:
        if session:
            session.rollback()
        logger.error("duplicate_task", asana_gid=asana_gid, error=str(e))
        raise DuplicateError(f"Task with asana_gid '{asana_gid}' already exists")
    except Exception as e:
        if session:
            session.rollback()
        logger.error("task_creation_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_task_by_gid(asana_gid: str, session: Session | None = None) -> Task | None:
    """Get a task by its Asana GID.

    Args:
        asana_gid: Asana task GID
        session: Database session (optional, will create if not provided)

    Returns:
        Task instance or None if not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        task = session.query(Task).filter_by(asana_gid=asana_gid).first()

        if task:
            logger.debug("task_found", asana_gid=asana_gid, task_id=task.id)
        else:
            logger.debug("task_not_found", asana_gid=asana_gid)

        return task

    except Exception as e:
        logger.error("task_fetch_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_tasks_by_project(
    project_id: int,
    assigned_to_aegis: bool | None = None,
    completed: bool | None = None,
    session: Session | None = None,
) -> list[Task]:
    """Get all tasks for a project, with optional filters.

    Args:
        project_id: Database ID of project
        assigned_to_aegis: Filter by assignment to Aegis (optional)
        completed: Filter by completion status (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        List of Task instances
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        query = session.query(Task).filter_by(project_id=project_id)

        if assigned_to_aegis is not None:
            query = query.filter_by(assigned_to_aegis=assigned_to_aegis)

        if completed is not None:
            query = query.filter_by(completed=completed)

        tasks = query.order_by(Task.created_at.desc()).all()

        logger.debug(
            "tasks_fetched_by_project",
            project_id=project_id,
            count=len(tasks),
            assigned_to_aegis=assigned_to_aegis,
            completed=completed,
        )

        return tasks

    except Exception as e:
        logger.error("tasks_fetch_by_project_failed", project_id=project_id, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def update_task(
    asana_gid: str,
    name: str | None = None,
    description: str | None = None,
    html_notes: str | None = None,
    completed: bool | None = None,
    completed_at: datetime | None = None,
    due_on: str | None = None,
    due_at: datetime | None = None,
    assignee_gid: str | None = None,
    assignee_name: str | None = None,
    assigned_to_aegis: bool | None = None,
    num_subtasks: int | None = None,
    tags: list | None = None,
    custom_fields: dict | None = None,
    modified_at: datetime | None = None,
    last_synced_at: datetime | None = None,
    session: Session | None = None,
) -> Task:
    """Update a task's fields.

    Args:
        asana_gid: Asana task GID
        name: New name (optional)
        description: New description (optional)
        html_notes: New HTML notes (optional)
        completed: New completion status (optional)
        completed_at: New completion timestamp (optional)
        due_on: New due date string (optional)
        due_at: New due datetime (optional)
        assignee_gid: New assignee GID (optional)
        assignee_name: New assignee name (optional)
        assigned_to_aegis: New assignment status (optional)
        num_subtasks: New subtask count (optional)
        tags: New tags list (optional)
        custom_fields: New custom fields dict (optional)
        modified_at: New modified timestamp (optional)
        last_synced_at: New last synced timestamp (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Updated Task instance

    Raises:
        NotFoundError: If task not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        task = session.query(Task).filter_by(asana_gid=asana_gid).first()

        if not task:
            raise NotFoundError(f"Task with asana_gid '{asana_gid}' not found")

        # Update fields that were provided
        if name is not None:
            task.name = name
        if description is not None:
            task.description = description
        if html_notes is not None:
            task.html_notes = html_notes
        if completed is not None:
            task.completed = completed
        if completed_at is not None:
            task.completed_at = completed_at
        if due_on is not None:
            task.due_on = due_on
        if due_at is not None:
            task.due_at = due_at
        if assignee_gid is not None:
            task.assignee_gid = assignee_gid
        if assignee_name is not None:
            task.assignee_name = assignee_name
        if assigned_to_aegis is not None:
            task.assigned_to_aegis = assigned_to_aegis
        if num_subtasks is not None:
            task.num_subtasks = num_subtasks
        if tags is not None:
            task.tags = tags
        if custom_fields is not None:
            task.custom_fields = custom_fields
        if modified_at is not None:
            task.modified_at = modified_at
        if last_synced_at is not None:
            task.last_synced_at = last_synced_at

        session.commit()
        session.refresh(task)

        logger.info("task_updated", task_id=task.id, asana_gid=asana_gid)

        return task

    except NotFoundError:
        if session:
            session.rollback()
        logger.error("task_not_found_for_update", asana_gid=asana_gid)
        raise
    except Exception as e:
        if session:
            session.rollback()
        logger.error("task_update_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def mark_task_complete(
    asana_gid: str,
    completed_at: datetime | None = None,
    session: Session | None = None,
) -> Task:
    """Mark a task as completed.

    Args:
        asana_gid: Asana task GID
        completed_at: Completion timestamp (default: now)
        session: Database session (optional, will create if not provided)

    Returns:
        Updated Task instance

    Raises:
        NotFoundError: If task not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        task = session.query(Task).filter_by(asana_gid=asana_gid).first()

        if not task:
            raise NotFoundError(f"Task with asana_gid '{asana_gid}' not found")

        task.completed = True
        task.completed_at = completed_at or datetime.utcnow()

        session.commit()
        session.refresh(task)

        logger.info(
            "task_marked_complete",
            task_id=task.id,
            asana_gid=asana_gid,
            completed_at=task.completed_at,
        )

        return task

    except NotFoundError:
        if session:
            session.rollback()
        logger.error("task_not_found_for_completion", asana_gid=asana_gid)
        raise
    except Exception as e:
        if session:
            session.rollback()
        logger.error("task_completion_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


# ============================================================================
# TaskExecution CRUD Operations
# ============================================================================


def create_task_execution(
    task_id: int | None = None,
    status: str = "pending",
    agent_type: str | None = None,
    started_at: datetime | None = None,
    context: dict | None = None,
    execution_metadata: dict | None = None,
    session: Session | None = None,
) -> TaskExecution:
    """Create a new task execution record.

    Args:
        task_id: Database ID of task (optional until task sync implemented)
        status: Execution status (default: 'pending')
        agent_type: Type of agent executing task (optional)
        started_at: Start timestamp (default: now)
        context: Execution context dict (optional)
        execution_metadata: Execution metadata dict (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Created TaskExecution instance
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        # Create task execution instance
        execution = TaskExecution(
            task_id=task_id,
            status=status,
            agent_type=agent_type,
            started_at=started_at or datetime.utcnow(),
            context=context or {},
            execution_metadata=execution_metadata or {},
        )

        session.add(execution)
        session.commit()
        session.refresh(execution)

        logger.info(
            "task_execution_created",
            execution_id=execution.id,
            task_id=task_id,
            status=status,
        )

        return execution

    except Exception as e:
        if session:
            session.rollback()
        logger.error("task_execution_creation_failed", task_id=task_id, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_task_executions_by_task(
    task_id: int,
    status: str | None = None,
    session: Session | None = None,
) -> list[TaskExecution]:
    """Get all executions for a task, optionally filtered by status.

    Args:
        task_id: Database ID of task
        status: Filter by status (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        List of TaskExecution instances
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        query = session.query(TaskExecution).filter_by(task_id=task_id)

        if status:
            query = query.filter_by(status=status)

        executions = query.order_by(TaskExecution.started_at.desc()).all()

        logger.debug(
            "task_executions_fetched",
            task_id=task_id,
            count=len(executions),
            status=status,
        )

        return executions

    except Exception as e:
        logger.error("task_executions_fetch_failed", task_id=task_id, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def update_task_execution_status(
    execution_id: int,
    status: str,
    completed_at: datetime | None = None,
    success: bool | None = None,
    error_message: str | None = None,
    output: str | None = None,
    duration_seconds: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    session: Session | None = None,
) -> TaskExecution:
    """Update a task execution's status and related fields.

    Args:
        execution_id: Database ID of task execution
        status: New status
        completed_at: Completion timestamp (optional)
        success: Success flag (optional)
        error_message: Error message if failed (optional)
        output: Execution output (optional)
        duration_seconds: Execution duration (optional)
        input_tokens: Number of input tokens used (optional)
        output_tokens: Number of output tokens used (optional)
        cost_usd: Cost in USD (optional)
        session: Database session (optional, will create if not provided)

    Returns:
        Updated TaskExecution instance

    Raises:
        NotFoundError: If execution not found
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        execution = session.query(TaskExecution).filter_by(id=execution_id).first()

        if not execution:
            raise NotFoundError(f"TaskExecution with id {execution_id} not found")

        # Update status
        execution.status = status

        # Update optional fields
        if completed_at is not None:
            execution.completed_at = completed_at
        if success is not None:
            execution.success = success
        if error_message is not None:
            execution.error_message = error_message
        if output is not None:
            execution.output = output
        if duration_seconds is not None:
            execution.duration_seconds = duration_seconds
        if input_tokens is not None:
            execution.input_tokens = input_tokens
        if output_tokens is not None:
            execution.output_tokens = output_tokens
        if cost_usd is not None:
            execution.cost_usd = cost_usd

        session.commit()
        session.refresh(execution)

        logger.info(
            "task_execution_updated",
            execution_id=execution_id,
            status=status,
            success=success,
        )

        return execution

    except NotFoundError:
        if session:
            session.rollback()
        logger.error("task_execution_not_found_for_update", execution_id=execution_id)
        raise
    except Exception as e:
        if session:
            session.rollback()
        logger.error("task_execution_update_failed", execution_id=execution_id, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


# ============================================================================
# Helper Functions
# ============================================================================


def get_or_create_project(
    asana_gid: str,
    name: str,
    portfolio_gid: str,
    workspace_gid: str,
    session: Session | None = None,
) -> tuple[Project, bool]:
    """Get existing project or create if not exists.

    Args:
        asana_gid: Asana project GID
        name: Project name
        portfolio_gid: Asana portfolio GID
        workspace_gid: Asana workspace GID
        session: Database session (optional, will create if not provided)

    Returns:
        Tuple of (Project instance, created flag)
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        # Try to get existing project
        project = session.query(Project).filter_by(asana_gid=asana_gid).first()

        if project:
            logger.debug("project_already_exists", asana_gid=asana_gid)
            return (project, False)

        # Create new project
        project = Project(
            asana_gid=asana_gid,
            name=name,
            portfolio_gid=portfolio_gid,
            workspace_gid=workspace_gid,
        )

        session.add(project)
        session.commit()
        session.refresh(project)

        logger.info("project_created_via_get_or_create", asana_gid=asana_gid)

        return (project, True)

    except Exception as e:
        if session:
            session.rollback()
        logger.error("get_or_create_project_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()


def get_or_create_task(
    asana_gid: str,
    project_id: int,
    name: str,
    session: Session | None = None,
) -> tuple[Task, bool]:
    """Get existing task or create if not exists.

    Args:
        asana_gid: Asana task GID
        project_id: Database ID of parent project
        name: Task name
        session: Database session (optional, will create if not provided)

    Returns:
        Tuple of (Task instance, created flag)
    """
    should_close_session = False

    try:
        if session is None:
            session = next(get_db_session())
            should_close_session = True

        # Try to get existing task
        task = session.query(Task).filter_by(asana_gid=asana_gid).first()

        if task:
            logger.debug("task_already_exists", asana_gid=asana_gid)
            return (task, False)

        # Create new task
        task = Task(
            asana_gid=asana_gid,
            project_id=project_id,
            name=name,
        )

        session.add(task)
        session.commit()
        session.refresh(task)

        logger.info("task_created_via_get_or_create", asana_gid=asana_gid)

        return (task, True)

    except Exception as e:
        if session:
            session.rollback()
        logger.error("get_or_create_task_failed", asana_gid=asana_gid, error=str(e))
        raise
    finally:
        if should_close_session and session:
            session.close()
