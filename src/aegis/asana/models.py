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
    workspace_gid: str | None = None


class AsanaSection(BaseModel):
    """Asana section model."""

    gid: str
    name: str
    project: dict | None = None


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

    created_by: AsanaUser | None = None
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

    # Dependencies (for blocking check)
    dependencies: list[dict] = Field(default_factory=list)

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

    # -------------------------------------------------------------------------
    # Custom Field Helper Methods (for Swarm)
    # -------------------------------------------------------------------------

    def get_custom_field(self, field_name: str) -> str | int | float | None:
        """Get value of a custom field by name.

        Args:
            field_name: Name of custom field (e.g., "Agent", "Swarm Status")

        Returns:
            Custom field value, or None if not found
        """
        for field in self.custom_fields:
            if field.get("name") == field_name:
                # Handle different field types
                if "enum_value" in field and field["enum_value"]:
                    return field["enum_value"].get("name")
                elif "text_value" in field:
                    return field["text_value"]
                elif "number_value" in field:
                    return field["number_value"]
                elif "display_value" in field:
                    return field["display_value"]
                else:
                    return field.get("value")
        return None

    @property
    def agent(self) -> str | None:
        """Get agent type from custom fields."""
        return self.get_custom_field("Agent")

    @property
    def swarm_status(self) -> str | None:
        """Get swarm status from custom fields."""
        return self.get_custom_field("Swarm Status")

    @property
    def session_id(self) -> str | None:
        """Get session ID from custom fields."""
        return self.get_custom_field("Session ID")

    @property
    def cost(self) -> float | None:
        """Get cost from custom fields."""
        value = self.get_custom_field("Cost")
        return float(value) if value is not None else None

    @property
    def max_cost(self) -> float | None:
        """Get max cost from custom fields."""
        value = self.get_custom_field("Max Cost")
        return float(value) if value is not None else None

    @property
    def merge_approval(self) -> str | None:
        """Get merge approval from custom fields."""
        return self.get_custom_field("Merge Approval")

    @property
    def worktree_path(self) -> str | None:
        """Get worktree path from custom fields."""
        return self.get_custom_field("Worktree Path")


class AsanaTaskUpdate(BaseModel):
    """Model for updating a task."""

    completed: bool | None = None
    notes: str | None = None
    assignee: str | None = None
    due_on: str | None = None
    name: str | None = None
