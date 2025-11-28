"""Tests for orchestrator main module."""

import asyncio
import contextlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from aegis.asana.models import AsanaProject, AsanaTask
from aegis.config import Settings
from aegis.orchestrator.main import AgentPool, Orchestrator, TaskQueue
from aegis.orchestrator.prioritizer import TaskPrioritizer, TaskScore


def create_task(**overrides):
    """Helper to create test tasks with default values."""
    defaults = {
        "gid": "123",
        "name": "Test Task",
        "notes": "Test notes",
        "completed": False,
        "created_at": datetime.now(UTC),
        "modified_at": datetime.now(UTC),
        "projects": [],
    }
    defaults.update(overrides)
    return AsanaTask(**defaults)


@pytest.fixture
def prioritizer():
    """Create a basic prioritizer."""
    return TaskPrioritizer()


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.asana_access_token = "test_token"
    settings.asana_portfolio_gid = "portfolio_123"
    settings.poll_interval_seconds = 1
    settings.max_concurrent_tasks = 3
    settings.shutdown_timeout = 300
    settings.subprocess_term_timeout = 10
    settings.priority_weight_due_date = 10.0
    settings.priority_weight_dependency = 8.0
    settings.priority_weight_user_priority = 7.0
    settings.priority_weight_project_importance = 5.0
    settings.priority_weight_age = 3.0
    return settings


class TestTaskQueue:
    """Test TaskQueue functionality."""

    @pytest.mark.asyncio
    async def test_add_tasks(self, prioritizer):
        """Test adding tasks to queue."""
        queue = TaskQueue(prioritizer)
        tasks = [
            create_task(gid="1", name="Task 1"),
            create_task(gid="2", name="Task 2"),
        ]

        await queue.add_tasks(tasks)
        size = await queue.size()

        assert size == 2

    @pytest.mark.asyncio
    async def test_remove_task(self, prioritizer):
        """Test removing task from queue."""
        queue = TaskQueue(prioritizer)
        task = create_task(gid="1")

        await queue.add_tasks([task])
        await queue.remove_task("1")
        size = await queue.size()

        assert size == 0

    @pytest.mark.asyncio
    async def test_get_next_task_empty_queue(self, prioritizer):
        """Test getting next task from empty queue."""
        queue = TaskQueue(prioritizer)
        result = await queue.get_next_task()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_task_returns_highest_priority(self, prioritizer):
        """Test that get_next_task returns highest priority task."""
        queue = TaskQueue(prioritizer)

        # Create tasks with different priorities (overdue task should be highest)
        from datetime import timedelta

        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

        tasks = [
            create_task(gid="1", name="Task 1"),  # No due date
            create_task(gid="2", name="Task 2", due_on=yesterday),  # Overdue
            create_task(gid="3", name="Task 3"),  # No due date
        ]

        await queue.add_tasks(tasks)
        result = await queue.get_next_task()

        assert result is not None
        task, score = result
        assert task.gid == "2"  # Should return the overdue task

    @pytest.mark.asyncio
    async def test_clear(self, prioritizer):
        """Test clearing the queue."""
        queue = TaskQueue(prioritizer)
        tasks = [create_task(gid="1"), create_task(gid="2")]

        await queue.add_tasks(tasks)
        await queue.clear()
        size = await queue.size()

        assert size == 0


class TestAgentPool:
    """Test AgentPool functionality."""

    @pytest.mark.asyncio
    async def test_can_accept_task_when_empty(self):
        """Test that empty pool can accept tasks."""
        pool = AgentPool(max_concurrent=3)
        can_accept = await pool.can_accept_task()

        assert can_accept is True

    @pytest.mark.asyncio
    async def test_can_accept_task_when_full(self):
        """Test that full pool cannot accept tasks."""
        pool = AgentPool(max_concurrent=2)

        # Fill the pool
        mock_task1 = asyncio.create_task(asyncio.sleep(10))
        mock_task2 = asyncio.create_task(asyncio.sleep(10))

        await pool.add_task("task1", mock_task1)
        await pool.add_task("task2", mock_task2)

        can_accept = await pool.can_accept_task()
        assert can_accept is False

        # Cleanup
        mock_task1.cancel()
        mock_task2.cancel()
        try:
            await mock_task1
            await mock_task2
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_add_and_remove_task(self):
        """Test adding and removing tasks from pool."""
        pool = AgentPool(max_concurrent=3)
        mock_task = asyncio.create_task(asyncio.sleep(10))

        await pool.add_task("task1", mock_task)
        count = await pool.get_active_count()
        assert count == 1

        await pool.remove_task("task1")
        count = await pool.get_active_count()
        assert count == 0

        # Cleanup
        mock_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await mock_task

    @pytest.mark.asyncio
    async def test_get_active_count(self):
        """Test getting active task count."""
        pool = AgentPool(max_concurrent=3)

        mock_task1 = asyncio.create_task(asyncio.sleep(10))
        mock_task2 = asyncio.create_task(asyncio.sleep(10))

        await pool.add_task("task1", mock_task1)
        await pool.add_task("task2", mock_task2)

        count = await pool.get_active_count()
        assert count == 2

        # Cleanup
        mock_task1.cancel()
        mock_task2.cancel()
        try:
            await mock_task1
            await mock_task2
        except asyncio.CancelledError:
            pass


