"""Documentation Agent - The Librarian."""

from pathlib import Path

import structlog

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask
from aegis.infrastructure.memory_manager import MemoryManager

logger = structlog.get_logger()


class DocumentationAgent(BaseAgent):
    """Documentation Agent maintains institutional knowledge.

    Responsibilities:
    - Record user preferences in user_preferences.md
    - Update swarm_memory.md with decisions and context
    - Compact memory when it grows too large
    - Organize knowledge for easy retrieval
    """

    def __init__(self, *args, memory_manager: MemoryManager, **kwargs):
        """Initialize Documentation Agent.

        Args:
            memory_manager: MemoryManager instance
        """
        super().__init__(*args, **kwargs)
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        """Agent name."""
        return "Documentation Agent"

    @property
    def status_emoji(self) -> str:
        """Status emoji."""
        return "📚"

    def get_prompt(self, task: AsanaTask) -> str:
        """Generate prompt for documentation update.

        Args:
            task: AsanaTask containing preference/memory update

        Returns:
            Prompt text
        """
        prompt_file = Path(__file__).parent.parent.parent.parent / "prompts" / "documentation.md"

        if not prompt_file.exists():
            logger.warning("documentation_prompt_not_found", prompt_file=str(prompt_file))
            base_prompt = "Update documentation with the provided information."
        else:
            base_prompt = prompt_file.read_text(encoding="utf-8")

        # Load current preferences and memory
        user_prefs = self.memory_manager.read("user_preferences.md")
        swarm_memory = self.memory_manager.read("swarm_memory.md")

        # Add task context
        context = f"""
# Documentation Task

**Task Name**: {task.name}

**Request**:
{task.notes or "(No content provided)"}

---

# Current User Preferences

{user_prefs}

---

# Current Swarm Memory

{swarm_memory}

---

{base_prompt}

---

# Your Update

Analyze the request and update the appropriate documentation file(s).
"""

        return context

    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute documentation update.

        Args:
            task: AsanaTask with documentation request

        Returns:
            AgentResult with update status
        """
        logger.info("documentation_start", task_gid=task.gid, task_name=task.name)

        try:
            # Determine if this is a preference or memory update
            is_preference = (
                task.name.lower().startswith("preference:")
                or "preference" in (task.notes or "").lower()
            )

            # Generate and run prompt
            prompt = self.get_prompt(task)
            stdout, stderr, returncode = await self.run_claude_code(prompt, timeout=300)

            if returncode != 0:
                logger.error("documentation_failed", task_gid=task.gid, stderr=stderr)
                return AgentResult(
                    success=False,
                    error=f"Claude Code failed: {stderr}",
                    summary="Documentation update failed",
                )

            # Check if memory needs compaction
            compacted = self.memory_manager.compact("swarm_memory.md", max_tokens=20000)

            details = []
            if is_preference:
                details.append("User preference recorded")
            else:
                details.append("Swarm memory updated")

            if compacted:
                details.append("Memory compacted (exceeded 20k tokens)")

            logger.info(
                "documentation_complete",
                task_gid=task.gid,
                is_preference=is_preference,
                compacted=compacted,
            )

            return AgentResult(
                success=True,
                next_section="Done",
                summary="Documentation updated successfully",
                details=details,
            )

        except Exception as e:
            logger.error("documentation_error", task_gid=task.gid, error=str(e))
            return AgentResult(
                success=False,
                error=str(e),
                summary="Documentation update encountered an error",
            )
