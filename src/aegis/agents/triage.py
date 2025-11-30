"""Triage Agent - Requirements Analyst."""

import re
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent, AgentTargetType
from aegis.asana.models import AsanaTask, AsanaProject
from aegis.infrastructure.asana_service import AsanaService
from aegis.utils.asana_utils import format_asana_resource

logger = structlog.get_logger(__name__)


class TriageAgent(BaseAgent):
    """Triage Agent analyzes tasks and routes them appropriately.

    Responsibilities:
    - Analyze requirements for clarity
    - Determine if task is actionable
    - Create clarification questions if needed
    - Route to appropriate next agent
    """

    @property
    def name(self) -> str:
        """Agent name."""
        return "triage_agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "🔍"

    @property
    def target_type(self) -> AgentTargetType:
        """Target type."""
        return AgentTargetType.TASK

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for triage analysis.

        Args:
            task: AsanaTask to analyze

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "triage.prompt.txt"

        if not prompt_file.exists():
            logger.warning("triage_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Analyze this task and determine next steps."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

        # Add task context
        context = f"""
# Task to Triage

**Task Name**: {task.name}

**Description**:
{task.notes or "(No description provided)"}

**Custom Fields**:
- Agent: {task.agent}
- Status: {task.swarm_status}
- Due Date: {task.due_on or "Not set"}

**Project**: {task.projects[0].name if task.projects else "Unknown"}

---

{base_prompt}

---

# Output Format

You must output your decision as a valid JSON object matching the following schema:

```json
{{
    "success": true,
    "next_agent": "Planner" | "Triage" | "Documentation" | null,
    "next_section": "Planning" | "Clarification Needed" | "Ready Queue" | null,
    "summary": "Concise summary under 50 words",
    "details": ["Detail 1", "Detail 2"],
    "clear_session_id": boolean,
    "assignee": "me" | null
}}
```

Do not include any text outside the JSON block.
"""
        return context

    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute triage analysis.

        Args:
            target: AsanaTask to triage
            **kwargs: Additional arguments (interactive, etc.)

        Returns:
            AgentResult with routing decision
        """
        if not isinstance(target, AsanaTask):
             return AgentResult(success=False, error="TriageAgent only supports Tasks")

        task = target
        interactive = kwargs.get("interactive", False)
        logger.info("triage_start", task=format_asana_resource(task), interactive=interactive)

        try:
            # Generate and run prompt
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(prompt, interactive=interactive)

            if interactive:
                return AgentResult(
                    success=True,
                    summary="Interactive session completed",
                    details=["Ran interactively"],
                )

            if returncode != 0:
                logger.error("triage_failed", task=format_asana_resource(task), stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Triage analysis failed due to execution error",
                )

            # Parse decision from output
            try:
                # clean up potential markdown code blocks
                json_str = stdout.strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]

                decision = AgentResult.model_validate_json(json_str.strip())
            except Exception as e:
                logger.error("triage_json_parse_error", error=str(e), stdout=stdout)
                return AgentResult(
                    success=False,
                    next_agent="Triage",
                    next_section="Clarification Needed",
                    summary="Triage analysis failed: invalid JSON output",
                    details=["Could not parse Claude Code output as JSON.", f"Error: {str(e)}"],
                    clear_session_id=False,
                )

            logger.info(
                "triage_complete",
                task=format_asana_resource(task),
                decision=decision.next_agent,
            )

            return decision

        except Exception as e:
            import traceback
            logger.error("triage_error", task=format_asana_resource(task), error=str(e), traceback=traceback.format_exc())
            return AgentResult(
                success=False,
                error=str(e),
                summary="Triage analysis encountered an error",
            )
