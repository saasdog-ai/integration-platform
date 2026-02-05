"""Integration management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dto import (
    AvailableIntegrationResponse,
    AvailableIntegrationsResponse,
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    ConnectionConfigResponse,
    EntitySyncStatusItem,
    EntitySyncStatusListResponse,
    EntitySyncStatusResponse,
    NotifyChangeRequest,
    NotifyChangeResponse,
    OAuthCallbackRequest,
    ResetLastSyncTimeRequest,
    UserIntegrationResponse,
    UserIntegrationsResponse,
    WebhookReceiveResponse,
)
from app.auth import get_client_id
from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    SyncError,
    ValidationError,
)
from app.core.logging import get_logger
from app.domain.entities import AvailableIntegration, ChangeEvent, UserIntegration
from app.domain.enums import ChangeSourceType
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
            realm_id=request.realm_id,
        )
        return _to_user_integration_response(user_integration)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None
    except IntegrationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
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
