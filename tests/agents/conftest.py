"""Fixtures for agent tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from aegis.asana.models import AsanaTask, AsanaProject, AsanaUser
from aegis.agents.base import BaseAgent


@pytest.fixture
def mock_user():
    """Create a mock Asana user."""
    return AsanaUser(
        gid="user123",
        name="Test User",
        email="test@example.com"
    )


@pytest.fixture
def mock_project():
    """Create a mock Asana project."""
    return AsanaProject(
        gid="project123",
        name="Test Project",
        notes="Test Project Notes",
        archived=False
    )


@pytest.fixture
def mock_task_factory(mock_user, mock_project):
    """Factory to create mock Asana tasks."""
    def _create_task(**kwargs):
        defaults = {
            "gid": "task123",
            "name": "Test Task",
            "notes": "Test Description",
            "completed": False,
            "created_at": datetime.now(),
            "modified_at": datetime.now(),
            "assignee": mock_user,
            "projects": [mock_project],
            "permalink_url": "https://app.asana.com/0/1/2",
            "custom_fields": []
        }
        defaults.update(kwargs)

        # Handle custom fields specifically if passed as dict
        if "custom_fields" in kwargs and isinstance(kwargs["custom_fields"], dict):
            # Convert dict to list of objects if needed, or just leave as is if the model supports it
            # The model expects a list of dicts or objects. Let's assume list of dicts for now based on usage
            pass

        return AsanaTask(**defaults)
    return _create_task


class MockAgentMixin:
    """Mixin to add mocking capabilities to agents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_response = ""
        self._mock_returncode = 0
        self._mock_stderr = ""

    def set_mock_response(self, stdout: str, stderr: str = "", returncode: int = 0):
        """Set the mock response for run_claude_code."""
        self._mock_response = stdout
        self._mock_stderr = stderr
        self._mock_returncode = returncode

    async def run_claude_code(self, prompt: str, interactive: bool = False, **kwargs):
        """Mock implementation of run_claude_code."""
        return self._mock_response, self._mock_stderr, self._mock_returncode


@pytest.fixture
def mock_asana_service():
    """Mock AsanaService."""
    service = MagicMock()
    # Setup common methods to return awaitables if needed
    service.post_agent_comment = AsyncMock()
    return service


@pytest.fixture
def mock_worktree_manager(tmp_path):
    """Mock WorktreeManager."""
    manager = MagicMock()
    worktree_dir = tmp_path / "mock_worktree"
    worktree_dir.mkdir()
    manager.setup_worktree = MagicMock(return_value=str(worktree_dir))
    manager.get_worktree_path = MagicMock(return_value=str(worktree_dir))
    return manager


@pytest.fixture
def mock_repo_root(tmp_path):
    """Mock repo root."""
    return tmp_path


@pytest.fixture
def mock_agent_class(mock_asana_service, mock_worktree_manager, mock_repo_root):
    """Create a mocked agent class factory."""
    def _create_mock_agent_class(base_class):
        # Create a new class that inherits from MockAgentMixin and the target base class
        class MockedAgent(MockAgentMixin, base_class):
            def __init__(self, *args, **kwargs):
                # Inject required dependencies if not provided
                if "asana_service" not in kwargs:
                    kwargs["asana_service"] = mock_asana_service
                if "repo_root" not in kwargs:
                    kwargs["repo_root"] = mock_repo_root

                # Inject WorkerAgent specific dependencies
                if base_class.__name__ == "WorkerAgent" and "worktree_manager" not in kwargs:
                    kwargs["worktree_manager"] = mock_worktree_manager

                super().__init__(*args, **kwargs)

            async def _rebase_on_main(self, *args, **kwargs):
                """Mock rebase on main."""
                pass

        return MockedAgent
    return _create_mock_agent_class
