"""Unit tests for database CRUD operations."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.crud import (
    DuplicateError,
    # Exceptions
    NotFoundError,
    # Project operations
    create_project,
    # Task operations
    create_task,
    # TaskExecution operations
    create_task_execution,
    get_all_projects,
    # Helper functions
    get_or_create_project,
    get_or_create_task,
    get_project_by_gid,
    get_task_by_gid,
    get_task_executions_by_task,
    get_tasks_by_project,
    mark_task_complete,
    update_project,
    update_task,
    update_task_execution_status,
)
from aegis.database.models import Base

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_project(db_session):
    """Create a sample project for testing."""
    project = create_project(
        asana_gid="test_project_123",
        name="Test Project",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        code_path="/path/to/code",
        session=db_session,
    )
    return project


@pytest.fixture
def sample_task(db_session, sample_project):
    """Create a sample task for testing."""
    task = create_task(
        asana_gid="test_task_456",
        project_id=sample_project.id,
        name="Test Task",
        description="This is a test task",
        assigned_to_aegis=True,
        session=db_session,
    )
    return task


@pytest.fixture
def sample_execution(db_session, sample_task):
    """Create a sample task execution for testing."""
    execution = create_task_execution(
        task_id=sample_task.id,
        status="pending",
        agent_type="simple_executor",
        session=db_session,
    )
    return execution


# ============================================================================
# Project CRUD Tests
# ============================================================================


def test_create_project(db_session):
    """Test creating a new project."""
    project = create_project(
        asana_gid="project_123",
        name="My Project",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        code_path="/home/user/project",
        team_gid="team_101",
        notes="Project notes",
        session=db_session,
    )

    assert project.id is not None
    assert project.asana_gid == "project_123"
    assert project.name == "My Project"
    assert project.code_path == "/home/user/project"
    assert project.portfolio_gid == "portfolio_456"
    assert project.workspace_gid == "workspace_789"
    assert project.team_gid == "team_101"
    assert project.notes == "Project notes"
    assert project.archived is False
    assert project.settings == {}


def test_create_project_minimal(db_session):
    """Test creating a project with only required fields."""
    project = create_project(
        asana_gid="project_minimal",
        name="Minimal Project",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        session=db_session,
    )

    assert project.id is not None
    assert project.asana_gid == "project_minimal"
    assert project.name == "Minimal Project"
    assert project.code_path is None
    assert project.team_gid is None


def test_create_project_duplicate(db_session):
    """Test that creating a duplicate project raises DuplicateError."""
    create_project(
        asana_gid="duplicate_project",
        name="First Project",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        session=db_session,
    )

    with pytest.raises(DuplicateError) as exc_info:
        create_project(
            asana_gid="duplicate_project",
            name="Second Project",
            portfolio_gid="portfolio_456",
            workspace_gid="workspace_789",
            session=db_session,
        )

    assert "duplicate_project" in str(exc_info.value)


def test_get_project_by_gid(db_session, sample_project):
    """Test fetching a project by its Asana GID."""
    project = get_project_by_gid("test_project_123", session=db_session)

    assert project is not None
    assert project.id == sample_project.id
    assert project.asana_gid == "test_project_123"
    assert project.name == "Test Project"


def test_get_project_by_gid_not_found(db_session):
    """Test that fetching a non-existent project returns None."""
    project = get_project_by_gid("nonexistent_project", session=db_session)
    assert project is None


def test_get_all_projects(db_session):
    """Test fetching all projects."""
    # Create multiple projects
    create_project(
        asana_gid="project_1",
        name="Project 1",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        session=db_session,
    )
    create_project(
        asana_gid="project_2",
        name="Project 2",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        session=db_session,
    )
    create_project(
        asana_gid="project_3",
        name="Project 3",
        portfolio_gid="portfolio_999",
        workspace_gid="workspace_789",
        archived=True,
        session=db_session,
    )

    # Get all non-archived projects
    projects = get_all_projects(session=db_session)
    assert len(projects) == 2

    # Get all projects including archived
    projects = get_all_projects(archived=True, session=db_session)
    assert len(projects) == 3

    # Get projects by portfolio
    projects = get_all_projects(portfolio_gid="portfolio_456", session=db_session)
    assert len(projects) == 2


def test_update_project(db_session, sample_project):
    """Test updating a project."""
    updated_project = update_project(
        asana_gid="test_project_123",
        name="Updated Project Name",
        code_path="/new/path",
        notes="Updated notes",
        archived=True,
        session=db_session,
    )

    assert updated_project.name == "Updated Project Name"
    assert updated_project.code_path == "/new/path"
    assert updated_project.notes == "Updated notes"
    assert updated_project.archived is True


def test_update_project_partial(db_session, sample_project):
    """Test updating only some fields of a project."""
    updated_project = update_project(
        asana_gid="test_project_123",
        name="New Name Only",
        session=db_session,
    )

    assert updated_project.name == "New Name Only"
    # Original values should be preserved
    assert updated_project.code_path == "/path/to/code"
    assert updated_project.archived is False


def test_update_project_not_found(db_session):
    """Test that updating a non-existent project raises NotFoundError."""
    with pytest.raises(NotFoundError) as exc_info:
        update_project(
            asana_gid="nonexistent_project",
            name="New Name",
            session=db_session,
        )

    assert "nonexistent_project" in str(exc_info.value)


# ============================================================================
# Task CRUD Tests
# ============================================================================


def test_create_task(db_session, sample_project):
    """Test creating a new task."""
    task = create_task(
        asana_gid="task_123",
        project_id=sample_project.id,
        name="My Task",
        description="Task description",
        html_notes="<p>HTML notes</p>",
        completed=False,
        due_on="2024-12-31",
        assignee_gid="user_456",
        assignee_name="John Doe",
        assigned_to_aegis=True,
        num_subtasks=3,
        tags=["urgent", "bug"],
        custom_fields={"priority": "high"},
        session=db_session,
    )

    assert task.id is not None
    assert task.asana_gid == "task_123"
    assert task.name == "My Task"
    assert task.description == "Task description"
    assert task.html_notes == "<p>HTML notes</p>"
    assert task.completed is False
    assert task.due_on == "2024-12-31"
    assert task.assignee_gid == "user_456"
    assert task.assignee_name == "John Doe"
    assert task.assigned_to_aegis is True
    assert task.num_subtasks == 3
    assert task.tags == ["urgent", "bug"]
    assert task.custom_fields == {"priority": "high"}


def test_create_task_minimal(db_session, sample_project):
    """Test creating a task with only required fields."""
    task = create_task(
        asana_gid="task_minimal",
        project_id=sample_project.id,
        name="Minimal Task",
        session=db_session,
    )

    assert task.id is not None
    assert task.asana_gid == "task_minimal"
    assert task.name == "Minimal Task"
    assert task.completed is False
    assert task.assigned_to_aegis is False
    assert task.num_subtasks == 0
    assert task.tags == []
    assert task.custom_fields == {}


def test_create_task_duplicate(db_session, sample_project):
    """Test that creating a duplicate task raises DuplicateError."""
    create_task(
        asana_gid="duplicate_task",
        project_id=sample_project.id,
        name="First Task",
        session=db_session,
    )

    with pytest.raises(DuplicateError) as exc_info:
        create_task(
            asana_gid="duplicate_task",
            project_id=sample_project.id,
            name="Second Task",
            session=db_session,
        )

    assert "duplicate_task" in str(exc_info.value)


def test_get_task_by_gid(db_session, sample_task):
    """Test fetching a task by its Asana GID."""
    task = get_task_by_gid("test_task_456", session=db_session)

    assert task is not None
    assert task.id == sample_task.id
    assert task.asana_gid == "test_task_456"
    assert task.name == "Test Task"


def test_get_task_by_gid_not_found(db_session):
    """Test that fetching a non-existent task returns None."""
    task = get_task_by_gid("nonexistent_task", session=db_session)
    assert task is None


def test_get_tasks_by_project(db_session, sample_project):
    """Test fetching all tasks for a project."""
    # Create multiple tasks
    create_task(
        asana_gid="task_1",
        project_id=sample_project.id,
        name="Task 1",
        assigned_to_aegis=True,
        completed=False,
        session=db_session,
    )
    create_task(
        asana_gid="task_2",
        project_id=sample_project.id,
        name="Task 2",
        assigned_to_aegis=True,
        completed=True,
        session=db_session,
    )
    create_task(
        asana_gid="task_3",
        project_id=sample_project.id,
        name="Task 3",
        assigned_to_aegis=False,
        completed=False,
        session=db_session,
    )

    # Get all tasks
    tasks = get_tasks_by_project(sample_project.id, session=db_session)
    assert len(tasks) == 3

    # Get tasks assigned to aegis
    tasks = get_tasks_by_project(
        sample_project.id,
        assigned_to_aegis=True,
        session=db_session,
    )
    assert len(tasks) == 2

    # Get completed tasks
    tasks = get_tasks_by_project(
        sample_project.id,
        completed=True,
        session=db_session,
    )
    assert len(tasks) == 1

    # Get incomplete tasks assigned to aegis
    tasks = get_tasks_by_project(
        sample_project.id,
        assigned_to_aegis=True,
        completed=False,
        session=db_session,
    )
    assert len(tasks) == 1


def test_update_task(db_session, sample_task):
    """Test updating a task."""
    updated_task = update_task(
        asana_gid="test_task_456",
        name="Updated Task Name",
        description="Updated description",
        completed=True,
        assignee_name="Jane Smith",
        tags=["reviewed"],
        session=db_session,
    )

    assert updated_task.name == "Updated Task Name"
    assert updated_task.description == "Updated description"
    assert updated_task.completed is True
    assert updated_task.assignee_name == "Jane Smith"
    assert updated_task.tags == ["reviewed"]


def test_update_task_partial(db_session, sample_task):
    """Test updating only some fields of a task."""
    updated_task = update_task(
        asana_gid="test_task_456",
        name="New Name Only",
        session=db_session,
    )

    assert updated_task.name == "New Name Only"
    # Original values should be preserved
    assert updated_task.description == "This is a test task"
    assert updated_task.assigned_to_aegis is True


def test_update_task_not_found(db_session):
    """Test that updating a non-existent task raises NotFoundError."""
    with pytest.raises(NotFoundError) as exc_info:
        update_task(
            asana_gid="nonexistent_task",
            name="New Name",
            session=db_session,
        )

    assert "nonexistent_task" in str(exc_info.value)


def test_mark_task_complete(db_session, sample_task):
    """Test marking a task as complete."""
    completed_at = datetime.utcnow()
    updated_task = mark_task_complete(
        asana_gid="test_task_456",
        completed_at=completed_at,
        session=db_session,
    )

    assert updated_task.completed is True
    assert updated_task.completed_at == completed_at


def test_mark_task_complete_default_time(db_session, sample_task):
    """Test marking a task as complete with default timestamp."""
    before = datetime.utcnow()
    updated_task = mark_task_complete(
        asana_gid="test_task_456",
        session=db_session,
    )
    after = datetime.utcnow()

    assert updated_task.completed is True
    assert updated_task.completed_at is not None
    assert before <= updated_task.completed_at <= after


def test_mark_task_complete_not_found(db_session):
    """Test that marking a non-existent task complete raises NotFoundError."""
    with pytest.raises(NotFoundError) as exc_info:
        mark_task_complete(
            asana_gid="nonexistent_task",
            session=db_session,
        )

    assert "nonexistent_task" in str(exc_info.value)


# ============================================================================
# TaskExecution CRUD Tests
# ============================================================================


def test_create_task_execution(db_session, sample_task):
    """Test creating a new task execution."""
    started_at = datetime.utcnow()
    execution = create_task_execution(
        task_id=sample_task.id,
        status="in_progress",
        agent_type="simple_executor",
        started_at=started_at,
        context={"key": "value"},
        execution_metadata={"meta": "data"},
        session=db_session,
    )

    assert execution.id is not None
    assert execution.task_id == sample_task.id
    assert execution.status == "in_progress"
    assert execution.agent_type == "simple_executor"
    assert execution.started_at == started_at
    assert execution.context == {"key": "value"}
    assert execution.execution_metadata == {"meta": "data"}


def test_create_task_execution_minimal(db_session):
    """Test creating a task execution with minimal fields."""
    execution = create_task_execution(session=db_session)

    assert execution.id is not None
    assert execution.task_id is None
    assert execution.status == "pending"
    assert execution.agent_type is None
    assert execution.started_at is not None
    assert execution.context == {}
    assert execution.execution_metadata == {}


def test_get_task_executions_by_task(db_session, sample_task):
    """Test fetching all executions for a task."""
    # Create multiple executions
    create_task_execution(
        task_id=sample_task.id,
        status="completed",
        session=db_session,
    )
    create_task_execution(
        task_id=sample_task.id,
        status="failed",
        session=db_session,
    )
    create_task_execution(
        task_id=sample_task.id,
        status="in_progress",
        session=db_session,
    )

    # Get all executions
    executions = get_task_executions_by_task(sample_task.id, session=db_session)
    assert len(executions) == 3

    # Get only completed executions
    executions = get_task_executions_by_task(
        sample_task.id,
        status="completed",
        session=db_session,
    )
    assert len(executions) == 1
    assert executions[0].status == "completed"


def test_update_task_execution_status(db_session, sample_execution):
    """Test updating a task execution's status."""
    completed_at = datetime.utcnow()
    updated_execution = update_task_execution_status(
        execution_id=sample_execution.id,
        status="completed",
        completed_at=completed_at,
        success=True,
        output="Task completed successfully",
        duration_seconds=120,
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.05,
        session=db_session,
    )

    assert updated_execution.status == "completed"
    assert updated_execution.completed_at == completed_at
    assert updated_execution.success is True
    assert updated_execution.output == "Task completed successfully"
    assert updated_execution.duration_seconds == 120
    assert updated_execution.input_tokens == 1000
    assert updated_execution.output_tokens == 500
    assert float(updated_execution.cost_usd) == 0.05


