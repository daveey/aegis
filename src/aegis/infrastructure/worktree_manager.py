"""Git worktree manager for isolated task execution."""

import shutil
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger()


class WorktreeError(Exception):
    """Raised when worktree operations fail."""

    pass


class WorktreeManager:
    """Manages git worktrees for isolated task execution.

    Each task gets its own worktree with:
    - Isolated git branch (feat/task-<gid>)
    - Hydrated dependencies (uv sync)
    - Symlinked .env file
    """

    def __init__(
        self,
        repo_root: Path | str,
        worktree_dir: Path | str = "_worktrees",
        hydration_command: str = "uv sync",
    ):
        """Initialize worktree manager.

        Args:
            repo_root: Root of git repository
            worktree_dir: Directory to store worktrees (relative to repo_root)
            hydration_command: Command to run for dependency installation
        """
        self.repo_root = Path(repo_root).resolve()
        self.worktree_dir = self.repo_root / worktree_dir
        self.hydration_command = hydration_command

        # Ensure worktree directory exists
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

        # Ensure it's in .gitignore
        gitignore = self.repo_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            if worktree_dir not in content:
                gitignore.write_text(content + f"\n{worktree_dir}/\n")
        else:
            gitignore.write_text(f"{worktree_dir}/\n")

    def create_worktree(self, task_gid: str) -> Path:
        """Create worktree for a task.

        Args:
            task_gid: Asana task GID

        Returns:
            Path to created worktree

        Raises:
            WorktreeError: If worktree creation fails
        """
        worktree_path = self.worktree_dir / f"task-{task_gid}"
        branch_name = f"feat/task-{task_gid}"

        # Check if worktree already exists
        if worktree_path.exists():
            logger.warning(
                "worktree_exists",
                task_gid=task_gid,
                worktree_path=str(worktree_path),
            )
            # Clean up and recreate
            self.delete_worktree(task_gid)

        try:
            # Create worktree with new branch
            logger.info(
                "creating_worktree",
                task_gid=task_gid,
                branch=branch_name,
                worktree_path=str(worktree_path),
            )

            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(
                "worktree_created",
                task_gid=task_gid,
                branch=branch_name,
                worktree_path=str(worktree_path),
            )

            return worktree_path

        except subprocess.CalledProcessError as e:
            logger.error(
                "worktree_creation_failed",
                task_gid=task_gid,
                error=str(e),
                stderr=e.stderr,
            )
            raise WorktreeError(f"Failed to create worktree for task {task_gid}: {e.stderr}")

    def hydrate_worktree(self, task_gid: str) -> None:
        """Hydrate worktree with dependencies.

        Args:
            task_gid: Asana task GID

        Raises:
            WorktreeError: If hydration fails
        """
        worktree_path = self.worktree_dir / f"task-{task_gid}"

        if not worktree_path.exists():
            raise WorktreeError(f"Worktree for task {task_gid} does not exist")

        logger.info(
            "hydrating_worktree",
            task_gid=task_gid,
            command=self.hydration_command,
            worktree_path=str(worktree_path),
        )

        try:
            result = subprocess.run(
                self.hydration_command.split(),
                cwd=worktree_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 minute timeout
            )

            logger.info(
                "worktree_hydrated",
                task_gid=task_gid,
                worktree_path=str(worktree_path),
            )

        except subprocess.CalledProcessError as e:
            logger.error(
                "worktree_hydration_failed",
                task_gid=task_gid,
                error=str(e),
                stderr=e.stderr,
            )
            raise WorktreeError(f"Failed to hydrate worktree for task {task_gid}: {e.stderr}")
        except subprocess.TimeoutExpired as e:
            logger.error(
                "worktree_hydration_timeout",
                task_gid=task_gid,
                timeout=300,
            )
            raise WorktreeError(f"Hydration timeout for task {task_gid}")

    def symlink_env(self, task_gid: str) -> None:
        """Symlink .env file from repo root to worktree.

        Args:
            task_gid: Asana task GID

        Raises:
            WorktreeError: If symlinking fails
        """
        worktree_path = self.worktree_dir / f"task-{task_gid}"
        root_env = self.repo_root / ".env"
        worktree_env = worktree_path / ".env"

        if not worktree_path.exists():
            raise WorktreeError(f"Worktree for task {task_gid} does not exist")

        if not root_env.exists():
            logger.warning(
                "root_env_missing",
                root_env=str(root_env),
            )
            return

        try:
            # Remove existing .env if it exists
            if worktree_env.exists() or worktree_env.is_symlink():
                worktree_env.unlink()

            # Create symlink
            worktree_env.symlink_to(root_env)

            logger.info(
                "env_symlinked",
                task_gid=task_gid,
                worktree_env=str(worktree_env),
                root_env=str(root_env),
            )

        except OSError as e:
            logger.error(
                "env_symlink_failed",
                task_gid=task_gid,
                error=str(e),
            )
            raise WorktreeError(f"Failed to symlink .env for task {task_gid}: {e}")

    def setup_worktree(self, task_gid: str) -> Path:
        """Create and setup a complete worktree for a task.

        Performs all setup steps:
        1. Create worktree with branch
        2. Hydrate dependencies
        3. Symlink .env file

        Args:
            task_gid: Asana task GID

        Returns:
            Path to setup worktree

        Raises:
            WorktreeError: If any setup step fails
        """
        worktree_path = self.create_worktree(task_gid)
        self.hydrate_worktree(task_gid)
        self.symlink_env(task_gid)

        logger.info(
            "worktree_setup_complete",
            task_gid=task_gid,
            worktree_path=str(worktree_path),
        )

        return worktree_path

    def delete_worktree(self, task_gid: str, force: bool = False) -> None:
        """Delete worktree for a task.

        Args:
            task_gid: Asana task GID
            force: Force deletion even if worktree has uncommitted changes

        Raises:
            WorktreeError: If deletion fails
        """
        worktree_path = self.worktree_dir / f"task-{task_gid}"

        if not worktree_path.exists():
            logger.debug(
                "worktree_not_found",
                task_gid=task_gid,
                worktree_path=str(worktree_path),
            )
            return

        logger.info(
            "deleting_worktree",
            task_gid=task_gid,
            worktree_path=str(worktree_path),
            force=force,
        )

        try:
            # Remove worktree using git
            cmd = ["git", "worktree", "remove", str(worktree_path)]
            if force:
                cmd.append("--force")

            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(
                "worktree_deleted",
                task_gid=task_gid,
                worktree_path=str(worktree_path),
            )

        except subprocess.CalledProcessError as e:
            # If git worktree remove fails, try manual cleanup
            logger.warning(
                "git_worktree_remove_failed",
                task_gid=task_gid,
                error=str(e),
                stderr=e.stderr,
            )

            try:
                # Manual cleanup
                if worktree_path.exists():
                    shutil.rmtree(worktree_path)
                    logger.info(
                        "worktree_manual_cleanup",
                        task_gid=task_gid,
                        worktree_path=str(worktree_path),
                    )
            except Exception as cleanup_error:
                logger.error(
                    "worktree_cleanup_failed",
                    task_gid=task_gid,
                    error=str(cleanup_error),
                )
                raise WorktreeError(f"Failed to delete worktree for task {task_gid}: {cleanup_error}")

    def delete_branch(self, task_gid: str, force: bool = False) -> None:
        """Delete branch for a task.

        Args:
            task_gid: Asana task GID
            force: Force deletion even if branch is not fully merged

        Raises:
            WorktreeError: If deletion fails
        """
        branch_name = f"feat/task-{task_gid}"

        logger.info(
            "deleting_branch",
            task_gid=task_gid,
            branch=branch_name,
            force=force,
        )

        try:
            cmd = ["git", "branch", "-D" if force else "-d", branch_name]

            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(
                "branch_deleted",
                task_gid=task_gid,
                branch=branch_name,
            )

        except subprocess.CalledProcessError as e:
            # Branch might not exist or might be checked out elsewhere
            logger.warning(
                "branch_deletion_failed",
                task_gid=task_gid,
                branch=branch_name,
                error=str(e),
                stderr=e.stderr,
            )

    def cleanup_task(self, task_gid: str) -> None:
        """Complete cleanup for a task.

        Deletes worktree and branch in the correct order:
        1. Delete worktree (unlocks branch)
        2. Delete branch

        Args:
            task_gid: Asana task GID
        """
        logger.info("cleaning_up_task", task_gid=task_gid)

        # Delete worktree first (unlocks branch)
        self.delete_worktree(task_gid, force=True)

        # Then delete branch
        self.delete_branch(task_gid, force=True)

        logger.info("task_cleanup_complete", task_gid=task_gid)

    def prune_orphaned_worktrees(self, active_task_gids: list[str]) -> list[str]:
        """Prune orphaned worktrees that don't match active tasks.

        Args:
            active_task_gids: List of currently active task GIDs

        Returns:
            List of pruned task GIDs
        """
        logger.info("pruning_orphaned_worktrees", active_count=len(active_task_gids))

        pruned = []

        if not self.worktree_dir.exists():
            return pruned

        for worktree_path in self.worktree_dir.iterdir():
            if not worktree_path.is_dir():
                continue

            # Extract task GID from worktree name
            if worktree_path.name.startswith("task-"):
                task_gid = worktree_path.name[5:]  # Remove "task-" prefix

                if task_gid not in active_task_gids:
                    logger.info(
                        "orphaned_worktree_found",
                        task_gid=task_gid,
                        worktree_path=str(worktree_path),
                    )
                    self.cleanup_task(task_gid)
                    pruned.append(task_gid)

        logger.info("orphan_pruning_complete", pruned_count=len(pruned))

        return pruned

    def get_worktree_path(self, task_gid: str) -> Path:
        """Get path to worktree for a task.

        Args:
            task_gid: Asana task GID

        Returns:
            Path to worktree (may or may not exist)
        """
        return self.worktree_dir / f"task-{task_gid}"

    def worktree_exists(self, task_gid: str) -> bool:
        """Check if worktree exists for a task.

        Args:
            task_gid: Asana task GID

        Returns:
            True if worktree exists
        """
        return self.get_worktree_path(task_gid).exists()
