"""Tests for configuration module."""

import pytest

from app.core.config import Settings, get_settings


class TestSettings:
    """Tests for Settings configuration class."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")

        assert settings.app_env == "development"
        assert settings.auth_enabled is False
        assert settings.sync_globally_disabled is False
        assert settings.job_termination_enabled is True

    def test_environment_properties(self):
        """Test environment property methods."""
        settings = Settings(
            app_env="development",
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        )

        assert settings.is_development is True
        assert settings.is_production is False

        prod_settings = Settings(
            app_env="production",
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            auth_enabled=True,
            jwt_secret_key="secure-production-key-123456",
        )

        assert prod_settings.is_development is False
        assert prod_settings.is_production is True

    def test_database_url_sync_property(self):
        """Test database_url_sync property."""
        settings = Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")

        assert settings.database_url_sync == "postgresql://test:test@localhost:5432/test"
        assert "+asyncpg" not in settings.database_url_sync

    def test_jwt_settings(self):
        """Test JWT configuration."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            jwt_secret_key="my-secret-key",
            jwt_algorithm="HS256",
            jwt_issuer="test-issuer",
            jwt_audience="test-audience",
        )

        assert settings.jwt_secret_key == "my-secret-key"
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_issuer == "test-issuer"
        assert settings.jwt_audience == "test-audience"

    def test_queue_settings(self):
        """Test queue configuration."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            queue_url="https://sqs.us-east-1.amazonaws.com/123/my-queue",
            queue_max_receive_count=5,
            queue_wait_time_seconds=20,
        )

        assert settings.queue_url == "https://sqs.us-east-1.amazonaws.com/123/my-queue"
        assert settings.queue_max_receive_count == 5
        assert settings.queue_wait_time_seconds == 20

    def test_rate_limit_settings(self):
        """Test rate limiting configuration."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            rate_limit_enabled=True,
            rate_limit_requests_per_minute=100,
            rate_limit_burst=20,
        )

        assert settings.rate_limit_enabled is True
        assert settings.rate_limit_requests_per_minute == 100
        assert settings.rate_limit_burst == 20

    def test_disabled_integrations_list(self):
        """Test disabled integrations list."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            disabled_integrations=["QuickBooks", "Xero"],
        )

        assert "QuickBooks" in settings.disabled_integrations
        assert "Xero" in settings.disabled_integrations
        assert len(settings.disabled_integrations) == 2

    def test_disabled_integrations_comma_string(self):
        """Test disabled integrations from comma-separated string."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            disabled_integrations="QuickBooks, Xero, Sage",
        )

        assert len(settings.disabled_integrations) == 3
        assert "QuickBooks" in settings.disabled_integrations

    def test_disabled_integrations_empty(self):
        """Test disabled integrations empty string."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            disabled_integrations="",
        )

        assert settings.disabled_integrations == []

    def test_job_runner_settings(self):
        """Test job runner configuration."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            job_runner_enabled=True,
            job_runner_max_workers=4,
            job_stuck_timeout_minutes=30,
        )

        assert settings.job_runner_enabled is True
        assert settings.job_runner_max_workers == 4
        assert settings.job_stuck_timeout_minutes == 30

    def test_cors_settings_list(self):
        """Test CORS settings with list."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            cors_allowed_origins=["https://app.example.com", "https://admin.example.com"],
        )

        assert len(settings.cors_allowed_origins) == 2
        assert "https://app.example.com" in settings.cors_allowed_origins

    def test_cors_settings_json_string(self):
        """Test CORS settings with JSON string."""
        settings = Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            cors_allowed_origins='["https://app.example.com"]',
        )

        assert len(settings.cors_allowed_origins) == 1
        assert "https://app.example.com" in settings.cors_allowed_origins

    def test_production_validation_errors(self):
        """Test production settings validation."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                app_env="production",
                database_url="postgresql+asyncpg://test:test@localhost:5432/test",
                auth_enabled=False,  # Invalid in production
            )

        assert "AUTH_ENABLED must be true" in str(exc_info.value)

    def test_production_jwt_key_validation(self):
        """Test production JWT key validation."""
        with pytest.raises(ValueError) as exc_info:
            Settings(
                app_env="production",
                database_url="postgresql+asyncpg://test:test@localhost:5432/test",
                auth_enabled=True,
                jwt_secret_key="CHANGE_THIS_IN_PRODUCTION",  # Invalid
            )

        assert "JWT_SECRET_KEY must be changed" in str(exc_info.value)


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_settings(self):
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()

        assert isinstance(settings, Settings)
        assert settings.app_env is not None

    def test_get_settings_is_cached(self):
        """Test that get_settings returns the same instance."""
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same cached instance
        assert settings1 is settings2