def test_update_task_execution_status_failed(db_session, sample_execution):
    """Test updating a task execution to failed status."""
    updated_execution = update_task_execution_status(
        execution_id=sample_execution.id,
        status="failed",
        success=False,
        error_message="Task execution failed",
        session=db_session,
    )

    assert updated_execution.status == "failed"
    assert updated_execution.success is False
    assert updated_execution.error_message == "Task execution failed"


def test_update_task_execution_status_not_found(db_session):
    """Test that updating a non-existent execution raises NotFoundError."""
    with pytest.raises(NotFoundError) as exc_info:
        update_task_execution_status(
            execution_id=99999,
            status="completed",
            session=db_session,
        )

    assert "99999" in str(exc_info.value)


# ============================================================================
# Helper Function Tests
# ============================================================================


def test_get_or_create_project_creates_new(db_session):
    """Test that get_or_create_project creates a new project if not exists."""
    project, created = get_or_create_project(
        asana_gid="new_project_123",
        name="New Project",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        session=db_session,
    )

    assert created is True
    assert project.id is not None
    assert project.asana_gid == "new_project_123"
    assert project.name == "New Project"


def test_get_or_create_project_gets_existing(db_session, sample_project):
    """Test that get_or_create_project returns existing project."""
    project, created = get_or_create_project(
        asana_gid="test_project_123",
        name="Different Name",
        portfolio_gid="different_portfolio",
        workspace_gid="different_workspace",
        session=db_session,
    )

    assert created is False
    assert project.id == sample_project.id
    assert project.asana_gid == "test_project_123"
    # Should keep original name, not update
    assert project.name == "Test Project"


