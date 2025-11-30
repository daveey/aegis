"""Base agent contract for all swarm agents."""

import subprocess
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path

import structlog
from sqlalchemy import select, update

from aegis.asana.models import AsanaTask, AsanaProject
from aegis.infrastructure.asana_service import AsanaService
from aegis.utils.asana_utils import format_asana_resource
from aegis.database.session import get_db_session
from aegis.database.master_models import WorkQueueItem, AgentState

logger = structlog.get_logger()


class AgentTargetType(str, Enum):
    """Type of target an agent operates on."""
    TASK = "task"
    PROJECT = "project"


class AgentError(Exception):
    """Raised when agent execution fails."""
    pass


from aegis.core.models import AgentResult


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
        agent_id: str | None = None,
    ):
        """Initialize base agent.

        Args:
            asana_service: AsanaService instance
            repo_root: Root of git repository
            session_id: Optional session ID for continuity
            agent_id: Unique ID for this agent instance (for locking)
        """
        self.asana = asana_service
        self.repo_root = Path(repo_root)
        self.session_id = session_id or str(uuid.uuid4())
        self.agent_id = agent_id or f"agent-{self.session_id[:8]}"
        self.started_at = datetime.utcnow()
        self.logger = structlog.get_logger(self.__module__)

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

    @property
    @abstractmethod
    def target_type(self) -> AgentTargetType:
        """Type of target this agent accepts."""
        pass

    @abstractmethod
    def get_prompt(self, target: AsanaTask | AsanaProject) -> str:
        """Generate Claude Code prompt for this agent.

        Args:
            target: Target to process (Task or Project)

        Returns:
            Prompt text for Claude Code CLI
        """
        pass

    @abstractmethod
    async def execute(self, target: AsanaTask | AsanaProject, **kwargs) -> AgentResult:
        """Execute agent logic.

        Args:
            target: Target to process (Task or Project)
            **kwargs: Additional agent-specific arguments

        Returns:
            AgentResult with next steps
        """
        pass

    async def claim_resource(self, resource_id: str, resource_type: str) -> bool:
        """Claim a resource (task/project) to prevent other agents from working on it.

        This checks the Master Work Queue to ensure the work item is assigned to THIS agent.

        Args:
            resource_id: ID of the resource (e.g. Task GID)
            resource_type: 'task' or 'project'

        Returns:
            True if claimed successfully (or already assigned to self), False otherwise.
        """
        self.logger.info("claiming_resource", resource_id=resource_id, agent_id=self.agent_id)

        with get_db_session(project_gid=None) as session: # Connect to Master DB
            # Check if there is a work item for this resource
            work_item = session.query(WorkQueueItem).filter(
                WorkQueueItem.resource_id == resource_id,
                WorkQueueItem.resource_type == resource_type,
                WorkQueueItem.status.in_(["pending", "assigned"])
            ).first()

            if not work_item:
                # If no work item exists, we can create one and assign it to self?
                # Or we assume work items must exist.
                # For now, let's allow ad-hoc claiming if no work item exists (e.g. CLI run)
                self.logger.info("no_work_item_found_creating_ad_hoc", resource_id=resource_id)
                work_item = WorkQueueItem(
                    agent_type=self.name, # Use agent name as type?
                    resource_id=resource_id,
                    resource_type=resource_type,
                    status="assigned",
                    assigned_to_agent_id=self.agent_id,
                    assigned_at=datetime.utcnow(),
                    priority=10
                )
                session.add(work_item)
                session.commit()
                return True

            if work_item.assigned_to_agent_id == self.agent_id:
                return True

            if work_item.status == "pending":
                # Claim it
                work_item.status = "assigned"
                work_item.assigned_to_agent_id = self.agent_id
                work_item.assigned_at = datetime.utcnow()
                session.commit()
                return True

            # Already assigned to someone else
            self.logger.warning(
                "resource_already_assigned",
                resource_id=resource_id,
                assigned_to=work_item.assigned_to_agent_id
            )
            return False

    async def release_resource(self, resource_id: str, resource_type: str, success: bool = True) -> None:
        """Release a claimed resource.

        Args:
            resource_id: ID of the resource
            resource_type: 'task' or 'project'
            success: Whether the work was completed successfully
        """
        self.logger.info("releasing_resource", resource_id=resource_id, success=success)

        with get_db_session(project_gid=None) as session:
            work_item = session.query(WorkQueueItem).filter(
                WorkQueueItem.resource_id == resource_id,
                WorkQueueItem.resource_type == resource_type,
                WorkQueueItem.assigned_to_agent_id == self.agent_id
            ).first()

            if work_item:
                work_item.status = "completed" if success else "failed"
                session.commit()

    async def add_work_to_queue(
        self,
        agent_type: str,
        resource_id: str,
        resource_type: str,
        priority: int = 0,
        payload: dict | None = None
    ) -> None:
        """Add a new unit of work to the Master Queue.

        Args:
            agent_type: Type of agent needed (e.g. 'TriageAgent')
            resource_id: ID of the resource
            resource_type: 'task' or 'project'
            priority: Priority level (higher is more urgent)
            payload: Optional context data
        """
        self.logger.info("adding_work_to_queue", agent_type=agent_type, resource_id=resource_id)

        with get_db_session(project_gid=None) as session:
            # Check if already exists
            existing = session.query(WorkQueueItem).filter(
                WorkQueueItem.resource_id == resource_id,
                WorkQueueItem.resource_type == resource_type,
                WorkQueueItem.status.in_(["pending", "assigned"])
            ).first()

            if existing:
                self.logger.info("work_already_exists", resource_id=resource_id)
                return

            work_item = WorkQueueItem(
                agent_type=agent_type,
                resource_id=resource_id,
                resource_type=resource_type,
                priority=priority,
                payload=payload or {},
                status="pending"
            )
            session.add(work_item)
            session.commit()

    async def run_claude_code(
        self,
        prompt: str,
        cwd: Path | None = None,
        timeout: int = 300,
        interactive: bool = False,
        log_path: Path | str | None = None,
        project_name: str | None = None,
    ) -> tuple[str, str, int]:
        """Run Claude Code CLI with prompt.

        Args:
            prompt: Prompt to send to Claude Code
            cwd: Working directory (default: repo_root)
            timeout: Timeout in seconds
            interactive: Whether to run in interactive mode (inherit stdio)
            log_path: Path to session log file
            project_name: Name of the project

        Returns:
            Tuple of (stdout, stderr, returncode)

        Raises:
            AgentError: If Claude Code execution fails
        """
        cwd = cwd or self.repo_root

        log_kwargs = {
            "agent": self.name,
            "session_id": self.session_id,
            "cwd": str(cwd),
            "interactive": interactive,
        }
        if log_path:
            log_kwargs["session_log_path"] = str(log_path)
        if project_name:
            log_kwargs["project"] = project_name

        self.logger.info("running_claude_code", **log_kwargs)
        if log_path:
            print(f"session_log_path= {log_path}")

        try:
            if interactive:
                # Run interactively - inherit stdio
                # Note: timeout is ignored in interactive mode as it depends on user input
                # Pass prompt as argument since we can't pipe stdin in interactive mode
                result = subprocess.run(
                    ["claude", "code", prompt],
                    cwd=cwd,
                    check=False,  # Don't raise on non-zero exit
                )
                stdout, stderr = "", ""
                returncode = result.returncode

            else:
                # Run headless - capture output
                # Pass prompt via stdin and use -p for print mode
                result = subprocess.run(
                    ["claude", "code", "-p"],
                    input=prompt,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                stdout, stderr = result.stdout, result.stderr
                returncode = result.returncode

            self.logger.info(
                "claude_code_complete",
                agent=self.name,
                session_id=self.session_id,
                returncode=returncode,
                stdout_size=len(stdout),
            )

            return stdout, stderr, returncode

        except subprocess.TimeoutExpired as e:
            self.logger.error(
                "claude_code_timeout",
                agent=self.name,
                session_id=self.session_id,
                timeout=timeout,
            )
            raise AgentError(f"Claude Code timeout after {timeout}s")
        except Exception as e:
            self.logger.error(
                "claude_code_error",
                agent=self.name,
                session_id=self.session_id,
                error=str(e),
            )
            raise AgentError(f"Claude Code execution failed: {e}")

    async def post_result_comment(
        self,
        target: AsanaTask | AsanaProject,
        result: AgentResult,
    ) -> None:
        """Post formatted result comment to Asana.

        Args:
            target: Target entity
            result: AgentResult to post
        """
        emoji = "✅" if result.success else "❌"

        # Handle different target types
        target_gid = target.gid

        await self.asana.post_agent_comment(
            task_gid=target_gid,
            agent_name=self.name,
            status_emoji=emoji,
            summary=result.summary,
            details=result.details,
            session_id=self.session_id,
        )

    async def check_cost_limit(self, target: AsanaTask | AsanaProject, current_cost: float) -> bool:
        """Check if task has exceeded cost limit.

        Args:
            target: Target entity
            current_cost: Current accumulated cost

        Returns:
            True if within limit, False if exceeded
        """
        if isinstance(target, AsanaProject):
            return True # Projects don't have cost limits yet

        max_cost = target.max_cost
        if max_cost is None:
            return True

        if current_cost >= max_cost:
            self.logger.warning(
                "cost_limit_exceeded",
                agent=self.name,
                target=format_asana_resource(target),
                current_cost=current_cost,
                max_cost=max_cost,
            )
            return False

        return True

    def get_log_file_path(self, target: AsanaTask | AsanaProject) -> Path:
        """Get path to log file for this execution.

        Args:
            target: Target entity

        Returns:
            Path to log file
        """
        logs_dir = self.repo_root / "logs"
        logs_dir.mkdir(exist_ok=True)

        return logs_dir / f"session-{self.session_id}-target-{target.gid}.log"

