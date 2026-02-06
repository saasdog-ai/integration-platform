"""End-to-end integration tests for the sync scheduler."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.entities import (
    SyncJob,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    IntegrationStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
)
from app.infrastructure.scheduling.scheduler import SyncScheduler
from tests.mocks import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)
from tests.mocks.feature_flags import MockFeatureFlagService


@pytest.fixture
def integration_repo() -> MockIntegrationRepository:
    """Create a mock integration repository."""
    return MockIntegrationRepository()


@pytest.fixture
def job_repo() -> MockSyncJobRepository:
    """Create a mock job repository."""
    return MockSyncJobRepository()


@pytest.fixture
def state_repo() -> MockIntegrationStateRepository:
    """Create a mock state repository."""
    return MockIntegrationStateRepository()


@pytest.fixture
def feature_flags() -> MockFeatureFlagService:
    """Create a mock feature flag service."""
    return MockFeatureFlagService()


class TestSchedulerE2E:
    """End-to-end tests for the scheduler triggering sync jobs."""

    @pytest.mark.asyncio
    async def test_scheduler_triggers_sync_with_scheduler_trigger_type(
        self,
        integration_repo: MockIntegrationRepository,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """
        E2E test that verifies:
        1. Integration with auto_sync_enabled=True is scheduled
        2. When triggered, creates a sync job with triggered_by=SCHEDULER
        """
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
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="* * * * *",  # Every minute for testing
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Create mock orchestrator that records calls
        triggered_jobs: list[dict] = []

        async def mock_trigger_sync(**kwargs):
            job = SyncJob(
                id=uuid4(),
                client_id=kwargs["client_id"],
                integration_id=kwargs["integration_id"],
                job_type=kwargs["job_type"],
                status=SyncJobStatus.PENDING,
                triggered_by=kwargs["triggered_by"],
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            triggered_jobs.append(
                {
                    "client_id": kwargs["client_id"],
                    "integration_id": kwargs["integration_id"],
                    "triggered_by": kwargs["triggered_by"],
                }
            )
            return job

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_sync = AsyncMock(side_effect=mock_trigger_sync)

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        # Verify job is scheduled
        assert scheduler._started is True
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 1

        # Manually trigger the job to test the callback
        await scheduler._trigger_sync(client_id, integration.id)

        # Verify the orchestrator was called with SCHEDULER trigger
        assert len(triggered_jobs) == 1
        assert triggered_jobs[0]["client_id"] == client_id
        assert triggered_jobs[0]["integration_id"] == integration.id
        assert triggered_jobs[0]["triggered_by"] == SyncJobTrigger.SCHEDULER

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_handles_multiple_clients(
        self,
        integration_repo: MockIntegrationRepository,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that scheduler correctly handles multiple clients with different integrations."""
        client1_id = uuid4()
        client2_id = uuid4()

        integration = integration_repo.seed_available_integration("Shared Integration")
        now = datetime.now(UTC)

        # Client 1 - auto sync enabled
        user_integration1 = UserIntegration(
            id=uuid4(),
            client_id=client1_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration1)

        settings1 = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="0 * * * *",  # Every hour
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client1_id, integration.id, settings1)

        # Client 2 - auto sync disabled
        user_integration2 = UserIntegration(
            id=uuid4(),
            client_id=client2_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )
        await integration_repo.create_user_integration(user_integration2)

        settings2 = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="0 * * * *",
            auto_sync_enabled=False,  # Disabled for client 2
        )
        await integration_repo.upsert_user_settings(client2_id, integration.id, settings2)

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_sync = AsyncMock()

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        # Only client 1 should be scheduled
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 1

        # Verify the job ID contains client1's info
        job_id = jobs[0].id
        assert str(client1_id) in job_id

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_refresh_picks_up_new_schedules(
        self,
        integration_repo: MockIntegrationRepository,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that refresh_schedules picks up newly enabled auto_sync."""
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

        # Start with auto_sync disabled
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="0 * * * *",
            auto_sync_enabled=False,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_sync = AsyncMock()

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        # No jobs scheduled initially
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 0

        # Enable auto_sync
        settings.auto_sync_enabled = True
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Refresh schedules
        await scheduler.refresh_schedules()

        # Now job should be scheduled
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 1

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_removes_jobs_when_auto_sync_disabled(
        self,
        integration_repo: MockIntegrationRepository,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that disabling auto_sync removes the scheduled job on refresh."""
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

        # Start with auto_sync enabled
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="0 * * * *",
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_sync = AsyncMock()

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        # Job is scheduled
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 1

        # Disable auto_sync
        settings.auto_sync_enabled = False
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Refresh schedules
        await scheduler.refresh_schedules()

        # Job should be removed
        jobs = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs) == 0

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_updates_cron_expression_on_refresh(
        self,
        integration_repo: MockIntegrationRepository,
        feature_flags: MockFeatureFlagService,
    ) -> None:
        """Test that changing cron expression is picked up on refresh."""
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

        # Start with hourly sync
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True)
            ],
            sync_frequency="0 * * * *",  # Hourly
            auto_sync_enabled=True,
        )
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        mock_orchestrator = MagicMock()
        mock_orchestrator.trigger_sync = AsyncMock()

        scheduler = SyncScheduler(
            integration_repo=integration_repo,
            sync_orchestrator=mock_orchestrator,
            feature_flags=feature_flags,
            timezone="UTC",
        )

        await scheduler.start()

        jobs_before = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs_before) == 1

        # Change to every 15 minutes
        settings.sync_frequency = "*/15 * * * *"
        await integration_repo.upsert_user_settings(client_id, integration.id, settings)

        # Refresh schedules
        await scheduler.refresh_schedules()

        # Job should still be scheduled (replace_existing=True)
        jobs_after = scheduler._scheduler.get_jobs() if scheduler._scheduler else []
        assert len(jobs_after) == 1

        await scheduler.stop()
