"""Planner Agent - The Architect."""

from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject
from aegis.utils.asana_utils import format_asana_resource

logger = structlog.get_logger(__name__)


class PlannerAgent(BaseAgent):
    """Planner Agent designs implementation architecture.

    Responsibilities:
    - Create detailed implementation plans
    - Design architecture and component structure
    - Identify all files and changes needed
    - Specify testing strategy
    - Use iterative Plan → Critique → Refine process
    """

    @property
    def name(self) -> str:
        """Agent name."""
        return "planner_agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "📐"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.TASK

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for planning.

        Args:
            task: AsanaTask to plan

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "planner.prompt.txt"

        if not prompt_file.exists():
            logger.warning("planner_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Create a detailed implementation plan for this task."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

        # Load swarm memory for context
        memory_file = self.repo_root / "swarm_memory.md"
        memory_context = ""
        if memory_file.exists():
            memory_context = memory_file.read_text(encoding="utf-8")

        # Add task context
        context = f"""
# Task to Plan

**Task Name**: {task.name}

**Description**:
{task.notes or "(No description provided)"}

**Project**: {task.projects[0].name if task.projects else "Unknown"}

**Repository**: {self.repo_root}

---

# Swarm Memory (Context)

{memory_context}

---

{base_prompt}

---

# Your Plan

Create a comprehensive implementation plan following the format specified above.
Use the Plan → Critique → Refine process (2-3 iterations) to ensure quality.
"""

        return context

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute planning.

        Args:
            target: AsanaTask to plan
            **kwargs: Additional arguments (interactive, etc.)

        Returns:
            AgentResult with plan and next steps
        """
        if not isinstance(target, AsanaTask):
             return AgentResult(success=False, error="PlannerAgent only supports Tasks")

        task = target
        interactive = kwargs.get("interactive", False)
        logger.info("planning_start", task=format_asana_resource(task), interactive=interactive)

        try:
            # Generate and run prompt
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(
                prompt,
                timeout=600,  # 10 min timeout
                interactive=interactive,
            )

            if interactive:
                return AgentResult(
                    success=True,
                    summary="Interactive session completed",
                    details=["Ran interactively"],
                )

            if returncode != 0:
                logger.error("planning_failed", task=format_asana_resource(task), stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Planning failed due to execution error",
                )

            # Check for blocker
            if "## BLOCKER ENCOUNTERED" in stdout:
                import re
                blocker_match = re.search(
                    r"## BLOCKER ENCOUNTERED\s*(.+?)(?:$)",
                    stdout,
                    re.IGNORECASE | re.DOTALL,
                )
                blocker_details = blocker_match.group(1).strip() if blocker_match else "No details provided"

                return AgentResult(
                    success=False,
                    next_agent="Triage",
                    next_section="Clarification Needed",
                    summary="Planning blocked",
                    details=["Blocker encountered:", blocker_details[:500]],
                    clear_session_id=False,
                    assignee="me",
                )

            # Plan is complete - route to Worker
            plan_summary = self._extract_summary(stdout)

            logger.info("planning_complete", task=format_asana_resource(task), plan_length=len(stdout))

            # Post plan as comment
            # (The orchestrator will handle posting via post_result_comment)

            return AgentResult(
                success=True,
                next_agent="Worker",
                next_section="Ready Queue",
                summary=f"Implementation plan created: {plan_summary}",
                details=[
                    f"Plan size: {len(stdout)} characters",
                    "Plan posted in task comments",
                    "Ready for Worker Agent execution",
                ],
                clear_session_id=True,  # Worker gets fresh session
            )

        except Exception as e:
            logger.error("planning_error", task=format_asana_resource(task), error=str(e))
            return AgentResult(
                success=False,
                error=str(e),
                summary="Planning encountered an error",
            )

    def _extract_summary(self, plan: str) -> str:
        """Extract brief summary from plan.

        Args:
            plan: Full plan text

        Returns:
            Brief summary (first line or objective)
        """
        # Try to find Objective line
        import re

        obj_match = re.search(r"\*\*Objective\*\*:\s*(.+?)(?:\n|$)", plan, re.IGNORECASE)
        if obj_match:
            return obj_match.group(1).strip()

        # Fallback: first non-empty line
        lines = [line.strip() for line in plan.split("\n") if line.strip()]
        if lines:
            return lines[0][:100]  # First 100 chars

        return "See plan details in comments"
