"""Unit tests for Asana client."""

from unittest.mock import MagicMock, patch

import pytest
from asana.rest import ApiException

from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTaskUpdate


class TestAsanaClient:
    """Tests for AsanaClient."""

    @pytest.fixture
    def client(self) -> AsanaClient:
        """Create a test client."""
        return AsanaClient(access_token="test_token")

    @pytest.fixture
    def mock_asana_client(self, client: AsanaClient) -> MagicMock:
        """Mock the underlying Asana client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_tasks_from_project(
        self, client: AsanaClient, sample_task_data: dict
    ) -> None:
        """Test fetching tasks from a project."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [sample_task_data]

            tasks = await client.get_tasks_from_project("67890")

            assert len(tasks) == 1
            assert tasks[0].gid == "11111"
            assert tasks[0].name == "Test Task"
            assert tasks[0].assignee is not None
            assert tasks[0].assignee.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_tasks_from_project_assigned_only(
        self, client: AsanaClient, sample_task_data: dict
    ) -> None:
        """Test fetching only assigned tasks."""
        unassigned_task = sample_task_data.copy()
        unassigned_task["assignee"] = None
        unassigned_task["gid"] = "22222"

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [sample_task_data, unassigned_task]

            tasks = await client.get_tasks_from_project("67890", assigned_only=True)

            # Should only return the assigned task
            assert len(tasks) == 1
            assert tasks[0].gid == "11111"

    @pytest.mark.asyncio
    async def test_get_task(self, client: AsanaClient, sample_task_data: dict) -> None:
        """Test fetching a single task."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = sample_task_data

            task = await client.get_task("11111")

            assert task.gid == "11111"
            assert task.name == "Test Task"
            assert task.notes == "This is a test task"

    @pytest.mark.asyncio
    async def test_update_task(self, client: AsanaClient, sample_task_data: dict) -> None:
        """Test updating a task."""
        updated_data = sample_task_data.copy()
        updated_data["completed"] = True

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = updated_data

            update = AsanaTaskUpdate(completed=True)
            task = await client.update_task("11111", update)

            assert task.completed is True

    @pytest.mark.asyncio
    async def test_add_comment(self, client: AsanaClient, sample_user: dict) -> None:
        """Test adding a comment to a task."""
        comment_data = {
            "gid": "33333",
            "created_at": "2025-01-01T12:00:00.000Z",
            "created_by": {"gid": "12345", "name": "Test User", "email": "test@example.com"},
            "text": "Test comment",
        }

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = comment_data

            comment = await client.add_comment("11111", "Test comment")

            assert comment.gid == "33333"
            assert comment.text == "Test comment"
            assert comment.created_by.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_comments(self, client: AsanaClient) -> None:
        """Test fetching comments for a task."""
        stories_data = [
            {
                "gid": "33333",
                "created_at": "2025-01-01T12:00:00.000Z",
                "created_by": {"gid": "12345", "name": "Test User", "email": "test@example.com"},
                "text": "Comment 1",
                "type": "comment",
            },
            {
                "gid": "44444",
                "created_at": "2025-01-01T13:00:00.000Z",
                "created_by": {"gid": "12345", "name": "Test User", "email": "test@example.com"},
                "text": "Comment 2",
                "type": "comment",
            },
            {
                # System story - should be filtered out
                "gid": "55555",
                "created_at": "2025-01-01T14:00:00.000Z",
                "created_by": {"gid": "12345", "name": "Test User"},
                "text": "Task completed",
                "type": "system",
            },
        ]

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = stories_data

            comments = await client.get_comments("11111")

            # Should only return comment stories, not system stories
            assert len(comments) == 2
            assert comments[0].text == "Comment 1"
            assert comments[1].text == "Comment 2"

    @pytest.mark.asyncio
    async def test_get_project(self, client: AsanaClient) -> None:
        """Test fetching project details."""
        project_data = {
            "gid": "67890",
            "name": "Test Project",
            "notes": "Project notes",
            "archived": False,
            "public": True,
        }

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = project_data

            project = await client.get_project("67890")

            assert project.gid == "67890"
            assert project.name == "Test Project"
            assert project.notes == "Project notes"
            assert project.archived is False
            assert project.public is True

    @pytest.mark.asyncio
    async def test_api_exception_handling(self, client: AsanaClient) -> None:
        """Test that API exceptions are properly raised."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = ApiException("API Error")

            with pytest.raises(ApiException):
                await client.get_task("11111")

    def test_parse_task(self, client: AsanaClient, sample_task_data: dict) -> None:
        """Test task parsing from raw API data."""
        task = client._parse_task(sample_task_data)

        assert task.gid == "11111"
        assert task.name == "Test Task"
        assert task.notes == "This is a test task"
        assert task.assignee is not None
        assert task.assignee.name == "Test User"
        assert len(task.projects) == 1
        assert task.projects[0].name == "Test Project"

    def test_parse_task_minimal(self, client: AsanaClient) -> None:
        """Test parsing task with minimal data."""
        minimal_data = {
            "gid": "11111",
            "name": "Minimal Task",
            "created_at": "2025-01-01T12:00:00.000Z",
            "modified_at": "2025-01-01T12:00:00.000Z",
        }

        task = client._parse_task(minimal_data)

        assert task.gid == "11111"
        assert task.name == "Minimal Task"
        assert task.assignee is None
        assert len(task.projects) == 0
