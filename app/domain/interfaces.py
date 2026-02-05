"""Repository and adapter interfaces for dependency injection and testing."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.entities import (
    AvailableIntegration,
    ConnectionConfig,
    EntitySyncStatus,
    ExternalRecord,
    IntegrationHistoryRecord,
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
    async def get_available_integration(self, integration_id: UUID) -> AvailableIntegration | None:
        """Get a specific available integration by ID."""
        pass

    @abstractmethod
    async def get_available_integration_by_name(self, name: str) -> AvailableIntegration | None:
        """Get a specific available integration by name."""
        pass

    @abstractmethod
    async def create_available_integration(
        self, integration: AvailableIntegration
    ) -> AvailableIntegration:
        """Create a new available integration. Raises ValueError if name already exists."""
        pass

    @abstractmethod
    async def update_available_integration(
        self, integration: AvailableIntegration
    ) -> AvailableIntegration:
        """Update an existing available integration. Raises ValueError if not found or name conflict."""
        pass

    @abstractmethod
    async def get_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegration | None:
        """Get user's integration connection."""
        pass

    @abstractmethod
    async def get_user_integrations(self, client_id: UUID) -> list[UserIntegration]:
        """Get all integrations for a user."""
        pass

    @abstractmethod
    async def get_all_user_integrations(self) -> list[UserIntegration]:
        """Get all user integrations across all clients (admin use only)."""
        pass

    @abstractmethod
    async def create_user_integration(self, integration: UserIntegration) -> UserIntegration:
        """Create a new user integration connection."""
        pass

    @abstractmethod
    async def update_user_integration(self, integration: UserIntegration) -> UserIntegration:
        """Update an existing user integration."""
        pass

    @abstractmethod
    async def delete_user_integration(self, client_id: UUID, integration_id: UUID) -> bool:
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
    async def get_system_settings(self, integration_id: UUID) -> UserIntegrationSettings | None:
        """Get system default settings for an integration."""
        pass

    @abstractmethod
    async def upsert_system_settings(
        self,
        integration_id: UUID,
        settings: UserIntegrationSettings,
    ) -> UserIntegrationSettings:
        """Create or update system default settings for an integration."""
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
    async def get_running_jobs(self, client_id: UUID, integration_id: UUID) -> list[SyncJob]:
        """Get currently running jobs for a client/integration."""
        pass

    @abstractmethod
    async def create_job_if_no_running(self, job: SyncJob) -> tuple[SyncJob | None, SyncJob | None]:
        """
        Atomically check for running jobs and create a new job if none exist.

        Uses database-level advisory lock to prevent race conditions.

        Args:
            job: The job to create.

        Returns:
            Tuple of (created_job, running_job):
            - If no running jobs: (created_job, None)
            - If running job exists: (None, running_job)
        """
        pass

    @abstractmethod
    async def get_pending_jobs(
        self,
        stale_seconds: int = 30,
    ) -> list[SyncJob]:
        """Find jobs stuck in PENDING status longer than stale_seconds.

        Used on startup to recover orphaned jobs whose queue messages
        were lost (e.g. in-memory queue after a server restart).
        """
        pass

    @abstractmethod
    async def get_stuck_jobs(
        self,
        stuck_threshold_minutes: int = 60,
    ) -> list[SyncJob]:
        """
        Find jobs that have been running longer than the threshold.

        Args:
            stuck_threshold_minutes: Minutes after which a running job is considered stuck.

        Returns:
            List of stuck jobs.
        """
        pass

    @abstractmethod
    async def terminate_stuck_job(
        self,
        job_id: UUID,
        reason: str = "Job exceeded maximum runtime",
    ) -> SyncJob | None:
        """
        Terminate a stuck job by marking it as failed.

        Args:
            job_id: The job to terminate.
            reason: Reason for termination.

        Returns:
            The terminated job, or None if job not found or not running.
        """
        pass


