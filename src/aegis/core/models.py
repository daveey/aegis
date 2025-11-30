"""Core data models for Aegis."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    """Result of agent execution."""

    success: bool = Field(..., description="Whether agent execution succeeded")
    next_agent: Optional[str] = Field(None, description="Next agent to route to")
    next_section: Optional[str] = Field(None, description="Next section to move task to")
    summary: str = Field(..., description="Concise summary for Asana comment (under 50 words)")
    details: List[str] = Field(default_factory=list, description="List of critical details for comment")
    error: Optional[str] = Field(None, description="Error message if failed")
    cost: float = Field(0.0, description="Cost of this execution in USD")
    clear_session_id: bool = Field(False, description="Whether to clear session ID")
    assignee: Optional[str] = Field(None, description="User GID or email to assign task to")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Execution timestamp")
