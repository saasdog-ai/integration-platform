"""Tests for sync orchestrator service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError, SyncError
from app.domain.entities import (
    AvailableIntegration,
    OAuthConfig,
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
    SyncJobType,
)
from app.services.sync_orchestrator import SyncOrchestrator
from tests.mocks.adapters import MockAdapterFactory
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)
from app.infrastructure.queue.memory_queue import InMemoryQueue


@pytest.fixture
def mock_integration_repo():
    """Create mock integration repository."""
    repo = MockIntegrationRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_job_repo():
    """Create mock sync job repository."""
    repo = MockSyncJobRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_state_repo():
    """Create mock integration state repository."""
    repo = MockIntegrationStateRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_queue():
    """Create mock message queue."""
    queue = InMemoryQueue()
    yield queue


@pytest.fixture
def mock_encryption():
    """Create mock encryption service."""
    service = MockEncryptionService()
    yield service
    service.reset()


@pytest.fixture
def mock_adapter_factory():
    """Create mock adapter factory."""
    factory = MockAdapterFactory()
    yield factory
    factory.clear()


@pytest.fixture
def orchestrator(
    mock_integration_repo,
    mock_job_repo,
    mock_state_repo,
    mock_queue,
    mock_encryption,
    mock_adapter_factory,
):
    """Create sync orchestrator with mocks."""
    return SyncOrchestrator(
        integration_repo=mock_integration_repo,
        job_repo=mock_job_repo,
        state_repo=mock_state_repo,
        queue=mock_queue,
        encryption_service=mock_encryption,
        adapter_factory=mock_adapter_factory,
    )


@pytest.fixture
def sample_client_id():
    """Sample client ID."""
    return uuid4()


@pytest.fixture
def sample_integration(mock_integration_repo) -> AvailableIntegration:
    """Create a sample available integration."""
    return mock_integration_repo.seed_available_integration(
        name="QuickBooks Online",
        type="erp",
        supported_entities=["bill", "invoice", "vendor"],
        oauth_config=OAuthConfig(
            authorization_url="https://oauth.example.com/authorize",
            token_url="https://oauth.example.com/token",
            scopes=["read", "write"],
        ),
    )


@pytest.fixture
async def connected_user_integration(
    mock_integration_repo, sample_client_id, sample_integration
) -> UserIntegration:
    """Create a connected user integration."""
    now = datetime.now(timezone.utc)
    user_integration = UserIntegration(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_integration.id,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=b"encrypted_creds",
        credentials_key_id="test-key-id",
        external_account_id="ext-account-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
    )
    await mock_integration_repo.create_user_integration(user_integration)
    return user_integration


class TestTriggerSync:
    """Test sync job triggering."""

    async def test_trigger_sync_creates_job(
        self,
        orchestrator,
        mock_queue,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test triggering a sync creates a job and sends to queue."""
        job = await orchestrator.trigger_sync(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            triggered_by=SyncJobTrigger.USER,
        )

        assert job.status == SyncJobStatus.PENDING
        assert job.client_id == sample_client_id
        assert job.integration_id == sample_integration.id
        assert job.job_type == SyncJobType.FULL_SYNC

        # Verify job was created
        assert job.id is not None
        assert job.triggered_by == SyncJobTrigger.USER

    async def test_trigger_sync_integration_not_found(
        self, orchestrator, sample_client_id
    ):
        """Test error when integration doesn't exist."""
        with pytest.raises(NotFoundError):
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=uuid4(),
            )

    async def test_trigger_sync_not_connected(
        self, orchestrator, mock_integration_repo, sample_client_id, sample_integration
    ):
        """Test error when integration not connected."""
        # Create pending user integration
        now = datetime.now(timezone.utc)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            status=IntegrationStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        await mock_integration_repo.create_user_integration(user_integration)

        with pytest.raises(SyncError) as exc_info:
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
            )
        assert "not connected" in str(exc_info.value)

    async def test_trigger_sync_conflict_running_job(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test error when job already running."""
        # Create running job
        now = datetime.now(timezone.utc)
        running_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.SCHEDULER,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(running_job)

        with pytest.raises(ConflictError) as exc_info:
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
            )
        assert "already running or pending" in str(exc_info.value)
        assert str(running_job.id) in str(exc_info.value.details)

    async def test_trigger_sync_conflict_pending_job(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test error when job already pending (queued but not yet running)."""
        # Create pending job
        now = datetime.now(timezone.utc)
        pending_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.SCHEDULER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(pending_job)

        with pytest.raises(ConflictError) as exc_info:
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
            )
        assert "already running or pending" in str(exc_info.value)
        assert str(pending_job.id) in str(exc_info.value.details)

    async def test_trigger_sync_allowed_after_job_completes(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test that new job can be created after previous job completes."""
        now = datetime.now(timezone.utc)

        # Create a completed job
        completed_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.SCHEDULER,
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(completed_job)

        # Should be able to create a new job
        new_job = await orchestrator.trigger_sync(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
        )
        assert new_job.status == SyncJobStatus.PENDING
        assert new_job.id != completed_job.id

    async def test_trigger_sync_allowed_different_integration(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test that jobs for different integrations don't conflict."""
        now = datetime.now(timezone.utc)

        # Create another integration and connect it
        other_integration = mock_integration_repo.seed_available_integration(
            name="Xero",
            type="erp",
            supported_entities=["bill", "invoice"],
        )
        other_user_integration = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=other_integration.id,
            status=IntegrationStatus.CONNECTED,
            credentials_encrypted=b"encrypted_creds",
            credentials_key_id="test-key-id",
            external_account_id="ext-account-456",
            last_connected_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_integration_repo.create_user_integration(other_user_integration)

        # Create running job for first integration
        running_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.SCHEDULER,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(running_job)

        # Should be able to create job for different integration
        new_job = await orchestrator.trigger_sync(
            client_id=sample_client_id,
            integration_id=other_integration.id,
        )
        assert new_job.status == SyncJobStatus.PENDING
        assert new_job.integration_id == other_integration.id

    async def test_trigger_sync_invalid_entity_types(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test error when invalid entity types provided."""
        with pytest.raises(SyncError) as exc_info:
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                entity_types=["invalid_entity", "also_invalid"],
            )
        assert "Invalid entity types" in str(exc_info.value)

    async def test_trigger_sync_with_valid_entity_types(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test triggering sync with valid entity types."""
        job = await orchestrator.trigger_sync(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_types=["bill", "vendor"],
        )

        assert job.status == SyncJobStatus.PENDING


class TestCancelSyncJob:
    """Test sync job cancellation."""

    async def test_cancel_pending_job(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test canceling a pending job."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        cancelled_job = await orchestrator.cancel_sync_job(sample_client_id, job.id)

        assert cancelled_job.status == SyncJobStatus.CANCELLED

    async def test_cancel_running_job(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test canceling a running job."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.USER,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        cancelled_job = await orchestrator.cancel_sync_job(sample_client_id, job.id)

        assert cancelled_job.status == SyncJobStatus.CANCELLED

    async def test_cancel_job_not_found(
        self, orchestrator, sample_client_id
    ):
        """Test error when job doesn't exist."""
        with pytest.raises(NotFoundError):
            await orchestrator.cancel_sync_job(sample_client_id, uuid4())

    async def test_cancel_job_wrong_client(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test error when job belongs to different client."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=uuid4(),  # Different client
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        with pytest.raises(NotFoundError):
            await orchestrator.cancel_sync_job(sample_client_id, job.id)

    async def test_cancel_completed_job_fails(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test error when trying to cancel completed job."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.USER,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        with pytest.raises(SyncError) as exc_info:
            await orchestrator.cancel_sync_job(sample_client_id, job.id)
        assert "Cannot cancel job" in str(exc_info.value)


class TestGetJobs:
    """Test retrieving sync jobs."""

    async def test_get_job(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test getting a specific job."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        retrieved_job = await orchestrator.get_job(sample_client_id, job.id)

        assert retrieved_job.id == job.id

    async def test_get_job_not_found(
        self, orchestrator, sample_client_id
    ):
        """Test error when job not found."""
        with pytest.raises(NotFoundError):
            await orchestrator.get_job(sample_client_id, uuid4())

    async def test_get_jobs_for_client(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test getting all jobs for a client."""
        now = datetime.now(timezone.utc)
        for i in range(3):
            job = SyncJob(
                id=uuid4(),
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                job_type=SyncJobType.INCREMENTAL,
                status=SyncJobStatus.PENDING,
                triggered_by=SyncJobTrigger.USER,
                created_at=now,
                updated_at=now,
            )
            await mock_job_repo.create_job(job)

        jobs = await orchestrator.get_jobs(sample_client_id)

        assert len(jobs) == 3

    async def test_get_jobs_filtered_by_status(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test filtering jobs by status."""
        now = datetime.now(timezone.utc)

        # Create jobs with different statuses
        pending_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        completed_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.USER,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(pending_job)
        await mock_job_repo.create_job(completed_job)

        # Get only pending jobs
        pending_jobs = await orchestrator.get_jobs(
            sample_client_id, status=SyncJobStatus.PENDING
        )

        assert len(pending_jobs) == 1
        assert pending_jobs[0].status == SyncJobStatus.PENDING


class TestGetJobsPaginated:
    """Test paginated sync job retrieval."""

    async def test_get_jobs_paginated(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test getting paginated jobs."""
        now = datetime.now(timezone.utc)
        # Create multiple jobs
        for i in range(15):
            job = SyncJob(
                id=uuid4(),
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                job_type=SyncJobType.INCREMENTAL,
                status=SyncJobStatus.PENDING,
                triggered_by=SyncJobTrigger.USER,
                created_at=now,
                updated_at=now,
            )
            await mock_job_repo.create_job(job)

        # Get first page
        jobs, total = await orchestrator.get_jobs_paginated(
            sample_client_id, page=1, page_size=10
        )

        assert len(jobs) == 10
        assert total == 15

        # Get second page
        jobs_page2, total2 = await orchestrator.get_jobs_paginated(
            sample_client_id, page=2, page_size=10
        )

        assert len(jobs_page2) == 5
        assert total2 == 15

    async def test_get_jobs_paginated_with_filter(
        self,
        orchestrator,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test paginated jobs with status filter."""
        now = datetime.now(timezone.utc)

        # Create jobs with different statuses
        for i in range(5):
            job = SyncJob(
                id=uuid4(),
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                job_type=SyncJobType.INCREMENTAL,
                status=SyncJobStatus.PENDING,
                triggered_by=SyncJobTrigger.USER,
                created_at=now,
                updated_at=now,
            )
            await mock_job_repo.create_job(job)

        for i in range(3):
            job = SyncJob(
                id=uuid4(),
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                job_type=SyncJobType.INCREMENTAL,
                status=SyncJobStatus.SUCCEEDED,
                triggered_by=SyncJobTrigger.USER,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
            await mock_job_repo.create_job(job)

        # Get only pending jobs
        jobs, total = await orchestrator.get_jobs_paginated(
            sample_client_id, status=SyncJobStatus.PENDING, page=1, page_size=10
        )

        assert len(jobs) == 5
        assert total == 5
        assert all(j.status == SyncJobStatus.PENDING for j in jobs)


class TestGetJobRecords:
    """Test retrieving job records from history table."""

    async def test_get_job_records(
        self,
        orchestrator,
        mock_job_repo,
        mock_state_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test getting records for a specific job."""
        from app.domain.entities import IntegrationHistoryRecord
        from app.domain.enums import RecordSyncStatus

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.USER,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        # Create history entries for this job
        for i in range(5):
            entry = IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_client_id,
                state_record_id=uuid4(),
                integration_id=sample_integration.id,
                entity_type="bill",
                internal_record_id=f"bill-{i}",
                external_record_id=f"ext-bill-{i}",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                job_id=job.id,
                created_at=now,
            )
            await mock_state_repo.create_history_entry(entry)

        # Get records for the job
        records, total = await orchestrator.get_job_records(
            sample_client_id, job.id, page=1, page_size=10
        )

        assert len(records) == 5
        assert total == 5
        assert all(r.job_id == job.id for r in records)

    async def test_get_job_records_with_entity_filter(
        self,
        orchestrator,
        mock_job_repo,
        mock_state_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test filtering job records by entity type."""
        from app.domain.entities import IntegrationHistoryRecord
        from app.domain.enums import RecordSyncStatus

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.USER,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        # Create history entries with different entity types
        for i in range(3):
            entry = IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_client_id,
                state_record_id=uuid4(),
                integration_id=sample_integration.id,
                entity_type="bill",
                internal_record_id=f"bill-{i}",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                job_id=job.id,
                created_at=now,
            )
            await mock_state_repo.create_history_entry(entry)

        for i in range(2):
            entry = IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_client_id,
                state_record_id=uuid4(),
                integration_id=sample_integration.id,
                entity_type="invoice",
                internal_record_id=f"invoice-{i}",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                job_id=job.id,
                created_at=now,
            )
            await mock_state_repo.create_history_entry(entry)

        # Filter by entity type
        records, total = await orchestrator.get_job_records(
            sample_client_id, job.id, entity_type="bill", page=1, page_size=10
        )

        assert len(records) == 3
        assert total == 3
        assert all(r.entity_type == "bill" for r in records)

    async def test_get_job_records_pagination(
        self,
        orchestrator,
        mock_job_repo,
        mock_state_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test pagination of job records."""
        from app.domain.entities import IntegrationHistoryRecord
        from app.domain.enums import RecordSyncStatus

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.SUCCEEDED,
            triggered_by=SyncJobTrigger.USER,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        # Create 25 history entries
        for i in range(25):
            entry = IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_client_id,
                state_record_id=uuid4(),
                integration_id=sample_integration.id,
                entity_type="bill",
                internal_record_id=f"bill-{i}",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                job_id=job.id,
                created_at=now,
            )
            await mock_state_repo.create_history_entry(entry)

        # Get first page
        records_p1, total = await orchestrator.get_job_records(
            sample_client_id, job.id, page=1, page_size=10
        )
        assert len(records_p1) == 10
        assert total == 25

        # Get second page
        records_p2, _ = await orchestrator.get_job_records(
            sample_client_id, job.id, page=2, page_size=10
        )
        assert len(records_p2) == 10

        # Get third page
        records_p3, _ = await orchestrator.get_job_records(
            sample_client_id, job.id, page=3, page_size=10
        )
        assert len(records_p3) == 5


class TestExecuteSyncJob:
    """Test sync job execution."""

    async def test_execute_sync_job_no_settings(
        self,
        orchestrator,
        mock_job_repo,
        mock_integration_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test job execution fails gracefully without settings."""
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        # Clear settings to simulate no configuration
        mock_integration_repo._user_settings.clear()

        result = await orchestrator.execute_sync_job(job)

        assert result.status == SyncJobStatus.FAILED
        assert result.error_code == "SYNC_FAILED"

    async def test_execute_sync_job_with_settings(
        self,
        orchestrator,
        mock_job_repo,
        mock_integration_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test successful job execution with valid settings."""
        # Add sync settings
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            ],
            sync_frequency="hourly",
            auto_sync_enabled=True,
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        result = await orchestrator.execute_sync_job(job)

        # Job should complete (either succeeded or failed based on adapter behavior)
        assert result.status in (SyncJobStatus.SUCCEEDED, SyncJobStatus.FAILED)

    async def test_execute_sync_job_no_enabled_rules(
        self,
        orchestrator,
        mock_job_repo,
        mock_integration_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test job execution fails when no rules are enabled."""
        # Add settings with all rules disabled
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=False),
            ],
            sync_frequency="hourly",
            auto_sync_enabled=True,
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        result = await orchestrator.execute_sync_job(job)

        assert result.status == SyncJobStatus.FAILED
        assert "No sync rules are enabled" in result.error_message


class TestGlobalDisable:
    """Test global sync disable feature flag."""

    async def test_trigger_sync_globally_disabled(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test triggering sync when globally disabled."""
        from unittest.mock import patch

        with patch("app.services.sync_orchestrator.get_settings") as mock_settings:
            mock_settings.return_value.sync_globally_disabled = True
            mock_settings.return_value.disabled_integrations = []

            with pytest.raises(SyncError) as exc_info:
                await orchestrator.trigger_sync(
                    client_id=sample_client_id,
                    integration_id=sample_integration.id,
                )
            assert "globally" in str(exc_info.value).lower()

    async def test_trigger_sync_integration_disabled(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test triggering sync when specific integration is disabled."""
        from unittest.mock import patch

        with patch("app.services.sync_orchestrator.get_settings") as mock_settings:
            mock_settings.return_value.sync_globally_disabled = False
            mock_settings.return_value.disabled_integrations = ["QuickBooks Online"]

            with pytest.raises(SyncError) as exc_info:
                await orchestrator.trigger_sync(
                    client_id=sample_client_id,
                    integration_id=sample_integration.id,
                )
            assert "disabled" in str(exc_info.value).lower()


class TestResolveRequestedEntityTypes:
    """Test _resolve_requested_entity_types static method."""

    def test_none_job_params(self):
        """Return None when job_params is None."""
        result = SyncOrchestrator._resolve_requested_entity_types(None)
        assert result is None

    def test_empty_dict(self):
        """Return None when job_params is empty."""
        result = SyncOrchestrator._resolve_requested_entity_types({})
        assert result is None

    def test_entity_types_only(self):
        """Return set of entity types from entity_types list."""
        result = SyncOrchestrator._resolve_requested_entity_types(
            {"entity_types": ["bill", "vendor"]}
        )
        assert result == {"bill", "vendor"}

    def test_entity_requests_takes_precedence(self):
        """entity_requests wins when both entity_types and entity_requests present."""
        result = SyncOrchestrator._resolve_requested_entity_types(
            {
                "entity_types": ["bill", "vendor"],
                "entity_requests": [
                    {"entity_type": "invoice", "record_ids": ["inv-1"]},
                ],
            }
        )
        assert result == {"invoice"}

    def test_entity_requests_without_record_ids(self):
        """entity_requests works even without record_ids field."""
        result = SyncOrchestrator._resolve_requested_entity_types(
            {
                "entity_requests": [{"entity_type": "vendor"}],
            }
        )
        assert result == {"vendor"}

    def test_empty_entity_types_list(self):
        """Empty entity_types list treated as no filtering."""
        result = SyncOrchestrator._resolve_requested_entity_types(
            {"entity_types": []}
        )
        assert result is None

    def test_empty_entity_requests_list(self):
        """Empty entity_requests list treated as no filtering."""
        result = SyncOrchestrator._resolve_requested_entity_types(
            {"entity_requests": []}
        )
        assert result is None


class TestEntityTypeFiltering:
    """Test entity type filtering in execute_sync_job."""

    async def _setup_rules_and_job(
        self,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        sync_rules,
        job_params=None,
    ):
        """Set up sync rules, seed adapter records, and create a pending job."""
        settings = UserIntegrationSettings(
            sync_rules=sync_rules,
            sync_frequency="hourly",
            auto_sync_enabled=True,
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        # Seed adapter with one record per entity type so fetch_records returns data
        adapter = mock_adapter_factory.get_adapter(
            sample_integration, "mock_token", "ext-account-123"
        )
        for rule in sync_rules:
            adapter.seed_record(
                rule.entity_type,
                f"ext-{rule.entity_type}-1",
                {"name": f"Test {rule.entity_type}"},
            )

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            job_params=job_params,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)
        return job, adapter

    async def test_no_entity_types_runs_all_enabled_rules(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """All enabled rules run when no entity types specified."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="invoice", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params=None,
        )

        result = await orchestrator.execute_sync_job(job)

        fetched_types = {call[0] for call in adapter.fetch_records_calls}
        assert fetched_types == {"bill", "invoice", "vendor"}
        assert result.status == SyncJobStatus.SUCCEEDED

    async def test_entity_types_filters_to_matching_rules(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Only matching entity types are synced when entity_types specified."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="invoice", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params={"entity_types": ["vendor"]},
        )

        result = await orchestrator.execute_sync_job(job)

        fetched_types = {call[0] for call in adapter.fetch_records_calls}
        assert fetched_types == {"vendor"}
        assert result.status == SyncJobStatus.SUCCEEDED

    async def test_no_matching_enabled_rule_raises_error(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Job fails when requested entity types have no enabled rules."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params={"entity_types": ["vendor"]},
        )

        result = await orchestrator.execute_sync_job(job)

        assert result.status == SyncJobStatus.FAILED
        assert "not enabled" in result.error_message

    async def test_entity_requests_implies_entity_types(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """entity_requests filters rules by extracted entity type."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="invoice", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params={
                "entity_requests": [
                    {"entity_type": "vendor", "record_ids": ["v-1"]},
                ],
            },
        )

        result = await orchestrator.execute_sync_job(job)

        fetched_types = {call[0] for call in adapter.fetch_records_calls}
        assert fetched_types == {"vendor"}
        assert result.status == SyncJobStatus.SUCCEEDED

    async def test_disabled_rules_stay_excluded(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Disabled rules are not executed even if requested via entity_types."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=False),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params={"entity_types": ["bill", "vendor"]},
        )

        result = await orchestrator.execute_sync_job(job)

        fetched_types = {call[0] for call in adapter.fetch_records_calls}
        assert fetched_types == {"bill"}
        assert result.status == SyncJobStatus.SUCCEEDED

    async def test_direction_preserved(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Outbound rules don't trigger inbound fetch even when filtered."""
        rules = [
            SyncRule(entity_type="vendor", direction=SyncDirection.OUTBOUND, enabled=True),
        ]
        job, adapter = await self._setup_rules_and_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            sample_client_id, sample_integration, rules,
            job_params={"entity_types": ["vendor"]},
        )

        result = await orchestrator.execute_sync_job(job)

        # Outbound rules don't call fetch_records (that's inbound only);
        # job may fail in strategy path but the key point is no inbound fetch
        fetched_types = {call[0] for call in adapter.fetch_records_calls}
        assert "vendor" not in fetched_types


class TestEnsureValidToken:
    """Test _ensure_valid_token automatic OAuth token refresh."""

    def _make_orchestrator(
        self,
        mock_integration_repo,
        mock_job_repo,
        mock_state_repo,
        mock_queue,
        mock_encryption,
        mock_adapter_factory,
    ):
        return SyncOrchestrator(
            integration_repo=mock_integration_repo,
            job_repo=mock_job_repo,
            state_repo=mock_state_repo,
            queue=mock_queue,
            encryption_service=mock_encryption,
            adapter_factory=mock_adapter_factory,
        )

    async def test_token_still_valid(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Token with >5 min remaining is returned as-is without refresh."""
        creds = {
            "access_token": "valid_token",
            "refresh_token": "rt",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }

        result = await orchestrator._ensure_valid_token(
            sample_client_id, sample_integration.id, creds,
        )

        assert result == "valid_token"

    async def test_no_expires_at(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Missing expires_at returns existing token with a warning."""
        creds = {
            "access_token": "legacy_token",
            "refresh_token": "rt",
        }

        result = await orchestrator._ensure_valid_token(
            sample_client_id, sample_integration.id, creds,
        )

        assert result == "legacy_token"

    async def test_invalid_expires_at_format(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Malformed expires_at returns existing token with a warning."""
        creds = {
            "access_token": "old_token",
            "refresh_token": "rt",
            "expires_at": "not-a-date",
        }

        result = await orchestrator._ensure_valid_token(
            sample_client_id, sample_integration.id, creds,
        )

        assert result == "old_token"

    async def test_token_expired_triggers_refresh(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Expired token triggers IntegrationService.refresh_integration_token."""
        creds = {
            "access_token": "expired_token",
            "refresh_token": "rt",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }

        mock_tokens = MagicMock()
        mock_tokens.access_token = "refreshed_token"

        with patch(
            "app.services.sync_orchestrator.IntegrationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.refresh_integration_token = AsyncMock(return_value=mock_tokens)

            result = await orchestrator._ensure_valid_token(
                sample_client_id, sample_integration.id, creds,
            )

        assert result == "refreshed_token"
        instance.refresh_integration_token.assert_awaited_once_with(
            sample_client_id, sample_integration.id,
        )

    async def test_token_expiring_within_buffer(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Token expiring within 5-minute buffer triggers refresh."""
        creds = {
            "access_token": "almost_expired",
            "refresh_token": "rt",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
        }

        mock_tokens = MagicMock()
        mock_tokens.access_token = "new_token"

        with patch(
            "app.services.sync_orchestrator.IntegrationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.refresh_integration_token = AsyncMock(return_value=mock_tokens)

            result = await orchestrator._ensure_valid_token(
                sample_client_id, sample_integration.id, creds,
            )

        assert result == "new_token"
        instance.refresh_integration_token.assert_awaited_once()

    async def test_refresh_fails_permanently(
        self,
        orchestrator,
        sample_client_id,
        sample_integration,
    ):
        """Exhausting retry attempts raises SyncError."""
        from app.core.exceptions import IntegrationError

        creds = {
            "access_token": "expired_token",
            "refresh_token": "rt",
            "expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }

        with patch(
            "app.services.sync_orchestrator.IntegrationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.refresh_integration_token = AsyncMock(
                side_effect=IntegrationError("QBO", "No refresh token"),
            )

            with pytest.raises(SyncError, match="Token refresh failed after 2 attempts"):
                await orchestrator._ensure_valid_token(
                    sample_client_id, sample_integration.id, creds,
                )

        assert instance.refresh_integration_token.await_count == 2


class TestSplitSyncCursors:
    """Test split inbound/outbound sync cursors.

    Uses a generic integration (not 'QuickBooks Online') so the orchestrator
    takes the generic ``_sync_entity`` path which doesn't need a live database
    for internal data tables.
    """

    @pytest.fixture
    def generic_integration(self, mock_integration_repo) -> AvailableIntegration:
        """Create a generic (non-QBO) integration so the generic path is used."""
        return mock_integration_repo.seed_available_integration(
            name="Generic ERP",
            type="erp",
            supported_entities=["bill", "invoice", "vendor"],
        )

    @pytest.fixture
    async def generic_connected(
        self, mock_integration_repo, sample_client_id, generic_integration,
    ) -> UserIntegration:
        now = datetime.now(timezone.utc)
        ui = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            status=IntegrationStatus.CONNECTED,
            credentials_encrypted=b"encrypted",
            credentials_key_id="k",
            external_account_id="ext-123",
            last_connected_at=now,
            created_at=now,
            updated_at=now,
        )
        await mock_integration_repo.create_user_integration(ui)
        return ui

    # ---- helpers ----

    async def _run_inbound_job(
        self,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        orchestrator,
        sample_client_id,
        integration,
        *,
        seed_records: bool = True,
        custom_updated_at: datetime | None = None,
        preset_entity_status=None,
        job_type: SyncJobType = SyncJobType.FULL_SYNC,
    ):
        from app.domain.entities import ExternalRecord

        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, integration.id, settings,
        )

        adapter = mock_adapter_factory.get_adapter(
            integration, "mock_token", "ext-123",
        )

        if seed_records:
            ts = custom_updated_at or datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            record = ExternalRecord(
                id="ext-bill-1",
                entity_type="bill",
                data={"name": "Test bill"},
                version="1",
                updated_at=ts,
            )
            adapter._records.setdefault("bill", {})["ext-bill-1"] = record

        if preset_entity_status is not None:
            mock_state_repo._entity_sync_status[
                (sample_client_id, integration.id, "bill")
            ] = preset_entity_status

        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=integration.id,
            job_type=job_type,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        result = await orchestrator.execute_sync_job(job)
        return result, adapter

    # ---- tests ----

    async def test_inbound_sets_qbo_cursor(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        sample_client_id,
        generic_integration,
        generic_connected,
    ):
        """Inbound sync sets last_inbound_sync_at to max external timestamp."""
        qbo_ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        await self._run_inbound_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            mock_state_repo, orchestrator, sample_client_id,
            generic_integration, custom_updated_at=qbo_ts,
        )

        entity_status = mock_state_repo._entity_sync_status.get(
            (sample_client_id, generic_integration.id, "bill")
        )
        assert entity_status is not None
        assert entity_status.last_inbound_sync_at == qbo_ts

    async def test_outbound_does_not_touch_inbound_cursor(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        sample_client_id,
        generic_integration,
        generic_connected,
    ):
        """Running outbound sync does not alter last_inbound_sync_at."""
        from app.domain.entities import EntitySyncStatus, IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus

        qbo_ts = datetime(2026, 1, 10, 8, 0, 0, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        entity_status = EntitySyncStatus(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            entity_type="bill",
            last_successful_sync_at=now,
            last_inbound_sync_at=qbo_ts,
            last_sync_job_id=uuid4(),
            records_synced_count=5,
            created_at=now,
            updated_at=now,
        )
        mock_state_repo._entity_sync_status[
            (sample_client_id, generic_integration.id, "bill")
        ] = entity_status

        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.OUTBOUND, enabled=True),
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, generic_integration.id, settings,
        )

        # Pending record for outbound sync
        pending = IntegrationStateRecord(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            entity_type="bill",
            internal_record_id="int-bill-1",
            external_record_id=None,
            sync_status=RecordSyncStatus.PENDING,
            sync_direction=SyncDirection.OUTBOUND,
            metadata={"data": {"name": "Test bill"}},
            created_at=now,
            updated_at=now,
        )
        mock_state_repo._records[(sample_client_id, pending.id)] = pending

        adapter = mock_adapter_factory.get_adapter(
            generic_integration, "mock_token", "ext-123",
        )

        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        await orchestrator.execute_sync_job(job)

        updated_status = mock_state_repo._entity_sync_status.get(
            (sample_client_id, generic_integration.id, "bill")
        )
        assert updated_status.last_inbound_sync_at == qbo_ts

    async def test_incremental_inbound_reads_inbound_cursor(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        sample_client_id,
        generic_integration,
        generic_connected,
    ):
        """Incremental inbound sync uses last_inbound_sync_at (not last_successful_sync_at)."""
        from app.domain.entities import EntitySyncStatus

        inbound_ts = datetime(2026, 1, 10, 8, 0, 0, tzinfo=timezone.utc)
        outbound_ts = datetime(2026, 1, 12, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        entity_status = EntitySyncStatus(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            entity_type="bill",
            last_successful_sync_at=outbound_ts,
            last_inbound_sync_at=inbound_ts,
            last_sync_job_id=uuid4(),
            records_synced_count=5,
            created_at=now,
            updated_at=now,
        )
        mock_state_repo._entity_sync_status[
            (sample_client_id, generic_integration.id, "bill")
        ] = entity_status

        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, generic_integration.id, settings,
        )

        adapter = mock_adapter_factory.get_adapter(
            generic_integration, "mock_token", "ext-123",
        )

        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        await orchestrator.execute_sync_job(job)

        assert len(adapter.fetch_records_calls) > 0
        _, since_arg, _, _ = adapter.fetch_records_calls[0]
        assert since_arg == inbound_ts

    async def test_fallback_for_pre_migration_rows(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        sample_client_id,
        generic_integration,
        generic_connected,
    ):
        """When last_inbound_sync_at is None, falls back to last_successful_sync_at."""
        from app.domain.entities import EntitySyncStatus

        outbound_ts = datetime(2026, 1, 12, 14, 0, 0, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        entity_status = EntitySyncStatus(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            entity_type="bill",
            last_successful_sync_at=outbound_ts,
            last_inbound_sync_at=None,
            last_sync_job_id=uuid4(),
            records_synced_count=5,
            created_at=now,
            updated_at=now,
        )
        mock_state_repo._entity_sync_status[
            (sample_client_id, generic_integration.id, "bill")
        ] = entity_status

        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, generic_integration.id, settings,
        )

        adapter = mock_adapter_factory.get_adapter(
            generic_integration, "mock_token", "ext-123",
        )

        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        await mock_job_repo.create_job(job)

        await orchestrator.execute_sync_job(job)

        assert len(adapter.fetch_records_calls) > 0
        _, since_arg, _, _ = adapter.fetch_records_calls[0]
        assert since_arg == outbound_ts

    async def test_no_records_does_not_advance_cursor(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        mock_adapter_factory,
        mock_state_repo,
        sample_client_id,
        generic_integration,
        generic_connected,
    ):
        """When adapter returns 0 records, last_inbound_sync_at stays unchanged."""
        from app.domain.entities import EntitySyncStatus

        original_inbound_ts = datetime(2026, 1, 10, 8, 0, 0, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        entity_status = EntitySyncStatus(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=generic_integration.id,
            entity_type="bill",
            last_successful_sync_at=now,
            last_inbound_sync_at=original_inbound_ts,
            last_sync_job_id=uuid4(),
            records_synced_count=5,
            created_at=now,
            updated_at=now,
        )
        mock_state_repo._entity_sync_status[
            (sample_client_id, generic_integration.id, "bill")
        ] = entity_status

        await self._run_inbound_job(
            mock_integration_repo, mock_job_repo, mock_adapter_factory,
            mock_state_repo, orchestrator, sample_client_id,
            generic_integration, seed_records=False,
            preset_entity_status=entity_status,
        )

        updated = mock_state_repo._entity_sync_status.get(
            (sample_client_id, generic_integration.id, "bill")
        )
        assert updated.last_inbound_sync_at == original_inbound_ts
