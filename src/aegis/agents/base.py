"""Base agent contract for all swarm agents."""

import subprocess
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import structlog

from aegis.asana.models import AsanaTask
from aegis.infrastructure.asana_service import AsanaService

logger = structlog.get_logger()


class AgentError(Exception):
    """Raised when agent execution fails."""

    pass


class AgentResult:
    """Result of agent execution."""

    def __init__(
        self,
        success: bool,
        next_agent: str | None = None,
        next_section: str | None = None,
        summary: str = "",
        details: list[str] | None = None,
        error: str | None = None,
        cost: float = 0.0,
        clear_session_id: bool = False,
    ):
        """Initialize agent result.

        Args:
            success: Whether agent execution succeeded
            next_agent: Next agent to route to (updates "Agent" field)
            next_section: Next section to move task to
            summary: Concise summary for Asana comment (under 50 words)
            details: List of critical details for comment
            error: Error message if failed
            cost: Cost of this execution in USD
            clear_session_id: Whether to clear session ID (new agent context)
        """
        self.success = success
        self.next_agent = next_agent
        self.next_section = next_section
        self.summary = summary
        self.details = details or []
        self.error = error
        self.cost = cost
        self.clear_session_id = clear_session_id
        self.timestamp = datetime.utcnow()


class BaseAgent(ABC):
    """Base class for all swarm agents.

    All agents must implement:
    - execute(): Main execution logic
    - get_prompt(): Generate Claude Code prompt from task
    """

    def __init__(
        self,
        asana_service: AsanaService,
        repo_root: Path | str,
        session_id: str | None = None,
    ):
        """Initialize base agent.

        Args:
            asana_service: AsanaService instance
            repo_root: Root of git repository
            session_id: Optional session ID for continuity
        """
        self.asana = asana_service
        self.repo_root = Path(repo_root)
        self.session_id = session_id or str(uuid.uuid4())
        self.started_at = datetime.utcnow()

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name (e.g., "Triage Agent")."""
        pass

    @property
    @abstractmethod
    def status_emoji(self) -> str:
        """Status emoji for comments (e.g., "🔍" for Triage)."""
        pass

    @abstractmethod
    def get_prompt(self, task: AsanaTask) -> str:
        """Generate Claude Code prompt for this agent.

        Args:
            task: AsanaTask to process

        Returns:
            Prompt text for Claude Code CLI
        """
        pass

    @abstractmethod
    async def execute(self, task: AsanaTask, **kwargs) -> AgentResult:
        """Execute agent logic.

        Args:
            task: AsanaTask to process
            **kwargs: Additional agent-specific arguments

        Returns:
            AgentResult with next steps
        """
        pass

    async def run_claude_code(
        self,
        prompt: str,
        cwd: Path | None = None,
        timeout: int = 300,
        interactive: bool = False,
    ) -> tuple[str, str, int]:
        """Run Claude Code CLI with prompt.

        Args:
            prompt: Prompt to send to Claude Code
            cwd: Working directory (default: repo_root)
            timeout: Timeout in seconds
            interactive: Whether to run in interactive mode (inherit stdio)

        Returns:
            Tuple of (stdout, stderr, returncode)

        Raises:
            AgentError: If Claude Code execution fails
        """
        cwd = cwd or self.repo_root

        logger.info(
            "running_claude_code",
            agent=self.name,
            session_id=self.session_id,
            cwd=str(cwd),
            interactive=interactive,
        )

        try:
            # Write prompt to temp file
            prompt_file = cwd / f".aegis_prompt_{self.session_id}.txt"
            prompt_file.write_text(prompt, encoding="utf-8")

            if interactive:
                # Run interactively - inherit stdio
                # Note: timeout is ignored in interactive mode as it depends on user input
                result = subprocess.run(
                    ["claude", "code", "--prompt-file", str(prompt_file)],
                    cwd=cwd,
                    check=False,  # Don't raise on non-zero exit
                )
                stdout, stderr = "", ""
                returncode = result.returncode

            else:
                # Run headless - capture output
                result = subprocess.run(
                    ["claude", "code", "--prompt-file", str(prompt_file)],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                stdout, stderr = result.stdout, result.stderr
                returncode = result.returncode

            # Cleanup prompt file
            prompt_file.unlink(missing_ok=True)

            logger.info(
                "claude_code_complete",
                agent=self.name,
                session_id=self.session_id,
                returncode=returncode,
                stdout_size=len(stdout),
            )

            return stdout, stderr, returncode

        except subprocess.TimeoutExpired as e:
            logger.error(
                "claude_code_timeout",
                agent=self.name,
                session_id=self.session_id,
                timeout=timeout,
            )
            raise AgentError(f"Claude Code timeout after {timeout}s")
        except Exception as e:
            logger.error(
                "claude_code_error",
                agent=self.name,
                session_id=self.session_id,
                error=str(e),
            )
            raise AgentError(f"Claude Code execution failed: {e}")

    async def post_result_comment(
        self,
        task: AsanaTask,
        result: AgentResult,
    ) -> None:
        """Post formatted result comment to Asana.

        Args:
            task: AsanaTask
            result: AgentResult to post
        """
        emoji = "✅" if result.success else "❌"

        await self.asana.post_agent_comment(
            task_gid=task.gid,
            agent_name=self.name,
            status_emoji=emoji,
            summary=result.summary,
            details=result.details,
            session_id=self.session_id,
        )

    async def check_cost_limit(self, task: AsanaTask, current_cost: float) -> bool:
        """Check if task has exceeded cost limit.

        Args:
            task: AsanaTask
            current_cost: Current accumulated cost

        Returns:
            True if within limit, False if exceeded
        """
        max_cost = task.max_cost
        if max_cost is None:
            return True

        if current_cost >= max_cost:
            logger.warning(
                "cost_limit_exceeded",
                agent=self.name,
                task_gid=task.gid,
                current_cost=current_cost,
                max_cost=max_cost,
            )
            return False

        return True

    def get_log_file_path(self, task: AsanaTask) -> Path:
        """Get path to log file for this execution.

        Args:
            task: AsanaTask

        Returns:
            Path to log file
        """
        logs_dir = self.repo_root / "logs"
        logs_dir.mkdir(exist_ok=True)

        return logs_dir / f"session-{self.session_id}-task-{task.gid}.log"