class TestOrchestrator:
    """Test Orchestrator functionality."""

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self, mock_settings):
        """Test orchestrator initializes correctly."""
        with patch("aegis.orchestrator.main.AsanaClient"):
            orchestrator = Orchestrator(mock_settings)

            assert orchestrator.settings == mock_settings
            assert orchestrator.task_queue is not None
            assert orchestrator.agent_pool is not None
            assert orchestrator._running is False

    @pytest.mark.asyncio
    async def test_fetch_tasks_from_portfolio(self, mock_settings):
        """Test fetching tasks from portfolio."""
        with patch("aegis.orchestrator.main.AsanaClient") as mock_client_class, \
             patch("aegis.orchestrator.main.get_priority_weights_from_settings"):

            # Setup mocks
            mock_client = mock_client_class.return_value
            mock_client.get_tasks_from_project = AsyncMock(return_value=[
                create_task(gid="1", name="Task 1", completed=False, assignee=None),
                create_task(gid="2", name="Task 2", completed=False, assignee=None),
                create_task(gid="3", name="Task 3", completed=True, assignee=None),  # Should be filtered
            ])

            orchestrator = Orchestrator(mock_settings)

            # Mock the portfolio API
            mock_project = {"gid": "proj_123", "name": "Test Project"}

            with patch("asana.Configuration"), \
                 patch("asana.ApiClient"), \
                 patch("asana.PortfoliosApi"):


                # Mock the to_thread call for get_items_for_portfolio
                with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                    mock_to_thread.return_value = [mock_project]

                    tasks = await orchestrator._fetch_tasks_from_portfolio()

                    # Should only get incomplete, unassigned tasks
                    assert len(tasks) == 2
                    assert all(not t.completed and not t.assignee for t in tasks)

    @pytest.mark.asyncio
    async def test_execute_task_success(self, mock_settings):
        """Test successful task execution."""
        with patch("aegis.orchestrator.main.AsanaClient") as mock_client_class, \
             patch("aegis.orchestrator.main.get_priority_weights_from_settings"):
            mock_client = mock_client_class.return_value
            mock_client.get_project = AsyncMock(return_value=AsanaProject(
                gid="proj_123",
                name="Test Project",
                notes="Code Location: /tmp/test",
            ))
            mock_client.add_comment = AsyncMock()

            orchestrator = Orchestrator(mock_settings)

            # Create a test task
            project = AsanaProject(gid="proj_123", name="Test Project")
            task = create_task(
                gid="task_123",
                name="Test Task",
                notes="Test description",
                projects=[project],
            )

            score = TaskScore(
                task_gid="task_123",
                task_name="Test Task",
                total_score=6.0,
                due_date_score=5.0,
                dependency_score=0.0,
                user_priority_score=0.0,
                project_score=0.0,
                age_score=1.0,
            )

            # Mock database operations
            mock_session = MagicMock()
            mock_execution = MagicMock()
            mock_execution.id = 1
            mock_session.add = MagicMock()
            mock_session.commit = MagicMock()
            mock_session.close = MagicMock()

            # Mock subprocess
            mock_process = MagicMock()
            mock_process.communicate.return_value = ("Success output", "")
            mock_process.returncode = 0

            with patch("aegis.orchestrator.main.get_db", return_value=mock_session), \
                 patch("aegis.orchestrator.main.TaskExecution", return_value=mock_execution), \
                 patch("subprocess.Popen", return_value=mock_process), \
                 patch.object(orchestrator.agent_pool, "remove_task", new_callable=AsyncMock):

                await orchestrator._execute_task(task, score)

                # Verify comment was posted
                mock_client.add_comment.assert_called_once()
                call_args = mock_client.add_comment.call_args
                assert call_args[0][0] == "task_123"
                assert "✓" in call_args[0][1]  # Success emoji

    @pytest.mark.asyncio
    async def test_execute_task_failure(self, mock_settings):
        """Test task execution with failure."""
        with patch("aegis.orchestrator.main.AsanaClient") as mock_client_class, \
             patch("aegis.orchestrator.main.get_priority_weights_from_settings"):
            mock_client = mock_client_class.return_value
            mock_client.get_project = AsyncMock(return_value=AsanaProject(
                gid="proj_123",
                name="Test Project",
                notes="Code Location: /tmp/test",
            ))
            mock_client.add_comment = AsyncMock()

            orchestrator = Orchestrator(mock_settings)

            # Create a test task
            project = AsanaProject(gid="proj_123", name="Test Project")
            task = create_task(
                gid="task_123",
                name="Test Task",
                projects=[project],
            )

            score = TaskScore(
                task_gid="task_123",
                task_name="Test Task",
                total_score=0.0,
                due_date_score=0.0,
                dependency_score=0.0,
                user_priority_score=0.0,
                project_score=0.0,
                age_score=0.0,
            )

            # Mock database operations
            mock_session = MagicMock()
            mock_execution = MagicMock()
            mock_execution.id = 1
            mock_session.add = MagicMock()
            mock_session.commit = MagicMock()
            mock_session.close = MagicMock()
            mock_session.query.return_value.get.return_value = mock_execution

            # Mock subprocess with failure
            mock_process = MagicMock()
            mock_process.communicate.return_value = ("", "Error output")
            mock_process.returncode = 1

            with patch("aegis.orchestrator.main.get_db", return_value=mock_session), \
                 patch("aegis.orchestrator.main.TaskExecution", return_value=mock_execution), \
                 patch("subprocess.Popen", return_value=mock_process), \
                 patch.object(orchestrator.agent_pool, "remove_task", new_callable=AsyncMock):

                await orchestrator._execute_task(task, score)

                # Verify error comment was posted
                mock_client.add_comment.assert_called_once()
                call_args = mock_client.add_comment.call_args
                assert call_args[0][0] == "task_123"
                assert "⚠️" in call_args[0][1]  # Warning emoji

    @pytest.mark.asyncio
    async def test_poll_loop_integration(self, mock_settings):
        """Test poll loop fetches and queues tasks."""
        with patch("aegis.orchestrator.main.AsanaClient"), \
             patch("aegis.orchestrator.main.get_priority_weights_from_settings"):
            orchestrator = Orchestrator(mock_settings)
            orchestrator._running = True
            orchestrator.shutdown_handler = MagicMock()
            orchestrator.shutdown_handler.shutdown_requested = False

            # Mock fetch method to return tasks once, then stop
            call_count = 0

            async def mock_fetch():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return [create_task(gid="1", name="Task 1")]
                else:
                    # Stop the loop
                    orchestrator._running = False
                    return []

            orchestrator._fetch_tasks_from_portfolio = mock_fetch

            # Mock database operations
            mock_session = MagicMock()
            mock_state = MagicMock()

            with patch("aegis.orchestrator.main.get_db", return_value=mock_session), \
                 patch("aegis.orchestrator.main.get_or_create_system_state", return_value=mock_state), \
                 patch("aegis.orchestrator.main.update_system_stats"):

                # Run poll loop (should complete after one iteration)
                await orchestrator._poll_loop()

                # Verify task was added to queue
                size = await orchestrator.task_queue.size()
                assert size == 1

    @pytest.mark.asyncio
    async def test_dispatch_loop_integration(self, mock_settings):
        """Test dispatch loop pulls tasks from queue and executes them."""
        with patch("aegis.orchestrator.main.AsanaClient"), \
             patch("aegis.orchestrator.main.get_priority_weights_from_settings"):
            orchestrator = Orchestrator(mock_settings)
            orchestrator._running = True
            orchestrator.shutdown_handler = MagicMock()
            orchestrator.shutdown_handler.shutdown_requested = False

            # Add a task to the queue
            task = create_task(gid="1", name="Test Task")
            await orchestrator.task_queue.add_tasks([task])

            # Mock execute_task to just stop the loop
            async def mock_execute(task, score):
                orchestrator._running = False

            orchestrator._execute_task = mock_execute

            # Run dispatch loop (should dispatch one task then stop)
            await orchestrator._dispatch_loop()

            # Verify queue is empty (task was dispatched)
            size = await orchestrator.task_queue.size()
            assert size == 0


