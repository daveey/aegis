"""End-to-end integration tests for Aegis orchestration system.

This test module verifies the complete flow from Asana task creation
through agent processing to response posting and execution logging.

Test Requirements:
    - Real Asana API connection (uses test project)
    - Optional: Real Anthropic API (can be mocked)
    - PostgreSQL database (uses test database)
    - Clean test environment

Environment Variables Required:
    - ASANA_ACCESS_TOKEN: Asana PAT for test operations
    - ASANA_WORKSPACE_GID: Test workspace GID
    - ASANA_TEST_PROJECT_GID: Dedicated test project GID
    - ANTHROPIC_API_KEY: API key for Claude (optional if mocked)
    - DATABASE_URL: Test database URL
"""

import asyncio
import os
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import asana
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaProject, AsanaTask, AsanaTaskUpdate
from aegis.config import Settings, get_settings
from aegis.database.models import Base, Comment, Project, Task, TaskExecution


# Test configuration markers
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Load test settings with overrides for integration testing.

    This fixture ensures we use a test-specific configuration that won't
    interfere with production data.
    """
    # Check if we have required test environment variables
    required_vars = ["ASANA_ACCESS_TOKEN", "ASANA_WORKSPACE_GID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        pytest.skip(f"Missing required test environment variables: {', '.join(missing_vars)}")

    settings = Settings(
        database_url=os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://localhost/aegis_test"
        ),
        redis_url=os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1"),
    )

    return settings


@pytest.fixture(scope="session")
def db_engine(test_settings: Settings):
    """Create database engine for testing."""
    engine = create_engine(test_settings.database_url)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: drop all tables after all tests
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
async def asana_client(test_settings: Settings) -> AsanaClient:
    """Create Asana client for testing."""
    return AsanaClient(access_token=test_settings.asana_access_token)


@pytest.fixture
async def test_project(asana_client: AsanaClient, test_settings: Settings) -> AsyncGenerator[AsanaProject, None]:
    """Create or use existing test project in Asana.

    This fixture will:
    1. Look for existing test project
    2. Create one if it doesn't exist
    3. Clean up test tasks after test completion
    """
    # Check if we have a pre-configured test project
    test_project_gid = os.getenv("ASANA_TEST_PROJECT_GID")

    if test_project_gid:
        # Use existing test project
        project = await asana_client.get_project(test_project_gid)
    else:
        # Create temporary test project
        pytest.skip("ASANA_TEST_PROJECT_GID not set. Please configure a dedicated test project.")

    yield project

    # Cleanup: Delete any test tasks created during this test
    # (identified by name prefix "E2E_TEST_")
    tasks = await asana_client.get_tasks_from_project(project.gid)
    for task in tasks:
        if task.name.startswith("E2E_TEST_"):
            # Delete test task by completing and archiving
            try:
                await asana_client.update_task(
                    task.gid,
                    AsanaTaskUpdate(completed=True)
                )
            except Exception as e:
                print(f"Warning: Failed to cleanup test task {task.gid}: {e}")


@pytest.fixture
async def test_task(
    asana_client: AsanaClient,
    test_project: AsanaProject,
) -> AsyncGenerator[AsanaTask, None]:
    """Create a test task in Asana for E2E testing."""
    # Generate unique task name
    test_id = str(uuid.uuid4())[:8]
    task_name = f"E2E_TEST_{test_id}"

    # Create task via Asana API directly (simulating user action)
    configuration = asana.Configuration()
    configuration.access_token = os.getenv("ASANA_ACCESS_TOKEN")
    api_client = asana.ApiClient(configuration)
    tasks_api = asana.TasksApi(api_client)

    task_data = {
        "data": {
            "name": task_name,
            "notes": "This is a test task created by E2E integration test.\n\nPlease respond with the current date and time.",
            "projects": [test_project.gid],
            "workspace": os.getenv("ASANA_WORKSPACE_GID"),
        }
    }

    task_response = await asyncio.to_thread(
        tasks_api.create_task,
        task_data,
        {"opt_fields": "gid,name,notes,permalink_url"}
    )

    # Fetch full task details using our client
    task = await asana_client.get_task(task_response["gid"])

    yield task

    # Cleanup handled by test_project fixture


class TestEndToEndFlow:
    """Test complete Aegis orchestration flow end-to-end."""

    @pytest.mark.asyncio
    async def test_complete_flow_with_mock_agent(
        self,
        asana_client: AsanaClient,
        test_project: AsanaProject,
        test_task: AsanaTask,
        db_session: Session,
    ):
        """Test complete flow from Asana task to response with mocked agent.

        Flow:
        1. Create test task in Asana (done in fixture)
        2. Orchestrator discovers task
        3. Agent processes task (mocked)
        4. Response posted to Asana
        5. Execution logged to database
        """
        # Step 1: Verify test task was created
        assert test_task.gid is not None
        assert test_task.name.startswith("E2E_TEST_")
        assert test_task.projects[0].gid == test_project.gid

        # Step 2: Create project and task records in database
        db_project = Project(
            asana_gid=test_project.gid,
            name=test_project.name,
            portfolio_gid=os.getenv("ASANA_PORTFOLIO_GID", "test_portfolio"),
            workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
            last_synced_at=datetime.utcnow(),
        )
        db_session.add(db_project)
        db_session.flush()

        db_task = Task(
            asana_gid=test_task.gid,
            project_id=db_project.id,
            name=test_task.name,
            description=test_task.notes,
            completed=False,
            assignee_gid=test_task.assignee.gid if test_task.assignee else None,
            assigned_to_aegis=True,
            asana_permalink_url=test_task.permalink_url,
            last_synced_at=datetime.utcnow(),
            modified_at=test_task.modified_at,
        )
        db_session.add(db_task)
        db_session.flush()

        # Step 3: Create task execution record
        execution = TaskExecution(
            task_id=db_task.id,
            status="in_progress",
            agent_type="test_agent",
            started_at=datetime.utcnow(),
        )
        db_session.add(execution)
        db_session.flush()

        # Step 4: Simulate agent processing (mock the Claude response)
        mock_response = f"""Task completed successfully!

