"""Graceful shutdown handling for Aegis.

This module provides signal handling and shutdown coordination to ensure:
- Clean termination without losing work
- In-progress tasks can complete
- State is saved to database
- Resources are properly cleaned up
"""

import asyncio
import os
import signal
import subprocess
from collections.abc import Callable

import structlog

logger = structlog.get_logger(__name__)


class ShutdownHandler:
    """Manages graceful shutdown of the Aegis system.

    Features:
    - Catches SIGTERM and SIGINT signals
    - Allows in-progress tasks to complete
    - Enforces maximum wait timeout
    - Coordinates cleanup across components
    """

    def __init__(self, shutdown_timeout: int = 300, subprocess_term_timeout: int = 10):
        """Initialize shutdown handler.

        Args:
            shutdown_timeout: Maximum seconds to wait for tasks to complete (default: 5 minutes)
            subprocess_term_timeout: Seconds to wait after SIGTERM before SIGKILL (default: 10)
        """
        self.shutdown_timeout = shutdown_timeout
        self.subprocess_term_timeout = subprocess_term_timeout
        self._shutdown_requested = False
        self._sigint_count = 0
        self._original_sigint_handler = None
        self._original_sigterm_handler = None
        self._cleanup_callbacks: list[Callable] = []
        self._in_progress_tasks: set[asyncio.Task] = set()
        self._in_progress_subprocesses: dict[int, subprocess.Popen] = {}
        self._active_sessions: set = set()

    @property
    def shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def register_cleanup_callback(self, callback: Callable) -> None:
        """Register a callback to be called during shutdown.

        Args:
            callback: Function to call during cleanup (can be sync or async)
        """
        self._cleanup_callbacks.append(callback)
        logger.debug("registered_cleanup_callback", callback=callback.__name__)

    def track_task(self, task: asyncio.Task) -> None:
        """Track an in-progress task for shutdown coordination.

        Args:
            task: Asyncio task to track
        """
        self._in_progress_tasks.add(task)
        task.add_done_callback(self._in_progress_tasks.discard)

    def track_subprocess(self, process: subprocess.Popen) -> None:
        """Track an in-progress subprocess for shutdown coordination.

        Args:
            process: Subprocess to track
        """
        if process.pid:
            self._in_progress_subprocesses[process.pid] = process
            logger.debug("tracking_subprocess", pid=process.pid)

    def untrack_subprocess(self, process: subprocess.Popen) -> None:
        """Remove subprocess from tracking.

        Args:
            process: Subprocess to stop tracking
        """
        if process.pid and process.pid in self._in_progress_subprocesses:
            del self._in_progress_subprocesses[process.pid]
            logger.debug("untracked_subprocess", pid=process.pid)

    def track_session(self, session) -> None:
        """Track a database session for cleanup.

        Args:
            session: SQLAlchemy session to track
        """
        self._active_sessions.add(session)
        logger.debug("tracking_db_session", session_id=id(session))

    def untrack_session(self, session) -> None:
        """Remove session from tracking.

        Args:
            session: Session to stop tracking
        """
        self._active_sessions.discard(session)
        logger.debug("untracked_db_session", session_id=id(session))

    def request_shutdown(self, signum: int | None = None, frame=None) -> None:
        """Request graceful shutdown.

        Args:
            signum: Signal number that triggered shutdown (optional)
            frame: Current stack frame (optional)
        """
        # Handle second SIGINT (ctrl-c) - force exit immediately
        if signum == signal.SIGINT:
            self._sigint_count += 1
            if self._sigint_count >= 2:
                logger.warning("force_exit_on_second_sigint", sigint_count=self._sigint_count)
                print("\n⚠️  Force exiting immediately (second ctrl-c detected)")
                os._exit(1)

        if self._shutdown_requested:
            logger.warning("shutdown_already_requested", signum=signum)
            return

        self._shutdown_requested = True
        signal_name = signal.Signals(signum).name if signum else "MANUAL"
        logger.info(
            "shutdown_requested",
            signal=signal_name,
            in_progress_tasks=len(self._in_progress_tasks),
            in_progress_subprocesses=len(self._in_progress_subprocesses),
            active_sessions=len(self._active_sessions),
        )

    def install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""
        # Store original handlers
        self._original_sigint_handler = signal.signal(signal.SIGINT, self.request_shutdown)
        self._original_sigterm_handler = signal.signal(signal.SIGTERM, self.request_shutdown)

        logger.info("signal_handlers_installed", signals=["SIGINT", "SIGTERM"])

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
        if self._original_sigterm_handler:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)

        logger.debug("signal_handlers_restored")

    async def wait_for_tasks(self) -> bool:
        """Wait for in-progress tasks to complete.

        Returns:
            True if all tasks completed, False if timeout occurred
        """
        if not self._in_progress_tasks:
            logger.info("no_tasks_to_wait_for")
            return True

        logger.info(
            "waiting_for_tasks",
            count=len(self._in_progress_tasks),
            timeout=self.shutdown_timeout,
        )

        try:
            await asyncio.wait_for(
                asyncio.gather(*self._in_progress_tasks, return_exceptions=True),
                timeout=self.shutdown_timeout,
            )
            logger.info("all_tasks_completed")
            return True
        except TimeoutError:
            logger.warning(
                "shutdown_timeout_exceeded",
                remaining_tasks=len(self._in_progress_tasks),
                timeout=self.shutdown_timeout,
            )
            return False

    async def terminate_subprocesses(self) -> bool:
        """Gracefully terminate all tracked subprocesses.

        Sends SIGTERM, waits for graceful exit, then sends SIGKILL if needed.

        Returns:
            True if all subprocesses terminated, False if force kill was needed
        """
        if not self._in_progress_subprocesses:
            logger.info("no_subprocesses_to_terminate")
            return True

        logger.info(
            "terminating_subprocesses",
            count=len(self._in_progress_subprocesses),
            timeout=self.subprocess_term_timeout,
        )

        # Send SIGTERM to all subprocesses
        for pid, process in list(self._in_progress_subprocesses.items()):
            try:
                if process.poll() is None:  # Still running
                    logger.info("sending_sigterm_to_subprocess", pid=pid)
                    process.terminate()  # Sends SIGTERM
                else:
                    # Already terminated
                    self.untrack_subprocess(process)
            except ProcessLookupError:
                logger.debug("subprocess_already_gone", pid=pid)
                self.untrack_subprocess(process)
            except Exception as e:
                logger.error("failed_to_terminate_subprocess", pid=pid, error=str(e))

        # Wait for graceful termination
        start_time = asyncio.get_event_loop().time()
        all_terminated = False

        while (asyncio.get_event_loop().time() - start_time) < self.subprocess_term_timeout:
            remaining = []
            for pid, process in list(self._in_progress_subprocesses.items()):
                if process.poll() is None:
                    remaining.append(pid)
                else:
                    logger.info("subprocess_terminated_gracefully", pid=pid)
                    self.untrack_subprocess(process)

            if not remaining:
                all_terminated = True
                break

            await asyncio.sleep(0.5)

        # Force kill any remaining processes
        if not all_terminated:
            logger.warning(
                "forcing_subprocess_termination",
                remaining=list(self._in_progress_subprocesses.keys()),
            )
            for pid, process in list(self._in_progress_subprocesses.items()):
                try:
                    if process.poll() is None:
                        logger.warning("sending_sigkill_to_subprocess", pid=pid)
                        process.kill()  # Sends SIGKILL
                        process.wait(timeout=2)
                    self.untrack_subprocess(process)
                except Exception as e:
                    logger.error("failed_to_kill_subprocess", pid=pid, error=str(e))

        return all_terminated

    async def close_database_sessions(self) -> None:
        """Close all tracked database sessions."""
        if not self._active_sessions:
            logger.debug("no_sessions_to_close")
            return

        logger.info("closing_database_sessions", count=len(self._active_sessions))

        for session in list(self._active_sessions):
            try:
                logger.debug("closing_db_session", session_id=id(session))
                session.close()
                self.untrack_session(session)
            except Exception as e:
                logger.error(
                    "failed_to_close_session",
                    session_id=id(session),
                    error=str(e),
                    exc_info=True,
                )

    async def run_cleanup_callbacks(self) -> None:
        """Execute all registered cleanup callbacks."""
        logger.info("running_cleanup_callbacks", count=len(self._cleanup_callbacks))

        for callback in self._cleanup_callbacks:
            try:
                logger.debug("executing_cleanup_callback", callback=callback.__name__)

                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()

                logger.debug("cleanup_callback_completed", callback=callback.__name__)
            except Exception as e:
                logger.error(
                    "cleanup_callback_failed",
                    callback=callback.__name__,
                    error=str(e),
                    exc_info=True,
                )

    async def shutdown(self) -> None:
        """Execute complete shutdown sequence.

        Steps:
        1. Wait for in-progress asyncio tasks (with timeout)
        2. Terminate subprocesses gracefully (SIGTERM then SIGKILL)
        3. Close tracked database sessions
        4. Run cleanup callbacks
        5. Restore signal handlers
        """
        logger.info("shutdown_sequence_started")

        all_completed = True
        subprocesses_terminated = True

        try:
            # Wait for asyncio tasks to complete
            tasks_completed = await self.wait_for_tasks()
            all_completed = tasks_completed

            if not tasks_completed:
                logger.warning("asyncio_tasks_timeout")

            # Terminate subprocesses gracefully
            subprocesses_terminated = await self.terminate_subprocesses()
            all_completed = all_completed and subprocesses_terminated

            if not subprocesses_terminated:
                logger.warning("subprocesses_force_killed")

            # Close tracked database sessions
            await self.close_database_sessions()

            # Run cleanup callbacks (includes mark_orchestrator_stopped and cleanup_db_connections)
            await self.run_cleanup_callbacks()

            logger.info(
                "shutdown_sequence_completed",
                clean_shutdown=all_completed,
                tasks_completed=tasks_completed,
                subprocesses_terminated=subprocesses_terminated,
            )

        except Exception as e:
            logger.error("shutdown_sequence_failed", error=str(e), exc_info=True)
            raise
        finally:
            # Always restore signal handlers
            self.restore_signal_handlers()


# Global singleton instance
_shutdown_handler: ShutdownHandler | None = None


def get_shutdown_handler(
    shutdown_timeout: int = 300,
    subprocess_term_timeout: int = 10
) -> ShutdownHandler:
    """Get or create the global shutdown handler.

    Args:
        shutdown_timeout: Maximum seconds to wait for tasks (default: 5 minutes)
        subprocess_term_timeout: Seconds to wait after SIGTERM before SIGKILL (default: 10)

    Returns:
        Global ShutdownHandler instance
    """
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = ShutdownHandler(
            shutdown_timeout=shutdown_timeout,
            subprocess_term_timeout=subprocess_term_timeout
        )
    return _shutdown_handler


def shutdown_requested() -> bool:
    """Check if shutdown has been requested.

    Returns:
        True if shutdown requested, False otherwise
    """
    global _shutdown_handler
    return _shutdown_handler.shutdown_requested if _shutdown_handler else False
