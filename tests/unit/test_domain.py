"""Unit tests for domain layer."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.entities import (
    AvailableIntegration,
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
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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
        now = datetime.now(timezone.utc)
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