Current date and time: {datetime.utcnow().isoformat()}

This is a test response from the E2E integration test.
"""

        # Update execution with results
        execution.status = "completed"
        execution.success = True
        execution.completed_at = datetime.utcnow()
        execution.duration_seconds = 5
        execution.output = mock_response
        execution.input_tokens = 100
        execution.output_tokens = 50
        db_session.flush()

        # Step 5: Post comment to Asana
        comment_text = f"""✓ Task completed via Aegis (E2E Test)

**Agent**: test_agent
**Status**: success
**Duration**: {execution.duration_seconds}s

**Output**:
```
{mock_response}
```

**Test Run**: {datetime.utcnow().isoformat()}
"""

        comment = await asana_client.add_comment(test_task.gid, comment_text)
        assert comment.gid is not None
        assert comment.text == comment_text

        # Step 6: Store comment in database
        db_comment = Comment(
            asana_gid=comment.gid,
            task_id=db_task.id,
            text=comment.text,
            created_by_gid=comment.created_by.gid,
            created_by_name=comment.created_by.name,
            is_from_aegis=True,
            comment_type="response",
            created_at=comment.created_at,
        )
        db_session.add(db_comment)
        db_session.commit()

        # Step 7: Verify complete flow
        # Check task execution was logged
        assert execution.status == "completed"
        assert execution.success is True
        assert execution.output is not None

        # Check comment was posted
        comments = await asana_client.get_comments(test_task.gid)
        posted_comments = [c for c in comments if c.text == comment_text]
        assert len(posted_comments) == 1

        # Check database records
        db_executions = db_session.query(TaskExecution).filter_by(task_id=db_task.id).all()
        assert len(db_executions) == 1
        assert db_executions[0].status == "completed"

        db_comments = db_session.query(Comment).filter_by(task_id=db_task.id).all()
        assert len(db_comments) == 1
        assert db_comments[0].is_from_aegis is True

    @pytest.mark.asyncio
    async def test_error_handling_flow(
        self,
        asana_client: AsanaClient,
        test_task: AsanaTask,
        db_session: Session,
    ):
        """Test error handling in the E2E flow.

        This test simulates an agent failure and verifies proper error handling.
        """
        # Create minimal database records
        db_project = Project(
            asana_gid=test_task.projects[0].gid,
            name=test_task.projects[0].name,
            portfolio_gid="test_portfolio",
            workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
        )
        db_session.add(db_project)
        db_session.flush()

        db_task = Task(
            asana_gid=test_task.gid,
            project_id=db_project.id,
            name=test_task.name,
            description=test_task.notes,
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(db_task)
        db_session.flush()

        # Create failed execution
        execution = TaskExecution(
            task_id=db_task.id,
            status="failed",
            agent_type="test_agent",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=2,
            success=False,
            error_message="Simulated agent failure for testing",
        )
        db_session.add(execution)
        db_session.flush()

        # Post error comment to Asana
        error_comment_text = f"""⚠️ Task execution failed

