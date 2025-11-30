"""Syncer Agent.

Synchronizes state between Asana and the local Project DB.
Also schedules work to the Master Queue based on task state.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import click
import structlog

from aegis.config import get_settings
from aegis.database.session import get_db_session, init_db
from aegis.database.crud import (
    create_task, update_task, get_task_by_gid,
    create_project, update_project, get_project_by_gid
)
from aegis.infrastructure.asana_service import AsanaService
from aegis.agents.base import BaseAgent, AgentTargetType

logger = structlog.get_logger(__name__)


class SyncerAgent(BaseAgent):
    """Synchronizes Asana state to local DB and schedules work."""

    def __init__(self, project_gid: str, **kwargs):
        super().__init__(**kwargs)
        self.project_gid = project_gid
        self.settings = get_settings()

    @property
    def name(self) -> str:
        return "syncer_agent"

    @property
    def status_emoji(self) -> str:
        return "🔄"

    @property
    def target_type(self) -> AgentTargetType:
        return AgentTargetType.PROJECT

    def get_prompt(self, target) -> str:
        return "" # Syncer doesn't use LLM

    async def execute(self, target, **kwargs):
        """Main sync loop."""
        # Note: Syncer usually runs indefinitely, but `execute` implies a single run.
        # We'll use a separate `run_forever` method for the process.
        pass

    async def run_forever(self):
        """Run the sync loop indefinitely."""
        logger.info("syncer_started", project_gid=self.project_gid)

        # Initialize Project DB
        init_db(project_gid=self.project_gid)

        while True:
            try:
                await self._sync_project()
                await asyncio.sleep(self.settings.poll_interval_seconds)
            except Exception as e:
                logger.error("sync_failed", error=str(e), exc_info=True)
                await asyncio.sleep(10)

    async def _sync_project(self):
        """Sync project and tasks from Asana."""
        # 1. Sync Project Details
        asana_project = await self.asana.get_project(self.project_gid)

        with get_db_session(self.project_gid) as session:
            project = get_project_by_gid(self.project_gid, session=session)
            if not project:
                create_project(
                    asana_gid=self.project_gid,
                    name=asana_project.name,
                    portfolio_gid=self.settings.asana_portfolio_gid, # Assumption
                    workspace_gid=asana_project.workspace_gid,
                    session=session
                )
            else:
                update_project(
                    asana_gid=self.project_gid,
                    name=asana_project.name,
                    last_synced_at=datetime.utcnow(),
                    session=session
                )

        # 2. Sync Tasks
        tasks = await self.asana.get_tasks_in_project(self.project_gid)

        for task_data in tasks:
            await self._sync_task(task_data)

    async def _sync_task(self, task_data):
        """Sync a single task and schedule work if needed."""
        task_gid = task_data.gid

        # Fetch full task details (or rely on what we have)
        # Assuming task_data has enough info or we fetch it
        # `get_tasks_in_project` usually returns compact objects.
        # We might need to fetch full details if we want custom fields etc.
        # For efficiency, maybe only fetch full if modified?
        # For now, let's fetch full details to be safe.
        task = await self.asana.get_task(task_gid)

        with get_db_session(self.project_gid) as session:
            db_task = get_task_by_gid(task_gid, session=session)

            # Determine section
            section_name = await self.asana.get_task_section(task_gid)

            if not db_task:
                # Create new task
                # We need project_id.
                project = get_project_by_gid(self.project_gid, session=session)
                if not project:
                    logger.error("project_not_found_in_db", project_gid=self.project_gid)
                    return

                create_task(
                    asana_gid=task_gid,
                    project_id=project.id,
                    name=task.name,
                    completed=task.completed,
                    assignee_gid=task.assignee.gid if task.assignee else None,
                    assignee_name=task.assignee.name if task.assignee else None,
                    session=session
                )
            else:
                # Update task
                update_task(
                    asana_gid=task_gid,
                    name=task.name,
                    completed=task.completed,
                    assignee_gid=task.assignee.gid if task.assignee else None,
                    session=session
                )

            # 3. Schedule Work based on Section
            # Logic from SwarmDispatcher
            if not task.completed:
                await self._schedule_work_for_task(task, section_name)

    async def _schedule_work_for_task(self, task, section_name):
        """Schedule work based on task section."""
        agent_type = None

        if section_name == "Ready Queue":
            agent_type = "triage_agent"
        elif section_name == "Planning":
            agent_type = "planner_agent"
        elif section_name == "In Progress":
            agent_type = "worker_agent"
        elif section_name == "Review":
            agent_type = "reviewer_agent"
        elif section_name == "Documentation":
            agent_type = "documentation_agent"

        if agent_type:
            # Add to Master Queue
            # We use the BaseAgent method which connects to Master DB
            await self.add_work_to_queue(
                agent_type=agent_type,
                resource_id=task.gid,
                resource_type="task",
                priority=5, # Default priority
                payload={"section": section_name}
            )


@click.command()
@click.option("--project-gid", required=True, help="Asana Project GID")
def main(project_gid: str):
    """Run the Syncer Agent."""
    # Setup logging
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
    }
    import logging.config
    logging.config.dictConfig(logging_config)

    settings = get_settings()
    asana_service = AsanaService(settings)

    agent = SyncerAgent(
        project_gid=project_gid,
        asana_service=asana_service,
        repo_root=Path.cwd(), # Or pass via args
        agent_id=f"syncer-{project_gid}"
    )

    asyncio.run(agent.run_forever())


if __name__ == "__main__":
    main()