class TestOrchestratorIntegration:
    """Integration tests for orchestrator components."""

    @pytest.mark.asyncio
    async def test_queue_and_pool_interaction(self, prioritizer):
        """Test interaction between TaskQueue and AgentPool."""
        queue = TaskQueue(prioritizer)
        pool = AgentPool(max_concurrent=2)

        # Add tasks to queue
        tasks = [
            create_task(gid="1", name="Task 1"),
            create_task(gid="2", name="Task 2"),
            create_task(gid="3", name="Task 3"),
        ]
        await queue.add_tasks(tasks)

        # Simulate dispatching tasks to pool
        async def dummy_execution():
            await asyncio.sleep(0.05)

        # Dispatch first two tasks
        task_handles = []
        for _ in range(2):
            if await pool.can_accept_task():
                result = await queue.get_next_task()
                if result:
                    task, _ = result
                    await queue.remove_task(task.gid)
                    exec_task = asyncio.create_task(dummy_execution())
                    task_handles.append(exec_task)
                    await pool.add_task(task.gid, exec_task)

        # Pool should be full
        assert not await pool.can_accept_task()
        assert await pool.get_active_count() == 2
        assert await queue.size() == 1

        # Wait for tasks to complete
        await asyncio.gather(*task_handles)

        # Remove completed tasks from pool
        await pool.remove_task("1")
        await pool.remove_task("2")

        # Pool should have capacity again
        assert await pool.can_accept_task()