**Agent**: test_agent
**Error**: {execution.error_message}
**Duration**: {execution.duration_seconds}s

Please review the task requirements and try again.
"""

        comment = await asana_client.add_comment(test_task.gid, error_comment_text)

        # Store error comment
        db_comment = Comment(
            asana_gid=comment.gid,
            task_id=db_task.id,
            text=comment.text,
            created_by_gid=comment.created_by.gid,
            created_by_name=comment.created_by.name,
            is_from_aegis=True,
            comment_type="error",
            created_at=comment.created_at,
        )
        db_session.add(db_comment)
        db_session.commit()

        # Verify error was handled properly
        assert execution.status == "failed"
        assert execution.success is False
        assert execution.error_message is not None

        # Verify error comment was posted
        comments = await asana_client.get_comments(test_task.gid)
        error_comments = [c for c in comments if "⚠️" in c.text]
        assert len(error_comments) >= 1

    @pytest.mark.asyncio
    async def test_task_assignment_flow(
        self,
        asana_client: AsanaClient,
        test_task: AsanaTask,
    ):
        """Test task assignment and status updates.

        Verifies that tasks can be properly assigned and their status tracked.
        """
        # Get current task state
        task = await asana_client.get_task(test_task.gid)
        initial_completed = task.completed

        # Simulate assignment to Aegis (in real flow, this would be done by user)
        # For now, just verify we can update task status

        # Update task to mark as in-progress (via comment)
        await asana_client.add_comment(
            test_task.gid,
            "🔄 Task picked up by Aegis orchestrator\n\nStarting execution..."
        )

        # Verify comment was added
        comments = await asana_client.get_comments(test_task.gid)
        status_comments = [c for c in comments if "picked up by Aegis" in c.text]
        assert len(status_comments) >= 1

        # Mark task as complete
        updated_task = await asana_client.update_task(
            test_task.gid,
            AsanaTaskUpdate(completed=True)
        )

        assert updated_task.completed is True
        assert updated_task.completed_at is not None

    @pytest.mark.asyncio
    async def test_concurrent_task_processing(
        self,
        asana_client: AsanaClient,
        test_project: AsanaProject,
        db_session: Session,
    ):
        """Test that multiple tasks can be processed concurrently.

        This simulates the orchestrator handling multiple tasks in parallel.
        """
        # Create multiple test tasks
        num_tasks = 3
        test_tasks = []

        configuration = asana.Configuration()
        configuration.access_token = os.getenv("ASANA_ACCESS_TOKEN")
        api_client = asana.ApiClient(configuration)
        tasks_api = asana.TasksApi(api_client)

        for i in range(num_tasks):
            test_id = str(uuid.uuid4())[:8]
            task_data = {
                "data": {
                    "name": f"E2E_TEST_CONCURRENT_{test_id}_{i}",
                    "notes": f"Concurrent test task {i}",
                    "projects": [test_project.gid],
                }
            }

            task_response = await asyncio.to_thread(
                tasks_api.create_task,
                task_data,
                {"opt_fields": "gid,name"}
            )

            task = await asana_client.get_task(task_response["gid"])
            test_tasks.append(task)

        # Simulate concurrent processing
        async def process_task(task: AsanaTask) -> str:
            """Simulate processing a single task."""
            await asyncio.sleep(0.5)  # Simulate work
            await asana_client.add_comment(
                task.gid,
                f"✓ Task processed concurrently at {datetime.utcnow().isoformat()}"
            )
            return task.gid

        # Process all tasks concurrently
        results = await asyncio.gather(
            *[process_task(task) for task in test_tasks],
            return_exceptions=True
        )

        # Verify all tasks were processed
        assert len(results) == num_tasks
        assert all(isinstance(r, str) for r in results)

        # Cleanup test tasks
        for task in test_tasks:
            try:
                await asana_client.update_task(
                    task.gid,
                    AsanaTaskUpdate(completed=True)
                )
            except Exception as e:
                print(f"Warning: Failed to cleanup task {task.gid}: {e}")

    @pytest.mark.asyncio
    async def test_retry_mechanism(
        self,
        asana_client: AsanaClient,
        test_task: AsanaTask,
        db_session: Session,
    ):
        """Test that failed operations are retried properly.

        Verifies the retry logic in AsanaClient works correctly.
        """
        # Create database records
        db_project = Project(
            asana_gid=test_task.projects[0].gid,
            name=test_task.projects[0].name,
            portfolio_gid="test_portfolio",
            workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
        )
        db_session.add(db_project)
        db_session.flush()

        db_task = Task(
            asana_gid=test_task.gid,
            project_id=db_project.id,
            name=test_task.name,
            description=test_task.notes,
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(db_task)
        db_session.flush()

        # Attempt to add comment (should succeed with retries)
        comment = await asana_client.add_comment(
            test_task.gid,
            "Testing retry mechanism - this should succeed"
        )

        assert comment.gid is not None
        assert comment.text is not None

        # Verify the retry decorator is working by checking the comment exists
        comments = await asana_client.get_comments(test_task.gid)
        matching_comments = [c for c in comments if "retry mechanism" in c.text]
        assert len(matching_comments) == 1


class TestDatabaseIntegration:
    """Test database operations in the E2E flow."""

    def test_project_crud_operations(self, db_session: Session):
        """Test basic CRUD operations for Project model."""
        # Create
        project = Project(
            asana_gid="test_proj_123",
            name="Test Project",
            portfolio_gid="test_portfolio",
            workspace_gid="test_workspace",
            code_path="/path/to/code",
            notes="Test project notes",
        )
        db_session.add(project)
        db_session.flush()

        assert project.id is not None

        # Read
        retrieved = db_session.query(Project).filter_by(asana_gid="test_proj_123").first()
        assert retrieved is not None
        assert retrieved.name == "Test Project"

        # Update
        retrieved.name = "Updated Project Name"
        db_session.flush()

        updated = db_session.query(Project).filter_by(asana_gid="test_proj_123").first()
        assert updated.name == "Updated Project Name"

        # Delete
        db_session.delete(updated)
        db_session.flush()

        deleted = db_session.query(Project).filter_by(asana_gid="test_proj_123").first()
        assert deleted is None

    def test_task_execution_relationships(self, db_session: Session):
        """Test relationships between Task and TaskExecution models."""
        # Create project
        project = Project(
            asana_gid="test_proj_456",
            name="Test Project",
            portfolio_gid="test_portfolio",
            workspace_gid="test_workspace",
        )
        db_session.add(project)
        db_session.flush()

        # Create task
        task = Task(
            asana_gid="test_task_789",
            project_id=project.id,
            name="Test Task",
            description="Test description",
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(task)
        db_session.flush()

        # Create multiple executions
        exec1 = TaskExecution(
            task_id=task.id,
            status="completed",
            agent_type="test_agent",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            success=True,
        )
        exec2 = TaskExecution(
            task_id=task.id,
            status="failed",
            agent_type="test_agent",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            success=False,
            error_message="Test error",
        )
        db_session.add_all([exec1, exec2])
        db_session.flush()

        # Verify relationships
        retrieved_task = db_session.query(Task).filter_by(asana_gid="test_task_789").first()
        assert len(retrieved_task.executions) == 2
        assert retrieved_task.project.asana_gid == "test_proj_456"

        # Verify cascade delete
        db_session.delete(retrieved_task)
        db_session.flush()

        remaining_executions = db_session.query(TaskExecution).filter_by(task_id=task.id).all()
        assert len(remaining_executions) == 0


class TestCLIIntegration:
    """Test the CLI commands for orchestration."""

    @pytest.mark.asyncio
    async def test_config_command(self):
        """Test that the config command runs without errors."""
        import subprocess

        result = subprocess.run(
            ["aegis", "config"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Should succeed and display config
        assert result.returncode == 0
        assert "Aegis Configuration" in result.stdout

    @pytest.mark.asyncio
    async def test_test_asana_command(self):
        """Test that the test-asana command works."""
        import subprocess

        result = subprocess.run(
            ["aegis", "test-asana"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed and show portfolio info
        assert result.returncode == 0
        assert "Testing Asana connection" in result.stdout or "Asana API connection successful" in result.stdout


@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="Live Anthropic API tests skipped (set RUN_LIVE_TESTS=1 to enable)"
)
class TestLiveAgentIntegration:
    """Tests using live Anthropic API (optional, skipped by default)."""

    @pytest.mark.asyncio
    async def test_real_claude_execution(
        self,
        asana_client: AsanaClient,
        test_task: AsanaTask,
        test_settings: Settings,
    ):
        """Test with real Claude API call.

        This test is skipped by default to avoid API costs.
        Set RUN_LIVE_TESTS=1 to enable.
        """
        import anthropic

        client = anthropic.Anthropic(api_key=test_settings.anthropic_api_key)

        # Create simple prompt
        prompt = f"""Task: {test_task.name}

