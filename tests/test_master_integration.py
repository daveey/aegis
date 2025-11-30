import asyncio
import os
import shutil
from pathlib import Path
import pytest
from aegis.orchestrator.master import MasterProcess
from aegis.database.session import get_db_session
from aegis.database.master_models import AgentState, WorkQueueItem

@pytest.mark.asyncio
async def test_master_process_startup():
    """Test that MasterProcess starts, initializes DB, and spawns agents."""

    # Setup test environment
    test_dir = Path.cwd() / ".aegis_test"
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # Mock .aegis dir
    original_cwd = Path.cwd()
    os.chdir(test_dir)

    # Create fake project DBs to simulate tracked projects
    projects_dir = test_dir / ".aegis" / "projects"
    projects_dir.mkdir(parents=True)
    (projects_dir / "12345.sqlite").touch()
    (projects_dir / "67890.sqlite").touch()

    master = MasterProcess()

    # Run master for a short time
    task = asyncio.create_task(master.start())

    try:
        await asyncio.sleep(5) # Give it time to start agents

        # Verify Master DB exists
        master_db = test_dir / ".aegis" / "master.sqlite"
        assert master_db.exists()

        # Check DB content
        with get_db_session(project_gid=None) as session:
            # Check agents registered
            agents = session.query(AgentState).all()
            print(f"Agents found: {[a.agent_id for a in agents]}")
            assert len(agents) >= 2 # At least 2 workers

            # Check if syncers are running (we can't check DB for syncers easily as they don't register in AgentState yet?
            # Wait, SyncerAgent doesn't register itself in AgentState in my implementation.
            # MasterProcess keeps them in `self.syncer_processes`.
            pass

        # Check internal state
        assert len(master.syncer_processes) == 2
        assert "12345" in master.syncer_processes
        assert "67890" in master.syncer_processes

        assert len(master.worker_processes) == 2

        # Create a dummy work item
        with get_db_session(project_gid=None) as session:
            work_item = WorkQueueItem(
                agent_type="WorkerAgent",
                resource_id="dummy_task_123", # Needs to be mocked or valid?
                # Worker will try to fetch from Asana. We need to mock AsanaService in the worker process?
                # That's hard since it's a subprocess.
                # For this integration test, the worker will fail to fetch the task and mark work as failed.
                # That is sufficient to prove it picked up the work.
                resource_type="task",
                priority=10,
                status="pending"
            )
            session.add(work_item)
            session.commit()
            work_item_id = work_item.id

        # Wait for worker to pick it up and process it
        # It should fail (target not found) but status should change to 'failed' or 'completed'
        final_status = None
        for i in range(20): # Increase timeout
            await asyncio.sleep(1)
            with get_db_session(project_gid=None) as session:
                item = session.query(WorkQueueItem).filter(WorkQueueItem.id == work_item_id).first()
                if item:
                    print(f"[{i}] Work item status: {item.status}, Assigned to: {item.assigned_to_agent_id}")
                    if item.status in ["completed", "failed"]:
                        final_status = item.status
                        break

        assert final_status in ["completed", "failed"]

    finally:
        await master.stop()
        await task
        os.chdir(original_cwd)
        # shutil.rmtree(test_dir) # Cleanup
