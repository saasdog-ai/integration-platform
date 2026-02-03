"""Tests for sync job runner."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.entities import (
    AvailableIntegration,
    QueueMessage,
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
from app.infrastructure.queue.memory_queue import InMemoryQueue
from app.services.sync_job_runner import SyncJobRunner
from tests.mocks.adapters import MockAdapterFactory
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)


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
    )


@pytest.fixture
async def connected_user_integration(
    mock_integration_repo, sample_client_id, sample_integration
) -> UserIntegration:
    """Create a connected user integration."""
    now = datetime.now(UTC)
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
    return user_integration


@pytest.fixture
def job_runner(
    mock_queue,
    mock_integration_repo,
    mock_job_repo,
    mock_state_repo,
    mock_encryption,
    mock_adapter_factory,
):
    """Create a sync job runner."""
    return SyncJobRunner(
        queue=mock_queue,
        integration_repo=mock_integration_repo,
        job_repo=mock_job_repo,
        state_repo=mock_state_repo,
        encryption_service=mock_encryption,
        adapter_factory=mock_adapter_factory,
        max_workers=2,
    )


class TestSyncJobRunner:
    """Tests for SyncJobRunner."""

    def test_initialization(self, job_runner):
        """Test runner initializes correctly."""
        assert job_runner._max_workers == 2
        assert not job_runner._running
        assert job_runner._consecutive_errors == 0

    def test_record_error_increments_counter(self, job_runner):
        """Test error recording."""
        assert job_runner._consecutive_errors == 0

        job_runner._record_error()
        assert job_runner._consecutive_errors == 1

        job_runner._record_error()
        assert job_runner._consecutive_errors == 2

    def test_record_success_resets_counter(self, job_runner):
        """Test success recording resets error counter."""
        job_runner._consecutive_errors = 5
        job_runner._backpressure_until = 1000000

        job_runner._record_success()

        assert job_runner._consecutive_errors == 0
        assert job_runner._backpressure_until == 0

    def test_backpressure_triggered_after_threshold(self, job_runner):
        """Test backpressure is triggered after error threshold."""
        # Record errors up to threshold
        for _ in range(5):
            job_runner._record_error()

        assert job_runner._backpressure_until > 0

    async def test_stop_when_not_running(self, job_runner):
        """Test stop does nothing when not running."""
        await job_runner.stop()
        assert not job_runner._running


class TestProcessMessage:
    """Tests for message processing."""

    async def test_process_valid_message(
        self,
        job_runner,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test processing a valid sync job message."""
        # Create a pending job
        now = datetime.now(UTC)
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

        # Create message
        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(job.id),
                "client_id": str(sample_client_id),
                "integration_id": str(sample_integration.id),
                "job_type": "full_sync",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        await job_runner._process_message(message)

        # Job should be updated (either running or succeeded/failed)
        updated_job = await mock_job_repo.get_job(job.id)
        assert updated_job.status != SyncJobStatus.PENDING

    async def test_process_message_missing_fields(self, job_runner, mock_queue):
        """Test processing a message with missing required fields."""
        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(uuid4()),
                # Missing client_id, integration_id, job_type
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        # Should not raise, but should delete malformed message
        await job_runner._process_message(message)

    async def test_process_message_invalid_uuid(self, job_runner, mock_queue):
        """Test processing a message with invalid UUID."""
        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": "not-a-uuid",
                "client_id": str(uuid4()),
                "integration_id": str(uuid4()),
                "job_type": "full_sync",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        await job_runner._process_message(message)
        # Should handle gracefully

    async def test_process_message_invalid_job_type(self, job_runner, mock_queue):
        """Test processing a message with invalid job type."""
        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(uuid4()),
                "client_id": str(uuid4()),
                "integration_id": str(uuid4()),
                "job_type": "invalid_type",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        await job_runner._process_message(message)
        # Should handle gracefully

    async def test_process_message_job_not_found(
        self, job_runner, sample_client_id, sample_integration
    ):
        """Test processing a message for non-existent job."""
        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(uuid4()),  # Non-existent job
                "client_id": str(sample_client_id),
                "integration_id": str(sample_integration.id),
                "job_type": "full_sync",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        await job_runner._process_message(message)
        # Should handle gracefully

    async def test_process_message_job_not_pending(
        self,
        job_runner,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test processing a message for job that's not pending."""
        now = datetime.now(UTC)
        # Create a completed job
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

        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(job.id),
                "client_id": str(sample_client_id),
                "integration_id": str(sample_integration.id),
                "job_type": "full_sync",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        await job_runner._process_message(message)

        # Job status should remain succeeded
        updated_job = await mock_job_repo.get_job(job.id)
        assert updated_job.status == SyncJobStatus.SUCCEEDED


class TestStuckJobHandling:
    """Tests for stuck job detection and termination."""

    async def test_check_stuck_jobs_disabled(self, job_runner):
        """Test stuck job check when termination is disabled."""
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.job_termination_enabled = False

            await job_runner._check_stuck_jobs()
            # Should return early without error

    async def test_check_stuck_jobs_rate_limited(self, job_runner):
        """Test stuck job check is rate limited."""
        job_runner._last_stuck_job_check = 999999999999  # Far future

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.job_termination_enabled = True

            await job_runner._check_stuck_jobs()
            # Should return early due to rate limiting

    async def test_terminates_stuck_jobs(
        self,
        job_runner,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test that stuck jobs are terminated."""
        # Create a stuck job (running for too long)
        stuck_time = datetime.now(UTC) - timedelta(hours=2)
        job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.USER,
            started_at=stuck_time,
            created_at=stuck_time,
            updated_at=stuck_time,
        )
        await mock_job_repo.create_job(job)

        job_runner._last_stuck_job_check = 0  # Force check

        with patch("app.services.sync_job_runner.get_settings") as mock_settings:
            mock_settings.return_value.job_termination_enabled = True
            mock_settings.return_value.job_stuck_timeout_minutes = 60

            await job_runner._check_stuck_jobs()

        # Job should be terminated
        updated_job = await mock_job_repo.get_job(job.id)
        assert updated_job.status == SyncJobStatus.FAILED
        assert updated_job.error_code == "JOB_TIMEOUT"


class TestTaskDoneCallback:
    """Tests for task completion callback."""

    def test_task_done_discards_task(self, job_runner):
        """Test task is removed from tracking set."""
        job_runner._semaphore = asyncio.Semaphore(2)

        mock_task = MagicMock()
        mock_task.result.return_value = None
        job_runner._tasks.add(mock_task)

        job_runner._task_done(mock_task)

        assert mock_task not in job_runner._tasks

    def test_task_done_releases_semaphore(self, job_runner):
        """Test semaphore is released on task completion."""
        job_runner._semaphore = asyncio.Semaphore(2)
        job_runner._semaphore.acquire()  # Reduce available

        mock_task = MagicMock()
        mock_task.result.return_value = None

        initial_value = job_runner._semaphore._value
        job_runner._task_done(mock_task)

        # Semaphore should be released (value increased)
        assert job_runner._semaphore._value == initial_value + 1

    def test_task_done_handles_exception(self, job_runner):
        """Test exception in task is handled."""
        job_runner._semaphore = asyncio.Semaphore(2)

        mock_task = MagicMock()
        mock_task.result.side_effect = ValueError("Task failed")

        # Should not raise
        job_runner._task_done(mock_task)


class TestPollAndProcess:
    """Tests for polling and processing."""

    async def test_poll_no_messages(self, job_runner, mock_queue):
        """Test polling when no messages available."""
        # Queue is empty by default
        await job_runner._poll_and_process()
        # Should complete without error

    async def test_poll_with_messages(
        self,
        job_runner,
        mock_queue,
        mock_job_repo,
        sample_client_id,
        sample_integration,
        connected_user_integration,
    ):
        """Test polling with available messages."""
        # Create a pending job
        now = datetime.now(UTC)
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

        # Send message to queue
        await mock_queue.send_message(
            {
                "job_id": str(job.id),
                "client_id": str(sample_client_id),
                "integration_id": str(sample_integration.id),
                "job_type": "full_sync",
            }
        )

        # Initialize semaphore
        job_runner._semaphore = asyncio.Semaphore(2)

        await job_runner._poll_and_process()

        # Wait for tasks to complete
        if job_runner._tasks:
            await asyncio.gather(*job_runner._tasks, return_exceptions=True)


class TestGlobalDisable:
    """Tests for global sync disable feature flag."""

    async def test_respects_global_disable_flag(
        self,
        job_runner,
        mock_job_repo,
        sample_client_id,
        sample_integration,
    ):
        """Test that global disable flag prevents job processing."""
        now = datetime.now(UTC)
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

        message = QueueMessage(
            message_id="msg-123",
            receipt_handle="receipt-123",
            body={
                "job_id": str(job.id),
                "client_id": str(sample_client_id),
                "integration_id": str(sample_integration.id),
                "job_type": "full_sync",
            },
            attributes={"ApproximateReceiveCount": "1"},
        )

        with patch("app.services.sync_job_runner.get_settings") as mock_settings:
            mock_settings.return_value.sync_globally_disabled = True
            mock_settings.return_value.queue_max_receive_count = 3

            await job_runner._process_message(message)

        # Job should still be pending
        updated_job = await mock_job_repo.get_job(job.id)
        assert updated_job.status == SyncJobStatus.PENDING