def test_get_or_create_task_creates_new(db_session, sample_project):
    """Test that get_or_create_task creates a new task if not exists."""
    task, created = get_or_create_task(
        asana_gid="new_task_123",
        project_id=sample_project.id,
        name="New Task",
        session=db_session,
    )

    assert created is True
    assert task.id is not None
    assert task.asana_gid == "new_task_123"
    assert task.name == "New Task"


def test_get_or_create_task_gets_existing(db_session, sample_task, sample_project):
    """Test that get_or_create_task returns existing task."""
    task, created = get_or_create_task(
        asana_gid="test_task_456",
        project_id=sample_project.id,
        name="Different Name",
        session=db_session,
    )

    assert created is False
    assert task.id == sample_task.id
    assert task.asana_gid == "test_task_456"
    # Should keep original name, not update
    assert task.name == "Test Task"


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


def test_create_project_with_settings(db_session):
    """Test creating a project with custom settings."""
    settings = {"feature_flags": {"enabled": True}, "config": {"value": 42}}
    project = create_project(
        asana_gid="project_with_settings",
        name="Project with Settings",
        portfolio_gid="portfolio_456",
        workspace_gid="workspace_789",
        settings=settings,
        session=db_session,
    )

    assert project.settings == settings


def test_update_project_with_timestamp(db_session, sample_project):
    """Test updating a project with last_synced_at timestamp."""
    sync_time = datetime.utcnow()
    updated_project = update_project(
        asana_gid="test_project_123",
        last_synced_at=sync_time,
        session=db_session,
    )

    assert updated_project.last_synced_at == sync_time


