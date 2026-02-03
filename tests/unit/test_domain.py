"""Unit tests for domain layer."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import (
    IntegrationHistoryRecord,
    IntegrationStateRecord,
    SyncJob,
    SyncRule,
    UserIntegrationSettings,
)
from app.domain.enums import (
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)


class TestEnums:
    """Tests for domain enums."""

    def test_integration_status_values(self):
        """Test IntegrationStatus enum values."""
        assert IntegrationStatus.PENDING.value == "pending"
        assert IntegrationStatus.CONNECTED.value == "connected"
        assert IntegrationStatus.ERROR.value == "error"
        assert IntegrationStatus.REVOKED.value == "revoked"

    def test_sync_job_status_values(self):
        """Test SyncJobStatus enum values."""
        assert SyncJobStatus.PENDING.value == "pending"
        assert SyncJobStatus.RUNNING.value == "running"
        assert SyncJobStatus.SUCCEEDED.value == "succeeded"
        assert SyncJobStatus.FAILED.value == "failed"
        assert SyncJobStatus.CANCELLED.value == "cancelled"

    def test_record_sync_status_values(self):
        """Test RecordSyncStatus enum values."""
        assert RecordSyncStatus.PENDING.value == "pending"
        assert RecordSyncStatus.SYNCED.value == "synced"
        assert RecordSyncStatus.FAILED.value == "failed"
        assert RecordSyncStatus.CONFLICT.value == "conflict"

    def test_sync_direction_values(self):
        """Test SyncDirection enum values."""
        assert SyncDirection.INBOUND.value == "inbound"
        assert SyncDirection.OUTBOUND.value == "outbound"
        assert SyncDirection.BIDIRECTIONAL.value == "bidirectional"


class TestIntegrationStateRecord:
    """Tests for IntegrationStateRecord entity."""

    def test_is_in_sync_when_all_versions_match(self):
        """Test is_in_sync when all version IDs match."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=5,
            external_version_id=5,
            last_sync_version_id=5,
            created_at=now,
            updated_at=now,
        )
        assert record.is_in_sync is True

    def test_is_in_sync_when_versions_differ(self):
        """Test is_in_sync when version IDs differ."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.PENDING,
            internal_version_id=6,
            external_version_id=5,
            last_sync_version_id=5,
            created_at=now,
            updated_at=now,
        )
        assert record.is_in_sync is False

    def test_needs_outbound_sync(self):
        """Test needs_outbound_sync when internal is ahead."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.PENDING,
            internal_version_id=6,
            external_version_id=5,
            last_sync_version_id=5,
            created_at=now,
            updated_at=now,
        )
        assert record.needs_outbound_sync is True

    def test_needs_inbound_sync(self):
        """Test needs_inbound_sync when external is ahead."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="123",
            sync_status=RecordSyncStatus.PENDING,
            internal_version_id=5,
            external_version_id=6,
            last_sync_version_id=5,
            created_at=now,
            updated_at=now,
        )
        assert record.needs_inbound_sync is True

    def test_nullable_internal_record_id(self):
        """Test IntegrationStateRecord accepts internal_record_id=None for inbound records."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id=None,
            external_record_id="ext-456",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            internal_version_id=1,
            external_version_id=1,
            last_sync_version_id=1,
            created_at=now,
            updated_at=now,
        )
        assert record.internal_record_id is None
        assert record.external_record_id == "ext-456"
        assert record.is_in_sync is True

    def test_default_internal_record_id_is_none(self):
        """Test IntegrationStateRecord defaults internal_record_id to None."""
        now = datetime.now(UTC)
        record = IntegrationStateRecord(
            id=uuid4(),
            client_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            external_record_id="ext-789",
            sync_status=RecordSyncStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        assert record.internal_record_id is None


class TestSyncRule:
    """Tests for SyncRule entity."""

    def test_sync_rule_creation(self):
        """Test SyncRule creation with defaults."""
        rule = SyncRule(
            entity_type="bill",
            direction=SyncDirection.INBOUND,
        )
        assert rule.entity_type == "bill"
        assert rule.direction == SyncDirection.INBOUND
        assert rule.enabled is True
        assert rule.field_mappings is None

    def test_sync_rule_with_field_mappings(self):
        """Test SyncRule with field mappings."""
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            enabled=True,
            field_mappings={"internal_name": "external_name"},
        )
        assert rule.field_mappings == {"internal_name": "external_name"}


class TestUserIntegrationSettings:
    """Tests for UserIntegrationSettings entity."""

    def test_settings_creation_with_defaults(self):
        """Test settings creation with default values."""
        settings = UserIntegrationSettings()
        assert settings.sync_rules == []
        assert settings.sync_frequency is None
        assert settings.auto_sync_enabled is False

    def test_settings_with_rules(self):
        """Test settings with sync rules."""
        rules = [
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND),
            SyncRule(entity_type="vendor", direction=SyncDirection.OUTBOUND),
        ]
        settings = UserIntegrationSettings(
            sync_rules=rules,
            sync_frequency="0 */6 * * *",
            auto_sync_enabled=True,
        )
        assert len(settings.sync_rules) == 2
        assert settings.sync_frequency == "0 */6 * * *"
        assert settings.auto_sync_enabled is True


class TestSyncJob:
    """Tests for SyncJob entity."""

    def test_sync_job_creation(self):
        """Test SyncJob creation."""
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
        assert job.status == SyncJobStatus.PENDING
        assert job.job_type == SyncJobType.FULL_SYNC
        assert job.triggered_by == SyncJobTrigger.USER
        assert job.started_at is None
        assert job.completed_at is None


class TestIntegrationHistoryRecord:
    """Tests for IntegrationHistoryRecord entity."""

    def test_creation(self):
        """Test IntegrationHistoryRecord creation with required fields."""
        now = datetime.now(UTC)
        record = IntegrationHistoryRecord(
            id=uuid4(),
            client_id=uuid4(),
            state_record_id=uuid4(),
            integration_id=uuid4(),
            entity_type="bill",
            internal_record_id="int-123",
            external_record_id="ext-456",
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=SyncDirection.INBOUND,
            job_id=uuid4(),
            created_at=now,
        )
        assert record.entity_type == "bill"
        assert record.internal_record_id == "int-123"
        assert record.external_record_id == "ext-456"
        assert record.sync_status == RecordSyncStatus.SYNCED
        assert record.sync_direction == SyncDirection.INBOUND
        assert record.error_code is None
        assert record.error_message is None
        assert record.error_details is None

    def test_nullable_fields(self):
        """Test IntegrationHistoryRecord with nullable fields set to None."""
        now = datetime.now(UTC)
        record = IntegrationHistoryRecord(
            id=uuid4(),
            client_id=uuid4(),
            state_record_id=uuid4(),
            integration_id=uuid4(),
            entity_type="vendor",
            internal_record_id=None,
            external_record_id=None,
            sync_status=RecordSyncStatus.PENDING,
            sync_direction=None,
            job_id=uuid4(),
            created_at=now,
        )
        assert record.internal_record_id is None
        assert record.external_record_id is None
        assert record.sync_direction is None
