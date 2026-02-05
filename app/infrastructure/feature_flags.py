"""Settings-backed feature flag service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.interfaces import FeatureFlagServiceInterface

if TYPE_CHECKING:
    from app.core.config import Settings


class ConfigFeatureFlagService(FeatureFlagServiceInterface):
    """Feature flag service that reads from Pydantic Settings.

    Accepts an optional ``Settings`` instance for testing; defaults to
    the cached singleton via ``get_settings()`` when omitted.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        self._settings = settings

    def is_sync_globally_disabled(self) -> bool:
        return self._settings.sync_globally_disabled

    def is_integration_disabled(self, integration_name: str) -> bool:
        return integration_name in self._settings.disabled_integrations

    def get_disabled_integrations(self) -> list[str]:
        return list(self._settings.disabled_integrations)

    def is_job_termination_enabled(self) -> bool:
        return self._settings.job_termination_enabled

    def is_auth_enabled(self) -> bool:
        return self._settings.auth_enabled

    def is_rate_limit_enabled(self) -> bool:
        return self._settings.rate_limit_enabled

    def is_job_runner_enabled(self) -> bool:
        return self._settings.job_runner_enabled

    def is_scheduler_enabled(self) -> bool:
        return self._settings.scheduler_enabled
