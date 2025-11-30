"""Refactor Agent - Scans for refactoring opportunities."""

from aegis.agents.base import BaseAgent, AgentResult, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject

class RefactorAgent(BaseAgent):
    """Agent that scans codebase for refactoring opportunities."""

    @property
    def name(self) -> str:
        return "refactor_agent"

    @property
    def status_emoji(self) -> str:
        return "🧹"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.PROJECT

    def get_prompt(self, target: AsanaTask | AsanaProject) -> str:
        """Generate prompt for refactoring analysis."""
        return """
        You are an expert software architect specializing in code quality and refactoring.

        Your task is to scan the codebase for areas that need refactoring.
        Focus on:
        1. Complex functions or classes that violate Single Responsibility Principle.
        2. Legacy code patterns that should be updated.
        3. Poorly named variables or functions.
        4. Lack of type hints or documentation.
        5. Performance bottlenecks.

        For each opportunity found, you must:
        1. Describe the issue clearly.
        2. Propose a specific refactoring plan.
        3. Estimate the effort (Low/Medium/High).

        If you find significant issues, create a NEW TASK for each one in the 'Proposals' section.
        Use the `asana_create_task` tool if available, or output a structured JSON list of tasks to create.

        Since I cannot directly create tasks yet, please output the proposals in this format:

        PROPOSAL:
        Title: Refactor [Component]: [Brief Description]
        Description:
        [Detailed description of the issue and proposed fix]

        Effort: [Effort]
        """

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute refactor analysis."""
        if not isinstance(target, AsanaProject):
             return AgentResult(success=False, error="RefactorAgent only supports Projects")

        # For now, we'll just run a simple analysis
        # In the future, we might want to target specific directories based on task description

        prompt = self.get_prompt(target)

        stdout, stderr, returncode = await self.run_claude_code(prompt)

        if returncode != 0:
            return AgentResult(
                success=False,
                error=f"Refactor analysis failed: {stderr}",
                summary="Refactor analysis failed",
            )

        # Parse output and create tasks (TODO: Implement parsing logic)
        # For now, we'll just report success and let the user review the logs/comments

        return AgentResult(
            success=True,
            summary="Refactor analysis complete. See logs for proposals.",
            details=["Ran analysis on codebase"],
            next_section="Done", # Ephemeral tasks go to Done
        )