class IntegrationStateRepositoryInterface(ABC):
    """Interface for integration state data access."""

    @abstractmethod
    async def get_record(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_id: str | None = None,
    ) -> IntegrationStateRecord | None:
        """Get a specific record's sync state by internal record ID."""
        pass

    @abstractmethod
    async def get_record_by_external_id(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        external_record_id: str,
    ) -> IntegrationStateRecord | None:
        """Get a specific record's sync state by external record ID."""
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
    async def upsert_record(self, record: IntegrationStateRecord) -> IntegrationStateRecord:
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
        job_id: UUID | None = None,
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
    async def list_entity_sync_statuses(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> list[EntitySyncStatus]:
        """Get all entity sync statuses for a client+integration."""
        pass

    @abstractmethod
    async def update_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        job_id: UUID,
        records_count: int,
        last_inbound_sync_at: datetime | None = None,
    ) -> EntitySyncStatus:
        """Update the entity sync status after a sync."""
        pass

    @abstractmethod
    async def reset_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        reset_inbound_sync_time: bool = True,
        reset_last_sync_time: bool = True,
    ) -> EntitySyncStatus | None:
        """Reset last sync times for an entity type to allow full re-sync."""
        pass

    @abstractmethod
    async def batch_upsert_records(
        self,
        records: list[IntegrationStateRecord],
    ) -> list[IntegrationStateRecord]:
        """
        Upsert multiple records in a single transaction.

        If any record fails, all changes are rolled back.
        This prevents orphaned records on partial failures.

        Args:
            records: List of records to upsert.

        Returns:
            List of upserted records.
        """
        pass

    @abstractmethod
    async def batch_mark_synced(
        self,
        updates: list[tuple[UUID, UUID, str | None]],  # (record_id, client_id, external_record_id)
        client_id: UUID | None = None,
        integration_id: UUID | None = None,
    ) -> None:
        """
        Mark multiple records as synced in a single transaction.

        Uses advisory lock when client_id and integration_id are provided to prevent
        concurrent batch operations from racing.

        If any update fails, all changes are rolled back.

        Args:
            updates: List of (record_id, client_id, external_record_id) tuples.
            client_id: Optional client_id for advisory lock (recommended).
            integration_id: Optional integration_id for advisory lock (recommended).
        """
        pass

    @abstractmethod
    async def get_records_by_job_id(
        self,
        client_id: UUID,
        job_id: UUID,
        entity_type: str | None = None,
        status: RecordSyncStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationStateRecord], int]:
        """
        Get paginated records that were modified by a specific sync job.

        Args:
            client_id: The client ID for multi-tenant isolation.
            job_id: The sync job ID to filter by.
            entity_type: Optional filter by entity type.
            status: Optional filter by sync status.
            page: Page number (1-indexed).
            page_size: Number of records per page.

        Returns:
            Tuple of (records, total_count).
        """
        pass

    @abstractmethod
    async def create_history_entry(
        self, entry: IntegrationHistoryRecord
    ) -> IntegrationHistoryRecord:
        """Create a single history entry."""
        pass

    @abstractmethod
    async def batch_create_history(self, entries: list[IntegrationHistoryRecord]) -> None:
        """Create multiple history entries in a single transaction."""
        pass

    @abstractmethod
    async def get_history_by_job_id(
        self,
        client_id: UUID,
        job_id: UUID,
        entity_type: str | None = None,
        status: RecordSyncStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationHistoryRecord], int]:
        """
        Get paginated history entries for a specific sync job.

        Args:
            client_id: The client ID for multi-tenant isolation.
            job_id: The sync job ID to filter by.
            entity_type: Optional filter by entity type.
            status: Optional filter by sync status.
            page: Page number (1-indexed).
            page_size: Number of records per page.

        Returns:
            Tuple of (history_records, total_count).
        """
        pass

    @abstractmethod
    async def cleanup_old_history(
        self,
        retention_days: int,
        batch_size: int = 10000,
    ) -> int:
        """
        Delete history entries older than retention_days.

        Uses batched deletes to avoid lock contention.

        Args:
            retention_days: Delete entries older than this many days.
            batch_size: Maximum rows to delete per transaction.

        Returns:
            Total number of rows deleted.
        """
        pass

    @abstractmethod
    async def bump_version_vectors(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        record_ids: list[str],
        bump_internal: bool = False,
        bump_external: bool = False,
    ) -> tuple[int, int]:
        """
        Bump version vectors for the given records, creating state records if needed.

        For push notifications: bump internal_version_id (our system changed).
        For webhook notifications: bump external_version_id (external system changed).

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.
            entity_type: The entity type (e.g. "vendor").
            record_ids: List of record IDs to bump.
            bump_internal: If True, bump internal_version_id.
            bump_external: If True, bump external_version_id.

        Returns:
            Tuple of (records_bumped, records_created).
        """
        pass


# =============================================================================
# Webhook Handler Interface
# =============================================================================


class WebhookHandlerInterface(ABC):
    """Abstract interface for per-provider webhook handlers."""

    @abstractmethod
    def verify_signature(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify the webhook signature from the provider."""
        pass

    @abstractmethod
    def parse_payload(self, body: bytes) -> tuple[str, list[str], str]:
        """
        Parse webhook payload into normalized form.

        Returns:
            Tuple of (entity_type, record_ids, event_type).
        """
        pass

    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name this handler supports."""
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

    @abstractmethod
    async def send_to_dlq(
        self,
        message: QueueMessage,
        error: str,
    ) -> str:
        """
        Send a failed message to the dead letter queue.

        Args:
            message: The original message that failed processing.
            error: The error that caused the failure.

        Returns:
            The DLQ message ID.
        """
        pass

    @abstractmethod
    async def get_dlq_messages(
        self,
        max_messages: int = 10,
    ) -> list[QueueMessage]:
        """
        Get messages from the dead letter queue for inspection.

        Args:
            max_messages: Maximum number of messages to retrieve.

        Returns:
            List of failed messages.
        """
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
    async def authenticate(
        self, auth_code: str, redirect_uri: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
        """Exchange auth code for tokens."""
        pass

    @abstractmethod
    async def refresh_token(
        self, refresh_token: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
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


# =============================================================================
# Feature Flag Interface
# =============================================================================


class FeatureFlagServiceInterface(ABC):
    """Abstract interface for feature flag access.

    Decouples feature flag reads from Settings so we can swap to
    LaunchDarkly or an internal service later.
    """

    @abstractmethod
    def is_sync_globally_disabled(self) -> bool: ...

    @abstractmethod
    def is_integration_disabled(self, integration_name: str) -> bool: ...

    @abstractmethod
    def get_disabled_integrations(self) -> list[str]: ...

    @abstractmethod
    def is_job_termination_enabled(self) -> bool: ...

    @abstractmethod
    def is_auth_enabled(self) -> bool: ...

    @abstractmethod
    def is_rate_limit_enabled(self) -> bool: ...

    @abstractmethod
    def is_job_runner_enabled(self) -> bool: ...

    @abstractmethod
    def is_scheduler_enabled(self) -> bool: ...
