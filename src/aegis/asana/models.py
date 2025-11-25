"""Data models for Asana entities."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task completion status."""

    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class AsanaUser(BaseModel):
    """Asana user model."""

    gid: str
    name: str
    email: str | None = None


class AsanaProject(BaseModel):
    """Asana project model."""

    gid: str
    name: str
    notes: str | None = None
    archived: bool = False
    public: bool = False


class AsanaComment(BaseModel):
    """Asana comment/story model."""

    gid: str
    created_at: datetime
    created_by: AsanaUser
    text: str
    resource_type: str = "story"


class AsanaAttachment(BaseModel):
    """Asana attachment model."""

    gid: str
    name: str
    resource_type: str
    download_url: str | None = None
    permanent_url: str | None = None


class AsanaTask(BaseModel):
    """Asana task model with all relevant fields."""

    gid: str
    name: str
    notes: str | None = None
    html_notes: str | None = None
    completed: bool = False
    completed_at: datetime | None = None
    created_at: datetime
    modified_at: datetime
    due_on: str | None = None
    due_at: datetime | None = None

    assignee: AsanaUser | None = None
    assignee_status: str | None = None

    projects: list[AsanaProject] = Field(default_factory=list)
    tags: list[dict] = Field(default_factory=list)

    # Subtasks
    parent: dict | None = None
    num_subtasks: int = 0

    # Additional context
    workspace: dict | None = None
    permalink_url: str | None = None

    # Custom fields for Aegis-specific metadata
    custom_fields: list[dict] = Field(default_factory=list)

    @property
    def is_assigned_to_aegis(self) -> bool:
        """Check if task is assigned to Aegis (placeholder for now)."""
        # TODO: Implement logic to check if assignee is the Aegis bot account
        return self.assignee is not None

    @property
    def full_context(self) -> str:
        """Get full task context including name and notes."""
        parts = [f"Task: {self.name}"]
        if self.notes:
            parts.append(f"\nDescription:\n{self.notes}")
        if self.due_on:
            parts.append(f"\nDue: {self.due_on}")
        return "\n".join(parts)


class AsanaTaskUpdate(BaseModel):
    """Model for updating a task."""

    completed: bool | None = None
    notes: str | None = None
    assignee: str | None = None
    due_on: str | None = None
    name: str | None = None
