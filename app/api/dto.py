"""API Data Transfer Objects (Request/Response models)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    ChangeSourceType,
    ConflictResolution,
    IntegrationStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
    SyncTriggerMode,
)

# =============================================================================
# Base DTOs
# =============================================================================


class BaseResponse(BaseModel):
    """Base response model."""

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    code: str
    details: dict[str, Any] | None = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    items: list[Any]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool = False


# =============================================================================
# Integration DTOs
# =============================================================================


class ConnectionConfigResponse(BaseResponse):
    """Connection/authentication configuration for an integration."""

    auth_type: str = "oauth2"
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = []
    api_key_header_name: str | None = None


class AvailableIntegrationResponse(BaseResponse):
    """Available integration response."""

    id: UUID
    name: str
    type: str
    description: str | None
    supported_entities: list[str]
    connection_config: ConnectionConfigResponse | None
    is_active: bool


class AvailableIntegrationsResponse(BaseResponse):
    """List of available integrations."""

    integrations: list[AvailableIntegrationResponse]


class UserIntegrationResponse(BaseResponse):
    """User's connected integration."""

    id: UUID
    client_id: UUID
    integration_id: UUID
    integration_name: str | None = None
    integration_type: str | None = None
    status: IntegrationStatus
    external_account_id: str | None
    last_connected_at: datetime | None
    disconnected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserIntegrationsResponse(BaseResponse):
    """List of user integrations."""

    integrations: list[UserIntegrationResponse]


class ConnectIntegrationRequest(BaseModel):
    """Request to start OAuth connection."""

    redirect_uri: str
    state: str | None = None


