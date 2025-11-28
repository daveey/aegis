"""Configuration management for Aegis."""

from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Don't try to parse JSON for list fields - let validators handle it
        env_parse_none_str="",
    )

    # Asana Configuration
    asana_access_token: str = Field(..., description="Asana Personal Access Token")
    asana_workspace_gid: str = Field(..., description="Asana Workspace GID")
    asana_team_gid: str = Field(..., description="Asana Team GID (for creating projects in organizations)")
    asana_portfolio_gid: str = Field(
        ..., description="Asana Portfolio GID (Aegis portfolio containing projects to monitor)"
    )

    # Anthropic Configuration
    anthropic_api_key: str = Field(..., description="Anthropic API Key")
    anthropic_model: str = Field(default="claude-sonnet-4-5-20250929", description="Claude model")
    anthropic_max_tokens: int = Field(default=4096, description="Max tokens per request")

    # Database Configuration
    database_url: str = Field(
        default="postgresql://localhost/aegis", description="PostgreSQL connection URL"
    )
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")

    # Vector Database Configuration
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant server URL")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant API key (if needed)")
    qdrant_collection: str = Field(default="aegis", description="Qdrant collection name")

    # Orchestrator Configuration
    poll_interval_seconds: int = Field(
        default=30, description="How often to poll Asana for new tasks"
    )
    max_concurrent_tasks: int = Field(
        default=3, description="Maximum concurrent tasks to process"
    )
    execution_mode: str = Field(
        default="simple_executor",
        description="Execution mode: 'simple_executor' (Claude API) or 'claude_cli' (subprocess)"
    )
    terminal_mode: bool = Field(
        default=False,
        description="Launch tasks in separate terminal windows (only for claude_cli mode)"
    )

    # Shutdown Configuration
    shutdown_timeout: int = Field(
        default=300, description="Maximum seconds to wait for tasks during shutdown (default: 5 minutes)"
    )
    subprocess_term_timeout: int = Field(
        default=10, description="Seconds to wait after SIGTERM before SIGKILL for subprocesses"
    )

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or console")

    # Feature Flags
    enable_vector_db: bool = Field(default=False, description="Enable vector database features")
    enable_multi_agent: bool = Field(default=False, description="Enable multi-agent orchestration")

    # Task Prioritization Configuration
    priority_weight_due_date: float = Field(
        default=10.0, description="Weight for due date urgency in task prioritization"
    )
    priority_weight_dependency: float = Field(
        default=8.0, description="Weight for task dependencies in prioritization"
    )
    priority_weight_user_priority: float = Field(
        default=7.0, description="Weight for user-assigned priority in prioritization"
    )
    priority_weight_project_importance: float = Field(
        default=5.0, description="Weight for project importance in prioritization"
    )
    priority_weight_age: float = Field(
        default=3.0, description="Weight for task age (anti-starvation) in prioritization"
    )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_priority_weights_from_settings(settings: Settings | None = None):
    """Create PriorityWeights from settings configuration.

    Args:
        settings: Settings instance (uses global if None)

    Returns:
        PriorityWeights instance configured from settings
    """
    from aegis.orchestrator.prioritizer import PriorityWeights

    if settings is None:
        settings = get_settings()

    return PriorityWeights(
        due_date=settings.priority_weight_due_date,
        dependency=settings.priority_weight_dependency,
        user_priority=settings.priority_weight_user_priority,
        project_importance=settings.priority_weight_project_importance,
        age_factor=settings.priority_weight_age,
    )
