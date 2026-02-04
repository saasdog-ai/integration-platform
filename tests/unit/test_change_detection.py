"""Tests for flexible change detection (push notifications + webhook support)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.entities import (
    ChangeEvent,
    IntegrationStateRecord,
    SyncJob,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    ChangeSourceType,
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
    SyncTriggerMode,
)
from app.infrastructure.queue.memory_queue import InMemoryQueue
from app.services.sync_orchestrator import SyncOrchestrator
from tests.mocks.adapters import MockAdapterFactory
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_integration_repo():
    repo = MockIntegrationRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_job_repo():
    repo = MockSyncJobRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_state_repo():
    repo = MockIntegrationStateRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_queue():
    queue = InMemoryQueue()
    yield queue


@pytest.fixture
def mock_encryption():
    service = MockEncryptionService()
    yield service
    service.reset()


@pytest.fixture
def mock_adapter_factory():
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
    return uuid4()


@pytest.fixture
def sample_integration(mock_integration_repo):
    return mock_integration_repo.seed_available_integration(
        name="QuickBooks Online",
        type="erp",
        supported_entities=["bill", "invoice", "vendor"],
    )


@pytest.fixture
def connected_integration(
    sample_client_id,
    sample_integration,
    mock_integration_repo,
):
    now = datetime.now(UTC)
    user_integration = UserIntegration(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_integration.id,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=b"encrypted",
        credentials_key_id="test-key",
        external_account_id="ext-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
        integration=sample_integration,
    )
    import asyncio

    asyncio.get_event_loop().run_until_complete(
        mock_integration_repo.create_user_integration(user_integration)
    )
    return user_integration


# =============================================================================
# Enum Tests
# =============================================================================


class TestNewEnums:
    """Tests for new enum values."""

    def test_change_source_type_values(self):
        assert ChangeSourceType.POLLING.value == "polling"
        assert ChangeSourceType.WEBHOOK.value == "webhook"
        assert ChangeSourceType.PUSH.value == "push"
        assert ChangeSourceType.HYBRID.value == "hybrid"

    def test_sync_trigger_mode_values(self):
        assert SyncTriggerMode.IMMEDIATE.value == "immediate"
        assert SyncTriggerMode.DEFERRED.value == "deferred"

    def test_sync_job_trigger_push(self):
        assert SyncJobTrigger.PUSH.value == "push"

    def test_change_source_type_from_string(self):
        assert ChangeSourceType("polling") == ChangeSourceType.POLLING
        assert ChangeSourceType("webhook") == ChangeSourceType.WEBHOOK
        assert ChangeSourceType("push") == ChangeSourceType.PUSH
        assert ChangeSourceType("hybrid") == ChangeSourceType.HYBRID

    def test_sync_trigger_mode_from_string(self):
        assert SyncTriggerMode("immediate") == SyncTriggerMode.IMMEDIATE
        assert SyncTriggerMode("deferred") == SyncTriggerMode.DEFERRED


# =============================================================================
# Domain Entity Tests
# =============================================================================


class TestSyncRuleDefaults:
    """Tests for SyncRule new field defaults."""

    def test_default_change_source(self):
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.INBOUND,
        )
        assert rule.change_source == ChangeSourceType.POLLING

    def test_default_sync_trigger(self):
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.INBOUND,
        )
        assert rule.sync_trigger == SyncTriggerMode.DEFERRED

    def test_explicit_change_source(self):
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.INBOUND,
            change_source=ChangeSourceType.WEBHOOK,
            sync_trigger=SyncTriggerMode.IMMEDIATE,
        )
        assert rule.change_source == ChangeSourceType.WEBHOOK
        assert rule.sync_trigger == SyncTriggerMode.IMMEDIATE

    def test_change_event_construction(self):
        client_id = uuid4()
        integration_id = uuid4()
        event = ChangeEvent(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["abc-123", "def-456"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )
        assert event.entity_type == "vendor"
        assert len(event.record_ids) == 2
        assert event.source == ChangeSourceType.PUSH
        assert event.provider is None


# =============================================================================
# Mock Repository Tests
# =============================================================================


class TestBumpVersionVectors:
    """Tests for bump_version_vectors in mock repository."""

    @pytest.mark.asyncio
    async def test_bump_internal_existing_record(self, mock_state_repo):
        client_id = uuid4()
        integration_id = uuid4()
        now = datetime.now(UTC)

        # Seed a record
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id="rec-1",
            external_record_id="ext-1",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=3,
            external_version_id=3,
            last_sync_version_id=3,
            created_at=now,
            updated_at=now,
        )
        await mock_state_repo.upsert_record(record)

        bumped, created = await mock_state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["rec-1"],
            bump_internal=True,
        )

        assert bumped == 1
        assert created == 0

        # Verify the record was actually bumped
        updated = await mock_state_repo.get_record(client_id, integration_id, "vendor", "rec-1")
        assert updated.internal_version_id == 4
        assert updated.external_version_id == 3
        assert updated.sync_status == RecordSyncStatus.PENDING

    @pytest.mark.asyncio
    async def test_bump_external_existing_record(self, mock_state_repo):
        client_id = uuid4()
        integration_id = uuid4()
        now = datetime.now(UTC)

        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id="rec-1",
            external_record_id="ext-1",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=3,
            external_version_id=3,
            last_sync_version_id=3,
            created_at=now,
            updated_at=now,
        )
        await mock_state_repo.upsert_record(record)

        bumped, created = await mock_state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["ext-1"],
            bump_external=True,
        )

        assert bumped == 1
        assert created == 0

        updated = await mock_state_repo.get_record_by_external_id(
            client_id, integration_id, "vendor", "ext-1"
        )
        assert updated.internal_version_id == 3
        assert updated.external_version_id == 4
        assert updated.sync_status == RecordSyncStatus.PENDING

    @pytest.mark.asyncio
    async def test_bump_creates_new_record_for_push(self, mock_state_repo):
        client_id = uuid4()
        integration_id = uuid4()

        bumped, created = await mock_state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["new-rec-1"],
            bump_internal=True,
        )

        assert bumped == 0
        assert created == 1

        record = await mock_state_repo.get_record(client_id, integration_id, "vendor", "new-rec-1")
        assert record is not None
        assert record.internal_version_id == 2
        assert record.external_version_id == 0
        assert record.sync_status == RecordSyncStatus.PENDING

    @pytest.mark.asyncio
    async def test_bump_creates_new_record_for_webhook(self, mock_state_repo):
        client_id = uuid4()
        integration_id = uuid4()

        bumped, created = await mock_state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["ext-new-1"],
            bump_external=True,
        )

        assert bumped == 0
        assert created == 1

        record = await mock_state_repo.get_record_by_external_id(
            client_id, integration_id, "vendor", "ext-new-1"
        )
        assert record is not None
        assert record.internal_version_id == 1
        assert record.external_version_id == 2
        assert record.sync_status == RecordSyncStatus.PENDING

    @pytest.mark.asyncio
    async def test_bump_multiple_records(self, mock_state_repo):
        client_id = uuid4()
        integration_id = uuid4()
        now = datetime.now(UTC)

        # Seed one record, leave one new
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id="existing-1",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=2,
            external_version_id=2,
            last_sync_version_id=2,
            created_at=now,
            updated_at=now,
        )
        await mock_state_repo.upsert_record(record)

        bumped, created = await mock_state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            record_ids=["existing-1", "brand-new-1"],
            bump_internal=True,
        )

        assert bumped == 1
        assert created == 1


# =============================================================================
# handle_change_event Tests
# =============================================================================


class TestHandleChangeEvent:
    """Tests for SyncOrchestrator.handle_change_event."""

    @pytest.mark.asyncio
    async def test_push_bumps_internal_version(
        self,
        orchestrator,
        mock_state_repo,
        mock_integration_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """Push notification bumps internal_version_id."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            internal_record_id="rec-1",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=3,
            external_version_id=3,
            last_sync_version_id=3,
            created_at=now,
            updated_at=now,
        )
        await mock_state_repo.upsert_record(record)

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            record_ids=["rec-1"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )

        bumped, created, job = await orchestrator.handle_change_event(event)
        assert bumped == 1
        assert created == 0
        assert job is None  # Default is DEFERRED

        updated = await mock_state_repo.get_record(
            sample_client_id, sample_integration.id, "vendor", "rec-1"
        )
        assert updated.internal_version_id == 4

    @pytest.mark.asyncio
    async def test_webhook_bumps_external_version(
        self,
        orchestrator,
        mock_state_repo,
        mock_integration_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """Webhook notification bumps external_version_id."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            internal_record_id="rec-1",
            external_record_id="ext-1",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=3,
            external_version_id=3,
            last_sync_version_id=3,
            created_at=now,
            updated_at=now,
        )
        await mock_state_repo.upsert_record(record)

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            record_ids=["ext-1"],
            event="updated",
            source=ChangeSourceType.WEBHOOK,
        )

        bumped, created, job = await orchestrator.handle_change_event(event)
        assert bumped == 1
        assert created == 0

        updated = await mock_state_repo.get_record_by_external_id(
            sample_client_id, sample_integration.id, "vendor", "ext-1"
        )
        assert updated.external_version_id == 4
        assert updated.internal_version_id == 3

    @pytest.mark.asyncio
    async def test_deferred_skips_sync_trigger(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """Deferred sync_trigger does not queue a sync job."""
        # Set up settings with DEFERRED (default)
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="vendor",
                    direction=SyncDirection.INBOUND,
                    sync_trigger=SyncTriggerMode.DEFERRED,
                )
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            record_ids=["new-1"],
            event="created",
            source=ChangeSourceType.PUSH,
        )

        _, _, job = await orchestrator.handle_change_event(event)
        assert job is None

    @pytest.mark.asyncio
    async def test_immediate_queues_sync(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """Immediate sync_trigger queues a sync job."""
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="vendor",
                    direction=SyncDirection.INBOUND,
                    sync_trigger=SyncTriggerMode.IMMEDIATE,
                )
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            record_ids=["rec-1"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )

        _, _, job = await orchestrator.handle_change_event(event)
        assert job is not None
        assert job.triggered_by == SyncJobTrigger.PUSH
        assert job.status == SyncJobStatus.PENDING

    @pytest.mark.asyncio
    async def test_immediate_swallows_conflict(
        self,
        orchestrator,
        mock_integration_repo,
        mock_job_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """ConflictError is swallowed when a job is already running."""
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="vendor",
                    direction=SyncDirection.INBOUND,
                    sync_trigger=SyncTriggerMode.IMMEDIATE,
                )
            ],
        )
        await mock_integration_repo.upsert_user_settings(
            sample_client_id, sample_integration.id, settings
        )

        # Create an existing running job
        now = datetime.now(UTC)
        existing_job = SyncJob(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
            started_at=now,
        )
        await mock_job_repo.create_job(existing_job)

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="vendor",
            record_ids=["rec-1"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )

        # Should not raise, should return None for job
        bumped, created, job = await orchestrator.handle_change_event(event)
        assert job is None
        # Version vectors were still bumped
        assert bumped + created > 0

    @pytest.mark.asyncio
    async def test_not_found_integration(
        self,
        orchestrator,
        sample_client_id,
    ):
        """handle_change_event raises NotFoundError for missing integration."""
        from app.core.exceptions import NotFoundError

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=uuid4(),
            entity_type="vendor",
            record_ids=["rec-1"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )

        with pytest.raises(NotFoundError):
            await orchestrator.handle_change_event(event)

    @pytest.mark.asyncio
    async def test_unsupported_entity_type(
        self,
        orchestrator,
        mock_integration_repo,
        sample_integration,
        connected_integration,
        sample_client_id,
    ):
        """handle_change_event raises SyncError for unsupported entity type."""
        from app.core.exceptions import SyncError

        event = ChangeEvent(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            entity_type="unknown_entity",
            record_ids=["rec-1"],
            event="updated",
            source=ChangeSourceType.PUSH,
        )

        with pytest.raises(SyncError, match="Unsupported entity type"):
            await orchestrator.handle_change_event(event)


# =============================================================================
# API Endpoint Tests
# =============================================================================


@pytest.fixture
def sample_integration_id():
    return uuid4()


@pytest.fixture
def api_sample_client_id():
    return uuid4()


@pytest.fixture
def mock_sync_orchestrator():
    return AsyncMock(spec=SyncOrchestrator)


@pytest.fixture
def api_test_app(
    mock_sync_orchestrator,
    api_sample_client_id,
):
    """Create a test app with only the integrations router for notify/webhook tests."""
    from app.api import integrations_router
    from app.api.integrations import get_client_id as get_client_id_integrations
    from app.api.integrations import get_integration_service
    from app.api.integrations import (
        get_sync_orchestrator as get_sync_orchestrator_integrations,
    )

    mock_integration_service = AsyncMock()
    app = FastAPI()
    app.include_router(integrations_router)

    app.dependency_overrides[get_integration_service] = lambda: mock_integration_service
    app.dependency_overrides[get_sync_orchestrator_integrations] = lambda: mock_sync_orchestrator
    app.dependency_overrides[get_client_id_integrations] = lambda: api_sample_client_id

    return app


@pytest.fixture
def api_client(api_test_app):
    return TestClient(api_test_app)


class TestNotifyEndpoint:
    """Tests for POST /{integration_id}/notify endpoint."""

    def test_notify_success(
        self,
        api_client,
        mock_sync_orchestrator,
        sample_integration_id,
    ):
        mock_sync_orchestrator.handle_change_event.return_value = (5, 2, None)

        response = api_client.post(
            f"/integrations/{sample_integration_id}/notify",
            json={
                "entity_type": "vendor",
                "record_ids": ["abc-123"],
                "event": "updated",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["records_bumped"] == 5
        assert data["records_created"] == 2
        assert data["sync_triggered"] is False
        assert data["sync_job_id"] is None

    def test_notify_with_sync_triggered(
        self,
        api_client,
        mock_sync_orchestrator,
        sample_integration_id,
    ):
        job_id = uuid4()
        now = datetime.now(UTC)
        mock_job = SyncJob(
            id=job_id,
            client_id=uuid4(),
            integration_id=sample_integration_id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.PUSH,
            created_at=now,
            updated_at=now,
        )
        mock_sync_orchestrator.handle_change_event.return_value = (1, 0, mock_job)

        response = api_client.post(
            f"/integrations/{sample_integration_id}/notify",
            json={
                "entity_type": "vendor",
                "record_ids": ["abc-123"],
                "event": "updated",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sync_triggered"] is True
        assert data["sync_job_id"] == str(job_id)

    def test_notify_not_found(
        self,
        api_client,
        mock_sync_orchestrator,
        sample_integration_id,
    ):
        from app.core.exceptions import NotFoundError

        mock_sync_orchestrator.handle_change_event.side_effect = NotFoundError(
            "Integration", sample_integration_id
        )

        response = api_client.post(
            f"/integrations/{sample_integration_id}/notify",
            json={
                "entity_type": "vendor",
                "record_ids": ["abc-123"],
                "event": "updated",
            },
        )
        assert response.status_code == 404

    def test_notify_bad_entity_type(
        self,
        api_client,
        mock_sync_orchestrator,
        sample_integration_id,
    ):
        from app.core.exceptions import SyncError

        mock_sync_orchestrator.handle_change_event.side_effect = SyncError(
            "Unsupported entity type: bad_entity"
        )

        response = api_client.post(
            f"/integrations/{sample_integration_id}/notify",
            json={
                "entity_type": "bad_entity",
                "record_ids": ["abc-123"],
                "event": "updated",
            },
        )
        assert response.status_code == 400

    def test_notify_empty_record_ids(
        self,
        api_client,
        sample_integration_id,
    ):
        response = api_client.post(
            f"/integrations/{sample_integration_id}/notify",
            json={
                "entity_type": "vendor",
                "record_ids": [],
                "event": "updated",
            },
        )
        assert response.status_code == 422


class TestWebhookEndpoint:
    """Tests for POST /{integration_id}/webhooks/{provider} endpoint."""

    def test_webhook_returns_501(
        self,
        api_client,
        sample_integration_id,
    ):
        response = api_client.post(
            f"/integrations/{sample_integration_id}/webhooks/procore",
        )
        assert response.status_code == 501
        data = response.json()
        assert "procore" in data["detail"]

    def test_webhook_returns_501_any_provider(
        self,
        api_client,
        sample_integration_id,
    ):
        response = api_client.post(
            f"/integrations/{sample_integration_id}/webhooks/quickbooks",
        )
        assert response.status_code == 501
        data = response.json()
        assert "quickbooks" in data["detail"]
