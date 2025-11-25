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
        default=5, description="Maximum concurrent tasks to process"
    )

    # Logging Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or console")

    # Feature Flags
    enable_vector_db: bool = Field(default=False, description="Enable vector database features")
    enable_multi_agent: bool = Field(default=False, description="Enable multi-agent orchestration")


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
