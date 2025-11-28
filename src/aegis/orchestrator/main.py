"""Main orchestrator for Aegis task processing.

The orchestrator is responsible for:
1. Polling Asana for new/updated tasks
2. Prioritizing tasks using the TaskPrioritizer
3. Managing a task queue
4. Dispatching tasks to agents for execution
5. Handling task completion and errors
6. Maintaining system state in the database
"""

import asyncio
import contextlib
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from rich.console import Console

from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTask
from aegis.config import Settings, get_priority_weights_from_settings
from aegis.database.models import TaskExecution
from aegis.database.session import cleanup_db_connections, get_db
from aegis.database.state import (
    get_or_create_system_state,
    mark_in_progress_tasks_interrupted_async,
    mark_orchestrator_running,
    mark_orchestrator_stopped,
    mark_orchestrator_stopped_async,
    update_system_stats,
)
from aegis.orchestrator.display import OrchestratorDisplay
from aegis.orchestrator.prioritizer import TaskPrioritizer, TaskScore
from aegis.utils.shutdown import ShutdownHandler, get_shutdown_handler

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)


class TaskQueue:
    """Priority queue for managing tasks to be processed.

    Uses TaskPrioritizer to maintain priority ordering.
    """

    def __init__(self, prioritizer: TaskPrioritizer):
        """Initialize the task queue.

        Args:
            prioritizer: TaskPrioritizer instance for scoring tasks
        """
        self.prioritizer = prioritizer
        self._tasks: dict[str, AsanaTask] = {}  # gid -> task
        self._lock = asyncio.Lock()

    async def add_tasks(self, tasks: list[AsanaTask]) -> None:
        """Add tasks to the queue (or update if already present).

        Args:
            tasks: List of tasks to add
        """
        async with self._lock:
            for task in tasks:
                self._tasks[task.gid] = task

            logger.info("tasks_added_to_queue", count=len(tasks), total_in_queue=len(self._tasks))

    async def remove_task(self, task_gid: str) -> None:
        """Remove a task from the queue.

        Args:
            task_gid: GID of task to remove
        """
        async with self._lock:
            if task_gid in self._tasks:
                del self._tasks[task_gid]
                logger.debug("task_removed_from_queue", task_gid=task_gid)

    async def get_next_task(self) -> tuple[AsanaTask, TaskScore] | None:
        """Get the highest priority task from the queue.

        Returns:
            Tuple of (task, score) or None if queue is empty
        """
        async with self._lock:
            if not self._tasks:
                return None

            # Get prioritized list
            task_list = list(self._tasks.values())
            prioritized = self.prioritizer.prioritize_tasks(task_list)

            if not prioritized:
                return None

            # Return highest priority task (but don't remove it yet)
            return prioritized[0]

    async def size(self) -> int:
        """Get current queue size.

        Returns:
            Number of tasks in queue
        """
        async with self._lock:
            return len(self._tasks)

    async def clear(self) -> None:
        """Clear all tasks from the queue."""
        async with self._lock:
            self._tasks.clear()
            logger.info("task_queue_cleared")


class AgentPool:
    """Manages a pool of concurrent agent execution slots.

    This is a simplified version that tracks concurrent task executions.
    In the future, this could be expanded to manage actual agent processes.
    """

    def __init__(self, max_concurrent: int):
        """Initialize the agent pool.

        Args:
            max_concurrent: Maximum number of concurrent tasks
        """
        self.max_concurrent = max_concurrent
        self._active_tasks: dict[str, asyncio.Task] = {}  # task_gid -> asyncio.Task
        self._lock = asyncio.Lock()

    async def can_accept_task(self) -> bool:
        """Check if pool has capacity for another task.

        Returns:
            True if pool has available slots
        """
        async with self._lock:
            return len(self._active_tasks) < self.max_concurrent

    async def add_task(self, task_gid: str, task_coro: asyncio.Task) -> None:
        """Add a task to the active pool.

        Args:
            task_gid: GID of the task being executed
            task_coro: Asyncio task handle
        """
        async with self._lock:
            self._active_tasks[task_gid] = task_coro
            logger.debug("task_added_to_pool", task_gid=task_gid, active_count=len(self._active_tasks))

    async def remove_task(self, task_gid: str) -> None:
        """Remove a task from the active pool.

        Args:
            task_gid: GID of the task to remove
        """
        async with self._lock:
            if task_gid in self._active_tasks:
                del self._active_tasks[task_gid]
                logger.debug("task_removed_from_pool", task_gid=task_gid, active_count=len(self._active_tasks))

    async def get_active_count(self) -> int:
        """Get number of currently active tasks.

        Returns:
            Number of active tasks
        """
        async with self._lock:
            return len(self._active_tasks)

    async def wait_for_completion(self) -> None:
        """Wait for all active tasks to complete."""
        while True:
            async with self._lock:
                if not self._active_tasks:
                    break
                tasks = list(self._active_tasks.values())

            if tasks:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            await asyncio.sleep(0.1)


