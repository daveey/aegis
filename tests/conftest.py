"""Pytest configuration and shared fixtures."""

from datetime import datetime

import pytest

from aegis.asana.models import AsanaProject, AsanaTask, AsanaUser


@pytest.fixture
def sample_user() -> AsanaUser:
    """Sample Asana user."""
    return AsanaUser(gid="12345", name="Test User", email="test@example.com")


@pytest.fixture
def sample_project() -> AsanaProject:
    """Sample Asana project."""
    return AsanaProject(
        gid="67890", name="Test Project", notes="Test project notes", archived=False
    )


@pytest.fixture
def sample_task(sample_user: AsanaUser, sample_project: AsanaProject) -> AsanaTask:
    """Sample Asana task."""
    return AsanaTask(
        gid="11111",
        name="Test Task",
        notes="This is a test task",
        completed=False,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
        modified_at=datetime(2025, 1, 1, 12, 0, 0),
        assignee=sample_user,
        projects=[sample_project],
        permalink_url="https://app.asana.com/0/11111/11111",
    )


@pytest.fixture
def sample_task_data() -> dict:
    """Sample raw task data from Asana API."""
    return {
        "gid": "11111",
        "name": "Test Task",
        "notes": "This is a test task",
        "html_notes": "<body>This is a test task</body>",
        "completed": False,
        "completed_at": None,
        "created_at": "2025-01-01T12:00:00.000Z",
        "modified_at": "2025-01-01T12:00:00.000Z",
        "due_on": None,
        "due_at": None,
        "assignee": {"gid": "12345", "name": "Test User", "email": "test@example.com"},
        "assignee_status": "inbox",
        "projects": [{"gid": "67890", "name": "Test Project"}],
        "tags": [],
        "parent": None,
        "num_subtasks": 0,
        "workspace": {"gid": "99999", "name": "Test Workspace"},
        "permalink_url": "https://app.asana.com/0/11111/11111",
        "custom_fields": [],
    }
