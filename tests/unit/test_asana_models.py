"""Unit tests for Asana data models."""

from datetime import datetime

from aegis.asana.models import (
    AsanaComment,
    AsanaProject,
    AsanaTask,
    AsanaTaskUpdate,
    AsanaUser,
    TaskStatus,
)


class TestAsanaUser:
    """Tests for AsanaUser model."""

    def test_user_with_email(self) -> None:
        """Test user creation with email."""
        user = AsanaUser(gid="123", name="Test User", email="test@example.com")
        assert user.gid == "123"
        assert user.name == "Test User"
        assert user.email == "test@example.com"

    def test_user_without_email(self) -> None:
        """Test user creation without email."""
        user = AsanaUser(gid="123", name="Test User")
        assert user.gid == "123"
        assert user.name == "Test User"
        assert user.email is None


class TestAsanaProject:
    """Tests for AsanaProject model."""

    def test_project_basic(self) -> None:
        """Test basic project creation."""
        project = AsanaProject(gid="456", name="Test Project")
        assert project.gid == "456"
        assert project.name == "Test Project"
        assert project.archived is False
        assert project.public is False

    def test_project_with_notes(self) -> None:
        """Test project with notes."""
        project = AsanaProject(
            gid="456", name="Test Project", notes="Project notes", archived=True, public=True
        )
        assert project.notes == "Project notes"
        assert project.archived is True
        assert project.public is True


class TestAsanaTask:
    """Tests for AsanaTask model."""

    def test_task_basic(self, sample_task: AsanaTask) -> None:
        """Test basic task properties."""
        assert sample_task.gid == "11111"
        assert sample_task.name == "Test Task"
        assert sample_task.notes == "This is a test task"
        assert sample_task.completed is False
        assert sample_task.assignee is not None
        assert sample_task.assignee.name == "Test User"

    def test_task_full_context(self, sample_task: AsanaTask) -> None:
        """Test full_context property."""
        context = sample_task.full_context
        assert "Test Task" in context
        assert "This is a test task" in context

    def test_task_full_context_with_due_date(self, sample_task: AsanaTask) -> None:
        """Test full_context with due date."""
        sample_task.due_on = "2025-12-31"
        context = sample_task.full_context
        assert "Test Task" in context
        assert "This is a test task" in context
        assert "Due: 2025-12-31" in context

    def test_task_is_assigned_to_aegis(self, sample_task: AsanaTask) -> None:
        """Test is_assigned_to_aegis property."""
        # With assignee
        assert sample_task.is_assigned_to_aegis is True

        # Without assignee
        sample_task.assignee = None
        assert sample_task.is_assigned_to_aegis is False

    def test_task_without_notes(self, sample_user: AsanaUser) -> None:
        """Test task without notes."""
        task = AsanaTask(
            gid="22222",
            name="Minimal Task",
            completed=False,
            created_at=datetime.now(),
            modified_at=datetime.now(),
        )
        assert task.notes is None
        context = task.full_context
        assert "Minimal Task" in context
        assert "Description:" not in context


class TestAsanaTaskUpdate:
    """Tests for AsanaTaskUpdate model."""

    def test_update_completed(self) -> None:
        """Test updating task to completed."""
        update = AsanaTaskUpdate(completed=True)
        data = update.model_dump(exclude_none=True)
        assert data == {"completed": True}

    def test_update_multiple_fields(self) -> None:
        """Test updating multiple fields."""
        update = AsanaTaskUpdate(
            completed=True, notes="Updated notes", name="Updated Name", due_on="2025-12-31"
        )
        data = update.model_dump(exclude_none=True)
        assert data == {
            "completed": True,
            "notes": "Updated notes",
            "name": "Updated Name",
            "due_on": "2025-12-31",
        }

    def test_update_exclude_none(self) -> None:
        """Test that None values are excluded."""
        update = AsanaTaskUpdate(completed=True)
        data = update.model_dump(exclude_none=True)
        assert "notes" not in data
        assert "assignee" not in data
        assert "due_on" not in data


class TestAsanaComment:
    """Tests for AsanaComment model."""

    def test_comment_creation(self, sample_user: AsanaUser) -> None:
        """Test comment creation."""
        comment = AsanaComment(
            gid="33333",
            created_at=datetime.now(),
            created_by=sample_user,
            text="Test comment",
        )
        assert comment.gid == "33333"
        assert comment.text == "Test comment"
        assert comment.created_by.name == "Test User"
        assert comment.resource_type == "story"


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert TaskStatus.INCOMPLETE == "incomplete"
        assert TaskStatus.COMPLETE == "complete"
