"""Worker Agent - The Builder."""

import subprocess
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject
from aegis.infrastructure.worktree_manager import WorktreeManager
from aegis.utils.asana_utils import format_asana_resource

logger = structlog.get_logger(__name__)


class WorkerAgent(BaseAgent):
    """Worker Agent executes implementation plans.

    Responsibilities:
    - Implement code according to Planner's design
    - Write and run tests
    - Follow project conventions
    - Rebase on main before handoff
    - Prepare code for review
    """

    def __init__(self, *args, worktree_manager: WorktreeManager, **kwargs):
        """Initialize Worker Agent.

        Args:
            worktree_manager: WorktreeManager instance
        """
        super().__init__(*args, **kwargs)
        self.worktree_manager = worktree_manager

    @property
    def name(self) -> str:
        """Agent name."""
        return "worker_agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "🔨"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.TASK

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for implementation.

        Args:
            task: AsanaTask to implement

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "worker.prompt.txt"

        if not prompt_file.exists():
            logger.warning("worker_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Implement the task according to the plan."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8").replace("{task_id}", task.gid)

        # Get plan from task comments (should be posted by Planner)
        # For now, use task description as fallback
        plan = task.notes or "No plan provided - use best judgment"

        # Load user preferences
        prefs_file = self.repo_root / "user_preferences.md"
        user_preferences = ""
        if prefs_file.exists():
            user_preferences = prefs_file.read_text(encoding="utf-8")

        # Add task context
        context = f"""
# Task to Implement

**Task Name**: {task.name}

**Implementation Plan**:
{plan}

**Repository**: {self.repo_root}
**Worktree**: {self.worktree_manager.get_worktree_path(task.gid)}
**Branch**: feat/task-{task.gid}

---

# User Preferences

{user_preferences}

---

{base_prompt}

---

# Your Implementation

Follow the plan step-by-step. Test as you go. Remember to rebase on main before finishing.
"""

        return context

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute implementation.

        Args:
            target: AsanaTask to implement
            **kwargs: Additional arguments

        Returns:
            AgentResult with implementation status
        """
        if not isinstance(target, AsanaTask):
             return AgentResult(success=False, error="WorkerAgent only supports Tasks")

        task = target
        interactive = kwargs.get("interactive", False)
        logger.info("worker_start", task=format_asana_resource(task), interactive=interactive)

        worktree_path = None

        try:
            # Setup worktree
            logger.info("setting_up_worktree", task=format_asana_resource(task))
            worktree_path = self.worktree_manager.setup_worktree(task.gid)

            # Generate and run prompt IN THE WORKTREE
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(
                prompt,
                cwd=worktree_path,
                timeout=1800,  # 30 minute timeout for implementation
                interactive=interactive,
            )

            if interactive:
                return AgentResult(
                    success=True,
                    summary="Interactive session completed",
                    details=["Ran interactively"],
                )

            if returncode != 0:
                logger.error("worker_failed", task=format_asana_resource(task), stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Implementation failed during execution",
                )

            # Rebase on main
            logger.info("rebasing_on_main", task=format_asana_resource(task))
            await self._rebase_on_main(task.gid, worktree_path)

            # Extract implementation summary
            files_created, files_modified, tests_status = self._parse_implementation_summary(stdout)

            logger.info(
                "worker_complete",
                task=format_asana_resource(task),
                files_created=len(files_created),
                files_modified=len(files_modified),
            )

            if tests_status == "Blocker Encountered":
                # Extract blocker details
                import re
                blocker_match = re.search(
                    r"## BLOCKER ENCOUNTERED\s*(.+?)(?:$)",
                    stdout,
                    re.IGNORECASE | re.DOTALL,
                )
                blocker_details = blocker_match.group(1).strip() if blocker_match else "No details provided"

                return AgentResult(
                    success=False,
                    next_agent="Triage",
                    next_section="Clarification Needed",
                    summary="Implementation blocked",
                    details=["Blocker encountered:", blocker_details[:500]], # Truncate if too long
                    clear_session_id=False,
                    assignee="me",
                )

            details = []
            if files_created:
                details.append(f"Created {len(files_created)} file(s)")
            if files_modified:
                details.append(f"Modified {len(files_modified)} file(s)")
            details.append(f"Tests: {tests_status}")
            details.append("Rebased on main")

            return AgentResult(
                success=True,
                next_agent="Reviewer",
                next_section="Review",
                summary="Implementation complete and ready for review",
                details=details,
                clear_session_id=True,  # Reviewer gets fresh session
            )

        except Exception as e:
            logger.error("worker_error", task=format_asana_resource(task), error=str(e))

            # Don't cleanup worktree on error - may need for debugging
            return AgentResult(
                success=False,
                error=str(e),
                summary="Implementation encountered an error",
            )

    async def _rebase_on_main(self, task_gid: str, worktree_path: Path) -> None:
        """Rebase feature branch on main.

        Args:
            task_gid: Task GID
            worktree_path: Path to worktree

        Raises:
            Exception: If rebase fails
        """
        try:
            # Fetch latest main
            subprocess.run(
                ["git", "fetch", "origin", "main"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
            )

            # Merge main into feature branch
            result = subprocess.run(
                ["git", "merge", "origin/main"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    logger.error(
                        "rebase_conflict",
                        task_gid=task_gid,
                        stderr=result.stderr,
                    )
                    raise Exception(f"Merge conflict detected: {result.stderr}")
                else:
                    raise Exception(f"Merge failed: {result.stderr}")

            logger.info("rebase_complete", task_gid=task_gid)

        except subprocess.CalledProcessError as e:
            logger.error("rebase_failed", task_gid=task_gid, error=str(e))
            raise

    def _parse_implementation_summary(self, output: str) -> tuple[list[str], list[str], str]:
        """Parse implementation summary from output.

        Args:
            output: Claude Code stdout

        Returns:
            Tuple of (files_created, files_modified, tests_status)
        """
        import re

        files_created = []
        files_modified = []
        tests_status = "Unknown"

        # Find "Files Created" section
        created_match = re.search(
            r"\*\*Files Created\*\*:\s*(.+?)(?:\*\*|$)",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        if created_match:
            created_text = created_match.group(1)
            files_created = [
                line.strip().split()[0]
                for line in created_text.split("\n")
                if line.strip().startswith("-") or line.strip().startswith("`")
            ]

        # Find "Files Modified" section
        modified_match = re.search(
            r"\*\*Files Modified\*\*:\s*(.+?)(?:\*\*|$)",
            output,
            re.IGNORECASE | re.DOTALL,
        )
        if modified_match:
            modified_text = modified_match.group(1)
            files_modified = [
                line.strip().split()[0]
                for line in modified_text.split("\n")
                if line.strip().startswith("-") or line.strip().startswith("`")
            ]

        # Check tests status
        if "passed" in output.lower():
            tests_status = "Passed"
        elif "failed" in output.lower():
            tests_status = "Some failures"
        elif "Tests Run" in output or "pytest" in output:
            tests_status = "Run"

        # Check for blocker
        if "## BLOCKER ENCOUNTERED" in output:
            return [], [], "Blocker Encountered"

        return files_created, files_modified, tests_status


import click
import asyncio
from aegis.config import get_settings
from aegis.asana.client import AsanaClient
from aegis.infrastructure.asana_service import AsanaService
from aegis.database.session import get_db_session
from aegis.database.master_models import WorkQueueItem, AgentState
from datetime import datetime

@click.command()
@click.option("--agent-id", required=True, help="Unique ID for this agent instance")
def main(agent_id: str):
    """Run the Worker Agent process."""
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

    async def run_loop():
        settings = get_settings()
        client = AsanaClient(settings.asana_access_token)
        asana_service = AsanaService(client)
        worktree_manager = WorktreeManager(Path.cwd()) # Assuming running from repo root

        agent = WorkerAgent(
            asana_service=asana_service,
            repo_root=Path.cwd(),
            worktree_manager=worktree_manager,
            agent_id=agent_id
        )

        logger.info("worker_agent_started", agent_id=agent_id)

        while True:
            try:
                # Poll for assigned work
                work_item = None
                with get_db_session(project_gid=None) as session:
                    # Check if we have been assigned work
                    work_item = session.query(WorkQueueItem).filter(
                        WorkQueueItem.assigned_to_agent_id == agent_id,
                        WorkQueueItem.status == "assigned"
                    ).first()

                    if work_item:
                        # Refresh to detach from session if needed, or just keep ID
                        work_item_id = work_item.id
                        resource_id = work_item.resource_id
                        resource_type = work_item.resource_type

                if work_item:
                    logger.info("work_received", work_item_id=work_item_id, resource_id=resource_id)

                    # Fetch target
                    target = None
                    fetch_success = True
                    try:
                        if resource_type == "task":
                            target = await asana_service.get_task(resource_id)
                        elif resource_type == "project":
                            # Worker usually works on tasks, but handle project if needed
                            # target = await asana_service.get_project(resource_id)
                            pass
                    except Exception as e:
                        logger.error("fetch_target_failed", resource_id=resource_id, error=str(e))
                        fetch_success = False

                    if fetch_success and target:
                        # Execute
                        try:
                            result = await agent.execute(target)
                            success = result.success
                        except Exception as e:
                            logger.error("execution_failed", resource_id=resource_id, error=str(e))
                            success = False
                    else:
                        if not fetch_success:
                             logger.error("target_fetch_failed", resource_id=resource_id)
                        else:
                             logger.error("target_not_found", resource_id=resource_id)
                        success = False

                    # Update status
                    with get_db_session(project_gid=None) as session:
                        # Update Work Item
                        session.query(WorkQueueItem).filter(WorkQueueItem.id == work_item_id).update({
                            "status": "completed" if success else "failed",
                            "completed_at": datetime.utcnow()
                        })

                        # Update Agent State
                        session.query(AgentState).filter(AgentState.agent_id == agent_id).update({
                            "status": "idle",
                            "current_work_item_id": None
                        })
                        session.commit()

                    logger.info("work_completed", work_item_id=work_item_id, success=success)

                else:
                    # Heartbeat
                    with get_db_session(project_gid=None) as session:
                        session.query(AgentState).filter(AgentState.agent_id == agent_id).update({
                            "last_heartbeat_at": datetime.utcnow()
                        })
                        session.commit()

                    await asyncio.sleep(1.0)

            except Exception as e:
                logger.error("worker_loop_error", error=str(e))
                await asyncio.sleep(5.0)

    asyncio.run(run_loop())

if __name__ == "__main__":
    main()
