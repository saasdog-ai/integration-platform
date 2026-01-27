"""Tests for sync orchestrator service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
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

        with pytest.raises(ConflictError):
            await orchestrator.trigger_sync(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
            )

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
