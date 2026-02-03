"""Domain entities (Pydantic models)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ConflictResolution,
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)


class BaseEntity(BaseModel):
    """Base entity with common fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    updated_by: str | None = None


class SyncRule(BaseModel):
    """Configurable sync rule for an entity type."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: str  # NOT an enum - configurable string from DB
    direction: SyncDirection
    enabled: bool = True
    master_if_conflict: ConflictResolution = (
        ConflictResolution.EXTERNAL
    )  # Default to external as master
    field_mappings: dict[str, str] | None = None  # internal_field -> external_field


class UserIntegrationSettings(BaseModel):
    """User-specific integration settings."""

    model_config = ConfigDict(from_attributes=True)

    sync_rules: list[SyncRule] = Field(default_factory=list)
    sync_frequency: str | None = None  # Cron expression
    auto_sync_enabled: bool = False


class SystemIntegrationSettings(BaseModel):
    """System default settings for an integration."""

    model_config = ConfigDict(from_attributes=True)

    default_sync_rules: list[SyncRule] = Field(default_factory=list)
    default_sync_frequency: str | None = None


class OAuthConfig(BaseModel):
    """OAuth configuration for an integration."""

    model_config = ConfigDict(from_attributes=True)

    authorization_url: str
    token_url: str
    scopes: list[str] = Field(default_factory=list)
    client_id: str | None = None
    client_secret: str | None = None


class AvailableIntegration(BaseEntity):
    """Integration definition from database."""

    name: str  # "QuickBooks Online", "Xero"
    type: str  # "erp", "hris", "crm" - NOT an enum
    description: str | None = None
    supported_entities: list[str] = Field(default_factory=list)  # ["bill", "invoice", "vendor"]
    oauth_config: OAuthConfig | None = None
    is_active: bool = True


class UserIntegration(BaseEntity):
    """User's connected integration."""

    client_id: UUID
    integration_id: UUID
    status: IntegrationStatus = IntegrationStatus.PENDING
    credentials_encrypted: bytes | None = None
    credentials_key_id: str | None = None
    external_account_id: str | None = None
    last_connected_at: datetime | None = None
    disconnected_at: datetime | None = None

    # Relationships (loaded separately)
    integration: AvailableIntegration | None = None
    settings: UserIntegrationSettings | None = None


class SyncJob(BaseEntity):
    """Sync job execution."""

    client_id: UUID
    integration_id: UUID
    job_type: SyncJobType
    status: SyncJobStatus = SyncJobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    entities_processed: dict[str, Any] | None = None  # Summary per entity type
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    triggered_by: SyncJobTrigger = SyncJobTrigger.USER
    job_params: dict[str, Any] | None = None  # Full request params for idempotent retry

    # Relationships (loaded separately)
    integration: AvailableIntegration | None = None


class EntitySyncStatus(BaseEntity):
    """Last successful sync time per entity type."""

    client_id: UUID
    integration_id: UUID
    entity_type: str  # NOT an enum - configurable string
    last_successful_sync_at: datetime | None = None
    last_inbound_sync_at: datetime | None = None
    last_sync_job_id: UUID | None = None
    records_synced_count: int = 0


class IntegrationStateRecord(BaseEntity):
    """Record-level sync state."""

    client_id: UUID
    integration_id: UUID
    entity_type: str  # NOT an enum - configurable string
    internal_record_id: str | None = None  # None for inbound records not yet written internally
    external_record_id: str | None = None  # ID in external system
    sync_status: RecordSyncStatus = RecordSyncStatus.PENDING
    sync_direction: SyncDirection | None = None
    internal_version_id: int = 1
    external_version_id: int = 0
    last_sync_version_id: int = 0
    last_synced_at: datetime | None = None
    last_job_id: UUID | None = None  # Links to the sync job that last modified this record
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_in_sync(self) -> bool:
        """Check if all version vectors match (fully synced)."""
        return self.internal_version_id == self.external_version_id == self.last_sync_version_id

    @property
    def needs_outbound_sync(self) -> bool:
        """Check if internal changes need to be synced to external."""
        return self.internal_version_id > self.last_sync_version_id

    @property
    def needs_inbound_sync(self) -> bool:
        """Check if external changes need to be synced to internal."""
        return self.external_version_id > self.last_sync_version_id


class IntegrationHistoryRecord(BaseModel):
    """Snapshot of a record's sync state for a specific job."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    state_record_id: UUID
    integration_id: UUID
    entity_type: str
    internal_record_id: str | None = None
    external_record_id: str | None = None
    sync_status: RecordSyncStatus
    sync_direction: SyncDirection | None = None
    job_id: UUID
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    created_at: datetime


class ExternalRecord(BaseModel):
    """Record fetched from an external system."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    data: dict[str, Any]
    version: str | None = None
    updated_at: datetime | None = None


class OAuthTokens(BaseModel):
    """OAuth tokens from external system."""

    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    expires_at: datetime | None = None
    scope: str | None = None


class QueueMessage(BaseModel):
    """Message from a queue."""

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    receipt_handle: str
    body: dict[str, Any]
    attributes: dict[str, Any] = Field(default_factory=dict)


class EntitySyncRequest(BaseModel):
    """Request to sync specific entities, optionally with specific record IDs."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: str  # e.g., "vendor", "bill", "invoice"
    record_ids: list[str] | None = None  # If None, sync all records of this type


class SyncJobMessage(BaseModel):
    """Sync job message for queue dispatch."""

    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    client_id: UUID
    integration_id: UUID
    job_type: SyncJobType
    entity_types: list[str] | None = None  # Simple list of entity types (sync all records)
    entity_requests: list[EntitySyncRequest] | None = (
        None  # Detailed requests with optional record IDs
    )
