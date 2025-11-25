"""Unit tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from aegis.config import Settings, get_settings


class TestSettings:
    """Tests for Settings model."""

    def test_settings_from_env(self) -> None:
        """Test loading settings from environment variables."""
        with patch.dict(
            os.environ,
            {
                "ASANA_ACCESS_TOKEN": "test_asana_token",
                "ASANA_WORKSPACE_GID": "workspace_123",
                "ASANA_PROJECT_GIDS": "proj_1,proj_2,proj_3",
                "ANTHROPIC_API_KEY": "test_anthropic_key",
                "ANTHROPIC_MODEL": "claude-opus-4-5-20251101",
                "DATABASE_URL": "postgresql://localhost/test_db",
                "REDIS_URL": "redis://localhost:6380",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.asana_access_token == "test_asana_token"
            assert settings.asana_workspace_gid == "workspace_123"
            assert settings.asana_project_gids == ["proj_1", "proj_2", "proj_3"]
            assert settings.anthropic_api_key == "test_anthropic_key"
            assert settings.anthropic_model == "claude-opus-4-5-20251101"
            assert settings.database_url == "postgresql://localhost/test_db"
            assert settings.redis_url == "redis://localhost:6380"

    def test_settings_defaults(self) -> None:
        """Test default settings values."""
        with patch.dict(
            os.environ,
            {
                "ASANA_ACCESS_TOKEN": "test_token",
                "ASANA_WORKSPACE_GID": "workspace_123",
                "ANTHROPIC_API_KEY": "test_key",
            },
            clear=True,
        ):
            settings = Settings()

            # Test defaults
            assert settings.anthropic_model == "claude-sonnet-4-5-20250929"
            assert settings.anthropic_max_tokens == 4096
            assert settings.database_url == "postgresql://localhost/aegis"
            assert settings.redis_url == "redis://localhost:6379"
            assert settings.poll_interval_seconds == 30
            assert settings.max_concurrent_tasks == 5
            assert settings.log_level == "INFO"
            assert settings.log_format == "json"
            assert settings.enable_vector_db is False
            assert settings.enable_multi_agent is False

    def test_settings_feature_flags(self) -> None:
        """Test feature flag settings."""
        with patch.dict(
            os.environ,
            {
                "ASANA_ACCESS_TOKEN": "test_token",
                "ASANA_WORKSPACE_GID": "workspace_123",
                "ANTHROPIC_API_KEY": "test_key",
                "ENABLE_VECTOR_DB": "true",
                "ENABLE_MULTI_AGENT": "true",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.enable_vector_db is True
            assert settings.enable_multi_agent is True

    def test_settings_missing_required(self) -> None:
        """Test that missing required settings raise an error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception):  # pydantic will raise ValidationError
                Settings()

    def test_settings_custom_values(self) -> None:
        """Test custom configuration values."""
        with patch.dict(
            os.environ,
            {
                "ASANA_ACCESS_TOKEN": "test_token",
                "ASANA_WORKSPACE_GID": "workspace_123",
                "ANTHROPIC_API_KEY": "test_key",
                "POLL_INTERVAL_SECONDS": "60",
                "MAX_CONCURRENT_TASKS": "10",
                "LOG_LEVEL": "DEBUG",
                "LOG_FORMAT": "console",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.poll_interval_seconds == 60
            assert settings.max_concurrent_tasks == 10
            assert settings.log_level == "DEBUG"
            assert settings.log_format == "console"


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_singleton(self) -> None:
        """Test that get_settings returns the same instance."""
        # Reset the global settings
        import aegis.config

        aegis.config._settings = None

        with patch.dict(
            os.environ,
            {
                "ASANA_ACCESS_TOKEN": "test_token",
                "ASANA_WORKSPACE_GID": "workspace_123",
                "ANTHROPIC_API_KEY": "test_key",
            },
            clear=True,
        ):
            settings1 = get_settings()
            settings2 = get_settings()

            assert settings1 is settings2
