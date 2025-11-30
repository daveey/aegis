"""PID manager for singleton orchestrator process."""

import os
import signal
from pathlib import Path

import structlog

logger = structlog.get_logger()


class PIDLockError(Exception):
    """Raised when PID lock cannot be acquired."""

    pass


class PIDManager:
    """Manages PID file for singleton orchestrator process.

    Ensures only one instance of the orchestrator runs at a time.
    """

    def __init__(self, project_gid: str | None = None, pid_file: Path | str | None = None, root_dir: Path | str | None = None):
        """Initialize PID manager.

        Args:
            project_gid: Asana Project GID (for centralized PID management)
            pid_file: Explicit path to PID file (legacy/override)
            root_dir: Root directory for the project (default: current directory)
        """
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()

        if pid_file:
            self.pid_file = Path(pid_file)
        elif project_gid:
            # Use centralized PID location for tracked projects
            self.pid_file = self.root_dir / ".aegis" / "pids" / f"{project_gid}.pid"
        else:
            # Default legacy location
            self.pid_file = self.root_dir / ".aegis" / "pid"

        if not self.pid_file.parent.exists():
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._locked = False

    def acquire(self) -> None:
        """Acquire PID lock.

        Raises:
            PIDLockError: If lock is already held by another process
        """
        if self.pid_file.exists():
            # Check if existing process is still running
            try:
                with open(self.pid_file) as f:
                    existing_pid = int(f.read().strip())

                # Check if process exists
                try:
                    os.kill(existing_pid, 0)  # Signal 0 doesn't kill, just checks existence
                    # Process exists
                    logger.error(
                        "pid_lock_held",
                        existing_pid=existing_pid,
                        pid_file=str(self.pid_file),
                    )
                    raise PIDLockError(
                        f"Orchestrator already running with PID {existing_pid}. "
                        f"Use 'aegis stop' to shut it down first."
                    )
                except ProcessLookupError:
                    # Process doesn't exist - stale PID file
                    logger.warning(
                        "stale_pid_file",
                        existing_pid=existing_pid,
                        pid_file=str(self.pid_file),
                    )
                    self.pid_file.unlink()
            except (ValueError, IOError) as e:
                logger.warning(
                    "invalid_pid_file",
                    error=str(e),
                    pid_file=str(self.pid_file),
                )
                self.pid_file.unlink()

        # Write current PID
        current_pid = os.getpid()
        with open(self.pid_file, "w") as f:
            f.write(str(current_pid))

        self._locked = True
        logger.info("pid_lock_acquired", pid=current_pid, pid_file=str(self.pid_file))

    def release(self) -> None:
        """Release PID lock by removing PID file."""
        if self._locked and self.pid_file.exists():
            try:
                self.pid_file.unlink()
                logger.info("pid_lock_released", pid_file=str(self.pid_file))
            except OSError as e:
                logger.warning("pid_lock_release_failed", error=str(e), pid_file=str(self.pid_file))
            finally:
                self._locked = False

    def get_running_pid(self) -> int | None:
        """Get PID of running orchestrator process.

        Returns:
            PID of running process, or None if not running
        """
        if not self.pid_file.exists():
            return None

        try:
            with open(self.pid_file) as f:
                pid = int(f.read().strip())

            # Verify process exists
            try:
                os.kill(pid, 0)
                return pid
            except ProcessLookupError:
                return None
        except (ValueError, IOError):
            return None

    def stop_orchestrator(self, timeout: int = 30) -> bool:
        """Stop running orchestrator process.

        Args:
            timeout: Seconds to wait for graceful shutdown before SIGKILL

        Returns:
            True if process was stopped, False if no process was running
        """
        pid = self.get_running_pid()
        if pid is None:
            logger.info("no_orchestrator_running")
            return False

        logger.info("stopping_orchestrator", pid=pid)

        try:
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for process to exit
            import time

            elapsed = 0
            while elapsed < timeout:
                try:
                    os.kill(pid, 0)  # Check if still running
                    time.sleep(1)
                    elapsed += 1
                except ProcessLookupError:
                    # Process exited
                    logger.info("orchestrator_stopped_gracefully", pid=pid, elapsed=elapsed)
                    if self.pid_file.exists():
                        self.pid_file.unlink()
                    return True

            # Timeout - force kill
            logger.warning("orchestrator_timeout_forcing_kill", pid=pid, timeout=timeout)
            os.kill(pid, signal.SIGKILL)
            if self.pid_file.exists():
                self.pid_file.unlink()
            return True

        except ProcessLookupError:
            # Process already gone
            logger.info("orchestrator_already_stopped", pid=pid)
            if self.pid_file.exists():
                self.pid_file.unlink()
            return False
        except PermissionError as e:
            logger.error("orchestrator_stop_permission_denied", pid=pid, error=str(e))
            raise PIDLockError(f"Permission denied when trying to stop process {pid}")

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False
