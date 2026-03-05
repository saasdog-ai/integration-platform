"""Integration management endpoints."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dto import (
    AvailableIntegrationResponse,
    AvailableIntegrationsResponse,
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    DoNotSyncRequest,
    EntitySyncStatusItem,
    EntitySyncStatusListResponse,
    EntitySyncStatusResponse,
    ForceSyncRequest,
    NotifyChangeRequest,
    NotifyChangeResponse,
    OAuthCallbackRequest,
    OverrideResultResponse,
    ResetLastSyncTimeRequest,
    SyncRecordResponse,
    SyncRecordsResponse,
    UserIntegrationResponse,
    UserIntegrationsResponse,
    WebhookReceiveResponse,
)
from app.api.mappers import to_available_integration_response, to_user_integration_response
from app.auth import AuthenticatedClient, get_client_id, get_current_client
from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    SyncError,
    ValidationError,
)
from app.core.logging import get_logger
from app.domain.entities import AuditLogEntry, ChangeEvent
from app.domain.enums import ChangeSourceType, RecordSyncStatus
from app.domain.interfaces import IntegrationStateRepositoryInterface
from app.services.integration_service import IntegrationService
from app.services.sync_orchestrator import SyncOrchestrator

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


def get_integration_service() -> IntegrationService:
    """Dependency to get integration service."""
    from app.core.dependency_injection import get_container
    from app.infrastructure.adapters.factory import get_adapter_factory

    container = get_container()
    return IntegrationService(
        integration_repo=container.integration_repository,
        encryption_service=container.encryption_service,
        adapter_factory=get_adapter_factory(),
    )


def get_sync_orchestrator() -> SyncOrchestrator:
    """Dependency to get sync orchestrator."""
    from app.core.dependency_injection import get_container
    from app.infrastructure.adapters.factory import get_adapter_factory

    container = get_container()
    return SyncOrchestrator(
        integration_repo=container.integration_repository,
        job_repo=container.sync_job_repository,
        state_repo=container.integration_state_repository,
        queue=container.message_queue,
        encryption_service=container.encryption_service,
        adapter_factory=get_adapter_factory(),
        feature_flags=container.feature_flag_service,
    )


def get_state_repository() -> IntegrationStateRepositoryInterface:
    """Dependency to get the integration state repository."""
    from app.core.dependency_injection import get_container

    return get_container().integration_state_repository


_to_available_integration_response = to_available_integration_response
_to_user_integration_response = to_user_integration_response


@router.get(
    "/available",
    response_model=AvailableIntegrationsResponse,
    summary="List available integrations",
)
async def list_available_integrations(
    active_only: bool = True,
    service: IntegrationService = Depends(get_integration_service),
) -> AvailableIntegrationsResponse:
    """Get list of all available integrations that can be connected."""
    integrations = await service.get_available_integrations(active_only=active_only)
    return AvailableIntegrationsResponse(
        integrations=[_to_available_integration_response(i) for i in integrations]
    )


@router.get(
    "/available/{integration_id}",
    response_model=AvailableIntegrationResponse,
    summary="Get available integration details",
)
async def get_available_integration(
    integration_id: UUID,
    service: IntegrationService = Depends(get_integration_service),
) -> AvailableIntegrationResponse:
    """Get details of a specific available integration."""
    try:
        integration = await service.get_available_integration(integration_id)
        return _to_available_integration_response(integration)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None


@router.get(
    "",
    response_model=UserIntegrationsResponse,
    summary="List connected integrations",
)
async def list_user_integrations(
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
) -> UserIntegrationsResponse:
    """Get list of user's connected integrations."""
    integrations = await service.get_user_integrations(client_id)
    return UserIntegrationsResponse(
        integrations=[_to_user_integration_response(i) for i in integrations]
    )


@router.get(
    "/{integration_id}",
    response_model=UserIntegrationResponse,
    summary="Get connected integration",
)
async def get_user_integration(
    integration_id: UUID,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
) -> UserIntegrationResponse:
    """Get a specific connected integration."""
    try:
        integration = await service.get_user_integration(client_id, integration_id)
        return _to_user_integration_response(integration)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None


@router.post(
    "/{integration_id}/connect",
    response_model=ConnectIntegrationResponse,
    summary="Start OAuth connection",
)
async def connect_integration(
    integration_id: UUID,
    request: ConnectIntegrationRequest,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
) -> ConnectIntegrationResponse:
    """Start OAuth flow to connect an integration."""
    try:
        auth_url = await service.get_oauth_authorization_url(
            client_id=client_id,
            integration_id=integration_id,
            redirect_uri=request.redirect_uri,
            state=request.state,
        )
        return ConnectIntegrationResponse(authorization_url=auth_url)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.post(
    "/{integration_id}/callback",
    response_model=UserIntegrationResponse,
    summary="Complete OAuth connection",
)
async def oauth_callback(
    integration_id: UUID,
    request: OAuthCallbackRequest,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
) -> UserIntegrationResponse:
    """Complete OAuth flow with authorization code."""
    try:
        user_integration = await service.complete_oauth_callback(
            client_id=client_id,
            integration_id=integration_id,
            auth_code=request.code,
            redirect_uri=request.redirect_uri,
            state=request.state,
            realm_id=request.realm_id,
        )
        return _to_user_integration_response(user_integration)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except IntegrationError as e:
        logger.error("OAuth callback failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to complete OAuth connection. Please try again.",
        ) from e


