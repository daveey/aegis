"""Ideation Agent - Suggests new features."""

from aegis.agents.base import BaseAgent, AgentResult, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject

class IdeationAgent(BaseAgent):
    """Agent that suggests new features and improvements."""

    @property
    def name(self) -> str:
        return "ideation_agent"

    @property
    def status_emoji(self) -> str:
        return "💡"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.PROJECT

    def get_prompt(self, target: AsanaTask | AsanaProject) -> str:
        """Generate prompt for ideation."""
        context = target.notes or "General improvement"
        return f"""
        You are a creative product manager and engineer.

        Your task is to suggest new features or improvements for the project.
        Context: {context}

        Review the current codebase and project structure (docs/architecture/design.md).
        Suggest 3-5 high-value features or improvements that align with the project goals.

        If you find good ideas, create a NEW TASK for each one in the 'Proposals' section.

        PROPOSAL:
        Title: Feature: [Feature Name]
        Description:
        [Detailed description of the feature and value proposition]

        Effort: [Effort]
        """

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute ideation."""
        if not isinstance(target, AsanaProject):
             return AgentResult(success=False, error="IdeationAgent only supports Projects")

        prompt = self.get_prompt(target)
        log_path = self.get_log_file_path(target)
        project_name = target.name

        stdout, stderr, returncode = await self.run_claude_code(
            prompt,
            log_path=log_path,
            project_name=project_name
        )

        if returncode != 0:
            return AgentResult(
                success=False,
                error=f"Ideation failed: {stderr}",
                summary="Ideation failed",
            )

        return AgentResult(
            success=True,
            summary="Ideation complete. See logs for proposals.",
            details=["Generated feature suggestions"],
            next_section="Done",
        )
