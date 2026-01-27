"""Settings management service."""

from uuid import UUID

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.domain.entities import SyncRule, UserIntegrationSettings
from app.domain.enums import SyncDirection
from app.domain.interfaces import IntegrationRepositoryInterface

logger = get_logger(__name__)


class SettingsService:
    """Service for managing integration settings."""

    def __init__(
        self,
        integration_repo: IntegrationRepositoryInterface,
    ) -> None:
        """
        Initialize settings service.

        Args:
            integration_repo: Repository for integration data access.
        """
        self._repo = integration_repo

    async def get_user_settings(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> UserIntegrationSettings:
        """
        Get user settings for an integration, falling back to system defaults.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.

        Returns:
            User settings, or system defaults if no user settings exist.
        """
        # Verify integration exists
        integration = await self._repo.get_available_integration(integration_id)
        if not integration:
            raise NotFoundError("Integration", integration_id)

        # Try to get user settings
        user_settings = await self._repo.get_user_settings(client_id, integration_id)
        if user_settings:
            return user_settings

        # Fall back to system defaults
        system_settings = await self._repo.get_system_settings(integration_id)
        if system_settings:
            return system_settings

        # Return empty settings with all supported entities as inbound
        return UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type=entity,
                    direction=SyncDirection.INBOUND,
                    enabled=False,
                )
                for entity in integration.supported_entities
            ],
            sync_frequency=None,
            auto_sync_enabled=False,
        )

    async def update_user_settings(
        self,
        client_id: UUID,
        integration_id: UUID,
        settings: UserIntegrationSettings,
        user_id: str | None = None,
    ) -> UserIntegrationSettings:
        """
        Update user settings for an integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.
            settings: The new settings.
            user_id: Optional user ID for audit.

        Returns:
            The updated settings.
        """
        # Verify integration exists
        integration = await self._repo.get_available_integration(integration_id)
        if not integration:
            raise NotFoundError("Integration", integration_id)

        # Validate entity types
        supported_entities = set(integration.supported_entities)
        for rule in settings.sync_rules:
            if rule.entity_type not in supported_entities:
                raise ValidationError(
                    f"Entity type '{rule.entity_type}' is not supported by {integration.name}. "
                    f"Supported: {', '.join(supported_entities)}",
                    field="sync_rules.entity_type",
                )

        # Validate cron expression if provided
        if settings.sync_frequency:
            self._validate_cron_expression(settings.sync_frequency)

        # Save settings
        updated = await self._repo.upsert_user_settings(
            client_id, integration_id, settings
        )

        logger.info(
            "User settings updated",
            extra={
                "client_id": str(client_id),
                "integration_id": str(integration_id),
                "enabled_rules": sum(1 for r in settings.sync_rules if r.enabled),
                "auto_sync": settings.auto_sync_enabled,
            },
        )

        return updated

    async def get_system_settings(
        self,
        integration_id: UUID,
    ) -> UserIntegrationSettings | None:
        """
        Get system default settings for an integration.

        Args:
            integration_id: The integration ID.

        Returns:
            System settings if configured, None otherwise.
        """
        # Verify integration exists
        integration = await self._repo.get_available_integration(integration_id)
        if not integration:
            raise NotFoundError("Integration", integration_id)

        return await self._repo.get_system_settings(integration_id)

    async def get_enabled_sync_rules(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> list[SyncRule]:
        """
        Get enabled sync rules for a user's integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.

        Returns:
            List of enabled sync rules.
        """
        settings = await self.get_user_settings(client_id, integration_id)
        return [rule for rule in settings.sync_rules if rule.enabled]

    async def is_auto_sync_enabled(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> bool:
        """
        Check if auto-sync is enabled for a user's integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.

        Returns:
            True if auto-sync is enabled.
        """
        settings = await self.get_user_settings(client_id, integration_id)
        return settings.auto_sync_enabled

    def _validate_cron_expression(self, cron_expr: str) -> None:
        """Validate a cron expression."""
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValidationError(
                f"Invalid cron expression: expected 5 parts, got {len(parts)}",
                field="sync_frequency",
            )

        # Basic validation - could use croniter for more thorough validation
        for i, part in enumerate(parts):
            if not self._is_valid_cron_part(part, i):
                field_names = ["minute", "hour", "day of month", "month", "day of week"]
                raise ValidationError(
                    f"Invalid cron expression: invalid {field_names[i]} value '{part}'",
                    field="sync_frequency",
                )

    def _is_valid_cron_part(self, part: str, field_index: int) -> bool:
        """Validate a single cron field."""
        if part == "*":
            return True

        # Handle ranges, lists, and steps
        for char in ",/-":
            if char in part:
                subparts = part.replace(",", " ").replace("-", " ").replace("/", " ").split()
                for subpart in subparts:
                    if subpart != "*" and not subpart.isdigit():
                        return False
                return True

        # Simple number
        if part.isdigit():
            value = int(part)
            ranges = [
                (0, 59),  # minute
                (0, 23),  # hour
                (1, 31),  # day of month
                (1, 12),  # month
                (0, 7),  # day of week (0 and 7 both = Sunday)
            ]
            min_val, max_val = ranges[field_index]
            return min_val <= value <= max_val

        return False
