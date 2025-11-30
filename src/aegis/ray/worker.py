
import ray
import structlog
from pathlib import Path
from datetime import datetime

from aegis.config import get_settings
from aegis.asana.client import AsanaClient
from aegis.infrastructure.asana_service import AsanaService
from aegis.infrastructure.worktree_manager import WorktreeManager
from aegis.agents.worker import WorkerAgent
from aegis.database.session import get_db_session
from aegis.database.master_models import WorkQueueItem, AgentState
from aegis.utils.asana_utils import format_asana_resource

logger = structlog.get_logger(__name__)

@ray.remote
class WorkerActor:
    """Ray Actor wrapper for WorkerAgent."""

    def __init__(self, agent_id: str, repo_root: str):
        self.agent_id = agent_id
        self.repo_root = Path(repo_root)

        # Initialize dependencies
        self.settings = get_settings()
        self.client = AsanaClient(self.settings.asana_access_token)
        self.asana_service = AsanaService(self.client)
        self.worktree_manager = WorktreeManager(self.repo_root)

        self.agent = WorkerAgent(
            asana_service=self.asana_service,
            repo_root=self.repo_root,
            worktree_manager=self.worktree_manager,
            agent_id=self.agent_id
        )

        # Register in DB
        self._register_agent()

    def _register_agent(self):
        """Register agent in the database."""
        with get_db_session(project_gid=None) as session:
            existing_agent = session.query(AgentState).filter_by(agent_id=self.agent_id).first()

            if existing_agent:
                existing_agent.status = "idle"
                existing_agent.started_at = datetime.utcnow()
                existing_agent.last_heartbeat_at = datetime.utcnow()
                # We don't have a PID in the traditional sense, but we can store something else or leave it
                existing_agent.pid = 0
            else:
                agent = AgentState(
                    agent_id=self.agent_id,
                    agent_type="worker_agent",
                    status="idle",
                    pid=0
                )
                session.add(agent)
                session.commit()

    async def execute_task(self, work_item_id: int, resource_id: str, resource_type: str):
        """Execute a task assigned by the Master."""
        logger.info("worker_actor_executing", agent_id=self.agent_id, work_item_id=work_item_id)

        # Update status to busy
        with get_db_session(project_gid=None) as session:
            session.query(AgentState).filter(AgentState.agent_id == self.agent_id).update({
                "status": "busy",
                "current_work_item_id": work_item_id
            })
            session.commit()

        success = False
        try:
            # Fetch target
            target = None
            if resource_type == "task":
                target = await self.asana_service.get_task(resource_id)
            elif resource_type == "project":
                # Worker usually works on tasks
                pass

            if target:
                # Execute
                result = await self.agent.execute(target)
                success = result.success
            else:
                logger.error("target_not_found", resource_id=resource_id)

        except Exception as e:
            logger.error("execution_failed", error=str(e))
            success = False

        # Update Work Item and Agent Status
        with get_db_session(project_gid=None) as session:
            # Update Work Item
            session.query(WorkQueueItem).filter(WorkQueueItem.id == work_item_id).update({
                "status": "completed" if success else "failed",
                "completed_at": datetime.utcnow()
            })

            # Update Agent State
            session.query(AgentState).filter(AgentState.agent_id == self.agent_id).update({
                "status": "idle",
                "current_work_item_id": None
            })
            session.commit()

        return success

    async def heartbeat(self):
        """Update heartbeat."""
        with get_db_session(project_gid=None) as session:
            session.query(AgentState).filter(AgentState.agent_id == self.agent_id).update({
                "last_heartbeat_at": datetime.utcnow()
            })
            session.commit()
        return True
