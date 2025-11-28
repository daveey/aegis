"""Reviewer Agent - The Gatekeeper."""

import subprocess
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask
from aegis.infrastructure.worktree_manager import WorktreeManager

logger = structlog.get_logger()


class ReviewerAgent(BaseAgent):
    """Reviewer Agent verifies code quality before merge.

    Responsibilities:
    - Review code quality and correctness
    - Run full test suite
    - Check security and performance
    - Approve for merge OR send back to Worker
    """

    def __init__(self, *args, worktree_manager: WorktreeManager, **kwargs):
        """Initialize Reviewer Agent.

        Args:
            worktree_manager: WorktreeManager instance
        """
        super().__init__(*args, **kwargs)
        self.worktree_manager = worktree_manager

    @property
    def name(self) -> str:
        """Agent name."""
        return "Reviewer Agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "✓"

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for code review.

        Args:
            task: AsanaTask to review

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "reviewer.md"

        if not prompt_file.exists():
            logger.warning("reviewer_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Review the implementation and run all tests."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

        worktree_path = self.worktree_manager.get_worktree_path(task.gid)

        # Add task context
        context = f"""
# Task to Review

**Task Name**: {task.name}

**Description**:
{task.notes or "(No description provided)"}

**Worktree**: {worktree_path}
**Branch**: feat/task-{task.gid}

---

{base_prompt}

---

# Your Review

Perform a thorough code review following the checklist.
Run all tests and verify quality standards.
"""

        return context

    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute code review.

        Args:
            task: AsanaTask to review
            **kwargs: Additional arguments (interactive, etc.)

        Returns:
            AgentResult with review decision
        """
        interactive = kwargs.get("interactive", False)
        logger.info("review_start", task_gid=task.gid, task_name=task.name, interactive=interactive)

        worktree_path = self.worktree_manager.get_worktree_path(task.gid)

        if not worktree_path.exists():
            logger.error("worktree_not_found", task_gid=task.gid, worktree_path=str(worktree_path))
            return AgentResult(
                success=False,
                error="Worktree not found - implementation may have failed",
                summary="Review cannot proceed without worktree",
            )

        try:
            # First, run tests to get objective results
            test_results = await self._run_tests(task.gid, worktree_path)

            # Generate and run review prompt IN THE WORKTREE
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(
                prompt,
                cwd=worktree_path,
                timeout=900,  # 15 minute timeout for review
                interactive=interactive,
            )

            if interactive:
                return AgentResult(
                    success=True,
                    summary="Interactive session completed",
                    details=["Ran interactively"],
                )

            if returncode != 0:
                logger.error("review_failed", task_gid=task.gid, stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Review failed during execution",
                )

            # Parse review decision
            approved, issues = self._parse_review_decision(stdout)

            if approved:
                logger.info("review_approved", task_gid=task.gid)
                return AgentResult(
                    success=True,
                    next_agent="Merger",
                    next_section="Merging",
                    summary="Code review passed - approved for merge",
                    details=[
                        f"Tests: {test_results}",
                        "Code quality: Excellent",
                        "Security: No issues found",
                        "Ready for integration",
                    ],
                    clear_session_id=True,  # Merger gets fresh session
                )
            else:
                logger.info("review_rejected", task_gid=task.gid, issues=len(issues))
                return AgentResult(
                    success=False,
                    next_agent="Worker",
                    next_section="Ready Queue",
                    summary=f"Code review found {len(issues)} issue(s) - needs revision",
                    details=issues[:5],  # First 5 issues
                    clear_session_id=False,  # Worker continues same session
                )

        except Exception as e:
            logger.error("review_error", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                error=str(e),
                summary="Review encountered an error",
            )

    async def _run_tests(self, task_gid: str, worktree_path: Path) -> str:
        """Run test suite in worktree.

        Args:
            task_gid: Task GID
            worktree_path: Path to worktree

        Returns:
            Test results summary
        """
        try:
            logger.info("running_tests", task_gid=task_gid, worktree_path=str(worktree_path))

            result = subprocess.run(
                ["pytest", "tests/", "-v", "--tb=short"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # Parse test results
            if "passed" in result.stdout:
                import re

                match = re.search(r"(\d+) passed", result.stdout)
                if match:
                    passed_count = match.group(1)
                    return f"{passed_count} tests passed"

            if result.returncode == 0:
                return "All tests passed"
            else:
                return "Some tests failed"

        except subprocess.TimeoutExpired:
            logger.error("tests_timeout", task_gid=task_gid)
            return "Tests timed out"
        except FileNotFoundError:
            logger.warning("pytest_not_found", task_gid=task_gid)
            return "pytest not available"
        except Exception as e:
            logger.error("tests_error", task_gid=task_gid, error=str(e))
            return f"Test error: {str(e)}"

    def _parse_review_decision(self, output: str) -> tuple[bool, list[str]]:
        """Parse review decision from output.

        Args:
            output: Claude Code stdout

        Returns:
            Tuple of (approved, list_of_issues)
        """
        # Check for approval
        approved = (
            "Review: APPROVED" in output
            or "APPROVED ✅" in output
            or "Ready for Merge: ✅" in output
        )

        # Check for rejection
        rejected = (
            "Review: REVISIONS NEEDED" in output
            or "REVISIONS NEEDED ❌" in output
            or "Issues Found:" in output
        )

        # Extract issues if rejected
        issues = []
        if rejected:
            import re

            # Find "Issues Found" section
            issues_match = re.search(
                r"Issues Found:(.+?)(?:\*\*Test Results\*\*|$)",
                output,
                re.IGNORECASE | re.DOTALL,
            )
            if issues_match:
                issues_text = issues_match.group(1)
                # Extract individual issues (look for numbered or bulleted lists)
                issue_lines = re.findall(r"(?:^|\n)\s*(?:\d+\.|-|\*)\s*(.+?)(?:\n|$)", issues_text)
                issues = [issue.strip() for issue in issue_lines if issue.strip()]

        # Default to approved if unclear and no issues found
        if not rejected and not issues:
            approved = True

        return approved, issues