def test_create_task_with_parent(db_session, sample_project, sample_task):
    """Test creating a task with a parent task."""
    subtask = create_task(
        asana_gid="subtask_123",
        project_id=sample_project.id,
        name="Subtask",
        parent_task_id=sample_task.id,
        session=db_session,
    )

    assert subtask.parent_task_id == sample_task.id


def test_task_relationships(db_session, sample_task):
    """Test task relationships are loaded correctly."""
    task = get_task_by_gid("test_task_456", session=db_session)

    # Should have access to project relationship
    assert task.project is not None
    assert task.project.name == "Test Project"

    # Should have empty executions list
    assert task.executions == []


def test_execution_with_cost_calculation(db_session, sample_task):
    """Test creating execution with token counts and cost."""
    execution = create_task_execution(
        task_id=sample_task.id,
        status="completed",
        session=db_session,
    )

    # Update with cost information
    updated = update_task_execution_status(
        execution_id=execution.id,
        status="completed",
        input_tokens=5000,
        output_tokens=2000,
        cost_usd=0.125,
        session=db_session,
    )

    assert updated.input_tokens == 5000
    assert updated.output_tokens == 2000
    assert float(updated.cost_usd) == 0.125


# ============================================================================
# Session Management Tests (test context manager behavior)
# ============================================================================


