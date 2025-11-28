"""Worker Agent - The Builder."""

import subprocess
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask
from aegis.infrastructure.worktree_manager import WorktreeManager

logger = structlog.get_logger()


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
        return "Worker Agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "🔨"

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for implementation.

        Args:
            task: AsanaTask to implement

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "worker.md"

        if not prompt_file.exists():
            logger.warning("worker_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Implement the task according to the plan."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

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

    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute implementation.

        Args:
            task: AsanaTask to implement

        Returns:
            AgentResult with implementation status
        """
        logger.info("worker_start", task_gid=task.gid, task_name=task.name)

        worktree_path = None

        try:
            # Setup worktree
            logger.info("setting_up_worktree", task_gid=task.gid)
            worktree_path = self.worktree_manager.setup_worktree(task.gid)

            # Generate and run prompt IN THE WORKTREE
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(
                prompt,
                cwd=worktree_path,
                timeout=1800,  # 30 minute timeout for implementation
            )

            if returncode != 0:
                logger.error("worker_failed", task_gid=task.gid, stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Implementation failed during execution",
                )

            # Rebase on main
            logger.info("rebasing_on_main", task_gid=task.gid)
            await self._rebase_on_main(task.gid, worktree_path)

            # Extract implementation summary
            files_created, files_modified, tests_status = self._parse_implementation_summary(stdout)

            logger.info(
                "worker_complete",
                task_gid=task.gid,
                files_created=len(files_created),
                files_modified=len(files_modified),
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
            logger.error("worker_error", task_gid=task.gid, error=str(e))

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

        return files_created, files_modified, tests_status
