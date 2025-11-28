"""Triage Agent - Requirements Analyst."""

import re
from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask
from aegis.infrastructure.asana_service import AsanaService

logger = structlog.get_logger()


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
        return "Triage Agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "🔍"

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for triage analysis.

        Args:
            task: AsanaTask to analyze

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "triage.md"

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

# Your Analysis

Analyze the task above and provide your decision in the format specified.
"""

        return context

    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute triage analysis.

        Args:
            task: AsanaTask to triage

        Returns:
            AgentResult with routing decision
        """
        logger.info("triage_start", task_gid=task.gid, task_name=task.name)

        try:
            # Generate and run prompt
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(prompt)

            if returncode != 0:
                logger.error("triage_failed", task_gid=task.gid, stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Triage analysis failed due to execution error",
                )

            # Parse decision from output
            decision = self._parse_decision(stdout)

            logger.info(
                "triage_complete",
                task_gid=task.gid,
                decision=decision.get("action"),
            )

            return decision

        except Exception as e:
            logger.error("triage_error", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                error=str(e),
                summary="Triage analysis encountered an error",
            )

    def _parse_decision(self, output: str) -> AgentResult:
        """Parse triage decision from Claude Code output.

        Args:
            output: Claude Code stdout

        Returns:
            AgentResult with routing decision
        """
        # Look for decision markers
        if "DECISION: Route to Planner" in output or "Route to Planner" in output:
            # Extract summary
            summary_match = re.search(r"SUMMARY:\s*(.+?)(?:\n|$)", output, re.IGNORECASE)
            summary = summary_match.group(1).strip() if summary_match else "Requirements are clear"

            return AgentResult(
                success=True,
                next_agent="Planner",
                next_section="Planning",
                summary=f"Task triaged: {summary}",
                details=["Routing to Planner for architecture design"],
                clear_session_id=True,
            )

        elif "DECISION: Request Clarification" in output or "Request Clarification" in output:
            # Extract questions
            questions_match = re.search(
                r"QUESTIONS:\s*(.+?)(?:REASONING:|$)",
                output,
                re.IGNORECASE | re.DOTALL,
            )
            questions = []
            if questions_match:
                questions_text = questions_match.group(1).strip()
                questions = [q.strip() for q in re.findall(r"^\d+\.\s*(.+?)$", questions_text, re.MULTILINE)]

            return AgentResult(
                success=True,
                next_agent="Triage",  # Stay with Triage until clarified
                next_section="Clarification Needed",
                summary="Task needs clarification from user",
                details=[f"Question {i+1}: {q}" for i, q in enumerate(questions)],
                clear_session_id=False,  # Keep session for continuity
            )

        elif "DECISION: Route to Documentation" in output or "Route to Documentation" in output:
            # Extract preference
            pref_match = re.search(r"PREFERENCE:\s*(.+?)(?:\n|$)", output, re.IGNORECASE)
            preference = pref_match.group(1).strip() if pref_match else "User preference update"

            return AgentResult(
                success=True,
                next_agent="Documentation",
                next_section="Ready Queue",
                summary=f"Preference to record: {preference}",
                details=["Routing to Documentation Agent"],
                clear_session_id=True,
            )

        else:
            # Fallback - assume route to planner
            logger.warning("triage_decision_unclear", output=output[:200])
            return AgentResult(
                success=True,
                next_agent="Planner",
                next_section="Planning",
                summary="Task appears actionable (decision unclear, defaulting to Planner)",
                details=["Defaulted to Planner - decision format not recognized"],
                clear_session_id=True,
            )
