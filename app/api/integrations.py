"""Integration management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dto import (
    AvailableIntegrationResponse,
    AvailableIntegrationsResponse,
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    OAuthCallbackRequest,
    OAuthConfigResponse,
    UserIntegrationResponse,
    UserIntegrationsResponse,
)
from app.auth import get_client_id
from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.domain.entities import AvailableIntegration, UserIntegration
from app.services.integration_service import IntegrationService

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


def _to_available_integration_response(
    integration: AvailableIntegration,
) -> AvailableIntegrationResponse:
    """Convert domain entity to response DTO."""
    oauth_config = None
    if integration.oauth_config:
        oauth_config = OAuthConfigResponse(
            authorization_url=integration.oauth_config.authorization_url,
            token_url=integration.oauth_config.token_url,
            scopes=integration.oauth_config.scopes,
        )

    return AvailableIntegrationResponse(
        id=integration.id,
        name=integration.name,
        type=integration.type,
        description=integration.description,
        supported_entities=integration.supported_entities,
        oauth_config=oauth_config,
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
        integration_name=user_integration.integration.name
        if user_integration.integration
        else None,
        integration_type=user_integration.integration.type
        if user_integration.integration
        else None,
        status=user_integration.status,
        external_account_id=user_integration.external_account_id,
        last_connected_at=user_integration.last_connected_at,
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
        )


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
        )


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
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


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
        )
        return _to_user_integration_response(user_integration)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        )
    except IntegrationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )


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
        )