class ConnectIntegrationResponse(BaseResponse):
    """Response with OAuth authorization URL."""

    authorization_url: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request."""

    code: str
    redirect_uri: str
    state: str  # Required for CSRF protection
    realm_id: str | None = None


# =============================================================================
# Settings DTOs
# =============================================================================


class SyncRuleRequest(BaseModel):
    """Sync rule in request."""

    entity_type: str
    direction: SyncDirection
    enabled: bool = True
    master_if_conflict: ConflictResolution = ConflictResolution.EXTERNAL
    field_mappings: dict[str, str] | None = None
    change_source: ChangeSourceType = ChangeSourceType.POLLING
    sync_trigger: SyncTriggerMode = SyncTriggerMode.DEFERRED


class SyncRuleResponse(BaseResponse):
    """Sync rule in response."""

    entity_type: str
    direction: SyncDirection
    enabled: bool
    master_if_conflict: ConflictResolution
    field_mappings: dict[str, str] | None
    change_source: ChangeSourceType
    sync_trigger: SyncTriggerMode


class UserSettingsRequest(BaseModel):
    """Request to update user settings."""

    sync_rules: list[SyncRuleRequest]
    sync_frequency: str | None = None
    auto_sync_enabled: bool = False


class UserSettingsResponse(BaseResponse):
    """User settings response."""

    sync_rules: list[SyncRuleResponse]
    sync_frequency: str | None
    auto_sync_enabled: bool


# =============================================================================
# Sync Job DTOs
# =============================================================================


class TriggerSyncRequest(BaseModel):
    """Request to trigger a sync job."""

    integration_id: UUID
    job_type: SyncJobType = SyncJobType.INCREMENTAL
    entity_types: list[str] | None = None


class SyncJobResponse(BaseResponse):
    """Sync job response."""

    id: UUID
    client_id: UUID
    integration_id: UUID
    integration_name: str | None = None
    job_type: SyncJobType
    status: SyncJobStatus
    triggered_by: SyncJobTrigger
    started_at: datetime | None
    completed_at: datetime | None
    entities_processed: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    error_details: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class SyncJobsResponse(BaseResponse):
    """Paginated list of sync jobs."""

    jobs: list[SyncJobResponse]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class SyncJobListParams(BaseModel):
    """Query parameters for listing sync jobs."""

    integration_id: UUID | None = None
    status: SyncJobStatus | None = None
    since: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# =============================================================================
# Sync Record Detail DTOs
# =============================================================================


class SyncRecordResponse(BaseResponse):
    """Individual record sync details."""

    id: UUID
    entity_type: str
    internal_record_id: str | None
    external_record_id: str | None
    sync_direction: SyncDirection | None
    sync_status: str  # synced, failed, pending, conflict
    is_success: bool  # Computed from sync_status
    updated_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    do_not_sync: bool = False
    force_synced_at: datetime | None = None


class SyncRecordsResponse(BaseResponse):
    """Paginated list of sync records for a job."""

    records: list[SyncRecordResponse]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 1


# =============================================================================
# Entity Sync Status List DTOs
# =============================================================================


class EntitySyncStatusItem(BaseResponse):
    """Individual entity sync status."""

    entity_type: str
    last_successful_sync_at: datetime | None
    last_inbound_sync_at: datetime | None
    last_sync_job_id: UUID | None
    records_synced_count: int


class EntitySyncStatusListResponse(BaseResponse):
    """List of entity sync statuses."""

    statuses: list[EntitySyncStatusItem]


# =============================================================================
# Last Sync Time Reset DTOs
# =============================================================================


class ResetLastSyncTimeRequest(BaseModel):
    """Request to reset last sync times for an entity type."""

    reset_inbound_sync_time: bool = True
    reset_last_sync_time: bool = True


class EntitySyncStatusResponse(BaseResponse):
    """Entity sync status after reset."""

    entity_type: str
    last_successful_sync_at: datetime | None
    last_inbound_sync_at: datetime | None
    last_sync_job_id: UUID | None
    records_synced_count: int
    message: str


# =============================================================================
# Health DTOs
# =============================================================================


class HealthResponse(BaseResponse):
    """Health check response."""

    status: str
    version: str = "0.1.0"
    timestamp: datetime


class HealthDetailResponse(BaseResponse):
    """Detailed health check response."""

    status: str
    version: str = "0.1.0"
    timestamp: datetime
    database: str
    queue: str
    encryption: str


# =============================================================================
# Change Notification DTOs
# =============================================================================


class NotifyChangeRequest(BaseModel):
    """Request to notify of record changes (push notification)."""

    entity_type: str
    record_ids: list[str] = Field(min_length=1, max_length=1000)
    event: str  # e.g. "created", "updated", "deleted"


class NotifyChangeResponse(BaseResponse):
    """Response from a change notification."""

    records_bumped: int
    records_created: int
    sync_triggered: bool
    sync_job_id: UUID | None = None


class WebhookReceiveResponse(BaseResponse):
    """Response from a webhook endpoint."""

    accepted: bool
    records_bumped: int = 0
    records_created: int = 0
    sync_triggered: bool = False
    sync_job_id: UUID | None = None


# =============================================================================
# Admin Integration Management DTOs
# =============================================================================


class CreateAvailableIntegrationRequest(BaseModel):
    """Request to create a new available integration."""

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    description: str | None = None
    connection_config: dict[str, Any] | None = None
    supported_entities: list[str] = Field(default_factory=list)
    is_active: bool = True


class UpdateAvailableIntegrationRequest(BaseModel):
    """Request to update an available integration (partial update)."""

    name: str | None = None
    type: str | None = None
    description: str | None = None
    connection_config: dict[str, Any] | None = None
    supported_entities: list[str] | None = None
    is_active: bool | None = None


# =============================================================================
# Manual Override DTOs
# =============================================================================


class RecordSelector(BaseModel):
    """Flexible record selector — exactly one of the three ID lists must be provided."""

    state_ids: list[UUID] | None = None
    entity_type: str | None = None
    internal_record_ids: list[str] | None = None
    external_record_ids: list[str] | None = None

    @model_validator(mode="after")
    def validate_exactly_one_selector(self) -> "RecordSelector":
        selectors = [self.state_ids, self.internal_record_ids, self.external_record_ids]
        provided = [s for s in selectors if s]
        if len(provided) != 1:
            raise ValueError(
                "Provide exactly one of: state_ids, internal_record_ids, external_record_ids"
            )
        if (self.internal_record_ids or self.external_record_ids) and not self.entity_type:
            raise ValueError(
                "entity_type is required when using internal_record_ids or external_record_ids"
            )
        return self


class ForceSyncRequest(RecordSelector):
    """Request to force-sync records (clear errors, equalize version vectors)."""

    pass


class DoNotSyncRequest(RecordSelector):
    """Request to toggle do-not-sync flag on records."""

    do_not_sync: bool


class OverrideResultResponse(BaseResponse):
    """Response for bulk override operations."""

    records_updated: int
    records_skipped: int
    skipped_details: list[dict[str, str]] = Field(default_factory=list)
