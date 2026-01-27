"""Repository and adapter interfaces for dependency injection and testing."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.entities import (
    AvailableIntegration,
    EntitySyncStatus,
    ExternalRecord,
    IntegrationStateRecord,
    OAuthTokens,
    QueueMessage,
    SyncJob,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import RecordSyncStatus, SyncJobStatus


# =============================================================================
# Repository Interfaces (All DB Access)
# =============================================================================


class IntegrationRepositoryInterface(ABC):
    """Interface for integration data access - mock this for unit tests."""

    @abstractmethod
    async def get_available_integrations(
        self, active_only: bool = True
    ) -> list[AvailableIntegration]:
        """Get all available integrations."""
        pass

    @abstractmethod
    async def get_available_integration(
        self, integration_id: UUID
    ) -> AvailableIntegration | None:
        """Get a specific available integration by ID."""
        pass

    @abstractmethod
    async def get_available_integration_by_name(
        self, name: str
    ) -> AvailableIntegration | None:
        """Get a specific available integration by name."""
        pass

    @abstractmethod
    async def get_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegration | None:
        """Get user's integration connection."""
        pass

    @abstractmethod
    async def get_user_integrations(
        self, client_id: UUID
    ) -> list[UserIntegration]:
        """Get all integrations for a user."""
        pass

    @abstractmethod
    async def create_user_integration(
        self, integration: UserIntegration
    ) -> UserIntegration:
        """Create a new user integration connection."""
        pass

    @abstractmethod
    async def update_user_integration(
        self, integration: UserIntegration
    ) -> UserIntegration:
        """Update an existing user integration."""
        pass

    @abstractmethod
    async def delete_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> bool:
        """Delete a user integration connection."""
        pass

    @abstractmethod
    async def get_user_settings(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegrationSettings | None:
        """Get user's integration settings."""
        pass

    @abstractmethod
    async def upsert_user_settings(
        self, client_id: UUID, integration_id: UUID, settings: UserIntegrationSettings
    ) -> UserIntegrationSettings:
        """Create or update user's integration settings."""
        pass

    @abstractmethod
    async def get_system_settings(
        self, integration_id: UUID
    ) -> UserIntegrationSettings | None:
        """Get system default settings for an integration."""
        pass


class SyncJobRepositoryInterface(ABC):
    """Interface for sync job data access."""

    @abstractmethod
    async def create_job(self, job: SyncJob) -> SyncJob:
        """Create a new sync job."""
        pass

    @abstractmethod
    async def get_job(self, job_id: UUID) -> SyncJob | None:
        """Get a sync job by ID."""
        pass

    @abstractmethod
    async def get_jobs_for_client(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[SyncJob]:
        """Get sync jobs for a client with optional filters."""
        pass

    @abstractmethod
    async def update_job_status(
        self,
        job_id: UUID,
        status: SyncJobStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
        entities_processed: dict[str, Any] | None = None,
    ) -> SyncJob:
        """Update job status and related fields."""
        pass

    @abstractmethod
    async def get_running_jobs(
        self, client_id: UUID, integration_id: UUID
    ) -> list[SyncJob]:
        """Get currently running jobs for a client/integration."""
        pass


class IntegrationStateRepositoryInterface(ABC):
    """Interface for integration state data access."""

    @abstractmethod
    async def get_record(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_id: str,
    ) -> IntegrationStateRecord | None:
        """Get a specific record's sync state."""
        pass

    @abstractmethod
    async def get_records_by_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        status: RecordSyncStatus,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        """Get records by sync status."""
        pass

    @abstractmethod
    async def get_pending_records(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        """Get records pending sync."""
        pass

    @abstractmethod
    async def upsert_record(
        self, record: IntegrationStateRecord
    ) -> IntegrationStateRecord:
        """Create or update a record's sync state."""
        pass

    @abstractmethod
    async def update_sync_status(
        self,
        record_id: UUID,
        client_id: UUID,
        status: RecordSyncStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        """Update a record's sync status."""
        pass

    @abstractmethod
    async def mark_synced(
        self,
        record_id: UUID,
        client_id: UUID,
        external_record_id: str | None = None,
    ) -> None:
        """Mark a record as successfully synced."""
        pass

    @abstractmethod
    async def get_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
    ) -> EntitySyncStatus | None:
        """Get the last sync status for an entity type."""
        pass

    @abstractmethod
    async def update_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        job_id: UUID,
        records_count: int,
    ) -> EntitySyncStatus:
        """Update the entity sync status after a sync."""
        pass


# =============================================================================
# Queue Interface
# =============================================================================


class MessageQueueInterface(ABC):
    """Abstract interface for message queues - easy to mock for tests."""

    @abstractmethod
    async def send_message(
        self,
        message_body: dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Send message to queue, return message ID."""
        pass

    @abstractmethod
    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[QueueMessage]:
        """Receive messages with long polling."""
        pass

    @abstractmethod
    async def delete_message(self, receipt_handle: str) -> None:
        """Delete message after successful processing."""
        pass

    @abstractmethod
    async def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Extend message visibility for long-running jobs."""
        pass


# =============================================================================
# Encryption Interface
# =============================================================================


class EncryptionServiceInterface(ABC):
    """Abstract interface for encryption services."""

    @abstractmethod
    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """
        Encrypt data.

        Returns:
            Tuple of (ciphertext, key_id)
        """
        pass

    @abstractmethod
    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt data.

        Args:
            ciphertext: The encrypted data
            key_id: The key ID used for encryption

        Returns:
            The decrypted plaintext
        """
        pass


# =============================================================================
# External Adapter Interface
# =============================================================================


class IntegrationAdapterInterface(ABC):
    """
    Abstract interface for external system adapters (QuickBooks, Xero, etc.)
    Mock this for unit tests - no real API calls needed.
    """

    @abstractmethod
    async def authenticate(self, auth_code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange auth code for tokens."""
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> OAuthTokens:
        """Refresh expired access token."""
        pass

    @abstractmethod
    async def fetch_records(
        self,
        entity_type: str,  # NOT an enum - string from DB
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """
        Fetch records from external system.

        Args:
            entity_type: The entity type to fetch (e.g., "vendor", "bill").
            since: Only fetch records modified after this time.
            page_token: Pagination token for fetching next page.
            record_ids: Optional list of specific record IDs to fetch.

        Returns:
            Tuple of (records, next_page_token)
        """
        pass

    @abstractmethod
    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Get a single record from external system."""
        pass

    @abstractmethod
    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Create record in external system."""
        pass

    @abstractmethod
    async def update_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Update record in external system."""
        pass

    @abstractmethod
    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Delete record in external system."""
        pass


class AdapterFactoryInterface(ABC):
    """Factory to get adapter for an integration - mock for tests."""

    @abstractmethod
    def get_adapter(
        self,
        integration: AvailableIntegration,
        access_token: str,
        external_account_id: str | None = None,
    ) -> IntegrationAdapterInterface:
        """Return adapter for the given integration."""
        pass