@router.delete(
    "/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect integration",
)
async def disconnect_integration(
    integration_id: UUID,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
) -> None:
    """Disconnect a connected integration."""
    try:
        await service.disconnect_integration(client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None


@router.get(
    "/{integration_id}/sync-status",
    response_model=EntitySyncStatusListResponse,
    summary="List entity sync statuses",
)
async def list_entity_sync_statuses(
    integration_id: UUID,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> EntitySyncStatusListResponse:
    """List all entity sync statuses for an integration."""
    # Verify the integration belongs to this client
    try:
        await service.get_user_integration(client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None

    statuses = await state_repo.list_entity_sync_statuses(
        client_id=client_id,
        integration_id=integration_id,
    )

    return EntitySyncStatusListResponse(
        statuses=[
            EntitySyncStatusItem(
                entity_type=s.entity_type,
                last_successful_sync_at=s.last_successful_sync_at,
                last_inbound_sync_at=s.last_inbound_sync_at,
                last_sync_job_id=s.last_sync_job_id,
                records_synced_count=s.records_synced_count,
            )
            for s in statuses
        ]
    )


@router.post(
    "/{integration_id}/sync-status/{entity_type}/reset",
    response_model=EntitySyncStatusResponse,
    summary="Reset entity last sync time",
)
async def reset_entity_last_sync_time(
    integration_id: UUID,
    entity_type: str,
    request: ResetLastSyncTimeRequest,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> EntitySyncStatusResponse:
    """Reset last sync times for an entity type to allow full re-sync."""
    # Verify the integration belongs to this client
    try:
        await service.get_user_integration(client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None

    result = await state_repo.reset_entity_sync_status(
        client_id=client_id,
        integration_id=integration_id,
        entity_type=entity_type,
        reset_inbound_sync_time=request.reset_inbound_sync_time,
        reset_last_sync_time=request.reset_last_sync_time,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sync status found for entity type: {entity_type}",
        )

    parts = []
    if request.reset_inbound_sync_time:
        parts.append("inbound sync time")
    if request.reset_last_sync_time:
        parts.append("last sync time")
    message = f"Successfully reset {' and '.join(parts)} for {entity_type}"

    return EntitySyncStatusResponse(
        entity_type=result.entity_type,
        last_successful_sync_at=result.last_successful_sync_at,
        last_inbound_sync_at=result.last_inbound_sync_at,
        last_sync_job_id=result.last_sync_job_id,
        records_synced_count=result.records_synced_count,
        message=message,
    )


@router.post(
    "/{integration_id}/notify",
    response_model=NotifyChangeResponse,
    summary="Notify of record changes (push)",
)
async def notify_change(
    integration_id: UUID,
    request: NotifyChangeRequest,
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> NotifyChangeResponse:
    """
    Notify the platform that records have changed in the internal system.

    Bumps version vectors for the specified records and optionally
    triggers a sync job based on the entity's sync_trigger setting.
    """
    event = ChangeEvent(
        client_id=client_id,
        integration_id=integration_id,
        entity_type=request.entity_type,
        record_ids=request.record_ids,
        event=request.event,
        source=ChangeSourceType.PUSH,
    )
    try:
        records_bumped, records_created, sync_job = await orchestrator.handle_change_event(event)
        return NotifyChangeResponse(
            records_bumped=records_bumped,
            records_created=records_created,
            sync_triggered=sync_job is not None,
            sync_job_id=sync_job.id if sync_job else None,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None
    except SyncError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post(
    "/{integration_id}/webhooks/{provider}",
    response_model=WebhookReceiveResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Receive webhook from provider (stub)",
)
async def receive_webhook(
    integration_id: UUID,
    provider: str,
    client_id: UUID = Depends(get_client_id),
) -> WebhookReceiveResponse:
    """
    Receive a webhook from an external provider.

    This is a stub endpoint. Provider-specific handlers will be
    registered in future implementations.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Webhook handler for provider '{provider}' is not implemented",
    )


# =============================================================================
# Manual Override Endpoints
# =============================================================================


async def _resolve_state_ids(
    request: ForceSyncRequest | DoNotSyncRequest,
    integration_id: UUID,
    client_id: UUID,
    state_repo: IntegrationStateRepositoryInterface,
) -> list[UUID]:
    """Resolve any selector form to a list of state record UUIDs."""
    if request.state_ids:
        return request.state_ids
    return await state_repo.resolve_record_ids(
        client_id=client_id,
        integration_id=integration_id,
        entity_type=request.entity_type,  # type: ignore[arg-type]  # validated by model
        internal_record_ids=request.internal_record_ids,
        external_record_ids=request.external_record_ids,
    )


@router.post(
    "/{integration_id}/records/force-sync",
    response_model=OverrideResultResponse,
    summary="Force-sync failing records",
)
async def force_sync_records(
    integration_id: UUID,
    request: ForceSyncRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    service: IntegrationService = Depends(get_integration_service),
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> OverrideResultResponse:
    """
    Mark failing records as synced: clear errors, equalize version vectors.

    If a user later modifies a force-synced record, the normal sync loop
    will detect the version change and re-attempt sync.
    """
    # Verify the integration belongs to this client
    try:
        await service.get_user_integration(client.client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None

    state_ids = await _resolve_state_ids(request, integration_id, client.client_id, state_repo)
    if not state_ids:
        return OverrideResultResponse(records_updated=0, records_skipped=0)

    updated, skipped = await state_repo.force_sync_records(
        client_id=client.client_id,
        integration_id=integration_id,
        state_ids=state_ids,
    )

    # Write audit log
    await state_repo.write_audit_entry(
        AuditLogEntry(
            id=uuid4(),
            client_id=client.client_id,
            integration_id=integration_id,
            action="force_sync",
            entity_type=request.entity_type,
            target_record_ids=state_ids,
            details={"records_updated": updated, "records_skipped": len(skipped)},
            performed_by=client.user_id,
            created_at=datetime.now(UTC),
        )
    )

    return OverrideResultResponse(
        records_updated=updated,
        records_skipped=len(skipped),
        skipped_details=skipped,
    )


@router.post(
    "/{integration_id}/records/do-not-sync",
    response_model=OverrideResultResponse,
    summary="Toggle do-not-sync flag on records",
)
async def set_do_not_sync(
    integration_id: UUID,
    request: DoNotSyncRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    service: IntegrationService = Depends(get_integration_service),
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> OverrideResultResponse:
    """
    Toggle the do-not-sync flag on records to exclude or re-include them in sync.

    When toggled ON, records are skipped in both inbound and outbound sync.
    When toggled OFF, records with version mismatches are set to PENDING.
    """
    # Verify the integration belongs to this client
    try:
        await service.get_user_integration(client.client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None

    state_ids = await _resolve_state_ids(request, integration_id, client.client_id, state_repo)
    if not state_ids:
        return OverrideResultResponse(records_updated=0, records_skipped=0)

    updated, skipped = await state_repo.set_do_not_sync(
        client_id=client.client_id,
        integration_id=integration_id,
        state_ids=state_ids,
        do_not_sync=request.do_not_sync,
    )

    # Write audit log
    action = "do_not_sync_enabled" if request.do_not_sync else "do_not_sync_disabled"
    await state_repo.write_audit_entry(
        AuditLogEntry(
            id=uuid4(),
            client_id=client.client_id,
            integration_id=integration_id,
            action=action,
            entity_type=request.entity_type,
            target_record_ids=state_ids,
            details={"do_not_sync": request.do_not_sync, "records_updated": updated},
            performed_by=client.user_id,
            created_at=datetime.now(UTC),
        )
    )

    return OverrideResultResponse(
        records_updated=updated,
        records_skipped=len(skipped),
        skipped_details=skipped,
    )


@router.get(
    "/{integration_id}/records",
    response_model=SyncRecordsResponse,
    summary="Browse integration records",
)
async def list_integration_records(
    integration_id: UUID,
    client_id: UUID = Depends(get_client_id),
    service: IntegrationService = Depends(get_integration_service),
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
    entity_type: str | None = Query(None),
    sync_status: str | None = Query(None),
    do_not_sync: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> SyncRecordsResponse:
    """Browse all records for an integration with optional filters."""
    # Verify the integration belongs to this client
    try:
        await service.get_user_integration(client_id, integration_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None

    status_enum = RecordSyncStatus(sync_status) if sync_status else None

    records, total = await state_repo.get_records_paginated(
        client_id=client_id,
        integration_id=integration_id,
        entity_type=entity_type,
        sync_status=status_enum,
        do_not_sync=do_not_sync,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return SyncRecordsResponse(
        records=[
            SyncRecordResponse(
                id=r.id,
                entity_type=r.entity_type,
                internal_record_id=r.internal_record_id,
                external_record_id=r.external_record_id,
                sync_direction=r.sync_direction,
                sync_status=r.sync_status.value,
                is_success=r.sync_status == RecordSyncStatus.SYNCED,
                updated_at=r.updated_at,
                error_code=r.error_code,
                error_message=r.error_message,
                error_details=r.error_details,
                do_not_sync=r.do_not_sync,
                force_synced_at=r.force_synced_at,
            )
            for r in records
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
