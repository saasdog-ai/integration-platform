"""Unit tests for services layer."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities import (
    AvailableIntegration,
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
from app.services.settings_service import SettingsService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)


class TestSettingsService:
    """Tests for SettingsService."""

    @pytest.fixture
    def repo(self) -> MockIntegrationRepository:
        """Create mock repository."""
        repo = MockIntegrationRepository()
        yield repo
        repo.clear()

    @pytest.fixture
    def service(self, repo: MockIntegrationRepository) -> SettingsService:
        """Create settings service with mock repository."""
        return SettingsService(integration_repo=repo)

    @pytest.fixture
    def integration(self, repo: MockIntegrationRepository) -> AvailableIntegration:
        """Create test integration."""
        return repo.seed_available_integration(
            name="Test Integration",
            type="erp",
            supported_entities=["bill", "invoice", "vendor"],
        )

    @pytest.mark.asyncio
    async def test_get_user_settings_returns_defaults(
        self,
        service: SettingsService,
        integration: AvailableIntegration,
    ):
        """Test getting user settings returns defaults when none exist."""
        client_id = uuid4()
        settings = await service.get_user_settings(client_id, integration.id)

        assert settings is not None
        assert len(settings.sync_rules) == 3  # All supported entities
        assert all(not rule.enabled for rule in settings.sync_rules)
        assert settings.auto_sync_enabled is False

    @pytest.mark.asyncio
    async def test_update_user_settings(
        self,
        service: SettingsService,
        integration: AvailableIntegration,
    ):
        """Test updating user settings."""
        client_id = uuid4()
        new_settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="bill",
                    direction=SyncDirection.INBOUND,
                    enabled=True,
                ),
            ],
            sync_frequency="0 */6 * * *",
            auto_sync_enabled=True,
        )

        updated = await service.update_user_settings(client_id, integration.id, new_settings)

        assert updated.auto_sync_enabled is True
        assert len(updated.sync_rules) == 1
        assert updated.sync_rules[0].entity_type == "bill"

    @pytest.mark.asyncio
    async def test_update_settings_validates_entity_types(
        self,
        service: SettingsService,
        integration: AvailableIntegration,
    ):
        """Test that invalid entity types are rejected."""
        from app.core.exceptions import ValidationError

        client_id = uuid4()
        invalid_settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="invalid_entity",
                    direction=SyncDirection.INBOUND,
                    enabled=True,
                ),
            ],
        )

        with pytest.raises(ValidationError) as exc_info:
            await service.update_user_settings(client_id, integration.id, invalid_settings)

        assert "invalid_entity" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_settings_validates_cron_expression(
        self,
        service: SettingsService,
        integration: AvailableIntegration,
    ):
        """Test that invalid cron expressions are rejected."""
        from app.core.exceptions import ValidationError

        client_id = uuid4()
        invalid_settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(
                    entity_type="bill",
                    direction=SyncDirection.INBOUND,
                    enabled=True,
                ),
            ],
            sync_frequency="invalid cron",  # Invalid
        )

        with pytest.raises(ValidationError) as exc_info:
            await service.update_user_settings(client_id, integration.id, invalid_settings)

        assert "cron" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_enabled_sync_rules(
        self,
        service: SettingsService,
        repo: MockIntegrationRepository,
        integration: AvailableIntegration,
    ):
        """Test getting only enabled sync rules."""
        client_id = uuid4()

        # Set up settings with mixed enabled/disabled rules
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
                SyncRule(entity_type="invoice", direction=SyncDirection.OUTBOUND, enabled=False),
                SyncRule(entity_type="vendor", direction=SyncDirection.BIDIRECTIONAL, enabled=True),
            ],
        )
        await repo.upsert_user_settings(client_id, integration.id, settings)

        enabled_rules = await service.get_enabled_sync_rules(client_id, integration.id)

        assert len(enabled_rules) == 2
        assert all(rule.enabled for rule in enabled_rules)
        entity_types = {rule.entity_type for rule in enabled_rules}
        assert entity_types == {"bill", "vendor"}


class TestMockRepositories:
    """Tests for mock repository implementations."""

    @pytest.mark.asyncio
    async def test_mock_integration_repo_seed_and_get(self):
        """Test seeding and retrieving integrations."""
        repo = MockIntegrationRepository()
        integration = repo.seed_available_integration(
            name="Test", type="erp", supported_entities=["bill"]
        )

        retrieved = await repo.get_available_integration(integration.id)
        assert retrieved is not None
        assert retrieved.name == "Test"
        assert retrieved.type == "erp"

    @pytest.mark.asyncio
    async def test_mock_integration_repo_user_integration(self):
        """Test user integration CRUD."""
        repo = MockIntegrationRepository()
        client_id = uuid4()
        integration = repo.seed_available_integration("Test", "erp")

        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration.id,
            status=IntegrationStatus.CONNECTED,
            created_at=now,
            updated_at=now,
        )

        created = await repo.create_user_integration(user_integration)
        assert created.id == user_integration.id

        retrieved = await repo.get_user_integration(client_id, integration.id)
        assert retrieved is not None
        assert retrieved.status == IntegrationStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_mock_sync_job_repo_create_and_update(self):
        """Test sync job create and status update."""
        repo = MockSyncJobRepository()
        now = datetime.now(UTC)

        job = SyncJob(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )

        created = await repo.create_job(job)
        assert created.status == SyncJobStatus.PENDING

        updated = await repo.update_job_status(
            job.id,
            SyncJobStatus.RUNNING,
        )
        assert updated.status == SyncJobStatus.RUNNING
        assert updated.started_at is not None

    @pytest.mark.asyncio
    async def test_mock_sync_job_repo_get_running_jobs(self):
        """Test getting running jobs."""
        repo = MockSyncJobRepository()
        client_id = uuid4()
        integration_id = uuid4()
        now = datetime.now(UTC)

        # Create two jobs, one running
        job1 = SyncJob(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            job_type=SyncJobType.FULL_SYNC,
            status=SyncJobStatus.RUNNING,
            triggered_by=SyncJobTrigger.USER,
            created_at=now,
            updated_at=now,
        )
        job2 = SyncJob(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            job_type=SyncJobType.INCREMENTAL,
            status=SyncJobStatus.PENDING,
            triggered_by=SyncJobTrigger.SCHEDULER,
            created_at=now,
            updated_at=now,
        )

        await repo.create_job(job1)
        await repo.create_job(job2)

        running = await repo.get_running_jobs(client_id, integration_id)
        assert len(running) == 1
        assert running[0].id == job1.id


class TestMockIntegrationStateRepository:
    """Tests for MockIntegrationStateRepository."""

    @pytest.mark.asyncio
    async def test_upsert_and_get_record(self):
        """Test upserting and retrieving a record."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)

        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.PENDING,
            internal_version_id=1,
            external_version_id=0,
            last_sync_version_id=0,
            created_at=now,
            updated_at=now,
        )

        await repo.upsert_record(record)

        retrieved = await repo.get_record(
            record.client_id,
            record.integration_id,
            record.entity_type,
            record.internal_record_id,
        )
        assert retrieved is not None
        assert retrieved.sync_status == RecordSyncStatus.PENDING

    @pytest.mark.asyncio
    async def test_mark_synced(self):
        """Test marking a record as synced."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)

        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.PENDING,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=0,
            created_at=now,
            updated_at=now,
        )

        await repo.upsert_record(record)
        await repo.mark_synced(record.id, record.client_id, "ext-123")

        updated = await repo.get_record(
            record.client_id,
            record.integration_id,
            record.entity_type,
            record.internal_record_id,
        )
        assert updated.sync_status == RecordSyncStatus.SYNCED
        assert updated.external_record_id == "ext-123"
        assert updated.last_sync_version_id == 1

    @pytest.mark.asyncio
    async def test_get_record_by_external_id(self):
        """Test retrieving a record by external ID."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        integration_id = uuid4()

        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="bill",
            internal_record_id=None,
            external_record_id="ext-100",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )

        await repo.upsert_record(record)

        retrieved = await repo.get_record_by_external_id(
            client_id, integration_id, "bill", "ext-100"
        )
        assert retrieved is not None
        assert retrieved.external_record_id == "ext-100"
        assert retrieved.internal_record_id is None

        # get_record with None internal_record_id returns None
        not_found = await repo.get_record(client_id, integration_id, "bill", None)
        assert not_found is None

    @pytest.mark.asyncio
    async def test_upsert_dedup_by_external_id(self):
        """Test that upsert deduplicates by external ID when internal ID is None."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        integration_id = uuid4()
        record_id = uuid4()

        # Insert initial record with no internal ID
        record = IntegrationStateRecord(
            id=record_id,
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id=None,
            external_record_id="ext-vendor-1",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        await repo.upsert_record(record)

        # Upsert again with same external ID — should update, not duplicate
        updated_record = IntegrationStateRecord(
            id=uuid4(),  # Different ID, but same external_record_id
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id=None,
            external_record_id="ext-vendor-1",
            sync_status=RecordSyncStatus.PENDING,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=2,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        result = await repo.upsert_record(updated_record)

        assert result.id == record_id  # Should update the original record
        assert result.external_version_id == 2
        assert result.sync_status == RecordSyncStatus.PENDING

        # Should still be only one record
        all_records = [
            r
            for r in repo._records.values()
            if r.client_id == client_id and r.entity_type == "vendor"
        ]
        assert len(all_records) == 1

    @pytest.mark.asyncio
    async def test_upsert_backfill_internal_record_id(self):
        """Test that upsert backfills internal_record_id when newly known."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        integration_id = uuid4()

        # Insert with no internal ID (inbound record not yet written internally)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="bill",
            internal_record_id=None,
            external_record_id="ext-bill-1",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        await repo.upsert_record(record)

        # Now backfill with the internal ID after internal write succeeds
        backfill_record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="bill",
            internal_record_id="internal-bill-1",
            external_record_id="ext-bill-1",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        result = await repo.upsert_record(backfill_record)

        assert result.internal_record_id == "internal-bill-1"
        assert result.external_record_id == "ext-bill-1"

        # Should be retrievable by internal ID now
        by_internal = await repo.get_record(client_id, integration_id, "bill", "internal-bill-1")
        assert by_internal is not None
        assert by_internal.external_record_id == "ext-bill-1"


