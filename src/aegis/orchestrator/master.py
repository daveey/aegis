"""Master Process Orchestrator.

Manages the lifecycle of the swarm:
- Maintains the central Work Queue.
- Manages the Agent Pool (Workers).
- Manages Syncer Agents for each tracked project.
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn

import structlog
from sqlalchemy import select, update, delete, func

from aegis.config import get_settings
from aegis.database.master_models import WorkQueueItem, AgentState
from aegis.database.session import get_db_session, init_db
from aegis.database.crud import get_all_projects

logger = structlog.get_logger(__name__)


class MasterProcess:
    """Central orchestrator for the Aegis swarm."""

    def __init__(self):
        self.settings = get_settings()
        self.running = False
        self.syncer_processes: dict[str, asyncio.subprocess.Process] = {} # project_gid -> process
        self.worker_processes: dict[str, asyncio.subprocess.Process] = {} # agent_id -> process

        # Signals
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the Master Process."""
        logger.info("master_process_starting")
        self.running = True

        # Initialize Master DB
        init_db(project_gid=None)

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        try:
            # 1. Start Syncer Agents for all tracked projects
            await self._start_syncers()

            # 2. Start Worker Pool (initial pool)
            await self._start_worker_pool()

            # 3. Main Loop
            await self._main_loop()

        except Exception as e:
            logger.error("master_process_failed", error=str(e), exc_info=True)
            await self.stop()

    async def stop(self) -> None:
        """Stop the Master Process and all subprocesses."""
        if not self.running:
            return

        logger.info("master_process_stopping")
        self.running = False
        self._shutdown_event.set()

        # Terminate all subprocesses
        for gid, proc in self.syncer_processes.items():
            logger.info("terminating_syncer", project_gid=gid)
            try:
                proc.terminate()
                await proc.wait()
            except Exception as e:
                logger.error("failed_to_terminate_syncer", project_gid=gid, error=str(e))

        for agent_id, proc in self.worker_processes.items():
            logger.info("terminating_worker", agent_id=agent_id)
            try:
                proc.terminate()
                await proc.wait()
            except Exception as e:
                logger.error("failed_to_terminate_worker", agent_id=agent_id, error=str(e))

        logger.info("master_process_stopped")
        # sys.exit(0) # Don't exit here, let caller handle it

    async def _start_syncers(self) -> None:
        """Start Syncer Agents for all tracked projects."""
        from aegis.core.tracker import ProjectTracker

        tracker = ProjectTracker()
        projects = tracker.get_projects()

        if not projects:
            logger.warning("no_projects_found", path=str(tracker.projects_file))
            return

        for project in projects:
            await self._spawn_syncer(project["gid"])

    async def _spawn_syncer(self, project_gid: str) -> None:
        """Spawn a Syncer Agent subprocess."""
        if project_gid in self.syncer_processes:
            return

        logger.info("spawning_syncer", project_gid=project_gid)

        cmd = [
            sys.executable, "-m", "aegis.agents.syncer",
            "--project-gid", project_gid
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self.syncer_processes[project_gid] = proc

        # We should probably monitor these processes in the main loop

    async def _start_worker_pool(self) -> None:
        """Start the initial pool of worker agents."""
        # For now, let's start a fixed number of workers, e.g. 2
        for i in range(2):
            await self._spawn_worker(f"worker-{i}")

    async def _spawn_worker(self, agent_id: str) -> None:
        """Spawn a Worker Agent subprocess."""
        logger.info("spawning_worker", agent_id=agent_id)

        # Worker agent entry point
        cmd = [
            sys.executable, "-m", "aegis.agents.worker",
            "--agent-id", agent_id
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self.worker_processes[agent_id] = proc

        # Register in DB
        with get_db_session() as session:
            existing_agent = session.query(AgentState).filter_by(agent_id=agent_id).first()

            if existing_agent:
                existing_agent.status = "idle"
                existing_agent.pid = proc.pid
                existing_agent.started_at = datetime.utcnow()
                existing_agent.last_heartbeat_at = datetime.utcnow()
            else:
                agent = AgentState(
                    agent_id=agent_id,
                    agent_type="worker_agent",
                    status="idle",
                    pid=proc.pid
                )
                session.add(agent)

    async def _main_loop(self) -> None:
        """Main orchestration loop."""
        while self.running:
            try:
                # 1. Check for pending work
                await self._schedule_work()

                # 2. Monitor subprocesses
                await self._monitor_processes()

                # 3. Sleep
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error("error_in_main_loop", error=str(e))
                await asyncio.sleep(5.0)

    async def _schedule_work(self) -> None:
        """Assign pending work to idle agents."""
        with get_db_session() as session:
            # Get idle workers
            idle_agents = session.query(AgentState).filter(
                AgentState.status == "idle",
                AgentState.agent_type == "worker_agent" # Only schedule workers for now
            ).all()

            if not idle_agents:
                return

            # Get pending work
            # Prioritize by priority desc, created_at asc
            pending_work = session.query(WorkQueueItem).filter(
                WorkQueueItem.status == "pending"
            ).order_by(
                WorkQueueItem.priority.desc(),
                WorkQueueItem.created_at.asc()
            ).limit(len(idle_agents)).all()

            if not pending_work:
                return

            # Assign work
            for work_item, agent in zip(pending_work, idle_agents):
                logger.info("assigning_work", work_id=work_item.id, agent_id=agent.agent_id)

                work_item.status = "assigned"
                work_item.assigned_to_agent_id = agent.agent_id
                work_item.assigned_at = datetime.utcnow()

                agent.status = "busy"
                agent.current_work_item_id = work_item.id

                # Notify agent (in a real implementation we might use IPC or the agent polls the DB)
                # Since we are using DB polling for agents too, the agent will pick this up.

    async def _monitor_processes(self) -> None:
        """Check if subprocesses are still alive."""
        # Check Syncers
        for gid, proc in list(self.syncer_processes.items()):
            if proc.returncode is not None:
                logger.warning("syncer_died", project_gid=gid, returncode=proc.returncode)
                del self.syncer_processes[gid]
                # Restart?
                await self._spawn_syncer(gid)

        # Check Workers
        for agent_id, proc in list(self.worker_processes.items()):
            if proc.returncode is not None:
                logger.warning("worker_died", agent_id=agent_id, returncode=proc.returncode)
                del self.worker_processes[agent_id]

                # Mark agent as offline in DB
                with get_db_session() as session:
                    session.execute(
                        update(AgentState)
                        .where(AgentState.agent_id == agent_id)
                        .values(status="offline")
                    )

                # Restart?
                await self._spawn_worker(agent_id)

if __name__ == "__main__":
    # Entry point for running Master directly
    logging.basicConfig(level=logging.INFO)
    master = MasterProcess()
    asyncio.run(master.start())