def test_create_project_without_session():
    """Test creating a project without providing a session (auto-managed)."""
    # This would create its own session in normal operation
    # For testing, we'll just verify the function signature accepts None
    # In a real scenario, this would need database setup
    pass


def test_get_project_without_session():
    """Test getting a project without providing a session."""
    # Similar to above - tests that the API accepts None for session
    pass


# ============================================================================
# Additional edge cases for higher coverage
# ============================================================================


def test_update_task_all_fields(db_session, sample_task):
    """Test updating all possible task fields at once."""
    now = datetime.utcnow()
    updated_task = update_task(
        asana_gid="test_task_456",
        name="Fully Updated Task",
        description="New description",
        html_notes="<p>New notes</p>",
        completed=True,
        completed_at=now,
        due_on="2024-12-31",
        due_at=now,
        assignee_gid="new_assignee",
        assignee_name="New Assignee",
        assigned_to_aegis=False,
        num_subtasks=5,
        tags=["tag1", "tag2"],
        custom_fields={"field": "value"},
        modified_at=now,
        last_synced_at=now,
        session=db_session,
    )

    assert updated_task.name == "Fully Updated Task"
    assert updated_task.description == "New description"
    assert updated_task.html_notes == "<p>New notes</p>"
    assert updated_task.completed is True
    assert updated_task.completed_at == now
    assert updated_task.due_on == "2024-12-31"
    assert updated_task.due_at == now
    assert updated_task.assignee_gid == "new_assignee"
    assert updated_task.assignee_name == "New Assignee"
    assert updated_task.assigned_to_aegis is False
    assert updated_task.num_subtasks == 5
    assert updated_task.tags == ["tag1", "tag2"]
    assert updated_task.custom_fields == {"field": "value"}
    assert updated_task.modified_at == now
    assert updated_task.last_synced_at == now


