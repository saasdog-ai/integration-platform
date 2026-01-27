"""Application configuration using Pydantic Settings."""

import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="integration-platform")
    app_env: str = Field(default="development")  # development, staging, production
    log_level: str = Field(default="INFO")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5434/integration_platform"
    )
    database_pool_size: int = Field(default=10)
    database_max_overflow: int = Field(default=20)
    database_pool_recycle: int = Field(default=3600)
    database_pool_timeout: int = Field(default=30)
    database_statement_timeout_ms: int = Field(default=30000)  # 30 seconds max query time

    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_max_request_size: int = Field(default=10 * 1024 * 1024)  # 10 MB max request body

    # JWT Authentication
    auth_enabled: bool = Field(default=False)
    jwt_secret_key: str = Field(default="CHANGE_THIS_IN_PRODUCTION")
    jwt_algorithm: str = Field(default="HS256")
    jwt_jwks_url: str | None = Field(default=None)
    jwt_issuer: str | None = Field(default=None)
    jwt_audience: str | None = Field(default=None)

    # Cloud Provider
    cloud_provider: str | None = Field(default=None)  # aws, azure, gcp, or None

    # AWS Configuration
    aws_region: str = Field(default="us-east-1")
    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: str | None = Field(default=None)
    aws_endpoint_url: str | None = Field(default=None)  # For localstack

    # Queue Configuration
    queue_url: str | None = Field(default=None)
    queue_wait_time_seconds: int = Field(default=20)
    queue_max_receive_count: int = Field(default=3)  # Max retries before DLQ

    # Encryption (KMS)
    kms_key_id: str | None = Field(default=None)

    # Azure Configuration
    azure_storage_connection_string: str | None = Field(default=None)
    azure_keyvault_url: str | None = Field(default=None)

    # GCP Configuration
    gcp_project_id: str | None = Field(default=None)
    gcp_kms_keyring: str | None = Field(default=None)
    gcp_kms_key: str | None = Field(default=None)

    # Job Runner
    job_runner_max_workers: int = Field(default=5)
    job_runner_enabled: bool = Field(default=True)
    job_stuck_timeout_minutes: int = Field(default=60)  # Jobs running longer than this are considered stuck
    job_termination_enabled: bool = Field(default=True)  # Enable automatic stuck job termination

    # Feature Flags - can be used to disable specific integrations or features
    # Format: comma-separated list of integration names to disable
    disabled_integrations: list[str] = Field(default_factory=list)
    sync_globally_disabled: bool = Field(default=False)  # Kill switch for all sync jobs

    # Scheduler
    scheduler_enabled: bool = Field(default=True)
    scheduler_timezone: str = Field(default="UTC")

    # External API timeouts (for integration adapters)
    api_connect_timeout: float = Field(default=10.0)  # Connection timeout in seconds
    api_read_timeout: float = Field(default=30.0)  # Read timeout in seconds
    api_total_timeout: float = Field(default=60.0)  # Total request timeout in seconds

    # Rate Limiting (in-process)
    # NOTE: In production, rate limiting should be done at the API gateway level
    # (Kong, AWS API Gateway, nginx) or via Redis for distributed rate limiting.
    # This in-process rate limiter is useful for:
    # - Local development
    # - Single-instance deployments
    # - Defense-in-depth as a secondary limit
    rate_limit_enabled: bool = Field(default=False)  # Disabled by default - use API gateway
    rate_limit_requests_per_minute: int = Field(default=60)  # Max requests per minute per client
    rate_limit_burst: int = Field(default=10)  # Allow short bursts above limit

    # CORS
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:4000"]
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("disabled_integrations", mode="before")
    @classmethod
    def parse_disabled_integrations(cls, v: str | list[str]) -> list[str]:
        """Parse disabled integrations from JSON string, comma-separated, or list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [name.strip() for name in v.split(",") if name.strip()]
        return v or []

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL for Alembic."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.app_env == "development"

    def model_post_init(self, __context: object) -> None:
        """Validate settings after initialization."""
        if self.is_production:
            self._validate_production_settings()

    def _validate_production_settings(self) -> None:
        """Enforce production requirements."""
        errors: list[str] = []

        if not self.auth_enabled:
            errors.append("AUTH_ENABLED must be true in production")

        if self.jwt_secret_key == "CHANGE_THIS_IN_PRODUCTION":
            errors.append("JWT_SECRET_KEY must be changed in production")

        if self.jwt_algorithm.startswith("RS") and not self.jwt_jwks_url:
            errors.append("JWT_JWKS_URL is required for RS256/RS384/RS512 algorithms")

        if errors:
            raise ValueError(
                "Production configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