class Orchestrator:
    """Main orchestration engine for Aegis.

    Coordinates task polling, prioritization, queueing, and execution.
    """

    def __init__(self, settings: Settings, project_gid: str, project_name: str | None = None, use_live_display: bool = True, enable_web: bool = True, web_port: int = 8000, auto_dispatch: bool = False):
        """Initialize the orchestrator.

        Args:
            settings: Application settings
            project_gid: Asana project GID to monitor
            project_name: Optional project name (for display purposes)
            use_live_display: Whether to use the live full-screen display (default: True)
            enable_web: Whether to enable web dashboard (default: True)
            web_port: Port for web dashboard (default: 8000)
            auto_dispatch: Whether to automatically dispatch tasks (default: False - manual mode)
        """
        self.settings = settings
        self.project_gid = project_gid
        self.project_name = project_name or f"Project {project_gid}"
        self.use_live_display = use_live_display
        self.enable_web = enable_web
        self.web_port = web_port
        self.auto_dispatch = auto_dispatch
        self.asana_client = AsanaClient(settings.asana_access_token)

        # Initialize prioritizer with settings
        weights = get_priority_weights_from_settings(settings)
        self.prioritizer = TaskPrioritizer(weights=weights)

        # Initialize task queue and agent pool
        self.task_queue = TaskQueue(self.prioritizer)
        self.agent_pool = AgentPool(settings.max_concurrent_tasks)

        # Initialize SimpleExecutor if using API mode
        self.simple_executor: SimpleExecutor | None = None
        if settings.execution_mode == "simple_executor":
            self.simple_executor = SimpleExecutor(
                config=settings,
                asana_client=self.asana_client
            )
            logger.info("simple_executor_initialized")

        # Shutdown handling
        self.shutdown_handler: ShutdownHandler | None = None
        self._running = False

        # Display for rich console output (only if live display enabled)
        self.console = Console()
        self.display = OrchestratorDisplay(self.console, project_name=self.project_name) if use_live_display else None

        # Web server
        self.web_server: Any = None
        if enable_web:
            # Create display if web is enabled but live display is not
            if not self.display:
                self.display = OrchestratorDisplay(Console(), project_name=self.project_name)

        logger.info(
            "orchestrator_initialized",
            project_gid=project_gid,
            project_name=self.project_name,
            poll_interval=settings.poll_interval_seconds,
            max_concurrent=settings.max_concurrent_tasks,
            execution_mode=settings.execution_mode,
            auto_dispatch=auto_dispatch,
        )

    def _update_display_status(self, status: str, **kwargs) -> None:
        """Safely update display status (if display enabled)."""
        if self.display:
            self.display.update_orchestrator_status(status, **kwargs)

    def _add_task_to_display(self, task_gid: str, task_name: str, **kwargs) -> None:
        """Safely add task to display (if display enabled)."""
        if self.display:
            self.display.add_task(task_gid, task_name, **kwargs)

    def _update_task_in_display(self, task_gid: str, status: str, **kwargs) -> None:
        """Safely update task in display (if display enabled)."""
        if self.display:
            self.display.update_task_status(task_gid, status, **kwargs)

    def _remove_task_from_display(self, task_gid: str, final_status: str = "completed") -> None:
        """Safely remove task from display (if display enabled)."""
        if self.display:
            self.display.remove_task(task_gid, final_status)

    async def run(self) -> None:
        """Run the main orchestration loop.

        This is the main entry point that runs continuously until shutdown.
        """
        # Initialize shutdown handler
        self.shutdown_handler = get_shutdown_handler(
            shutdown_timeout=self.settings.shutdown_timeout,
            subprocess_term_timeout=self.settings.subprocess_term_timeout,
        )
        self.shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks
        self.shutdown_handler.register_cleanup_callback(mark_in_progress_tasks_interrupted_async)
        self.shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        self.shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        # Mark orchestrator as running
        mark_orchestrator_running()
        self._running = True

        # Update display status
        self._update_display_status("running", pid=os.getpid())

        # Configure logging
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / f"orchestrator_{os.getpid()}.log"

        # If using live display, redirect structlog to file
        if self.use_live_display:
            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.StackInfoRenderer(),
                    structlog.dev.set_exc_info,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer(),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
                context_class=dict,
                logger_factory=structlog.WriteLoggerFactory(file=open(str(log_file), "a")),
                cache_logger_on_first_use=False,
            )

        logger.info("orchestrator_started", pid=os.getpid(), log_file=str(log_file))

        # Show startup message
        self.console.print(f"\n[bold green]✓[/bold green] Orchestrator started (PID: {os.getpid()})")
        self.console.print(f"[dim]Logs: {log_file}[/dim]")

        # Start web server if enabled
        if self.enable_web:
            from aegis.orchestrator.web import OrchestratorWebServer
            self.web_server = OrchestratorWebServer(self, host="127.0.0.1", port=self.web_port)
            web_url = self.web_server.get_url()
            self.console.print(f"[bold cyan]🌐 Web Dashboard: {web_url}[/bold cyan]")
            # Start web server in background
            asyncio.create_task(self.web_server.start())
            logger.info("web_server_started", url=web_url)

        self.console.print("[dim]Press Ctrl+C to stop gracefully[/dim]\n")

        try:
            if self.use_live_display:
                # Run with live full-screen display
                live = self.display.create_live_display()
                with live:
                    # Start background tasks
                    tasks = [
                        asyncio.create_task(self._poll_loop()),
                        asyncio.create_task(self._display_loop(live)),
                    ]

                    # Only start dispatch loop if auto_dispatch is enabled
                    if self.auto_dispatch:
                        tasks.append(asyncio.create_task(self._dispatch_loop()))

                    # Wait for either task to complete (or shutdown signal)
                    done, pending = await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
            else:
                # Run without live display - just logs
                tasks = [asyncio.create_task(self._poll_loop())]

                # Only start dispatch loop if auto_dispatch is enabled
                if self.auto_dispatch:
                    tasks.append(asyncio.create_task(self._dispatch_loop()))

                # Wait for either task to complete (or shutdown signal)
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

        except Exception as e:
            logger.error("orchestrator_error", error=str(e), exc_info=True)
            raise
        finally:
            self._running = False

            # Update display status
            self._update_display_status("stopping")

            # Wait for active tasks to complete (with timeout)
            if self.shutdown_handler and not self.shutdown_handler.shutdown_requested:
                logger.info("orchestrator_shutting_down", message="Waiting for active tasks to complete")
                await self.agent_pool.wait_for_completion()
            else:
                logger.info("orchestrator_shutting_down", message="Shutdown requested, terminating active tasks")

            # Mark as stopped
            mark_orchestrator_stopped()
            self._update_display_status("stopped")

            # Run shutdown cleanup (this will terminate subprocesses)
            if self.shutdown_handler:
                await self.shutdown_handler.shutdown()

            logger.info("orchestrator_stopped")

    async def get_queued_tasks(self) -> list[tuple[AsanaTask, TaskScore]]:
        """Get all queued tasks with their priority scores.

        Returns:
            List of (task, score) tuples sorted by priority (highest first)
        """
        async with self.task_queue._lock:
            if not self.task_queue._tasks:
                return []

            # Get prioritized list
            task_list = list(self.task_queue._tasks.values())
            return self.prioritizer.prioritize_tasks(task_list)

    async def manual_execute_task(self, task_gid: str) -> dict[str, Any]:
        """Manually trigger execution of a specific task.

        Args:
            task_gid: GID of the task to execute

        Returns:
            dict with keys: success (bool), message (str), error (str | None)
        """
        try:
            # Check if pool has capacity
            if not await self.agent_pool.can_accept_task():
                return {
                    "success": False,
                    "message": "Agent pool is at capacity. Please wait for a task to complete.",
                    "error": "MAX_CONCURRENT_REACHED"
                }

            # Find task in queue
            async with self.task_queue._lock:
                if task_gid not in self.task_queue._tasks:
                    return {
                        "success": False,
                        "message": f"Task {task_gid} not found in queue",
                        "error": "TASK_NOT_FOUND"
                    }

                task = self.task_queue._tasks[task_gid]

            # Get priority score for logging
            prioritized = self.prioritizer.prioritize_tasks([task])
            score = prioritized[0][1] if prioritized else TaskScore(total_score=0.0)

            # Remove from queue (we're about to execute it)
            await self.task_queue.remove_task(task_gid)

            # Add to display
            self._add_task_to_display(task_gid, task.name, status="dispatched", started_at=datetime.now())

            # Create execution task
            execution_coro = asyncio.create_task(
                self._execute_task(task, score)
            )

            # Add to agent pool
            await self.agent_pool.add_task(task_gid, execution_coro)

            logger.info(
                "task_manually_dispatched",
                task_gid=task_gid,
                task_name=task.name,
                priority_score=score.total_score,
            )

            return {
                "success": True,
                "message": f"Task '{task.name}' dispatched for execution",
                "task_gid": task_gid,
                "task_name": task.name
            }

        except Exception as e:
            logger.error("manual_execute_task_error", task_gid=task_gid, error=str(e), exc_info=True)
            return {
                "success": False,
                "message": f"Failed to execute task: {str(e)}",
                "error": str(e)
            }

    async def _poll_loop(self) -> None:
        """Background loop that polls Asana for new/updated tasks."""
        logger.info("poll_loop_started", interval_seconds=self.settings.poll_interval_seconds, project_gid=self.project_gid)

        while self._running and not self.shutdown_handler.shutdown_requested:
            try:
                # Fetch tasks from the monitored project
                tasks = await self._fetch_tasks_from_project()

                # Add to queue
                if tasks:
                    await self.task_queue.add_tasks(tasks)

                    # Update system stats
                    queue_size = await self.task_queue.size()
                    active_count = await self.agent_pool.get_active_count()
                    update_system_stats(
                        total_tasks_pending=queue_size,
                        active_agents_count=active_count,
                    )

                # Update last sync time
                poll_time = datetime.now()
                session = get_db()
                try:
                    state = get_or_create_system_state(session)
                    state.last_tasks_sync_at = poll_time
                    session.commit()
                finally:
                    session.close()

                # Update display with last poll time
                self._update_display_status("running", pid=os.getpid(), last_poll_time=poll_time)

                logger.info(
                    "poll_completed",
                    tasks_found=len(tasks),
                    queue_size=await self.task_queue.size(),
                    project_gid=self.project_gid,
                )

            except Exception as e:
                logger.error("poll_loop_error", error=str(e), exc_info=True)

            # Wait for next poll interval
            await asyncio.sleep(self.settings.poll_interval_seconds)

        logger.info("poll_loop_stopped")

    async def _display_loop(self, live) -> None:
        """Background loop that updates the display.

        Args:
            live: Rich Live instance
        """
        logger.info("display_loop_started")

        while self._running and not self.shutdown_handler.shutdown_requested:
            try:
                # Update the display
                live.update(self.display.render())
                await asyncio.sleep(0.5)  # Update twice per second
            except Exception as e:
                logger.error("display_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(1)

        logger.info("display_loop_stopped")

    async def _dispatch_loop(self) -> None:
        """Background loop that dispatches tasks from queue to agents."""
        logger.info("dispatch_loop_started")

        while self._running and not self.shutdown_handler.shutdown_requested:
            try:
                # Check if we can accept more tasks
                if not await self.agent_pool.can_accept_task():
                    await asyncio.sleep(1)
                    continue

                # Get next task from queue
                next_task_info = await self.task_queue.get_next_task()
                if not next_task_info:
                    await asyncio.sleep(1)
                    continue

                task, score = next_task_info

                # Remove from queue (we're about to execute it)
                await self.task_queue.remove_task(task.gid)

                # Add to display
                self._add_task_to_display(task.gid, task.name, status="dispatched", started_at=datetime.now())

                # Create execution task
                execution_coro = asyncio.create_task(
                    self._execute_task(task, score)
                )

                # Add to agent pool
                await self.agent_pool.add_task(task.gid, execution_coro)

                logger.info(
                    "task_dispatched",
                    task_gid=task.gid,
                    task_name=task.name,
                    priority_score=score.total_score,
                )

            except Exception as e:
                logger.error("dispatch_loop_error", error=str(e), exc_info=True)

            # Small delay to prevent tight loop
            await asyncio.sleep(0.5)

        logger.info("dispatch_loop_stopped")

    async def _fetch_tasks_from_project(self) -> list[AsanaTask]:
        """Fetch all incomplete, unassigned tasks from the monitored project.

        Returns:
            List of tasks assigned to Aegis (or unassigned incomplete tasks)
        """
        try:
            # Get incomplete, unassigned tasks from this project
            tasks = await self.asana_client.get_tasks_from_project(
                self.project_gid,
                assigned_only=False,
            )

            # Filter for incomplete, unassigned tasks
            # TODO: In the future, also check for tasks assigned to Aegis bot user
            filtered_tasks = [
                t for t in tasks
                if not t.completed and not t.assignee
            ]

            logger.info(
                "fetched_project_tasks",
                project_gid=self.project_gid,
                project_name=self.project_name,
                total_tasks=len(filtered_tasks),
            )

            return filtered_tasks

        except Exception as e:
            logger.error(
                "failed_to_fetch_project_tasks",
                project_gid=self.project_gid,
                project_name=self.project_name,
                error=str(e),
                exc_info=True
            )
            return []

    async def _execute_task(self, task: AsanaTask, score: TaskScore) -> None:
        """Execute a single task using configured execution mode.

        Supports two execution modes:
        - simple_executor: Uses SimpleExecutor agent (Claude API)
        - claude_cli: Uses Claude CLI subprocess

        Args:
            task: Task to execute
            score: Priority score for the task
        """
        if self.settings.execution_mode == "simple_executor":
            await self._execute_task_with_simple_executor(task, score)
        else:
            await self._execute_task_with_claude_cli(task, score)

    async def _execute_task_with_simple_executor(self, task: AsanaTask, score: TaskScore) -> None:
        """Execute a task using SimpleExecutor agent via agent web service.

        This method:
        1. Launches an agent process (web service)
        2. Sends execute request via HTTP API
        3. Polls for completion
        4. Terminates the agent process

        Args:
            task: Task to execute
            score: Priority score for the task
        """
        task_execution_id = None
        session: Session | None = None
        agent_process = None
        agent_client = None

        try:
            # Create task execution record
            session = get_db()

            execution_context = {
                "asana_task_gid": task.gid,
                "asana_task_name": task.name,
                "project_gids": [p.gid for p in task.projects],
            }

            task_execution = TaskExecution(
                task_id=None,
                status="in_progress",
                agent_type="simple_executor",
                started_at=datetime.now(),
                context=execution_context,
            )
            session.add(task_execution)
            session.commit()
            task_execution_id = task_execution.id

            # Update display
            self._update_task_in_display(task.gid, "in_progress")

            logger.info(
                "task_execution_started",
                task_gid=task.gid,
                task_name=task.name,
                execution_id=task_execution_id,
                execution_mode="simple_executor_api",
                priority_score=score.total_score,
            )

            # Get project name
            project_name = task.projects[0].name if task.projects else "Unknown"

            # Get code path (optional)
            code_path = str(Path.cwd())  # Default to current directory

            # Launch agent process and get client
            from aegis.orchestrator.agent_client import launch_agent_and_get_client

            agent_process, agent_client = await launch_agent_and_get_client(
                agent_command=["python", "-m", "aegis.agents.agent_service"],
                startup_timeout=10.0
            )

            # Track subprocess for shutdown handling
            if self.shutdown_handler:
                self.shutdown_handler.track_subprocess(agent_process)

            logger.info(
                "agent_process_launched",
                task_gid=task.gid,
                pid=agent_process.pid,
            )

            # Send execute request
            execute_response = await agent_client.execute_task(
                task_gid=task.gid,
                project_name=project_name,
                code_path=code_path
            )

            # Update display to running
            self._update_task_in_display(task.gid, "running")

            logger.info(
                "agent_execute_sent",
                task_gid=task.gid,
                response=execute_response
            )

            # Wait for completion with polling
            final_status = await agent_client.wait_for_completion(
                task_id=task.gid,
                poll_interval=2.0,
                timeout=600.0  # 10 minutes
            )

            # Update execution record
            task_execution.status = final_status["status"]
            task_execution.completed_at = datetime.now()
            task_execution.success = final_status.get("success", False)
            task_execution.output = final_status.get("output", "")[:50000]  # Truncate if too long
            task_execution.error_message = final_status.get("error")

            # Update display with log file from agent
            if final_status.get("log_file"):
                self._update_task_in_display(task.gid, "running", log_file=final_status["log_file"])

            # Calculate duration
            if task_execution.started_at:
                duration = datetime.now() - task_execution.started_at
                task_execution.duration_seconds = int(duration.total_seconds())

            session.commit()

            # Update display - remove from active tasks
            display_status = "completed" if task_execution.success else "failed"
            self._remove_task_from_display(task.gid, display_status)

            logger.info(
                "task_execution_completed",
                task_gid=task.gid,
                execution_id=task_execution_id,
                success=task_execution.success,
                duration_seconds=task_execution.duration_seconds,
                execution_mode="simple_executor_api",
            )

        except Exception as e:
            # Update display - remove from active tasks
            self._remove_task_from_display(task.gid, "failed")

            logger.error(
                "task_execution_failed",
                task_gid=task.gid,
                execution_id=task_execution_id,
                execution_mode="simple_executor_api",
                error=str(e),
                exc_info=True,
            )

            # Update execution record
            if session and task_execution_id:
                try:
                    task_execution = session.query(TaskExecution).get(task_execution_id)
                    if task_execution:
                        task_execution.status = "failed"
                        task_execution.completed_at = datetime.now()
                        task_execution.success = False
                        task_execution.error_message = str(e)
                        session.commit()
                except Exception as db_error:
                    logger.error("failed_to_update_execution_record", error=str(db_error))

        finally:
            # Cleanup agent client
            if agent_client:
                try:
                    await agent_client.close()
                except Exception as e:
                    logger.error("failed_to_close_agent_client", error=str(e))

            # Terminate agent process
            if agent_process:
                try:
                    if self.shutdown_handler:
                        self.shutdown_handler.untrack_subprocess(agent_process)

                    # Terminate gracefully
                    agent_process.terminate()
                    try:
                        await asyncio.wait_for(agent_process.wait(), timeout=5.0)
                        logger.info("agent_process_terminated", pid=agent_process.pid)
                    except TimeoutError:
                        # Force kill if doesn't terminate
                        agent_process.kill()
                        await agent_process.wait()
                        logger.warning("agent_process_killed", pid=agent_process.pid)
                except Exception as e:
                    logger.error("failed_to_terminate_agent_process", error=str(e))

            # Ensure task is removed from display (in case of unexpected errors)
            if self.display and task.gid in self.display.active_tasks:
                self._remove_task_from_display(task.gid, "failed")

            # Close database session
            if session:
                session.close()

    async def _execute_task_with_claude_cli(self, task: AsanaTask, score: TaskScore) -> None:
        """Execute a task using Claude CLI subprocess.

        Args:
            task: Task to execute
            score: Priority score for the task
        """
        task_execution_id = None
        session: Session | None = None

        try:
            # Create task execution record
            # Note: For now, we create execution records without linking to Task table
            # In the future, we'll sync Asana tasks to database first
            session = get_db()

            # Store task GID in context for tracking
            execution_context = {
                "asana_task_gid": task.gid,
                "asana_task_name": task.name,
                "project_gids": [p.gid for p in task.projects],
            }

            task_execution = TaskExecution(
                task_id=None,  # TODO: Link to Task table once we implement task sync
                status="in_progress",
                agent_type="claude_cli",
                started_at=datetime.now(),
                context=execution_context,
            )
            session.add(task_execution)
            session.commit()
            task_execution_id = task_execution.id

            # Update display
            self._update_task_in_display(task.gid, "in_progress")

            logger.info(
                "task_execution_started",
                task_gid=task.gid,
                task_name=task.name,
                execution_id=task_execution_id,
                priority_score=score.total_score,
            )

            # Get project info for code path
            code_path = None
            if task.projects:
                project = await self.asana_client.get_project(task.projects[0].gid)
                if project.notes:
                    for line in project.notes.split("\n"):
                        if line.startswith("Code Location:"):
                            code_path = line.split(":", 1)[1].strip()
                            code_path = os.path.expanduser(code_path)
                            break

            # Format task context
            project_gid = task.projects[0].gid if task.projects else None
            task_context = f"""Task: {task.name}
Task GID: {task.gid}
Project: {task.projects[0].name if task.projects else 'N/A'}
Project GID: {project_gid}"""

            if code_path:
                task_context += f"\nCode Location: {code_path}"

            if task.notes:
                task_context += f"\n\nTask Description:\n{task.notes}"

            task_context += f"""

IMPORTANT: When you have completed this task, you must:

1. Post a comment to the Asana task with a summary of what you accomplished
2. Mark the task as complete in Asana
3. Move the task to the "Implemented" section

Use this Python helper:
```bash
python -m aegis.agent_helpers {task.gid} {project_gid} "YOUR_SUMMARY_HERE"
```

After completing these steps, EXIT. Do not wait for further input."""

            # Determine working directory
            working_dir = code_path if code_path and os.path.isdir(code_path) else None

            # Execute using Claude CLI
            # Check if terminal mode is enabled
            if self.settings.terminal_mode:
                # Launch in terminal - we can't easily track completion
                from aegis.cli import (
                    launch_in_hyper_terminal,  # Import here to avoid circular import
                )

                # Update display with running status
                self._update_task_in_display(task.gid, "running")

                logger.info(
                    "launching_task_in_terminal",
                    task_gid=task.gid,
                    task_name=task.name,
                )

                launch_in_hyper_terminal(
                    ["claude", "--dangerously-skip-permissions", task_context],
                    cwd=working_dir
                )

                # For terminal mode, mark as launched and return
                # We can't track completion or capture output
                task_execution.status = "launched"
                task_execution.completed_at = datetime.now()
                task_execution.success = True
                task_execution.output = "Launched in terminal mode"
                session.commit()

                logger.info(
                    "task_launched_in_terminal",
                    task_gid=task.gid,
                    execution_id=task_execution_id,
                )

                # Remove from display after launching
                self._remove_task_from_display(task.gid, "launched")

                # Don't post to Asana - the agent will do it via agent_helpers
                return

            # Background mode - run and write output to log file
            # Create unique log file for this task
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = logs_dir / f"task_{task.gid}_{timestamp}.log"

            # Update display with log file path before starting
            self._update_task_in_display(
                task.gid,
                "running",
                log_file=str(log_file)
            )

            logger.info("starting_task_subprocess", task_gid=task.gid, log_file=str(log_file))

            # Open log file for writing
            with open(log_file, "w") as log_fh:
                # Write header to log file
                log_fh.write("=== Aegis Task Execution Log ===\n")
                log_fh.write(f"Task: {task.name}\n")
                log_fh.write(f"Task GID: {task.gid}\n")
                log_fh.write(f"Started: {datetime.now().isoformat()}\n")
                log_fh.write(f"Working Directory: {working_dir}\n")
                log_fh.write("=" * 50 + "\n\n")
                log_fh.flush()

                # Run Claude CLI with output redirected to log file
                process = subprocess.Popen(
                    ["claude", "--dangerously-skip-permissions", task_context],
                    cwd=working_dir,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,  # Merge stderr into stdout
                    text=True,
                )

                # Track subprocess for shutdown handling
                if self.shutdown_handler:
                    self.shutdown_handler.track_subprocess(process)

                try:
                    # Wait for completion with timeout (5 minutes) - use asyncio.to_thread to avoid blocking
                    await asyncio.wait_for(
                        asyncio.to_thread(process.wait),
                        timeout=300
                    )
                except TimeoutError:
                    if self.shutdown_handler:
                        self.shutdown_handler.untrack_subprocess(process)
                    logger.error("task_execution_timeout", task_gid=task.gid, timeout_seconds=300)
                    process.kill()
                    process.wait()  # Ensure process is reaped
                    raise TimeoutError("Task execution timed out after 300 seconds")
                finally:
                    if self.shutdown_handler:
                        self.shutdown_handler.untrack_subprocess(process)

                # Write footer to log file
                log_fh.write(f"\n\n{'=' * 50}\n")
                log_fh.write(f"Completed: {datetime.now().isoformat()}\n")
                log_fh.write(f"Exit Code: {process.returncode}\n")
                log_fh.flush()

            # Read the log file to get output for database
            with open(log_file) as log_fh:
                output = log_fh.read()

            # Update execution record
            task_execution.status = "completed" if process.returncode == 0 else "failed"
            task_execution.completed_at = datetime.now()
            task_execution.success = process.returncode == 0
            task_execution.output = output[:50000]  # Truncate if too long

            if process.returncode != 0:
                task_execution.error_message = f"Exit code: {process.returncode}"

            # Calculate duration
            if task_execution.started_at:
                duration = datetime.now() - task_execution.started_at
                task_execution.duration_seconds = int(duration.total_seconds())

            session.commit()

            # Post result to Asana
            status_emoji = "✓" if process.returncode == 0 else "⚠️"
            status_text = "completed" if process.returncode == 0 else f"completed with errors (exit code {process.returncode})"

            comment_text = f"""{status_emoji} Task {status_text} via Aegis Orchestrator

**Timestamp**: {datetime.now().isoformat()}
**Priority Score**: {score.total_score:.2f}

**Output**:
```
{output[:10000] if output else '(No output captured)'}
```

**Execution ID**: {task_execution_id}
"""

            await self.asana_client.add_comment(task.gid, comment_text)

            # Update display - remove from active tasks
            final_status = "completed" if task_execution.success else "failed"
            self._remove_task_from_display(task.gid, final_status)

            logger.info(
                "task_execution_completed",
                task_gid=task.gid,
                execution_id=task_execution_id,
                success=task_execution.success,
                duration_seconds=task_execution.duration_seconds,
            )

        except Exception as e:
            logger.error(
                "task_execution_failed",
                task_gid=task.gid,
                execution_id=task_execution_id,
                error=str(e),
                exc_info=True,
            )

            # Update execution record
            if session and task_execution_id:
                try:
                    task_execution = session.query(TaskExecution).get(task_execution_id)
                    if task_execution:
                        task_execution.status = "failed"
                        task_execution.completed_at = datetime.now()
                        task_execution.success = False
                        task_execution.error_message = str(e)
                        session.commit()
                except Exception as db_error:
                    logger.error("failed_to_update_execution_record", error=str(db_error))

            # Post error to Asana
            try:
                error_comment = f"""⚠️ Task execution failed via Aegis Orchestrator

**Timestamp**: {datetime.now().isoformat()}
**Error**: {str(e)}

The orchestrator encountered an error while executing this task. Please review and retry if needed.
"""
                await self.asana_client.add_comment(task.gid, error_comment)
            except Exception as comment_error:
                logger.error("failed_to_post_error_comment", error=str(comment_error))

            # Update display - remove from active tasks
            self._remove_task_from_display(task.gid, "failed")

        finally:
            # Remove from agent pool
            await self.agent_pool.remove_task(task.gid)

            # Ensure task is removed from display (in case of unexpected errors)
            if self.display and task.gid in self.display.active_tasks:
                self._remove_task_from_display(task.gid, "failed")

            # Close database session
            if session:
                session.close()
