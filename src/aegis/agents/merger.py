"""Merger Agent - The Integrator."""

import subprocess
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask
from aegis.infrastructure.worktree_manager import WorktreeManager

logger = structlog.get_logger()


class MergerAgent(BaseAgent):
    """Merger Agent safely integrates code into main branch.

    Responsibilities:
    - Verify merge approval status
    - Execute safe merge protocol in isolated worktree
    - Run tests after merge
    - Push to main
    - Clean up worktrees and branches
    """

    def __init__(self, *args, worktree_manager: WorktreeManager, **kwargs):
        """Initialize Merger Agent.

        Args:
            worktree_manager: WorktreeManager instance
        """
        super().__init__(*args, **kwargs)
        self.worktree_manager = worktree_manager
        self.merger_worktree = self.repo_root / "_worktrees" / "merger_staging"

    @property
    def name(self) -> str:
        """Agent name."""
        return "Merger Agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "🔀"

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for merge operation.

        Args:
            task: AsanaTask to merge

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "merger.md"

        if not prompt_file.exists():
            logger.warning("merger_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Execute safe merge protocol to integrate code into main."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

        # Add task context
        context = f"""
# Task to Merge

**Task Name**: {task.name}

**Description**:
{task.notes or "(No description provided)"}

**Feature Branch**: feat/task-{task.gid}
**Merge Approval**: {task.merge_approval or "Auto-Approve"}

**Merger Worktree**: {self.merger_worktree}

---

{base_prompt}

---

# Execute Merge

Follow the Safe Merge Protocol exactly as specified.
NEVER skip steps or force anything.
"""

        return context

    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute safe merge.

        Args:
            task: AsanaTask to merge
            **kwargs: Additional arguments (interactive, etc.)

        Returns:
            AgentResult with merge status
        """
        interactive = kwargs.get("interactive", False)
        logger.info("merge_start", task_gid=task.gid, task_name=task.name, interactive=interactive)

        try:
            # Check merge approval
            if not self._check_merge_approval(task) and not interactive:
                logger.warning("merge_approval_required", task_gid=task.gid)
                return AgentResult(
                    success=False,
                    next_section="Clarification Needed",
                    summary="Manual merge approval required",
                    details=["Merge Approval is set to 'Manual Check'", "Please review and approve manually"],
                )

            # Ensure merger worktree exists
            self._setup_merger_worktree()

            if interactive:
                # Interactive merge - just run bash in the worktree or similar?
                # Actually, for merger, interactive might mean running the merge commands interactively?
                # Or just giving the user a shell in the merger worktree?
                # The prompt implies running the AGENT interactively, which means running Claude Code interactively.
                # So we should generate the prompt and run it.

                prompt = self.get_prompt(task)
                await self.run_claude_code(
                    prompt,
                    cwd=self.merger_worktree,
                    interactive=True,
                )
                return AgentResult(
                    success=True,
                    summary="Interactive session completed",
                    details=["Ran interactively"],
                )

            # Execute merge in isolated worktree
            merge_commit, test_results = await self._execute_safe_merge(task)

            # Cleanup
            self.worktree_manager.cleanup_task(task.gid)

            logger.info("merge_complete", task_gid=task.gid, merge_commit=merge_commit)

            return AgentResult(
                success=True,
                next_section="Done",
                summary="Code successfully merged to main",
                details=[
                    f"Merge commit: {merge_commit}",
                    f"Tests: {test_results}",
                    f"Branch cleaned up: feat/task-{task.gid}",
                    "Worktree removed",
                ],
            )

        except MergeConflictError as e:
            logger.error("merge_conflict", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                next_section="Clarification Needed",
                summary="Merge conflict requires manual resolution",
                details=[str(e)],
            )

        except MergeTestFailureError as e:
            logger.error("merge_test_failure", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                next_agent="Reviewer",
                next_section="Review",
                summary="Tests failed after merge - needs investigation",
                details=[str(e)],
            )

        except Exception as e:
            logger.error("merge_error", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                error=str(e),
                summary="Merge encountered an error",
            )

    def _check_merge_approval(self, task: AsanaTask) -> bool:
        """Check if task has merge approval.

        Args:
            task: AsanaTask

        Returns:
            True if approved
        """
        approval = task.merge_approval
        return approval in ["Auto-Approve", "Approved"]

    def _setup_merger_worktree(self) -> None:
        """Setup merger staging worktree if it doesn't exist."""
        if not self.merger_worktree.exists():
            logger.info("creating_merger_worktree", path=str(self.merger_worktree))
            subprocess.run(
                ["git", "worktree", "add", str(self.merger_worktree), "main"],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
            )

        # Ensure it's on main and up-to-date
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=self.merger_worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=self.merger_worktree,
            check=True,
            capture_output=True,
        )

    async def _execute_safe_merge(self, task: AsanaTask) -> tuple[str, str]:
        """Execute safe merge protocol.

        Args:
            task: AsanaTask

        Returns:
            Tuple of (merge_commit_hash, test_results)

        Raises:
            MergeConflictError: If merge conflicts
            MergeTestFailureError: If tests fail after merge
        """
        branch_name = f"feat/task-{task.gid}"

        try:
            # Fetch latest
            subprocess.run(
                ["git", "fetch", "origin", "main", branch_name],
                cwd=self.merger_worktree,
                check=True,
                capture_output=True,
            )

            # Merge with no-ff
            result = subprocess.run(
                ["git", "merge", "--no-ff", branch_name, "-m", f"Merge {branch_name}: {task.name}"],
                cwd=self.merger_worktree,
                capture_output=True,
                text=True,
            )

            # Check for conflicts
            if result.returncode != 0:
                if "CONFLICT" in result.stdout or "CONFLICT" in result.stderr:
                    # Abort merge
                    subprocess.run(
                        ["git", "merge", "--abort"],
                        cwd=self.merger_worktree,
                        capture_output=True,
                    )
                    raise MergeConflictError(f"Merge conflicts detected:\n{result.stderr}")
                else:
                    raise Exception(f"Merge failed: {result.stderr}")

            # Get merge commit hash
            merge_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.merger_worktree,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            # Run tests
            logger.info("running_post_merge_tests", task_gid=task.gid)
            test_result = subprocess.run(
                ["pytest", "tests/", "-v"],
                cwd=self.merger_worktree,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if test_result.returncode != 0:
                # Tests failed - abort merge
                subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    cwd=self.merger_worktree,
                    check=True,
                    capture_output=True,
                )
                raise MergeTestFailureError(f"Tests failed after merge:\n{test_result.stdout}")

            test_results = "All tests passed"

            # Push to main
            logger.info("pushing_to_main", task_gid=task.gid)
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.merger_worktree,
                check=True,
                capture_output=True,
            )

            # Delete remote branch
            logger.info("deleting_remote_branch", branch=branch_name)
            subprocess.run(
                ["git", "push", "origin", "--delete", branch_name],
                cwd=self.merger_worktree,
                capture_output=True,  # Don't fail if branch already deleted
            )

            return merge_commit[:8], test_results

        except subprocess.TimeoutExpired:
            raise MergeTestFailureError("Tests timed out after merge")


class MergeConflictError(Exception):
    """Raised when merge conflicts are detected."""

    pass


class MergeTestFailureError(Exception):
    """Raised when tests fail after merge."""

    pass
