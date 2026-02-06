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
        updated = await self._repo.upsert_user_settings(client_id, integration_id, settings)

        logger.info(
            "User settings updated",
            extra={
                "client_id": str(client_id),
                "integration_id": str(integration_id),
                "enabled_rules": sum(1 for r in settings.sync_rules if r.enabled),
                "auto_sync": settings.auto_sync_enabled,
            },
        )

        # Refresh scheduler if settings affect scheduling (auto_sync or sync_frequency)
        await self._refresh_scheduler_if_enabled()

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

    async def update_system_settings(
        self,
        integration_id: UUID,
        settings: UserIntegrationSettings,
    ) -> UserIntegrationSettings:
        """
        Update system default settings for an integration.

        Args:
            integration_id: The integration ID.
            settings: The new default settings.

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
        updated = await self._repo.upsert_system_settings(integration_id, settings)

        logger.info(
            "System default settings updated",
            extra={
                "integration_id": str(integration_id),
                "enabled_rules": sum(1 for r in settings.sync_rules if r.enabled),
                "auto_sync": settings.auto_sync_enabled,
            },
        )

        return updated

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

    async def _refresh_scheduler_if_enabled(self) -> None:
        """Refresh the scheduler if it's enabled."""
        try:
            from app.core.dependency_injection import get_container

            container = get_container()
            if container.feature_flag_service.is_scheduler_enabled():
                await container.scheduler.refresh_schedules()
        except Exception as e:
            # Log but don't fail the settings update
            logger.warning(
                "Failed to refresh scheduler after settings update",
                extra={"error": str(e)},
            )

    def _validate_cron_expression(self, cron_expr: str) -> None:
        """
        Validate a cron expression (5-part standard format).

        Validates minute, hour, day-of-month, month, day-of-week fields.
        Supports: numbers, *, ranges (1-5), steps (*/5, 1-10/2), lists (1,3,5),
        month names (jan-dec), day names (sun-sat).
        """
        parts = cron_expr.split()
        if len(parts) != 5:
            raise ValidationError(
                f"Invalid cron expression: expected 5 parts, got {len(parts)}",
                field="sync_frequency",
            )

        field_names = ["minute", "hour", "day of month", "month", "day of week"]
        for i, part in enumerate(parts):
            if not self._is_valid_cron_part(part, i):
                raise ValidationError(
                    f"Invalid cron expression: invalid {field_names[i]} value '{part}'",
                    field="sync_frequency",
                )

    def _is_valid_cron_part(self, part: str, field_index: int) -> bool:
        """
        Validate a single cron field.

        Args:
            part: The cron field value (e.g., "5", "*/10", "1-5", "jan")
            field_index: 0=minute, 1=hour, 2=day-of-month, 3=month, 4=day-of-week

        Returns:
            True if valid, False otherwise.
        """
        # Field ranges: (min, max)
        ranges = [
            (0, 59),  # minute
            (0, 23),  # hour
            (1, 31),  # day of month
            (1, 12),  # month
            (0, 7),  # day of week (0 and 7 both = Sunday)
        ]
        min_val, max_val = ranges[field_index]

        # Month and day names
        month_names = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        day_names = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}

        def parse_value(val: str) -> int | None:
            """Parse a single value (number or name) to integer."""
            val = val.lower()
            if val.isdigit():
                return int(val)
            if field_index == 3 and val in month_names:
                return month_names[val]
            if field_index == 4 and val in day_names:
                return day_names[val]
            return None

        def is_valid_value(val: int) -> bool:
            """Check if value is in valid range for this field."""
            return min_val <= val <= max_val

        # Handle list (e.g., "1,3,5")
        if "," in part:
            return all(self._is_valid_cron_part(p.strip(), field_index) for p in part.split(","))

        # Handle step (e.g., "*/5" or "1-10/2")
        if "/" in part:
            base, step = part.split("/", 1)
            if not step.isdigit() or int(step) == 0:
                return False
            step_val = int(step)
            # Validate step doesn't exceed field range
            if step_val > max_val:
                return False
            # Validate base (can be * or a range)
            if base == "*":
                return True
            return self._is_valid_cron_part(base, field_index)

        # Handle range (e.g., "1-5")
        if "-" in part:
            parts = part.split("-")
            if len(parts) != 2:
                return False
            start = parse_value(parts[0])
            end = parse_value(parts[1])
            if start is None or end is None:
                return False
            if not is_valid_value(start) or not is_valid_value(end):
                return False
            # Range start must be <= end
            if start > end:
                return False
            return True

        # Handle wildcard
        if part == "*":
            return True

        # Handle single value
        val = parse_value(part)
        if val is not None:
            return is_valid_value(val)

        return False
