"""Consolidator Agent - Scans for code duplication."""

from aegis.agents.base import BaseAgent, AgentResult, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject

class ConsolidatorAgent(BaseAgent):
    """Agent that scans codebase for duplication and consolidation opportunities."""

    @property
    def name(self) -> str:
        return "consolidator_agent"

    @property
    def status_emoji(self) -> str:
        return "♻️"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.PROJECT

    def get_prompt(self, target: AsanaTask | AsanaProject) -> str:
        """Generate prompt for consolidation analysis."""
        return """
        You are an expert software engineer specializing in DRY (Don't Repeat Yourself) principles.

        Your task is to scan the codebase for duplicated code or logic.
        Focus on:
        1. Similar functions or classes in different files.
        2. Repeated configuration or setup logic.
        3. Copy-pasted code blocks.

        For each opportunity found, you must:
        1. Identify the duplicated locations.
        2. Propose a shared abstraction or utility.
        3. Estimate the effort (Low/Medium/High).

        If you find significant issues, create a NEW TASK for each one in the 'Proposals' section.

        PROPOSAL:
        Title: Consolidate [Functionality]: [Brief Description]
        Description:
        [Detailed description of duplication and proposed fix]

        Effort: [Effort]
        """

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute consolidation analysis."""
        if not isinstance(target, AsanaProject):
             return AgentResult(success=False, error="ConsolidatorAgent only supports Projects")

        prompt = self.get_prompt(target)

        stdout, stderr, returncode = await self.run_claude_code(prompt)

        if returncode != 0:
            return AgentResult(
                success=False,
                error=f"Consolidation analysis failed: {stderr}",
                summary="Consolidation analysis failed",
            )

        return AgentResult(
            success=True,
            summary="Consolidation analysis complete. See logs for proposals.",
            details=["Ran duplication analysis"],
            next_section="Done",
        )
