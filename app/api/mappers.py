"""Shared DTO mappers for API routers."""

from app.api.dto import (
    AvailableIntegrationResponse,
    ConnectionConfigResponse,
    UserIntegrationResponse,
)
from app.domain.entities import AvailableIntegration, UserIntegration


def to_available_integration_response(
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


def to_user_integration_response(
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
