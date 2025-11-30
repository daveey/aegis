
import ray
import structlog
import asyncio
from pathlib import Path
from datetime import datetime

from aegis.config import get_settings
from aegis.asana.client import AsanaClient
from aegis.infrastructure.asana_service import AsanaService
from aegis.agents.syncer import SyncerAgent

logger = structlog.get_logger(__name__)

@ray.remote
class SyncerActor:
    """Ray Actor wrapper for SyncerAgent."""

    def __init__(self, project_gid: str, repo_root: str, session_id: str):
        self.project_gid = project_gid
        self.repo_root = Path(repo_root)
        self.session_id = session_id

        # Initialize dependencies
        self.settings = get_settings()
        self.client = AsanaClient(self.settings.asana_access_token)
        self.asana_service = AsanaService(self.client)

        self.agent = SyncerAgent(
            project_gid=self.project_gid,
            asana_service=self.asana_service,
            repo_root=self.repo_root,
            agent_id=f"syncer-{self.project_gid}",
            session_id=self.session_id
        )
        self.running = False

    async def start(self):
        """Start the sync loop."""
        self.running = True
        logger.info("syncer_actor_started", project_gid=self.project_gid)

        # We can reuse the agent's run_forever logic, but we might want to control the loop here
        # to allow for graceful shutdown via a flag.
        # The agent's run_forever is:
        # while True:
        #    sync()
        #    sleep()

        # Let's just call the agent's logic but maybe we should modify the agent to accept a stop signal?
        # Or just reimplement the loop here calling _sync_project.
        # Accessing private method _sync_project is not ideal but practical.

        from aegis.database.session import init_db
        init_db(project_gid=self.project_gid)

        while self.running:
            try:
                await self.agent._sync_project()
                await asyncio.sleep(self.settings.poll_interval_seconds)
            except Exception as e:
                logger.error("sync_failed", error=str(e))
                await asyncio.sleep(10)

    def stop(self):
        """Stop the sync loop."""
        self.running = False