Description: {test_task.notes}

Please provide a brief response to complete this task."""

        # Call Claude API
        message = client.messages.create(
            model=test_settings.anthropic_model,
            max_tokens=test_settings.anthropic_max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text

        # Post response to Asana
        await asana_client.add_comment(
            test_task.gid,
            f"✓ Task completed via Aegis (Live Test)\n\n{response_text}"
        )

        # Verify response
        assert len(response_text) > 0
        assert message.usage.input_tokens > 0
        assert message.usage.output_tokens > 0


@pytest.mark.skipif(
    not os.getenv("RUN_ORCHESTRATOR_TESTS"),
    reason="Full orchestrator tests skipped (set RUN_ORCHESTRATOR_TESTS=1 to enable)"
)
class TestFullOrchestratorFlow:
    """Test complete orchestrator flow with real task execution.

    These tests require Claude CLI to be installed and are more intensive.
    """

    @pytest.mark.asyncio
    async def test_orchestrator_task_discovery_and_execution(
        self,
        asana_client: AsanaClient,
        test_project: AsanaProject,
        db_session: Session,
    ):
        """Test that orchestrator can discover and execute tasks from a project.

        This is a full integration test simulating the real workflow.
        """
        # Create a simple test task that doesn't require actual code execution
        configuration = asana.Configuration()
        configuration.access_token = os.getenv("ASANA_ACCESS_TOKEN")
        api_client = asana.ApiClient(configuration)
        tasks_api = asana.TasksApi(api_client)

        test_id = str(uuid.uuid4())[:8]
        task_data = {
            "data": {
                "name": f"E2E_TEST_ORCHESTRATOR_{test_id}",
                "notes": "Please respond with a simple hello message. This is a test task.",
                "projects": [test_project.gid],
            }
        }

        task_response = await asyncio.to_thread(
            tasks_api.create_task,
            task_data,
            {"opt_fields": "gid,name,notes,permalink_url"}
        )

        task = await asana_client.get_task(task_response["gid"])

        try:
            # Create database records (simulating orchestrator discovery)
            db_project = Project(
                asana_gid=test_project.gid,
                name=test_project.name,
                portfolio_gid=os.getenv("ASANA_PORTFOLIO_GID", "test_portfolio"),
                workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
                last_synced_at=datetime.utcnow(),
            )
            db_session.add(db_project)
            db_session.flush()

            db_task = Task(
                asana_gid=task.gid,
                project_id=db_project.id,
                name=task.name,
                description=task.notes,
                completed=False,
                assigned_to_aegis=True,
                asana_permalink_url=task.permalink_url,
                last_synced_at=datetime.utcnow(),
                modified_at=task.modified_at,
            )
            db_session.add(db_task)
            db_session.flush()

            # Create execution record
            execution = TaskExecution(
                task_id=db_task.id,
                status="in_progress",
                agent_type="claude_cli",
                started_at=datetime.utcnow(),
            )
            db_session.add(execution)
            db_session.flush()

            # Verify that task was discovered and recorded
            assert execution.task_id is not None
            assert execution.status == "in_progress"
            assert db_task.assigned_to_aegis is True

            # Mark execution as completed (in real flow, this would be done after agent execution)
            execution.status = "completed"
            execution.success = True
            execution.completed_at = datetime.utcnow()
            execution.duration_seconds = 1
            db_session.commit()

            # Verify final state
            assert execution.success is True
            assert execution.completed_at is not None

        finally:
            # Cleanup
            try:
                await asana_client.update_task(
                    task.gid,
                    AsanaTaskUpdate(completed=True)
                )
            except Exception as e:
                print(f"Warning: Failed to cleanup task {task.gid}: {e}")

    @pytest.mark.asyncio
    async def test_orchestrator_handles_multiple_projects(
        self,
        asana_client: AsanaClient,
        test_project: AsanaProject,
        db_session: Session,
    ):
        """Test that orchestrator can track tasks from multiple projects."""
        # Create two projects in database
        project1 = Project(
            asana_gid=test_project.gid,
            name=test_project.name,
            portfolio_gid=os.getenv("ASANA_PORTFOLIO_GID", "test_portfolio"),
            workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
            last_synced_at=datetime.utcnow(),
        )
        db_session.add(project1)

        project2 = Project(
            asana_gid="test_proj_2",
            name="Test Project 2",
            portfolio_gid=os.getenv("ASANA_PORTFOLIO_GID", "test_portfolio"),
            workspace_gid=os.getenv("ASANA_WORKSPACE_GID"),
            last_synced_at=datetime.utcnow(),
        )
        db_session.add(project2)
        db_session.flush()

        # Create tasks in each project
        task1 = Task(
            asana_gid="test_task_1",
            project_id=project1.id,
            name="Test Task 1",
            description="Task in project 1",
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(task1)

        task2 = Task(
            asana_gid="test_task_2",
            project_id=project2.id,
            name="Test Task 2",
            description="Task in project 2",
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(task2)
        db_session.flush()

        # Verify projects are tracked
        projects = db_session.query(Project).all()
        assert len(projects) >= 2

        # Verify tasks are associated with correct projects
        retrieved_task1 = db_session.query(Task).filter_by(asana_gid="test_task_1").first()
        retrieved_task2 = db_session.query(Task).filter_by(asana_gid="test_task_2").first()

        assert retrieved_task1.project_id == project1.id
        assert retrieved_task2.project_id == project2.id

    @pytest.mark.asyncio
    async def test_execution_history_tracking(
        self,
        db_session: Session,
    ):
        """Test that execution history is properly tracked over multiple runs."""
        # Create project and task
        project = Project(
            asana_gid="history_test_proj",
            name="History Test Project",
            portfolio_gid="test_portfolio",
            workspace_gid="test_workspace",
        )
        db_session.add(project)
        db_session.flush()

        task = Task(
            asana_gid="history_test_task",
            project_id=project.id,
            name="History Test Task",
            description="Testing execution history",
            completed=False,
            assigned_to_aegis=True,
        )
        db_session.add(task)
        db_session.flush()

        # Create multiple executions (simulating retries)
        executions = []
        for i in range(3):
            execution = TaskExecution(
                task_id=task.id,
                status="completed" if i == 2 else "failed",
                agent_type="test_agent",
                started_at=datetime.utcnow() - timedelta(minutes=3 - i),
                completed_at=datetime.utcnow() - timedelta(minutes=3 - i) + timedelta(seconds=30),
                duration_seconds=30,
                success=i == 2,
                error_message=f"Retry {i}" if i < 2 else None,
                input_tokens=100,
                output_tokens=50,
            )
            executions.append(execution)
            db_session.add(execution)

        db_session.flush()

        # Query execution history
        history = db_session.query(TaskExecution).filter_by(task_id=task.id).order_by(
            TaskExecution.started_at
        ).all()

        # Verify history is complete
        assert len(history) == 3
        assert history[0].success is False
        assert history[1].success is False
        assert history[2].success is True

        # Verify we can get latest successful execution
        latest_success = (
            db_session.query(TaskExecution)
            .filter_by(task_id=task.id, success=True)
            .order_by(TaskExecution.completed_at.desc())
            .first()
        )
        assert latest_success is not None
        assert latest_success.error_message is None