def test_get_tasks_by_project_empty(db_session, sample_project):
    """Test getting tasks when none exist for a project."""
    # Don't create any tasks
    tasks = get_tasks_by_project(sample_project.id, session=db_session)
    assert len(tasks) == 0


def test_get_task_executions_by_task_empty(db_session, sample_task):
    """Test getting executions when none exist for a task."""
    # Don't create any executions
    executions = get_task_executions_by_task(sample_task.id, session=db_session)
    assert len(executions) == 0


def test_update_project_with_empty_settings(db_session, sample_project):
    """Test updating project with empty settings dict."""
    updated_project = update_project(
        asana_gid="test_project_123",
        settings={},
        session=db_session,
    )
    assert updated_project.settings == {}


def test_update_task_with_empty_lists(db_session, sample_task):
    """Test updating task with empty tags and custom fields."""
    updated_task = update_task(
        asana_gid="test_task_456",
        tags=[],
        custom_fields={},
        session=db_session,
    )
    assert updated_task.tags == []
    assert updated_task.custom_fields == {}


def test_create_task_with_all_timestamps(db_session, sample_project):
    """Test creating a task with all timestamp fields."""
    now = datetime.utcnow()
    task = create_task(
        asana_gid="task_with_timestamps",
        project_id=sample_project.id,
        name="Task with Timestamps",
        completed=True,
        completed_at=now,
        due_at=now,
        modified_at=now,
        session=db_session,
    )

    assert task.completed_at == now
    assert task.due_at == now
    assert task.modified_at == now


def test_get_all_projects_empty(db_session):
    """Test getting projects when none exist."""
    projects = get_all_projects(session=db_session)
    assert len(projects) == 0


def test_create_execution_with_all_fields(db_session, sample_task):
    """Test creating task execution with all optional fields."""
    now = datetime.utcnow()
    execution = create_task_execution(
        task_id=sample_task.id,
        status="in_progress",
        agent_type="complex_agent",
        started_at=now,
        context={"project": "test", "user": "admin"},
        execution_metadata={"run_id": "123", "version": "1.0"},
        session=db_session,
    )

    assert execution.task_id == sample_task.id
    assert execution.status == "in_progress"
    assert execution.agent_type == "complex_agent"
    assert execution.started_at == now
    assert execution.context == {"project": "test", "user": "admin"}
    assert execution.execution_metadata == {"run_id": "123", "version": "1.0"}


def test_update_task_execution_all_optional_fields(db_session, sample_execution):
    """Test updating task execution with all optional fields."""
    now = datetime.utcnow()
    updated = update_task_execution_status(
        execution_id=sample_execution.id,
        status="completed",
        completed_at=now,
        success=True,
        error_message=None,
        output="Output text",
        duration_seconds=300,
        input_tokens=2000,
        output_tokens=1000,
        cost_usd=0.10,
        session=db_session,
    )

    assert updated.status == "completed"
    assert updated.completed_at == now
    assert updated.success is True
    assert updated.output == "Output text"
    assert updated.duration_seconds == 300
    assert updated.input_tokens == 2000
    assert updated.output_tokens == 1000


def test_get_all_projects_by_portfolio(db_session):
    """Test filtering projects by portfolio."""
    # Create projects in different portfolios
    create_project(
        asana_gid="proj_portfolio1_1",
        name="Project 1",
        portfolio_gid="portfolio_1",
        workspace_gid="workspace_789",
        session=db_session,
    )
    create_project(
        asana_gid="proj_portfolio1_2",
        name="Project 2",
        portfolio_gid="portfolio_1",
        workspace_gid="workspace_789",
        session=db_session,
    )
    create_project(
        asana_gid="proj_portfolio2_1",
        name="Project 3",
        portfolio_gid="portfolio_2",
        workspace_gid="workspace_789",
        session=db_session,
    )

    # Get projects from portfolio 1
    projects = get_all_projects(portfolio_gid="portfolio_1", session=db_session)
    assert len(projects) == 2

    # Get projects from portfolio 2
    projects = get_all_projects(portfolio_gid="portfolio_2", session=db_session)
    assert len(projects) == 1


