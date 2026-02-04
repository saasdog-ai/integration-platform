"""Settings management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dto import (
    SyncRuleResponse,
    UserSettingsRequest,
    UserSettingsResponse,
)
from app.auth import get_client_id
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.entities import SyncRule, UserIntegrationSettings
from app.services.settings_service import SettingsService

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations/{integration_id}/settings", tags=["settings"])


def get_settings_service() -> SettingsService:
    """Dependency to get settings service."""
    from app.core.dependency_injection import get_container

    container = get_container()
    return SettingsService(
        integration_repo=container.integration_repository,
    )


def _to_settings_response(settings: UserIntegrationSettings) -> UserSettingsResponse:
    """Convert domain entity to response DTO."""
    return UserSettingsResponse(
        sync_rules=[
            SyncRuleResponse(
                entity_type=rule.entity_type,
                direction=rule.direction,
                enabled=rule.enabled,
                master_if_conflict=rule.master_if_conflict,
                field_mappings=rule.field_mappings,
                change_source=rule.change_source,
                sync_trigger=rule.sync_trigger,
            )
            for rule in settings.sync_rules
        ],
        sync_frequency=settings.sync_frequency,
        auto_sync_enabled=settings.auto_sync_enabled,
    )


def _from_settings_request(request: UserSettingsRequest) -> UserIntegrationSettings:
    """Convert request DTO to domain entity."""
    return UserIntegrationSettings(
        sync_rules=[
            SyncRule(
                entity_type=rule.entity_type,
                direction=rule.direction,
                enabled=rule.enabled,
                master_if_conflict=rule.master_if_conflict,
                field_mappings=rule.field_mappings,
                change_source=rule.change_source,
                sync_trigger=rule.sync_trigger,
            )
            for rule in request.sync_rules
        ],
        sync_frequency=request.sync_frequency,
        auto_sync_enabled=request.auto_sync_enabled,
    )


@router.get(
    "",
    response_model=UserSettingsResponse,
    summary="Get integration settings",
)
async def get_settings(
    integration_id: UUID,
    client_id: UUID = Depends(get_client_id),
    service: SettingsService = Depends(get_settings_service),
) -> UserSettingsResponse:
    """Get user's integration settings."""
    try:
        settings = await service.get_user_settings(client_id, integration_id)
        return _to_settings_response(settings)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None


@router.put(
    "",
    response_model=UserSettingsResponse,
    summary="Update integration settings",
)
async def update_settings(
    integration_id: UUID,
    request: UserSettingsRequest,
    client_id: UUID = Depends(get_client_id),
    service: SettingsService = Depends(get_settings_service),
) -> UserSettingsResponse:
    """Update user's integration settings."""
    try:
        settings = _from_settings_request(request)
        updated = await service.update_user_settings(client_id, integration_id, settings)
        return _to_settings_response(updated)
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


@router.get(
    "/defaults",
    response_model=UserSettingsResponse,
    summary="Get default integration settings",
)
async def get_default_settings(
    integration_id: UUID,
    service: SettingsService = Depends(get_settings_service),
) -> UserSettingsResponse:
    """Get system default settings for an integration."""
    try:
        settings = await service.get_system_settings(integration_id)
        if settings:
            return _to_settings_response(settings)

        # Return empty settings if no defaults configured
        return UserSettingsResponse(
            sync_rules=[],
            sync_frequency=None,
            auto_sync_enabled=False,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration not found: {integration_id}",
        ) from None


@router.put(
    "/defaults",
    response_model=UserSettingsResponse,
    summary="Update default integration settings",
)
async def update_default_settings(
    integration_id: UUID,
    request: UserSettingsRequest,
    service: SettingsService = Depends(get_settings_service),
) -> UserSettingsResponse:
    """Update system default settings for an integration."""
    try:
        settings = _from_settings_request(request)
        updated = await service.update_system_settings(integration_id, settings)
        return _to_settings_response(updated)
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
