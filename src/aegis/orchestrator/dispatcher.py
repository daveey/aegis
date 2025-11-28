"""Swarm dispatcher - section-based state machine orchestrator."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import structlog

from aegis.agents import (
    DocumentationAgent,
    MergerAgent,
    PlannerAgent,
    ReviewerAgent,
    TriageAgent,
    WorkerAgent,
)
from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTask
from aegis.config import Settings
from aegis.infrastructure.asana_service import AsanaService
from aegis.infrastructure.memory_manager import MemoryManager
from aegis.infrastructure.pid_manager import PIDManager
from aegis.infrastructure.worktree_manager import WorktreeManager

logger = structlog.get_logger()


class SwarmDispatcher:
    """Swarm orchestrator using section-based state machine.

    Polls Asana sections and routes tasks to appropriate agents based on:
    - Section name (Ready Queue, Planning, Review, etc.)
    - Agent custom field (Triage, Planner, Worker, etc.)
    """

    def __init__(
        self,
        settings: Settings,
        project_gid: str,
    ):
        """Initialize dispatcher.

        Args:
            settings: Settings instance
            project_gid: Asana project GID to monitor
        """
        self.settings = settings
        self.project_gid = project_gid
        self.repo_root = Path.cwd()

        # Initialize clients and services
        self.asana_client = AsanaClient(settings.asana_access_token)
        self.asana_service = AsanaService(self.asana_client)

        # Initialize infrastructure
        self.pid_manager = PIDManager()
        self.memory_manager = MemoryManager(self.repo_root)
        self.worktree_manager = WorktreeManager(self.repo_root)

        # Load state
        self.state_file = self.repo_root / "swarm_state.json"
        self.state = self._load_state()

        # Agent tracking
        self.active_tasks: dict[str, asyncio.Task] = {}

        # Running flag
        self.running = False

    def _load_state(self) -> dict:
        """Load persisted state from JSON file."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("state_load_failed", error=str(e))

        # Default state
        return {
            "last_run_refactor_detector": None,
            "last_run_code_consolidator": None,
            "blocked_tasks": {},
            "custom_field_gids": {},
            "orchestrator": {
                "started_at": None,
                "last_poll": None,
                "active_tasks": [],
            },
        }

    def _save_state(self) -> None:
        """Save state to JSON file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error("state_save_failed", error=str(e))

    async def start(self) -> None:
        """Start the dispatcher.

        Main entry point for orchestration.
        """
        # Acquire PID lock
        try:
            self.pid_manager.acquire()
        except Exception as e:
            logger.error("pid_lock_failed", error=str(e))
            raise

        self.running = True
        self.state["orchestrator"]["started_at"] = datetime.utcnow().isoformat()
        self._save_state()

        logger.info(
            "dispatcher_started",
            project_gid=self.project_gid,
            poll_interval=self.settings.poll_interval_seconds,
        )

        try:
            # Startup tasks
            await self._startup_checks()

            # Main loop
            while self.running:
                try:
                    await self._poll_and_dispatch()
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                except Exception as e:
                    logger.error("poll_error", error=str(e))
                    await asyncio.sleep(self.settings.poll_interval_seconds)

        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the dispatcher gracefully."""
        logger.info("dispatcher_stopping")
        self.running = False

        # Wait for active tasks
        if self.active_tasks:
            logger.info("waiting_for_active_tasks", count=len(self.active_tasks))
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)

        # Release PID lock
        self.pid_manager.release()

        # Save final state
        self.state["orchestrator"]["started_at"] = None
        self._save_state()

        logger.info("dispatcher_stopped")

    async def _startup_checks(self) -> None:
        """Perform startup checks and cleanup."""
        logger.info("running_startup_checks")

        # Check for zombie tasks (In Progress but no active agent)
        try:
            tasks = await self.asana_client.get_tasks_from_project(self.project_gid)
            in_progress_tasks = [
                t for t in tasks
                if await self._get_task_section(t) == "In Progress"
            ]

            if in_progress_tasks:
                logger.warning(
                    "zombie_tasks_found",
                    count=len(in_progress_tasks),
                    task_gids=[t.gid for t in in_progress_tasks],
                )

                # Move back to Ready Queue
                for task in in_progress_tasks:
                    logger.info("recovering_zombie_task", task_gid=task.gid)
                    await self.asana_service.move_task_to_section(
                        task.gid,
                        self.project_gid,
                        "Ready Queue",
                    )

        except Exception as e:
            logger.error("zombie_check_failed", error=str(e))

        # Prune orphaned worktrees
        try:
            active_task_gids = list(self.active_tasks.keys())
            pruned = self.worktree_manager.prune_orphaned_worktrees(active_task_gids)
            if pruned:
                logger.info("orphaned_worktrees_pruned", count=len(pruned))
        except Exception as e:
            logger.error("worktree_prune_failed", error=str(e))

    async def _poll_and_dispatch(self) -> None:
        """Poll Asana and dispatch tasks to agents."""
        self.state["orchestrator"]["last_poll"] = datetime.utcnow().isoformat()
        self._save_state()

        try:
            # Fetch all incomplete tasks
            tasks = await self.asana_client.get_tasks_from_project(
                self.project_gid,
                assigned_only=False,
            )

            # Process tasks by section
            for task in tasks:
                if task.completed:
                    continue

                # Skip if already active
                if task.gid in self.active_tasks:
                    continue

                # Get section
                section_name = await self._get_task_section(task)
                if not section_name:
                    continue

                # Check if section is actionable
                if section_name not in ["Ready Queue", "Planning", "Review", "Merging"]:
                    continue

                # Check dependencies
                if await self.asana_service.is_task_blocked(task.gid):
                    logger.info("task_blocked", task_gid=task.gid, task_name=task.name)
                    continue

                # Dispatch to agent
                await self._dispatch_task(task, section_name)

        except Exception as e:
            logger.error("poll_failed", error=str(e))

    async def _get_task_section(self, task: AsanaTask) -> str | None:
        """Get section name for a task.

        Args:
            task: AsanaTask

        Returns:
            Section name or None
        """
        section = await self.asana_service.get_task_section(task.gid, self.project_gid)
        return section.name if section else None

    async def _dispatch_task(self, task: AsanaTask, section_name: str) -> None:
        """Dispatch task to appropriate agent.

        Args:
            task: AsanaTask to dispatch
            section_name: Section task is in
        """
        # Get agent type from custom field
        agent_type = task.agent or "Triage"  # Default to Triage

        logger.info(
            "dispatching_task",
            task_gid=task.gid,
            task_name=task.name,
            section=section_name,
            agent=agent_type,
        )

        # Create agent task
        agent_coro = self._execute_agent(task, section_name, agent_type)
        agent_task = asyncio.create_task(agent_coro)

        # Track active task
        self.active_tasks[task.gid] = agent_task
        self.state["orchestrator"]["active_tasks"] = list(self.active_tasks.keys())
        self._save_state()

        # Cleanup on completion
        agent_task.add_done_callback(lambda _: self._task_done(task.gid))

    def _task_done(self, task_gid: str) -> None:
        """Callback when agent task completes.

        Args:
            task_gid: Task GID
        """
        if task_gid in self.active_tasks:
            del self.active_tasks[task_gid]
            self.state["orchestrator"]["active_tasks"] = list(self.active_tasks.keys())
            self._save_state()

            logger.info("task_execution_complete", task_gid=task_gid)

    async def _execute_agent(
        self,
        task: AsanaTask,
        section_name: str,
        agent_type: str,
    ) -> None:
        """Execute agent for a task.

        Args:
            task: AsanaTask
            section_name: Section name
            agent_type: Agent type
        """
        try:
            # Move to In Progress
            await self.asana_service.move_task_to_section(
                task.gid,
                self.project_gid,
                "In Progress",
            )

            # Route to agent
            agent = self._create_agent(agent_type, task)

            if not agent:
                logger.error("unknown_agent_type", agent_type=agent_type, task_gid=task.gid)
                return

            # Execute agent
            result = await agent.execute(task)

            # Post result comment
            await agent.post_result_comment(task, result)

            # Handle result
            if result.success:
                # Transition task
                if result.next_section:
                    await self.asana_service.transition_task(
                        task_gid=task.gid,
                        project_gid=self.project_gid,
                        new_section=result.next_section,
                        new_agent=result.next_agent,
                        clear_session_id=result.clear_session_id,
                    )

                logger.info(
                    "agent_execution_success",
                    task_gid=task.gid,
                    agent=agent_type,
                    next_section=result.next_section,
                )
            else:
                # Handle failure
                logger.warning(
                    "agent_execution_failed",
                    task_gid=task.gid,
                    agent=agent_type,
                    error=result.error,
                )

                # Move back to appropriate section or Clarification Needed
                if result.next_section:
                    await self.asana_service.move_task_to_section(
                        task.gid,
                        self.project_gid,
                        result.next_section,
                    )

        except Exception as e:
            logger.error(
                "agent_execution_error",
                task_gid=task.gid,
                agent=agent_type,
                error=str(e),
            )

            # Move back to Ready Queue on error
            try:
                await self.asana_service.move_task_to_section(
                    task.gid,
                    self.project_gid,
                    "Ready Queue",
                )
            except Exception as move_error:
                logger.error("task_move_failed", task_gid=task.gid, error=str(move_error))

    def _create_agent(self, agent_type: str, task: AsanaTask):
        """Create agent instance based on type.

        Args:
            agent_type: Agent type name
            task: AsanaTask (for session ID)

        Returns:
            Agent instance or None
        """
        session_id = task.session_id

        if agent_type == "Triage":
            return TriageAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "Planner":
            return PlannerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "Worker":
            return WorkerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "Reviewer":
            return ReviewerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "Merger":
            return MergerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "Documentation":
            return DocumentationAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                memory_manager=self.memory_manager,
                session_id=session_id,
            )
        else:
            return None