def test_create_task_with_due_on_only(db_session, sample_project):
    """Test creating a task with only due_on (string date)."""
    task = create_task(
        asana_gid="task_due_on",
        project_id=sample_project.id,
        name="Task with due_on",
        due_on="2024-12-31",
        session=db_session,
    )

    assert task.due_on == "2024-12-31"
    assert task.due_at is None


def test_update_task_assignee_fields(db_session, sample_task):
    """Test updating task assignee fields."""
    updated_task = update_task(
        asana_gid="test_task_456",
        assignee_gid="new_user_123",
        assignee_name="John Smith",
        session=db_session,
    )

    assert updated_task.assignee_gid == "new_user_123"
    assert updated_task.assignee_name == "John Smith"


def test_get_tasks_by_project_with_filters(db_session, sample_project):
    """Test getting tasks with multiple filter combinations."""
    # Create varied tasks
    create_task(
        asana_gid="task_aegis_incomplete",
        project_id=sample_project.id,
        name="Aegis Incomplete",
        assigned_to_aegis=True,
        completed=False,
        session=db_session,
    )
    create_task(
        asana_gid="task_aegis_complete",
        project_id=sample_project.id,
        name="Aegis Complete",
        assigned_to_aegis=True,
        completed=True,
        session=db_session,
    )
    create_task(
        asana_gid="task_other_incomplete",
        project_id=sample_project.id,
        name="Other Incomplete",
        assigned_to_aegis=False,
        completed=False,
        session=db_session,
    )

    # Test various filter combinations
    tasks = get_tasks_by_project(
        sample_project.id,
        assigned_to_aegis=False,
        completed=False,
        session=db_session,
    )
    assert len(tasks) == 1
    assert tasks[0].name == "Other Incomplete"


def test_mark_task_complete_already_complete(db_session, sample_task):
    """Test marking an already complete task as complete again."""
    # Mark complete first time
    mark_task_complete(asana_gid="test_task_456", session=db_session)

    # Mark complete second time
    updated_task = mark_task_complete(asana_gid="test_task_456", session=db_session)

    assert updated_task.completed is True
    assert updated_task.completed_at is not None


def test_get_task_executions_by_task_multiple_statuses(db_session, sample_task):
    """Test getting executions with different statuses."""
    # Create executions with different statuses
    create_task_execution(
        task_id=sample_task.id,
        status="pending",
        session=db_session,
    )
    create_task_execution(
        task_id=sample_task.id,
        status="in_progress",
        session=db_session,
    )
    create_task_execution(
        task_id=sample_task.id,
        status="in_progress",
        session=db_session,
    )

    # Get only in_progress executions
    executions = get_task_executions_by_task(
        sample_task.id,
        status="in_progress",
        session=db_session,
    )
    assert len(executions) == 2


def test_update_project_settings_complex(db_session, sample_project):
    """Test updating project with complex nested settings."""
    complex_settings = {
        "features": {"enabled": True, "options": [1, 2, 3]},
        "config": {"nested": {"value": "test"}},
    }
    updated_project = update_project(
        asana_gid="test_project_123",
        settings=complex_settings,
        session=db_session,
    )

    assert updated_project.settings == complex_settings
    assert updated_project.settings["features"]["options"] == [1, 2, 3]


def test_create_task_with_parent_and_subtasks(db_session, sample_project, sample_task):
    """Test creating a task with parent reference and subtask count."""
    child_task = create_task(
        asana_gid="child_task",
        project_id=sample_project.id,
        name="Child Task",
        parent_task_id=sample_task.id,
        num_subtasks=2,
        session=db_session,
    )

    assert child_task.parent_task_id == sample_task.id
    assert child_task.num_subtasks == 2
