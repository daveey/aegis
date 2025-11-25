"""Graceful shutdown handling for Aegis.

This module provides signal handling and shutdown coordination to ensure:
- Clean termination without losing work
- In-progress tasks can complete
- State is saved to database
- Resources are properly cleaned up
"""

import asyncio
import signal
import sys
from typing import Callable, Optional

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

    def __init__(self, shutdown_timeout: int = 300):
        """Initialize shutdown handler.

        Args:
            shutdown_timeout: Maximum seconds to wait for tasks to complete (default: 5 minutes)
        """
        self.shutdown_timeout = shutdown_timeout
        self._shutdown_requested = False
        self._original_sigint_handler = None
        self._original_sigterm_handler = None
        self._cleanup_callbacks: list[Callable] = []
        self._in_progress_tasks: set[asyncio.Task] = set()

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

    def request_shutdown(self, signum: Optional[int] = None, frame=None) -> None:
        """Request graceful shutdown.

        Args:
            signum: Signal number that triggered shutdown (optional)
            frame: Current stack frame (optional)
        """
        if self._shutdown_requested:
            logger.warning("shutdown_already_requested", signum=signum)
            return

        self._shutdown_requested = True
        signal_name = signal.Signals(signum).name if signum else "MANUAL"
        logger.info(
            "shutdown_requested",
            signal=signal_name,
            in_progress_tasks=len(self._in_progress_tasks),
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
        except asyncio.TimeoutError:
            logger.warning(
                "shutdown_timeout_exceeded",
                remaining_tasks=len(self._in_progress_tasks),
                timeout=self.shutdown_timeout,
            )
            return False

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
        1. Wait for in-progress tasks (with timeout)
        2. Run cleanup callbacks
        3. Restore signal handlers
        """
        logger.info("shutdown_sequence_started")

        try:
            # Wait for tasks to complete
            all_completed = await self.wait_for_tasks()

            if not all_completed:
                logger.warning("forcing_shutdown_after_timeout")

            # Run cleanup callbacks
            await self.run_cleanup_callbacks()

            logger.info("shutdown_sequence_completed", clean_shutdown=all_completed)

        except Exception as e:
            logger.error("shutdown_sequence_failed", error=str(e), exc_info=True)
            raise
        finally:
            # Always restore signal handlers
            self.restore_signal_handlers()


# Global singleton instance
_shutdown_handler: Optional[ShutdownHandler] = None


def get_shutdown_handler(shutdown_timeout: int = 300) -> ShutdownHandler:
    """Get or create the global shutdown handler.

    Args:
        shutdown_timeout: Maximum seconds to wait for tasks (default: 5 minutes)

    Returns:
        Global ShutdownHandler instance
    """
    global _shutdown_handler
    if _shutdown_handler is None:
        _shutdown_handler = ShutdownHandler(shutdown_timeout=shutdown_timeout)
    return _shutdown_handler


def shutdown_requested() -> bool:
    """Check if shutdown has been requested.

    Returns:
        True if shutdown requested, False otherwise
    """
    global _shutdown_handler
    return _shutdown_handler.shutdown_requested if _shutdown_handler else False
