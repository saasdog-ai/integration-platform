"""Admin endpoints for cross-client integration management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dto import (
    EntitySyncStatusItem,
    EntitySyncStatusListResponse,
    EntitySyncStatusResponse,
    ResetLastSyncTimeRequest,
    UserIntegrationResponse,
    UserIntegrationsResponse,
)
from app.core.logging import get_logger
from app.domain.entities import UserIntegration
from app.domain.interfaces import (
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_integration_repository() -> IntegrationRepositoryInterface:
    """Dependency to get the integration repository."""
    from app.core.dependency_injection import get_container

    return get_container().integration_repository


def get_state_repository() -> IntegrationStateRepositoryInterface:
    """Dependency to get the integration state repository."""
    from app.core.dependency_injection import get_container

    return get_container().integration_state_repository


def _to_user_integration_response(
    user_integration: UserIntegration,
) -> UserIntegrationResponse:
    """Convert domain entity to response DTO."""
    return UserIntegrationResponse(
        id=user_integration.id,
        client_id=user_integration.client_id,
        integration_id=user_integration.integration_id,
        integration_name=user_integration.integration.name
        if user_integration.integration
        else None,
        integration_type=user_integration.integration.type
        if user_integration.integration
        else None,
        status=user_integration.status,
        external_account_id=user_integration.external_account_id,
        last_connected_at=user_integration.last_connected_at,
        disconnected_at=user_integration.disconnected_at,
        created_at=user_integration.created_at,
        updated_at=user_integration.updated_at,
    )


@router.get(
    "/integrations",
    response_model=UserIntegrationsResponse,
    summary="List all user integrations across all clients",
)
async def admin_list_all_integrations(
    repo: IntegrationRepositoryInterface = Depends(get_integration_repository),
) -> UserIntegrationsResponse:
    """Get all user integrations across all clients (admin use only)."""
    integrations = await repo.get_all_user_integrations()
    return UserIntegrationsResponse(
        integrations=[_to_user_integration_response(i) for i in integrations]
    )


@router.get(
    "/clients/{client_id}/integrations/{integration_id}/sync-status",
    response_model=EntitySyncStatusListResponse,
    summary="List entity sync statuses for a client integration",
)
async def admin_list_entity_sync_statuses(
    client_id: UUID,
    integration_id: UUID,
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> EntitySyncStatusListResponse:
    """List all entity sync statuses for a specific client and integration."""
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
    "/clients/{client_id}/integrations/{integration_id}/sync-status/{entity_type}/reset",
    response_model=EntitySyncStatusResponse,
    summary="Reset last sync time for a client integration entity",
)
async def admin_reset_last_sync_time(
    client_id: UUID,
    integration_id: UUID,
    entity_type: str,
    request: ResetLastSyncTimeRequest,
    state_repo: IntegrationStateRepositoryInterface = Depends(get_state_repository),
) -> EntitySyncStatusResponse:
    """Reset last sync times for an entity type to allow full re-sync (admin use only)."""
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
