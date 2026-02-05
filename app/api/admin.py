"""Admin endpoints for cross-client integration management."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dto import (
    AvailableIntegrationResponse,
    AvailableIntegrationsResponse,
    ConnectionConfigResponse,
    CreateAvailableIntegrationRequest,
    EntitySyncStatusItem,
    EntitySyncStatusListResponse,
    EntitySyncStatusResponse,
    ResetLastSyncTimeRequest,
    UpdateAvailableIntegrationRequest,
    UserIntegrationResponse,
    UserIntegrationsResponse,
)
from app.core.logging import get_logger
from app.domain.entities import AvailableIntegration, ConnectionConfig, UserIntegration
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
        integration_name=(
            user_integration.integration.name if user_integration.integration else None
        ),
        integration_type=(
            user_integration.integration.type if user_integration.integration else None
        ),
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


# =============================================================================
# Available Integration CRUD (Admin)
# =============================================================================


def _to_available_integration_response(
    integration: AvailableIntegration,
) -> AvailableIntegrationResponse:
    """Convert domain entity to response DTO."""
    connection_config = None
    if integration.connection_config:
        connection_config = ConnectionConfigResponse(
            auth_type=integration.connection_config.auth_type,
            authorization_url=integration.connection_config.authorization_url,
            token_url=integration.connection_config.token_url,
            scopes=integration.connection_config.scopes,
            api_key_header_name=integration.connection_config.api_key_header_name,
        )

    return AvailableIntegrationResponse(
        id=integration.id,
        name=integration.name,
        type=integration.type,
        description=integration.description,
        supported_entities=integration.supported_entities,
        connection_config=connection_config,
        is_active=integration.is_active,
    )


@router.post(
    "/integrations/available",
    response_model=AvailableIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an available integration",
)
async def admin_create_available_integration(
    request: CreateAvailableIntegrationRequest,
    repo: IntegrationRepositoryInterface = Depends(get_integration_repository),
) -> AvailableIntegrationResponse:
    """Create a new integration in the catalog (admin use only)."""
    now = datetime.now(UTC)
    connection_config = (
        ConnectionConfig(**request.connection_config) if request.connection_config else None
    )

    integration = AvailableIntegration(
        id=uuid4(),
        name=request.name,
        type=request.type,
        description=request.description,
        connection_config=connection_config,
        supported_entities=request.supported_entities,
        is_active=request.is_active,
        created_at=now,
        updated_at=now,
    )

    try:
        created = await repo.create_available_integration(integration)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None

    logger.info("Admin created available integration", integration_name=created.name)
    return _to_available_integration_response(created)


@router.get(
    "/integrations/available",
    response_model=AvailableIntegrationsResponse,
    summary="List all available integrations (admin)",
)
async def admin_list_available_integrations(
    include_inactive: bool = True,
    repo: IntegrationRepositoryInterface = Depends(get_integration_repository),
) -> AvailableIntegrationsResponse:
    """List all available integrations including inactive ones (admin use only)."""
    integrations = await repo.get_available_integrations(active_only=not include_inactive)
    return AvailableIntegrationsResponse(
        integrations=[_to_available_integration_response(i) for i in integrations]
    )


@router.get(
    "/integrations/available/{integration_id}",
    response_model=AvailableIntegrationResponse,
    summary="Get an available integration (admin)",
)
async def admin_get_available_integration(
    integration_id: UUID,
    repo: IntegrationRepositoryInterface = Depends(get_integration_repository),
) -> AvailableIntegrationResponse:
    """Get a specific available integration by ID, including inactive ones (admin use only)."""
    integration = await repo.get_available_integration(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        )
    return _to_available_integration_response(integration)


@router.put(
    "/integrations/available/{integration_id}",
    response_model=AvailableIntegrationResponse,
    summary="Update an available integration (admin)",
)
async def admin_update_available_integration(
    integration_id: UUID,
    request: UpdateAvailableIntegrationRequest,
    repo: IntegrationRepositoryInterface = Depends(get_integration_repository),
) -> AvailableIntegrationResponse:
    """Update an available integration. Setting is_active=false is the soft-delete mechanism."""
    existing = await repo.get_available_integration(integration_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        )

    # Apply partial update: only update fields that were provided
    updated = AvailableIntegration(
        id=existing.id,
        name=request.name if request.name is not None else existing.name,
        type=request.type if request.type is not None else existing.type,
        description=(
            request.description if request.description is not None else existing.description
        ),
        connection_config=(
            ConnectionConfig(**request.connection_config)
            if request.connection_config is not None
            else existing.connection_config
        ),
        supported_entities=(
            request.supported_entities
            if request.supported_entities is not None
            else existing.supported_entities
        ),
        is_active=request.is_active if request.is_active is not None else existing.is_active,
        created_at=existing.created_at,
        updated_at=datetime.now(UTC),
        created_by=existing.created_by,
        updated_by=existing.updated_by,
    )

    try:
        result = await repo.update_available_integration(updated)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None

    logger.info("Admin updated available integration", integration_id=str(integration_id))
    return _to_available_integration_response(result)
