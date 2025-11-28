"""Memory manager with file locking for shared memory files."""

import contextlib
import fcntl
import time
from pathlib import Path
from typing import Generator

import structlog

logger = structlog.get_logger()


class MemoryLockError(Exception):
    """Raised when memory file lock cannot be acquired."""

    pass


class MemoryManager:
    """Manages access to shared memory files with file-based locking.

    Ensures thread-safe and process-safe access to memory files like
    swarm_memory.md, user_preferences.md, etc.
    """

    def __init__(self, memory_dir: Path | str = "."):
        """Initialize memory manager.

        Args:
            memory_dir: Directory containing memory files
        """
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_path(self, memory_file: str) -> Path:
        """Get path to lock file for a memory file.

        Args:
            memory_file: Name of memory file (e.g., 'swarm_memory.md')

        Returns:
            Path to lock file (e.g., '.swarm_memory.md.lock')
        """
        return self.memory_dir / f".{memory_file}.lock"

    @contextlib.contextmanager
    def lock(
        self,
        memory_file: str,
        timeout: int = 30,
        poll_interval: float = 0.1,
    ) -> Generator[Path, None, None]:
        """Acquire exclusive lock on memory file.

        Args:
            memory_file: Name of memory file to lock
            timeout: Maximum seconds to wait for lock
            poll_interval: Seconds between lock attempts

        Yields:
            Path to the memory file

        Raises:
            MemoryLockError: If lock cannot be acquired within timeout
        """
        lock_path = self._get_lock_path(memory_file)
        memory_path = self.memory_dir / memory_file

        # Create memory file if it doesn't exist
        memory_path.touch(exist_ok=True)

        # Try to acquire lock
        lock_fd = None
        start_time = time.time()

        try:
            while True:
                try:
                    # Open lock file
                    lock_fd = open(lock_path, "w")

                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    logger.debug(
                        "memory_lock_acquired",
                        memory_file=memory_file,
                        lock_path=str(lock_path),
                    )
                    break

                except (IOError, OSError) as e:
                    # Lock is held by another process
                    elapsed = time.time() - start_time
                    if elapsed >= timeout:
                        logger.error(
                            "memory_lock_timeout",
                            memory_file=memory_file,
                            timeout=timeout,
                            error=str(e),
                        )
                        raise MemoryLockError(
                            f"Could not acquire lock on {memory_file} within {timeout}s"
                        )

                    # Wait and retry
                    if lock_fd:
                        lock_fd.close()
                        lock_fd = None

                    time.sleep(poll_interval)

            # Lock acquired - yield memory file path
            yield memory_path

        finally:
            # Release lock
            if lock_fd:
                try:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                    lock_fd.close()
                    logger.debug(
                        "memory_lock_released",
                        memory_file=memory_file,
                        lock_path=str(lock_path),
                    )
                except Exception as e:
                    logger.warning(
                        "memory_lock_release_failed",
                        memory_file=memory_file,
                        error=str(e),
                    )

            # Clean up lock file
            try:
                if lock_path.exists():
                    lock_path.unlink()
            except OSError as e:
                logger.warning(
                    "lock_file_cleanup_failed",
                    lock_path=str(lock_path),
                    error=str(e),
                )

    def read(self, memory_file: str, timeout: int = 30) -> str:
        """Read memory file with lock.

        Args:
            memory_file: Name of memory file to read
            timeout: Maximum seconds to wait for lock

        Returns:
            Contents of memory file
        """
        with self.lock(memory_file, timeout=timeout) as path:
            if path.exists():
                return path.read_text(encoding="utf-8")
            return ""

    def write(self, memory_file: str, content: str, timeout: int = 30) -> None:
        """Write memory file with lock.

        Args:
            memory_file: Name of memory file to write
            content: Content to write
            timeout: Maximum seconds to wait for lock
        """
        with self.lock(memory_file, timeout=timeout) as path:
            path.write_text(content, encoding="utf-8")
            logger.info(
                "memory_file_written",
                memory_file=memory_file,
                size=len(content),
            )

    def append(self, memory_file: str, content: str, timeout: int = 30) -> None:
        """Append to memory file with lock.

        Args:
            memory_file: Name of memory file to append to
            content: Content to append
            timeout: Maximum seconds to wait for lock
        """
        with self.lock(memory_file, timeout=timeout) as path:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(existing + content, encoding="utf-8")
            logger.info(
                "memory_file_appended",
                memory_file=memory_file,
                appended_size=len(content),
            )

    def compact(
        self,
        memory_file: str,
        max_tokens: int = 20000,
        timeout: int = 30,
    ) -> bool:
        """Compact memory file if it exceeds token limit.

        Summarizes the top 50% of content into a "History" section.

        Args:
            memory_file: Name of memory file to compact
            max_tokens: Token threshold for compaction
            timeout: Maximum seconds to wait for lock

        Returns:
            True if compaction was performed, False otherwise
        """
        with self.lock(memory_file, timeout=timeout) as path:
            if not path.exists():
                return False

            content = path.read_text(encoding="utf-8")

            # Rough token estimate (1 token ≈ 4 characters)
            estimated_tokens = len(content) / 4

            if estimated_tokens <= max_tokens:
                return False

            logger.info(
                "memory_compaction_needed",
                memory_file=memory_file,
                estimated_tokens=estimated_tokens,
                max_tokens=max_tokens,
            )

            # Split into lines
            lines = content.split("\n")
            split_point = len(lines) // 2

            # Create history section from top 50%
            history_lines = lines[:split_point]
            recent_lines = lines[split_point:]

            compacted_content = "# History (Summarized)\n\n"
            compacted_content += "\n".join(history_lines)
            compacted_content += "\n\n---\n\n# Recent Context\n\n"
            compacted_content += "\n".join(recent_lines)

            path.write_text(compacted_content, encoding="utf-8")

            logger.info(
                "memory_compacted",
                memory_file=memory_file,
                original_size=len(content),
                compacted_size=len(compacted_content),
            )

            return True
