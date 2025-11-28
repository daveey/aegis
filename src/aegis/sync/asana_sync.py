"""Asana synchronization utilities for Aegis.

This module provides functions to sync Asana projects and tasks into the local database.
It handles incremental updates by tracking last_synced_at timestamps.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from aegis.asana.client import AsanaClient
from aegis.config import Settings
from aegis.database.models import Project, SystemState, Task
from aegis.database.session import get_db_session

logger = structlog.get_logger()


async def sync_portfolio_projects(
    client: AsanaClient,
    portfolio_gid: str,
    workspace_gid: str,
    session: Session | None = None,
) -> list[Project]:
    """Sync all projects from a portfolio into the database.

    Args:
        client: AsanaClient instance
        portfolio_gid: GID of the portfolio to sync
        workspace_gid: GID of the workspace
        session: Optional Session (creates new if None)

    Returns:
        List of synced Project objects
    """
    logger.info("sync_portfolio_projects_started", portfolio_gid=portfolio_gid)

    # Fetch projects from Asana
    asana_projects = await client.get_projects_from_portfolio(portfolio_gid)
    logger.info("fetched_asana_projects", count=len(asana_projects))

    # Create session if not provided
    should_close_session = session is None
    if session is None:
        session_ctx = get_db_session()
        session = session_ctx.__enter__()

    try:
        synced_projects = []
        now = datetime.now(UTC)

        for asana_project in asana_projects:
            # Check if project exists
            db_project = session.query(Project).filter_by(asana_gid=asana_project.gid).first()

            if db_project:
                # Update existing project
                db_project.name = asana_project.name
                db_project.notes = asana_project.notes
                db_project.archived = asana_project.archived
                db_project.last_synced_at = now
                logger.info(
                    "updated_project",
                    project_gid=asana_project.gid,
                    project_name=asana_project.name,
                )
            else:
                # Create new project
                db_project = Project(
                    asana_gid=asana_project.gid,
                    name=asana_project.name,
                    notes=asana_project.notes,
                    portfolio_gid=portfolio_gid,
                    workspace_gid=workspace_gid,
                    archived=asana_project.archived,
                    last_synced_at=now,
                )
                session.add(db_project)
                logger.info(
                    "created_project",
                    project_gid=asana_project.gid,
                    project_name=asana_project.name,
                )

            synced_projects.append(db_project)

        # Update system state
        system_state = session.query(SystemState).filter_by(id=1).first()

        if system_state:
            system_state.last_portfolio_sync_at = now
        else:
            system_state = SystemState(
                id=1,
                last_portfolio_sync_at=now,
            )
            session.add(system_state)

        session.commit()
        logger.info("sync_portfolio_projects_completed", count=len(synced_projects))

        return synced_projects

    except Exception as e:
        session.rollback()
        logger.error("sync_portfolio_projects_failed", error=str(e))
        raise
    finally:
        if should_close_session:
            session_ctx.__exit__(None, None, None)


async def sync_project_tasks(
    client: AsanaClient,
    project: Project,
    session: Session | None = None,
) -> list[Task]:
    """Sync all tasks for a project into the database.

    Args:
        client: AsanaClient instance
        project: Project object from database
        session: Optional Session (creates new if None)

    Returns:
        List of synced Task objects
    """
    logger.info("sync_project_tasks_started", project_gid=project.asana_gid, project_name=project.name)

    # Fetch tasks from Asana
    asana_tasks = await client.get_tasks_from_project(project.asana_gid, assigned_only=False)
    logger.info("fetched_asana_tasks", project_gid=project.asana_gid, count=len(asana_tasks))

    # Create session if not provided
    should_close_session = session is None
    if session is None:
        session_ctx = get_db_session()
        session = session_ctx.__enter__()

    try:
        synced_tasks = []
        now = datetime.now(UTC)

        for asana_task in asana_tasks:
            # Check if task exists
            db_task = session.query(Task).filter_by(asana_gid=asana_task.gid).first()

            if db_task:
                # Update existing task
                db_task.name = asana_task.name
                db_task.description = asana_task.notes
                db_task.html_notes = asana_task.html_notes
                db_task.completed = asana_task.completed
                db_task.completed_at = asana_task.completed_at
                db_task.due_on = asana_task.due_on
                db_task.due_at = asana_task.due_at
                db_task.modified_at = asana_task.modified_at
                db_task.last_synced_at = now

                # Update assignee info
                if asana_task.assignee:
                    db_task.assignee_gid = asana_task.assignee.gid
                    db_task.assignee_name = asana_task.assignee.name
                    # Check if assigned to Aegis (you may need to adjust this check)
                    db_task.assigned_to_aegis = asana_task.is_assigned_to_aegis
                else:
                    db_task.assignee_gid = None
                    db_task.assignee_name = None
                    db_task.assigned_to_aegis = False

                # Update metadata
                db_task.asana_permalink_url = asana_task.permalink_url
                db_task.tags = [{"name": tag.get("name")} for tag in asana_task.tags]
                db_task.custom_fields = {
                    field.get("name"): field.get("display_value")
                    for field in asana_task.custom_fields
                    if field.get("name")
                }
                db_task.num_subtasks = asana_task.num_subtasks

                logger.info(
                    "updated_task",
                    task_gid=asana_task.gid,
                    task_name=asana_task.name,
                )
            else:
                # Create new task
                db_task = Task(
                    asana_gid=asana_task.gid,
                    project_id=project.id,
                    name=asana_task.name,
                    description=asana_task.notes,
                    html_notes=asana_task.html_notes,
                    completed=asana_task.completed,
                    completed_at=asana_task.completed_at,
                    due_on=asana_task.due_on,
                    due_at=asana_task.due_at,
                    modified_at=asana_task.modified_at,
                    last_synced_at=now,
                    assignee_gid=asana_task.assignee.gid if asana_task.assignee else None,
                    assignee_name=asana_task.assignee.name if asana_task.assignee else None,
                    assigned_to_aegis=asana_task.is_assigned_to_aegis,
                    asana_permalink_url=asana_task.permalink_url,
                    tags=[{"name": tag.get("name")} for tag in asana_task.tags],
                    custom_fields={
                        field.get("name"): field.get("display_value")
                        for field in asana_task.custom_fields
                        if field.get("name")
                    },
                    num_subtasks=asana_task.num_subtasks,
                )
                session.add(db_task)
                logger.info(
                    "created_task",
                    task_gid=asana_task.gid,
                    task_name=asana_task.name,
                )

            synced_tasks.append(db_task)

        # Update project's last_synced_at
        project.last_synced_at = now

        # Update system state
        system_state = session.query(SystemState).filter_by(id=1).first()

        if system_state:
            system_state.last_tasks_sync_at = now
        else:
            system_state = SystemState(
                id=1,
                last_tasks_sync_at=now,
            )
            session.add(system_state)

        session.commit()
        logger.info("sync_project_tasks_completed", project_gid=project.asana_gid, count=len(synced_tasks))

        return synced_tasks

    except Exception as e:
        session.rollback()
        logger.error("sync_project_tasks_failed", error=str(e), project_gid=project.asana_gid)
        raise
    finally:
        if should_close_session:
            session_ctx.__exit__(None, None, None)


async def sync_all(
    portfolio_gid: str | None = None,
    workspace_gid: str | None = None,
) -> tuple[list[Project], list[Task]]:
    """Sync all projects and tasks from the configured portfolio.

    Args:
        portfolio_gid: Portfolio GID (uses config if None)
        workspace_gid: Workspace GID (uses config if None)

    Returns:
        Tuple of (synced_projects, synced_tasks)
    """
    config = Settings()
    portfolio_gid = portfolio_gid or config.asana_portfolio_gid
    workspace_gid = workspace_gid or config.asana_workspace_gid

    client = AsanaClient(config.asana_access_token)

    logger.info("sync_all_started", portfolio_gid=portfolio_gid)

    # Sync projects and tasks using a single session
    with get_db_session() as session:
        projects = await sync_portfolio_projects(
            client=client,
            portfolio_gid=portfolio_gid,
            workspace_gid=workspace_gid,
            session=session,
        )

        # Sync tasks for each project
        all_tasks = []
        for project in projects:
            if not project.archived:
                tasks = await sync_project_tasks(
                    client=client,
                    project=project,
                    session=session,
                )
                all_tasks.extend(tasks)

    logger.info("sync_all_completed", project_count=len(projects), task_count=len(all_tasks))
    return projects, all_tasks
