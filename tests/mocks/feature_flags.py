"""Mock feature flag service for testing."""

from app.domain.interfaces import FeatureFlagServiceInterface


class MockFeatureFlagService(FeatureFlagServiceInterface):
    """In-memory mock feature flag service with directly settable attributes."""

    def __init__(self) -> None:
        self.sync_globally_disabled = False
        self.disabled_integrations: list[str] = []
        self.job_termination_enabled = True
        self.auth_enabled = False
        self.rate_limit_enabled = False
        self.job_runner_enabled = True
        self.scheduler_enabled = True

    def is_sync_globally_disabled(self) -> bool:
        return self.sync_globally_disabled

    def is_integration_disabled(self, integration_name: str) -> bool:
        return integration_name in self.disabled_integrations

    def get_disabled_integrations(self) -> list[str]:
        return list(self.disabled_integrations)

    def is_job_termination_enabled(self) -> bool:
        return self.job_termination_enabled

    def is_auth_enabled(self) -> bool:
        return self.auth_enabled

    def is_rate_limit_enabled(self) -> bool:
        return self.rate_limit_enabled

    def is_job_runner_enabled(self) -> bool:
        return self.job_runner_enabled

    def is_scheduler_enabled(self) -> bool:
        return self.scheduler_enabled

    def reset(self) -> None:
        """Reset all flags to defaults."""
        self.sync_globally_disabled = False
        self.disabled_integrations = []
        self.job_termination_enabled = True
        self.auth_enabled = False
        self.rate_limit_enabled = False
        self.job_runner_enabled = True
        self.scheduler_enabled = True
