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
    RefactorAgent,
    ConsolidatorAgent,
    IdeationAgent,
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
        repo_root: Path | None = None,
    ):
        """Initialize dispatcher.

        Args:
            settings: Settings instance
            project_gid: Asana project GID to monitor
            repo_root: Root directory of the repository (default: CWD)
        """
        self.settings = settings
        self.project_gid = project_gid
        self.repo_root = repo_root or Path.cwd()

        # Initialize clients and services
        self.asana_client = AsanaClient(settings.asana_access_token)
        self.asana_service = AsanaService(self.asana_client)

        # Initialize infrastructure
        self.pid_manager = PIDManager(project_gid=project_gid, root_dir=self.repo_root)
        self.memory_manager = MemoryManager(self.repo_root)
        self.worktree_manager = WorktreeManager(self.repo_root)

        # Load state
        self.state_file = self.repo_root / ".aegis" / "swarm_state.json"
        self.state = self._load_state()

        # Agent tracking
        self.active_tasks: dict[str, asyncio.Task] = {}

        # Running flag
        self.running = False

        # Bot user tracking
        self.bot_user_gid = None

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
                "recent_errors": [],
                "recent_events": [],
            },
        }

    def _save_state(self) -> None:
        """Save state to JSON file."""
        try:
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(self.state, f, indent=2)
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error("state_save_failed", error=str(e))

    def _record_event(self, event_type: str, **kwargs) -> None:
        """Record a significant event to state."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "details": kwargs
        }

        events = self.state["orchestrator"].get("recent_events", [])
        events.append(event)
        # Keep last 50 events
        self.state["orchestrator"]["recent_events"] = events[-50:]
        self._save_state()

    def _record_error(self, error: str, **kwargs) -> None:
        """Record an error to state."""
        err_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(error),
            "details": kwargs
        }

        errors = self.state["orchestrator"].get("recent_errors", [])
        errors.append(err_entry)
        # Keep last 20 errors
        self.state["orchestrator"]["recent_errors"] = errors[-20:]
        self._save_state()


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
        self._record_event("system_started", project_gid=self.project_gid)


        try:
            # Startup tasks
            await self._startup_checks()

            # Main loop
            while self.running:
                try:
                    await self._poll_and_dispatch()
                    await self._check_scheduled_agents()
                    await asyncio.sleep(self.settings.poll_interval_seconds)
                except Exception as e:
                    logger.error("poll_error", error=str(e))
                    self._record_error(str(e), context="poll_loop")
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
        self._record_event("system_stopped")


    async def _startup_checks(self) -> None:
        """Perform startup checks and cleanup."""
        logger.info("running_startup_checks")

        # Get bot user GID
        try:
            me = await self.asana_service.get_me()
            self.bot_user_gid = me.gid
            logger.info("bot_user_identified", bot_gid=self.bot_user_gid, bot_name=me.name)
        except Exception as e:
            logger.error("failed_to_identify_bot", error=str(e))
            # We can continue, but assignment filtering might be disabled or limited

        # Ensure custom fields are cached
        try:
            await self.asana_service.ensure_custom_field_gids(self.project_gid)
        except Exception as e:
            logger.error("failed_to_cache_custom_fields", error=str(e))

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
            self._record_error(str(e), context="startup_zombie_check")


        # Prune orphaned worktrees
        try:
            active_task_gids = list(self.active_tasks.keys())
            pruned = self.worktree_manager.prune_orphaned_worktrees(active_task_gids)
            if pruned:
                logger.info("orphaned_worktrees_pruned", count=len(pruned))
        except Exception as e:
            logger.error("worktree_prune_failed", error=str(e))

    async def _check_scheduled_agents(self) -> None:
        """Check and run scheduled maintenance agents."""
        now = datetime.utcnow()

        # Helper to check if run is needed
        async def check_and_run(agent_name: str, interval_days: int = 7):
            last_run_str = self.state.get(f"last_run_{agent_name}")
            should_run = False

            if not last_run_str:
                should_run = True
            else:
                last_run = datetime.fromisoformat(last_run_str)
                if (now - last_run).days >= interval_days:
                    should_run = True

            if should_run:
                logger.info("triggering_scheduled_agent", agent=agent_name)

                # Create ephemeral task
                task_name = f"[System] Auto-Run: {agent_name.replace('_', ' ').title()}"

                try:
                    # Create task in In Progress
                    task = await self.asana_service.create_task(
                        project_gid=self.project_gid,
                        name=task_name,
                        section_name="In Progress",
                        agent=agent_name, # This might fail if we don't handle custom field setting yet
                    )

                    # Manually set agent field since create_task might not have done it
                    # We need to find the option name that matches our internal agent name
                    # Internal: refactor_detector -> Agent Field: Refactor
                    agent_field_map = {
                        "refactor_detector": "Refactor",
                        "code_consolidator": "Consolidator",
                    }

                    agent_enum = agent_field_map.get(agent_name)
                    if agent_enum:
                         # We need to set the custom field.
                         # Since we don't have the GIDs easily available here without fetching them,
                         # let's rely on _execute_agent to handle it if we dispatch it?
                         # But _execute_agent expects an existing task.
                         # Let's just create the task and then dispatch it immediately.
                         pass

                    # Dispatch immediately
                    # We need to mock the task object to have the correct agent field if we couldn't set it
                    # Or we can just pass the agent type explicitly to _execute_agent if we modify it?
                    # _execute_agent takes agent_type as argument!

                    target_agent_type = agent_field_map.get(agent_name, "Triage")

                    await self._execute_agent(task, "In Progress", target_agent_type)

                    # Update state
                    self.state[f"last_run_{agent_name}"] = now.isoformat()
                    self._save_state()

                except Exception as e:
                    logger.error("scheduled_agent_failed", agent=agent_name, error=str(e))
                    self._record_error(str(e), context="scheduled_agent", agent=agent_name)


        # Check Refactor Detector (Weekly)
        await check_and_run("refactor_detector", interval_days=7)

        # Check Code Consolidator (Weekly)
        await check_and_run("code_consolidator", interval_days=7)

    async def _poll_and_dispatch(self) -> None:
        """Poll Asana and dispatch tasks to agents."""
        self.state["orchestrator"]["last_poll"] = datetime.utcnow().isoformat()
        self._save_state()

        try:
            # Track section counts
            section_counts = {}

            # Fetch all incomplete tasks
            tasks = await self.asana_client.get_tasks_from_project(
                self.project_gid,
                assigned_only=False,
            )

            # Process tasks by section
            for task in tasks:
                if task.completed:
                    continue

                # Get section
                section_name = await self._get_task_section(task)
                if not section_name:
                    continue

                # Update section counts
                section_counts[section_name] = section_counts.get(section_name, 0) + 1

                # Skip if already active
                if task.gid in self.active_tasks:
                    continue

                # Check if section is actionable
                if section_name not in ["Ready Queue", "Planning", "Review", "Merging"]:
                    continue

                # Check dependencies
                if await self.asana_service.is_task_blocked(task.gid):
                    logger.info("task_blocked", task_gid=task.gid, task_name=task.name)
                    continue

                # Check assignment
                # We need to determine agent type before checking if we should process it
                # But _should_process_task needs agent_type.
                # Let's get it first.
                agent_type = task.agent or "Triage"

                if not self._should_process_task(task, agent_type):
                    continue

                # Dispatch to agent
                await self._dispatch_task(task, section_name)

            # Update state with section counts
            self.state["orchestrator"]["section_counts"] = section_counts
            self._save_state()

        except Exception as e:
            # Check for 404 Not Found (Project deleted or invalid)
            error_str = str(e)
            if "(404)" in error_str and "Not Found" in error_str:
                logger.error("project_not_found_stopping", project_gid=self.project_gid)
                self.running = False
                return

            logger.error("poll_failed", error=error_str)
            self._record_error(error_str, context="poll_and_dispatch")


    def _should_process_task(self, task: AsanaTask, agent_type: str) -> bool:
        """Check if task should be processed by this agent instance.

        Args:
            task: AsanaTask
            agent_type: Agent type

        Returns:
            True if task should be processed
        """
        # Triage and Manager agents process everything (or unassigned)
        if agent_type in ["triage_agent", "manager_agent"]:
            return True

        # Other agents (Worker, Planner, etc.) only process if assigned to bot
        if self.bot_user_gid and task.assignee:
            if task.assignee.gid == self.bot_user_gid:
                return True
            else:
                # Assigned to someone else
                return False

        # If unassigned, assume we can pick it up (or maybe strict mode?)
        # For now, let's say unassigned tasks are fair game if in correct section
        return True

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
        agent_type = task.agent or "triage_agent"  # Default to Triage

        logger.info("dispatching_task",
            task_gid=task.gid,
            section=section_name,
            agent=agent_type,
        )
        self._record_event("task_dispatched", task_gid=task.gid, agent=agent_type, section=section_name)


        # Create agent task
        agent_coro = self._execute_agent(task, section_name, agent_type)
        agent_task = asyncio.create_task(agent_coro)

        # Track active task
        self.active_tasks[task.gid] = agent_task

        # Update state with detailed active task info
        active_tasks_list = self.state["orchestrator"].get("active_tasks_details", [])
        # Remove if exists (shouldn't happen but safe)
        active_tasks_list = [t for t in active_tasks_list if t["gid"] != task.gid]

        active_tasks_list.append({
            "gid": task.gid,
            "name": task.name,
            "agent": agent_type,
            "section": section_name,
            "started_at": datetime.utcnow().isoformat(),
        })

        self.state["orchestrator"]["active_tasks_details"] = active_tasks_list
        # Keep legacy list for now if needed, or just replace?
        # Let's keep legacy list for backward compat if any tools use it, but update it too
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

            # Remove from details
            active_tasks_list = self.state["orchestrator"].get("active_tasks_details", [])
            self.state["orchestrator"]["active_tasks_details"] = [
                t for t in active_tasks_list if t["gid"] != task_gid
            ]

            self._save_state()

            logger.info("task_execution_complete", task_gid=task_gid)
            self._record_event("task_completed", task_gid=task_gid)


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

            # Pickup: Update status and post comment
            await self.asana_service.set_custom_field_value(
                task_gid=task.gid,
                field_gid=self.asana_service.custom_field_gids.get(self.project_gid, {}).get("Swarm Status"),
                value="In Progress",
            )

            pickup_reason = "Assigned to me" if task.assignee and task.assignee.gid == self.bot_user_gid else "Triage routing"
            await self.asana_service.post_agent_comment(
                task_gid=task.gid,
                agent_name=agent_type,
                status_emoji="🚀",
                summary=f"Picking up task. Reason: {pickup_reason}",
                session_id=task.session_id,
            )

            # Route to agent
            agent = self._create_agent(agent_type, task)

            if not agent:
                logger.error("unknown_agent_type", agent_type=agent_type, task_gid=task.gid)
                self._record_error(f"Unknown agent type: {agent_type}", task_gid=task.gid)
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
                        assignee=result.assignee,
                    )

                    logger.info("agent_execution_success",
                        task_gid=task.gid,
                        agent=agent_type,
                        next_section=result.next_section,
                    )
                self._record_event("agent_success", task_gid=task.gid, agent=agent_type, next_section=result.next_section)

            else:
                # Handle failure
                logger.error("agent_execution_failed",
                    task_gid=task.gid,
                    agent=agent_type,
                    error=result.error,
                )
                self._record_error(result.error, task_gid=task.gid, agent=agent_type, context="agent_execution")


                # Move back to appropriate section or Clarification Needed
                if result.next_section:
                    await self.asana_service.move_task_to_section(
                        task.gid,
                        self.project_gid,
                        result.next_section,
                    )

        except Exception as e:
            logger.error("agent_execution_exception",
                task_gid=task.gid,
                agent=agent_type,
                error=str(e),
            )
            self._record_error(str(e), task_gid=task.gid, agent=agent_type, context="agent_execution_exception")


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

        if agent_type == "triage_agent":
            return TriageAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "planner_agent":
            return PlannerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "worker_agent":
            return WorkerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "reviewer_agent":
            return ReviewerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "merger_agent":
            return MergerAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                worktree_manager=self.worktree_manager,
                session_id=session_id,
            )
        elif agent_type == "documentation_agent":
            return DocumentationAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                memory_manager=self.memory_manager,
                session_id=session_id,
            )
        elif agent_type == "Documentation":
            return DocumentationAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                memory_manager=self.memory_manager,
                session_id=session_id,
            )
        elif agent_type == "refactor_agent":
            return RefactorAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "consolidator_agent":
            return ConsolidatorAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        elif agent_type == "ideation_agent":
            return IdeationAgent(
                asana_service=self.asana_service,
                repo_root=self.repo_root,
                session_id=session_id,
            )
        else:
            return None