class TestUpsertGuard:
    """Tests for upsert guard — internal_record_id must not be nulled out."""

    @pytest.mark.asyncio
    async def test_upsert_does_not_clear_internal_record_id(self):
        """Re-syncing with internal_record_id=None must preserve the original."""
        from app.domain.entities import IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        integration_id = uuid4()

        # Create record with both IDs set
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="bill",
            internal_record_id="int-100",
            external_record_id="ext-200",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        await repo.upsert_record(record)

        # Re-sync: same external_record_id but internal_record_id=None
        resync_record = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="bill",
            internal_record_id=None,
            external_record_id="ext-200",
            sync_status=RecordSyncStatus.PENDING,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=2,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        result = await repo.upsert_record(resync_record)

        # internal_record_id must NOT be nulled out
        assert result.internal_record_id == "int-100"
        assert result.external_record_id == "ext-200"
        assert result.external_version_id == 2


class TestIntegrationHistory:
    """Tests for integration history methods."""

    @pytest.mark.asyncio
    async def test_batch_create_and_get_history(self):
        """Create multiple history entries and retrieve by job ID."""
        from app.domain.entities import IntegrationHistoryRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        job_id = uuid4()

        entries = [
            IntegrationHistoryRecord(
                id=uuid4(),
                client_id=client_id,
                state_record_id=uuid4(),
                integration_id=uuid4(),
                entity_type="bill",
                internal_record_id=f"int-{i}",
                external_record_id=f"ext-{i}",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                job_id=job_id,
                created_at=now,
            )
            for i in range(5)
        ]

        await repo.batch_create_history(entries)

        records, total = await repo.get_history_by_job_id(client_id, job_id)
        assert total == 5
        assert len(records) == 5

    @pytest.mark.asyncio
    async def test_history_entries_survive_state_overwrite(self):
        """
        Job A creates state + history. Job B overwrites state.
        Job A's history should still be intact.
        """
        from app.domain.entities import IntegrationHistoryRecord, IntegrationStateRecord
        from app.domain.enums import RecordSyncStatus, SyncDirection

        repo = MockIntegrationStateRepository()
        now = datetime.now(UTC)
        client_id = uuid4()
        integration_id = uuid4()
        job_a_id = uuid4()
        job_b_id = uuid4()

        # Job A: create state record + history
        state = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id=None,
            external_record_id="ext-v1",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            last_job_id=job_a_id,
            created_at=now,
            updated_at=now,
        )
        await repo.upsert_record(state)

        history_a = IntegrationHistoryRecord(
            id=uuid4(),
            client_id=client_id,
            state_record_id=state.id,
            integration_id=integration_id,
            entity_type="vendor",
            external_record_id="ext-v1",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            job_id=job_a_id,
            created_at=now,
        )
        await repo.create_history_entry(history_a)

        # Job B: overwrite state record's last_job_id
        state_update = IntegrationStateRecord(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            entity_type="vendor",
            internal_record_id=None,
            external_record_id="ext-v1",
            sync_status=RecordSyncStatus.PENDING,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=2,
            last_sync_version_id=1,
            last_job_id=job_b_id,
            created_at=now,
            updated_at=now,
        )
        await repo.upsert_record(state_update)

        # State table now points to job B
        state_records, state_total = await repo.get_records_by_job_id(client_id, job_a_id)
        assert state_total == 0  # State overwritten by job B

        # But history for job A is still there
        history_records, history_total = await repo.get_history_by_job_id(client_id, job_a_id)
        assert history_total == 1
        assert history_records[0].job_id == job_a_id
        assert history_records[0].sync_status == RecordSyncStatus.SYNCED
