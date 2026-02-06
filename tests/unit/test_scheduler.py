"""Unit tests for the sync scheduler."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities import SyncJob, SyncRule, UserIntegration, UserIntegrationSettings
from app.domain.enums import (
    IntegrationStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.infrastructure.scheduling.scheduler import SyncScheduler
from tests.mocks import MockIntegrationRepository
from tests.mocks.feature_flags import MockFeatureFlagService


@pytest.fixture
def integration_repo() -> MockIntegrationRepository:
    """Create a mock integration repository."""
    return MockIntegrationRepository()


@pytest.fixture
def feature_flags() -> MockFeatureFlagService:
    """Create a mock feature flag service."""
    return MockFeatureFlagService()


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    """Create a mock sync orchestrator."""
    orchestrator = MagicMock()
    orchestrator.trigger_sync = AsyncMock()
    return orchestrator


@pytest.fixture
def scheduler(
    integration_repo: MockIntegrationRepository,
    mock_orchestrator: MagicMock,
    feature_flags: MockFeatureFlagService,
) -> SyncScheduler:
    """Create a scheduler instance."""
    return SyncScheduler(
        integration_repo=integration_repo,
        sync_orchestrator=mock_orchestrator,
        feature_flags=feature_flags,
        timezone="UTC",
    )


class TestSyncSchedulerStart:
    """Tests for SyncScheduler.start()."""

    @pytest.mark.asyncio
    async def test_start_loads_integrations_and_schedules_jobs(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that start() loads integrations and schedules cron jobs."""
        # Setup: Create an integration with auto_sync enabled
        client_id = uuid4()
        integration = integration_repo.seed_available_integration("Test Integration")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration)

        settings = UserIntegrationSettings(
            sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
            sync_frequency="0 * * * *",  # Every hour
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Act
        await scheduler.start()

        # Assert: Scheduler is running
        assert scheduler._started is True
        assert scheduler._scheduler is not None

        # Cleanup
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_skips_when_scheduler_disabled(
        self,
        scheduler: SyncScheduler,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that start() does nothing when scheduler is disabled."""
        feature_flags.scheduler_enabled = False

        await scheduler.start()

        assert scheduler._started is False
        assert scheduler._scheduler is None

    @pytest.mark.asyncio
    async def test_start_skips_revoked_integrations(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that revoked integrations are not scheduled."""
        client_id = uuid4()
        integration = integration_repo.seed_available_integration("Test Integration")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.REVOKED,  # Revoked (not connected)
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration)

        settings = UserIntegrationSettings(
            sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
            sync_frequency="0 * * * *",
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        await scheduler.start()

        # Scheduler started but no jobs scheduled for revoked integration
        assert scheduler._started is True
        # Check no jobs were added (scheduler has no jobs)
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_skips_integrations_without_auto_sync(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that integrations with auto_sync_enabled=False are not scheduled."""
        client_id = uuid4()
        integration = integration_repo.seed_available_integration("Test Integration")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration)

        settings = UserIntegrationSettings(
            sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
            sync_frequency="0 * * * *",
            auto_sync_enabled=False,  # Disabled
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        await scheduler.start()

        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_warns_on_already_started(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that calling start() twice logs a warning."""
        await scheduler.start()
        assert scheduler._started is True

        # Call start again - should not error
        await scheduler.start()
        assert scheduler._started is True

        await scheduler.stop()


class TestSyncSchedulerStop:
    """Tests for SyncScheduler.stop()."""

    @pytest.mark.asyncio
    async def test_stop_shuts_down_gracefully(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that stop() shuts down the scheduler gracefully."""
        await scheduler.start()
        assert scheduler._started is True

        await scheduler.stop()

        assert scheduler._started is False
        assert scheduler._scheduler is None

    @pytest.mark.asyncio
    async def test_stop_does_nothing_when_not_started(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that stop() is safe to call when scheduler not started."""
        assert scheduler._started is False

        # Should not raise
        await scheduler.stop()

        assert scheduler._started is False


class TestSyncSchedulerRefresh:
    """Tests for SyncScheduler.refresh_schedules()."""

    @pytest.mark.asyncio
    async def test_refresh_clears_and_reloads_jobs(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that refresh_schedules() clears existing jobs and reloads."""
        # Setup: Create an integration
        client_id = uuid4()
        integration = integration_repo.seed_available_integration("Test Integration")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration)

        settings = UserIntegrationSettings(
            sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
            sync_frequency="0 * * * *",
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        await scheduler.start()

        # Verify job is scheduled
        jobs_before = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs_before) == 1

        # Change settings to disable auto_sync
        settings.auto_sync_enabled = False
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Refresh
        await scheduler.refresh_schedules()

        # Verify job is removed
        jobs_after = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs_after) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_refresh_does_nothing_when_not_started(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that refresh_schedules() is safe when scheduler not started."""
        assert scheduler._started is False

        # Should not raise
        await scheduler.refresh_schedules()


class TestSyncSchedulerTriggerSync:
    """Tests for the _trigger_sync callback."""

    @pytest.mark.asyncio
    async def test_trigger_sync_calls_orchestrator(
        self,
        scheduler: SyncScheduler,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Test that _trigger_sync() calls the orchestrator with correct params."""
        client_id = uuid4()
        integration_id = uuid4()

        # Setup mock return value
        now = datetime.now(UTC)
        mock_job = SyncJob(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.SCHEDULER,
            created_at=now,
            updated_at=now,
        )
        mock_orchestrator.trigger_sync.return_value = mock_job

        # Call _trigger_sync directly
        await scheduler._trigger_sync(client_id, integration_id)

        # Verify orchestrator was called
        mock_orchestrator.trigger_sync.assert_called_once_with(
            client_id=client_id,
            integration_id=integration_id,
            job_type=SyncJobType.INCREMENTAL,
            triggered_by=SyncJobTrigger.SCHEDULER,
        )

    @pytest.mark.asyncio
    async def test_trigger_sync_handles_errors_gracefully(
        self,
        scheduler: SyncScheduler,
        mock_orchestrator: MagicMock,
    ) -> None:
        """Test that _trigger_sync() logs errors but doesn't crash."""
        client_id = uuid4()
        integration_id = uuid4()

        # Setup mock to raise exception
        mock_orchestrator.trigger_sync.side_effect = Exception("Database error")

        # Should not raise
        await scheduler._trigger_sync(client_id, integration_id)

        # Verify orchestrator was called
        mock_orchestrator.trigger_sync.assert_called_once()


class TestSyncSchedulerInvalidCron:
    """Tests for handling invalid cron expressions."""

    @pytest.mark.asyncio
    async def test_invalid_cron_expression_is_skipped(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that invalid cron expressions are logged and skipped."""
        client_id = uuid4()
        integration = integration_repo.seed_available_integration("Test Integration")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration)

        # Invalid cron expression
        settings = UserIntegrationSettings(
            sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
            sync_frequency="invalid cron",
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Should start without error
        await scheduler.start()

        # No jobs should be scheduled due to invalid cron
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_integration_returns_false_for_invalid_cron(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that _schedule_integration returns False for invalid cron."""
        await scheduler.start()

        result = await scheduler._schedule_integration(
            client_id=uuid4(),
            integration_id=uuid4(),
            cron_expr="not a valid cron expression",
        )

        assert result is False

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_schedule_integration_returns_true_for_valid_cron(
        self,
        scheduler: SyncScheduler,
    ) -> None:
        """Test that _schedule_integration returns True for valid cron."""
        await scheduler.start()

        result = await scheduler._schedule_integration(
            client_id=uuid4(),
            integration_id=uuid4(),
            cron_expr="0 * * * *",  # Every hour
        )

        assert result is True

        await scheduler.stop()


class TestSyncSchedulerFeatureFlag:
    """Tests for scheduler feature flag integration."""

    @pytest.mark.asyncio
    async def test_respects_scheduler_enabled_flag(
        self,
        integration_repo: MockIntegrationRepository,
        mock_orchestrator: MagicMock,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that scheduler respects is_scheduler_enabled() flag."""
        # Disable scheduler
        feature_flags.scheduler_enabled = False

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        # Scheduler should not have started
        assert scheduler._started is False
        assert scheduler._scheduler is None


class TestSyncSchedulerMultipleIntegrations:
    """Tests for scheduling multiple integrations."""

    @pytest.mark.asyncio
    async def test_schedules_multiple_integrations(
        self,
        scheduler: SyncScheduler,
        integration_repo: MockIntegrationRepository,
    ) -> None:
        """Test that multiple integrations are scheduled correctly."""
        client_id = uuid4()

        # Create two integrations
        integration1 = integration_repo.seed_available_integration("Integration 1")
        integration2 = integration_repo.seed_available_integration("Integration 2")

        now = datetime.now(UTC)

        for integration in [integration1, integration2]:
            user_integration = UserIntegration(
                id=uuid4(),
                client_id=client_id,
                integration_id=integration.id,
                status=IntegrationStatus.CONNECTED,
                created_at=now,
                updated_at=now,
            )
            await integration_repo.create_user_integration(user_integration)

            settings = UserIntegrationSettings(
                sync_rules=[SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND)],
                sync_frequency="0 * * * *",
                auto_sync_enabled=True,
            )
            await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        await scheduler.start()

        # Both integrations should be scheduled
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 2

        await scheduler.stop()
