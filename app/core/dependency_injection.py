"""Dependency injection container for the application."""

from functools import lru_cache
from typing import TYPE_CHECKING

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.domain.interfaces import (
        EncryptionServiceInterface,
        FeatureFlagServiceInterface,
        IntegrationRepositoryInterface,
        IntegrationStateRepositoryInterface,
        MessageQueueInterface,
        SyncJobRepositoryInterface,
    )


class DependencyContainer:
    """
    Central dependency container for the application.

    All repositories, adapters, and services are accessed through this container.
    This makes it easy to swap implementations for testing.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

        # Lazy-loaded dependencies
        self._integration_repo: IntegrationRepositoryInterface | None = None
        self._sync_job_repo: SyncJobRepositoryInterface | None = None
        self._integration_state_repo: IntegrationStateRepositoryInterface | None = None
        self._message_queue: MessageQueueInterface | None = None
        self._encryption_service: EncryptionServiceInterface | None = None
        self._feature_flag_service: FeatureFlagServiceInterface | None = None

    @property
    def integration_repository(self) -> "IntegrationRepositoryInterface":
        """Get the integration repository."""
        if self._integration_repo is None:
            from app.infrastructure.db.repositories import IntegrationRepository

            self._integration_repo = IntegrationRepository()
        return self._integration_repo

    @property
    def sync_job_repository(self) -> "SyncJobRepositoryInterface":
        """Get the sync job repository."""
        if self._sync_job_repo is None:
            from app.infrastructure.db.repositories import SyncJobRepository

            self._sync_job_repo = SyncJobRepository()
        return self._sync_job_repo

    @property
    def integration_state_repository(self) -> "IntegrationStateRepositoryInterface":
        """Get the integration state repository."""
        if self._integration_state_repo is None:
            from app.infrastructure.db.repositories import IntegrationStateRepository

            self._integration_state_repo = IntegrationStateRepository()
        return self._integration_state_repo

    @property
    def message_queue(self) -> "MessageQueueInterface":
        """Get the message queue."""
        if self._message_queue is None:
            from app.infrastructure.queue.factory import get_message_queue

            self._message_queue = get_message_queue()
        return self._message_queue

    @property
    def encryption_service(self) -> "EncryptionServiceInterface":
        """Get the encryption service."""
        if self._encryption_service is None:
            from app.infrastructure.encryption.factory import get_encryption_service

            self._encryption_service = get_encryption_service()
        return self._encryption_service

    @property
    def feature_flag_service(self) -> "FeatureFlagServiceInterface":
        """Get the feature flag service."""
        if self._feature_flag_service is None:
            from app.infrastructure.feature_flags import ConfigFeatureFlagService

            self._feature_flag_service = ConfigFeatureFlagService()
        return self._feature_flag_service

    def override_integration_repository(self, repo: "IntegrationRepositoryInterface") -> None:
        """Override integration repository (for testing)."""
        self._integration_repo = repo

    def override_sync_job_repository(self, repo: "SyncJobRepositoryInterface") -> None:
        """Override sync job repository (for testing)."""
        self._sync_job_repo = repo

    def override_integration_state_repository(
        self, repo: "IntegrationStateRepositoryInterface"
    ) -> None:
        """Override integration state repository (for testing)."""
        self._integration_state_repo = repo

    def override_message_queue(self, queue: "MessageQueueInterface") -> None:
        """Override message queue (for testing)."""
        self._message_queue = queue

    def override_encryption_service(self, service: "EncryptionServiceInterface") -> None:
        """Override encryption service (for testing)."""
        self._encryption_service = service

    def override_feature_flag_service(self, service: "FeatureFlagServiceInterface") -> None:
        """Override feature flag service (for testing)."""
        self._feature_flag_service = service

    def reset(self) -> None:
        """Reset all dependencies (useful for testing)."""
        self._integration_repo = None
        self._sync_job_repo = None
        self._integration_state_repo = None
        self._message_queue = None
        self._encryption_service = None
        self._feature_flag_service = None


@lru_cache
def get_container() -> DependencyContainer:
    """Get the singleton dependency container."""
    return DependencyContainer()


def reset_container() -> None:
    """Reset the dependency container (for testing)."""
    get_container.cache_clear()
