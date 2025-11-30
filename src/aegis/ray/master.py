
import ray
import asyncio
import structlog
from pathlib import Path
from datetime import datetime

from aegis.config import get_settings
from aegis.core.tracker import ProjectTracker
from aegis.database.session import get_db_session, init_db
from aegis.database.master_models import WorkQueueItem, AgentState
from aegis.ray.worker import WorkerActor
from aegis.ray.syncer import SyncerActor

logger = structlog.get_logger(__name__)

@ray.remote
class MasterActor:
    """Central orchestrator using Ray."""

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self.syncer_actors = {} # project_gid -> actor_handle
        self.worker_actors = {} # agent_id -> actor_handle
        self.worker_pool_size = 2

    async def start(self):
        """Start the Master Actor."""
        logger.info("master_actor_starting")
        self.running = True

        # Initialize Master DB
        init_db(project_gid=None)

        # 1. Start Syncers
        await self._start_syncers()

        # 2. Start Workers
        await self._start_worker_pool()

        # 3. Main Loop
        await self._main_loop()

    async def stop(self):
        """Stop the Master Actor."""
        self.running = False
        # Ray handles cleanup of actors when the script exits,
        # but we can explicitly stop them if needed.
        for actor in self.syncer_actors.values():
            actor.stop.remote()

    async def _start_syncers(self):
        """Start Syncer Actors for all tracked projects."""
        tracker = ProjectTracker()
        projects = tracker.get_projects()

        if not projects:
            logger.warning("no_projects_found")
            return

        for project in projects:
            gid = project["gid"]
            if gid not in self.syncer_actors:
                logger.info("spawning_syncer", project_gid=gid)
                timestamp = int(datetime.utcnow().timestamp())
                session_id = f"syncer-{gid}-{timestamp}"

                syncer = SyncerActor.remote(
                    project_gid=gid,
                    repo_root=project["local_path"],
                    session_id=session_id
                )
                # Start the sync loop asynchronously
                syncer.start.remote()
                self.syncer_actors[gid] = syncer

    async def _start_worker_pool(self):
        """Start the worker pool."""
        for i in range(self.worker_pool_size):
            agent_id = f"worker-{i}"
            if agent_id not in self.worker_actors:
                logger.info("spawning_worker", agent_id=agent_id)
                worker = WorkerActor.remote(
                    agent_id=agent_id,
                    repo_root=str(Path.cwd()) # Assuming running from repo root
                )
                self.worker_actors[agent_id] = worker

    async def _main_loop(self):
        """Main scheduling loop."""
        while self.running:
            try:
                await self._schedule_work()
                await self._monitor_workers()
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error("error_in_main_loop", error=str(e))
                await asyncio.sleep(5.0)

    async def _schedule_work(self):
        """Assign pending work to idle workers."""
        with get_db_session() as session:
            # Get idle workers from DB state
            # Note: We trust the DB state which is updated by workers
            idle_agents = session.query(AgentState).filter(
                AgentState.status == "idle",
                AgentState.agent_type == "worker_agent"
            ).all()

            if not idle_agents:
                return

            # Get pending work
            pending_work = session.query(WorkQueueItem).filter(
                WorkQueueItem.status == "pending"
            ).order_by(
                WorkQueueItem.priority.desc(),
                WorkQueueItem.created_at.asc()
            ).limit(len(idle_agents)).all()

            if not pending_work:
                return

            # Assign work
            for work_item, agent_state in zip(pending_work, idle_agents):
                agent_id = agent_state.agent_id
                if agent_id in self.worker_actors:
                    logger.info("assigning_work", work_id=work_item.id, agent_id=agent_id)

                    # Update DB to assigned (to prevent double assignment)
                    work_item.status = "assigned"
                    work_item.assigned_to_agent_id = agent_id
                    work_item.assigned_at = datetime.utcnow()
                    session.commit()

                    # Trigger execution on actor
                    worker = self.worker_actors[agent_id]
                    worker.execute_task.remote(
                        work_item_id=work_item.id,
                        resource_id=work_item.resource_id,
                        resource_type=work_item.resource_type
                    )

    async def _monitor_workers(self):
        """Send heartbeats or check health."""
        # Ray handles health checks mostly, but we can trigger heartbeats
        for worker in self.worker_actors.values():
            worker.heartbeat.remote()
