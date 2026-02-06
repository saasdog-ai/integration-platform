"""Sync job scheduler implementation using APScheduler."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import get_logger
from app.domain.enums import IntegrationStatus, SyncJobTrigger, SyncJobType
from app.domain.interfaces import (
    FeatureFlagServiceInterface,
    IntegrationRepositoryInterface,
    SyncSchedulerInterface,
)

if TYPE_CHECKING:
    from app.services.sync_orchestrator import SyncOrchestrator

logger = get_logger(__name__)


class SyncScheduler(SyncSchedulerInterface):
    """APScheduler-based sync job scheduler.

    Reads user integration settings and triggers sync jobs based on
    configured cron expressions (sync_frequency) when auto_sync_enabled=True.
    """

    def __init__(
        self,
        integration_repo: IntegrationRepositoryInterface,
        sync_orchestrator: SyncOrchestrator,
        feature_flags: FeatureFlagServiceInterface,
        timezone: str = "UTC",
    ) -> None:
        """
        Initialize the sync scheduler.

        Args:
            integration_repo: Repository for accessing integration data.
            sync_orchestrator: Orchestrator for triggering sync jobs.
            feature_flags: Feature flag service to check if scheduler is enabled.
            timezone: Timezone for cron expressions (default: UTC).
        """
        self._integration_repo = integration_repo
        self._sync_orchestrator = sync_orchestrator
        self._feature_flags = feature_flags
        self._timezone = timezone
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    async def start(self) -> None:
        """Start the scheduler and load all scheduled integrations."""
        if self._started:
            logger.warning("Scheduler already started")
            return

        if not self._feature_flags.is_scheduler_enabled():
            logger.info("Scheduler is disabled via feature flag")
            return

        self._scheduler = AsyncIOScheduler(timezone=self._timezone)
        self._scheduler.start()
        self._started = True

        logger.info("Scheduler started", extra={"timezone": self._timezone})

        # Load and schedule all integrations with auto_sync_enabled
        await self._load_schedules()

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._started or self._scheduler is None:
            return

        logger.info("Stopping scheduler...")
        self._scheduler.shutdown(wait=True)
        self._scheduler = None
        self._started = False
        logger.info("Scheduler stopped")

    async def refresh_schedules(self) -> None:
        """Reload all schedules from the database."""
        if not self._started or self._scheduler is None:
            logger.debug("Scheduler not running, skipping refresh")
            return

        logger.info("Refreshing schedules...")

        # Remove all existing jobs
        self._scheduler.remove_all_jobs()

        # Reload schedules
        await self._load_schedules()

        logger.info("Schedules refreshed")

    async def _load_schedules(self) -> None:
        """Load all integrations with auto_sync_enabled and schedule them."""
        if self._scheduler is None:
            return

        try:
            # Get all user integrations
            all_integrations = await self._integration_repo.get_all_user_integrations()

            scheduled_count = 0
            skipped_count = 0

            for user_integration in all_integrations:
                # Skip disconnected integrations
                if user_integration.status != IntegrationStatus.CONNECTED:
                    continue

                # Get settings for this integration
                settings = await self._integration_repo.get_user_settings(
                    user_integration.client_id,
                    user_integration.integration_id,
                )

                if not settings:
                    continue

                # Check if auto_sync is enabled and has a cron expression
                if not settings.auto_sync_enabled or not settings.sync_frequency:
                    continue

                # Schedule the integration
                success = await self._schedule_integration(
                    client_id=user_integration.client_id,
                    integration_id=user_integration.integration_id,
                    cron_expr=settings.sync_frequency,
                )

                if success:
                    scheduled_count += 1
                else:
                    skipped_count += 1

            logger.info(
                "Schedules loaded",
                extra={
                    "scheduled": scheduled_count,
                    "skipped": skipped_count,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to load schedules",
                extra={"error": str(e)},
                exc_info=True,
            )

    async def _schedule_integration(
        self,
        client_id: UUID,
        integration_id: UUID,
        cron_expr: str,
    ) -> bool:
        """
        Schedule a single integration for automated sync.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.
            cron_expr: The cron expression for scheduling.

        Returns:
            True if scheduled successfully, False otherwise.
        """
        if self._scheduler is None:
            return False

        job_id = f"{client_id}:{integration_id}"

        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone=self._timezone)

            self._scheduler.add_job(
                self._trigger_sync,
                trigger,
                id=job_id,
                args=[client_id, integration_id],
                replace_existing=True,
            )

            logger.debug(
                "Integration scheduled",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "cron_expr": cron_expr,
                },
            )
            return True

        except ValueError as e:
            # Invalid cron expression - log warning and skip
            logger.warning(
                "Invalid cron expression, skipping schedule",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "cron_expr": cron_expr,
                    "error": str(e),
                },
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to schedule integration",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "cron_expr": cron_expr,
                    "error": str(e),
                },
            )
            return False

    async def _trigger_sync(self, client_id: UUID, integration_id: UUID) -> None:
        """
        Trigger a sync job for an integration.

        Called by APScheduler when the cron trigger fires.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.
        """
        logger.info(
            "Scheduler triggering sync",
            extra={
                "client_id": str(client_id),
                "integration_id": str(integration_id),
            },
        )

        try:
            job = await self._sync_orchestrator.trigger_sync(
                client_id=client_id,
                integration_id=integration_id,
                job_type=SyncJobType.INCREMENTAL,
                triggered_by=SyncJobTrigger.SCHEDULER,
            )

            logger.info(
                "Scheduler triggered sync job",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "job_id": str(job.id),
                },
            )

        except Exception as e:
            # Log but don't crash - scheduler should continue running
            logger.error(
                "Scheduler failed to trigger sync",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "error": str(e),
                },
            )
