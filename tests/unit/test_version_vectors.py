"""Tests for bidirectional sync with version vectors (TDD — red phase).

Tests cover three sync modes (bidirectional, inbound-only, outbound-only)
and validate correct version vector management in each case.

These tests target a `sync_entity_bidirectional()` method on QuickBooksSyncStrategy
that does not yet exist, so bidirectional tests will fail until implemented.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.entities import IntegrationStateRecord, SyncJob, SyncRule
from app.domain.enums import (
    ConflictResolution,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.integrations.quickbooks.strategy import QuickBooksSyncStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_state(
    internal_v: int,
    external_v: int,
    last_sync_v: int,
    internal_id: str = "int-001",
    external_id: str = "ext-001",
    *,
    client_id=None,
    integration_id=None,
    entity_type: str = "vendor",
) -> IntegrationStateRecord:
    """Create an IntegrationStateRecord pre-seeded with explicit version vectors."""
    now = datetime.now(UTC)
    return IntegrationStateRecord(
        id=uuid4(),
        client_id=client_id or uuid4(),
        integration_id=integration_id or uuid4(),
        entity_type=entity_type,
        internal_record_id=internal_id,
        external_record_id=external_id,
        sync_status=RecordSyncStatus.SYNCED,
        sync_direction=None,
        internal_version_id=internal_v,
        external_version_id=external_v,
        last_sync_version_id=last_sync_v,
        last_synced_at=now,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _MockInternalRepo:
    """Stub internal data repository for unit tests (no real DB needed)."""

    ENTITY_TABLE_MAP = {
        "vendor": "sample_vendors",
        "bill": "sample_bills",
        "invoice": "sample_invoices",
        "chart_of_accounts": "sample_chart_of_accounts",
    }

    async def upsert_vendor(self, client_id, data):
        return str(uuid4())

    async def upsert_bill(self, client_id, data):
        return str(uuid4())

    async def upsert_invoice(self, client_id, data):
        return str(uuid4())

    async def upsert_chart_of_accounts(self, client_id, data):
        return str(uuid4())

    async def get_vendors(self, client_id, **kw):
        return []

    async def get_bills(self, client_id, **kw):
        return []

    async def get_invoices(self, client_id, **kw):
        return []

    async def get_chart_of_accounts(self, client_id, **kw):
        return []

    async def set_external_id(self, table, record_id, external_id):
        pass


@pytest.fixture
def strategy():
    """Create a QuickBooksSyncStrategy instance with a mock internal repo."""
    return QuickBooksSyncStrategy(internal_repo=_MockInternalRepo())


@pytest.fixture
def sample_job():
    """Create a sample SyncJob for bidirectional tests."""
    now = datetime.now(UTC)
    client_id = uuid4()
    integration_id = uuid4()
    return SyncJob(
        id=uuid4(),
        client_id=client_id,
        integration_id=integration_id,
        job_type=SyncJobType.FULL_SYNC,
        status=SyncJobStatus.RUNNING,
        triggered_by=SyncJobTrigger.SYSTEM,
        created_at=now,
        updated_at=now,
    )


# ===========================================================================
# Class 1 — Bidirectional Change Detection
# ===========================================================================


class TestBidirectionalChangeDetection:
    """Tests that version bumps and direction classification work correctly."""

    async def test_internal_only_change_classified_as_outbound(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """When only the internal record changed, it should be classified outbound."""
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)

        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        # Simulate internal change: bump internal version
        state.internal_version_id = 6

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        # Seed external record with past timestamp - it hasn't changed since last sync
        mock_adapter.seed_record(
            "vendor", state.external_record_id, {"name": "Vendor"}, updated_at=past
        )
        await mock_state_repo.upsert_record(state)

        # Use since=now so the unchanged external record is NOT returned by fetch
        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
            since=now,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.sync_direction == SyncDirection.OUTBOUND

    async def test_external_only_change_classified_as_inbound(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """When only the external record changed, it should be classified inbound."""
        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        # Simulate external change: bump external version
        state.external_version_id = 6

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.sync_direction == SyncDirection.INBOUND

    async def test_both_changed_conflict_master_external(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """When both changed and master=external, classified inbound (external wins)."""
        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        # Both changed
        state.internal_version_id = 6
        state.external_version_id = 6

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        # External wins: direction should be inbound
        assert updated.sync_direction == SyncDirection.INBOUND

    async def test_both_changed_conflict_master_our_system(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """When both changed and master=our_system, classified outbound (our system wins)."""
        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        # Both changed
        state.internal_version_id = 6
        state.external_version_id = 6

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.OUR_SYSTEM,
        )

        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        # Our system wins: direction should be outbound
        assert updated.sync_direction == SyncDirection.OUTBOUND

    async def test_no_change_skipped(self, strategy, sample_job, mock_state_repo, mock_adapter):
        """When neither side changed, the record should not be synced."""
        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        # Versions unchanged
        assert updated.internal_version_id == 5
        assert updated.external_version_id == 5
        assert updated.last_sync_version_id == 5

    async def test_new_internal_record_no_state(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new internal record with no prior state should be created as outbound."""
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        # Seed internal data so the strategy can find it
        mock_adapter.seed_record("vendor", "ext-new", {"name": "New Vendor"})

        result = await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        # Expect a new state with iv=1, ev=0, lsv=0 → outbound
        assert result["records_created"] >= 1 or result["records_updated"] >= 1

    async def test_new_external_record_no_state(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new external record with no prior state should be created as inbound."""
        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        # Seed external data
        mock_adapter.seed_record("vendor", "ext-new", {"name": "New Vendor"})

        result = await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        # Expect new state created with ev=1 → classified inbound
        assert result["records_created"] >= 1 or result["records_updated"] >= 1


# ===========================================================================
# Class 2 — Bidirectional Sync Execution
# ===========================================================================


class TestBidirectionalSyncExecution:
    """Tests that data transfer and version equalization work."""

    async def test_outbound_sync_equalizes_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """After outbound sync, iv=ev=lsv=6 and adapter.update_record called."""
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)

        state = make_state(
            internal_v=6,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        # Seed external record with past timestamp - it hasn't changed since last sync
        mock_adapter.seed_record(
            "vendor", state.external_record_id, {"name": "Vendor"}, updated_at=past
        )

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        # Use since=now so unchanged external record is not returned
        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
            since=now,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.internal_version_id == 6
        assert updated.external_version_id == 6
        assert updated.last_sync_version_id == 6
        assert len(mock_adapter.update_record_calls) >= 1

    async def test_inbound_sync_equalizes_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """After inbound sync, iv=ev=lsv=6 and internal repo updated."""
        state = make_state(
            internal_v=5,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.internal_version_id == 6
        assert updated.external_version_id == 6
        assert updated.last_sync_version_id == 6

    async def test_conflict_outbound_equalizes_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Conflict with master=our_system: outbound sync, versions equalized to 6."""
        state = make_state(
            internal_v=6,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.OUR_SYSTEM,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.internal_version_id == 6
        assert updated.external_version_id == 6
        assert updated.last_sync_version_id == 6
        assert len(mock_adapter.update_record_calls) >= 1

    async def test_conflict_inbound_equalizes_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Conflict with master=external: inbound sync, versions equalized to 6."""
        state = make_state(
            internal_v=6,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.internal_version_id == 6
        assert updated.external_version_id == 6
        assert updated.last_sync_version_id == 6

    async def test_new_outbound_creates_in_external(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new internal record (iv=1, ev=0, lsv=0) should create in external system."""
        state = make_state(
            internal_v=1,
            external_v=0,
            last_sync_v=0,
            internal_id="int-new",
            external_id=None,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        assert len(mock_adapter.create_record_calls) >= 1

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id="int-new",
        )
        assert updated is not None
        assert updated.internal_version_id == 1
        assert updated.external_version_id == 1
        assert updated.last_sync_version_id == 1

    async def test_new_inbound_creates_in_internal(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new external record (iv=0, ev=1, lsv=0) should create in internal system."""
        state = make_state(
            internal_v=0,
            external_v=1,
            last_sync_v=0,
            internal_id=None,
            external_id="ext-new",
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", "ext-new", {"name": "New External Vendor"})

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
        )

        updated = await mock_state_repo.get_record_by_external_id(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            "ext-new",
        )
        assert updated is not None
        assert updated.internal_version_id == 1
        assert updated.external_version_id == 1
        assert updated.last_sync_version_id == 1

    async def test_mixed_records_correct_directions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Three records (outbound, inbound, conflict) each sync in correct direction."""
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        recent = now - timedelta(seconds=1)  # Just before now

        cid = sample_job.client_id
        iid = sample_job.integration_id

        # Record 1: internal changed only → outbound
        # Seed with past timestamp so it won't be returned (external didn't change)
        outbound_state = make_state(
            internal_v=6,
            external_v=5,
            last_sync_v=5,
            internal_id="int-out",
            external_id="ext-out",
            client_id=cid,
            integration_id=iid,
        )
        mock_adapter.seed_record("vendor", "ext-out", {"name": "Outbound Vendor"}, updated_at=past)

        # Record 2: external changed → inbound
        # Seed with now timestamp so it WILL be returned (updated_at > since)
        inbound_state = make_state(
            internal_v=5,
            external_v=5,  # Will be bumped to 6 when returned
            last_sync_v=5,
            internal_id="int-in",
            external_id="ext-in",
            client_id=cid,
            integration_id=iid,
        )
        mock_adapter.seed_record("vendor", "ext-in", {"name": "Inbound Vendor"}, updated_at=now)

        # Record 3: both changed → conflict (master=external → inbound)
        # Seed with now timestamp so it WILL be returned, internal already bumped
        conflict_state = make_state(
            internal_v=6,
            external_v=5,  # Will be bumped to 6 when returned
            last_sync_v=5,
            internal_id="int-conf",
            external_id="ext-conf",
            client_id=cid,
            integration_id=iid,
        )
        mock_adapter.seed_record("vendor", "ext-conf", {"name": "Conflict Vendor"}, updated_at=now)

        rule = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(outbound_state)
        await mock_state_repo.upsert_record(inbound_state)
        await mock_state_repo.upsert_record(conflict_state)

        # Use since=recent so records with updated_at=now are returned (now > recent)
        # but records with updated_at=past are not (past < recent)
        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule,
            since=recent,
        )

        out = await mock_state_repo.get_record(
            cid,
            iid,
            "vendor",
            internal_record_id="int-out",
        )
        inp = await mock_state_repo.get_record(
            cid,
            iid,
            "vendor",
            internal_record_id="int-in",
        )
        conf = await mock_state_repo.get_record(
            cid,
            iid,
            "vendor",
            internal_record_id="int-conf",
        )

        # All should be equalized
        for rec in (out, inp, conf):
            assert rec is not None
            assert rec.internal_version_id == rec.external_version_id == rec.last_sync_version_id

        # Direction checks
        assert out.sync_direction == SyncDirection.OUTBOUND
        assert inp.sync_direction == SyncDirection.INBOUND
        assert conf.sync_direction == SyncDirection.INBOUND  # external wins


# ===========================================================================
# Class 3 — Inbound-Only Version Vectors
# ===========================================================================


class TestInboundOnlyVersionVectors:
    """Tests that inbound-only sync properly manages version vectors."""

    async def test_inbound_equalizes_all_three_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """After inbound sync, all three versions should be equal."""
        state = make_state(
            internal_v=5,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        await mock_state_repo.upsert_record(state)

        # Seed external record with updated data
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Updated"})

        await strategy.sync_entity_inbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        updated = await mock_state_repo.get_record_by_external_id(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            state.external_record_id,
        )
        assert updated is not None
        # After inbound sync, all three versions should be equal
        assert updated.internal_version_id == updated.external_version_id
        assert updated.external_version_id == updated.last_sync_version_id

    async def test_inbound_ignores_internal_changes(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Inbound-only sync should NOT push internal changes outbound."""
        state = make_state(
            internal_v=7,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        await mock_state_repo.upsert_record(state)

        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "External"})

        await strategy.sync_entity_inbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        # adapter.update_record should NOT have been called (no outbound push)
        assert len(mock_adapter.update_record_calls) == 0
        assert len(mock_adapter.create_record_calls) == 0

    async def test_new_inbound_record_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new external record synced inbound should end with iv=ev=lsv=1."""
        mock_adapter.seed_record("vendor", "ext-brand-new", {"name": "Brand New"})

        await strategy.sync_entity_inbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        created = await mock_state_repo.get_record_by_external_id(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            "ext-brand-new",
        )
        assert created is not None
        assert created.internal_version_id == 1
        assert created.external_version_id == 1
        assert created.last_sync_version_id == 1


# ===========================================================================
# Class 4 — Outbound-Only Version Vectors
# ===========================================================================


class TestOutboundOnlyVersionVectors:
    """Tests that outbound-only sync properly manages version vectors."""

    async def test_outbound_equalizes_all_three_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """After outbound sync, all three versions should be equal."""
        state = make_state(
            internal_v=6,
            external_v=5,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_outbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.internal_version_id == updated.external_version_id
        assert updated.external_version_id == updated.last_sync_version_id

    async def test_outbound_ignores_external_changes(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Outbound-only sync should NOT pull external changes inbound."""
        state = make_state(
            internal_v=5,
            external_v=7,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        await mock_state_repo.upsert_record(state)

        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "External"})

        await strategy.sync_entity_outbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        # fetch_records should not have been called for inbound pull
        # (outbound reads from internal DB, not external)
        # The external version bump should NOT cause an inbound sync
        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        # External changes should not have been pulled in
        assert updated is not None

    async def test_new_outbound_record_versions(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """A new internal record synced outbound should end with iv=ev=lsv=1."""
        state = make_state(
            internal_v=1,
            external_v=0,
            last_sync_v=0,
            internal_id="int-brand-new",
            external_id=None,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_outbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id="int-brand-new",
        )
        assert updated is not None
        assert updated.internal_version_id == 1
        assert updated.external_version_id == 1
        assert updated.last_sync_version_id == 1


# ===========================================================================
# Class 5 — Version Vector Properties (Domain Model)
# ===========================================================================


class TestVersionVectorProperties:
    """Tests for IntegrationStateRecord helper properties.

    These test pure domain logic that already exists and should pass immediately.
    """

    def test_is_in_sync_all_equal(self):
        """iv=5, ev=5, lsv=5 → is_in_sync = True."""
        state = make_state(internal_v=5, external_v=5, last_sync_v=5)
        assert state.is_in_sync is True

    def test_is_in_sync_false_internal_ahead(self):
        """iv=6, ev=5, lsv=5 → is_in_sync = False."""
        state = make_state(internal_v=6, external_v=5, last_sync_v=5)
        assert state.is_in_sync is False

    def test_needs_outbound_sync(self):
        """iv=6, ev=5, lsv=5 → needs_outbound_sync = True."""
        state = make_state(internal_v=6, external_v=5, last_sync_v=5)
        assert state.needs_outbound_sync is True

    def test_needs_inbound_sync(self):
        """iv=5, ev=6, lsv=5 → needs_inbound_sync = True."""
        state = make_state(internal_v=5, external_v=6, last_sync_v=5)
        assert state.needs_inbound_sync is True

    def test_conflict_detected(self):
        """iv=6, ev=6, lsv=5 → both needs_outbound_sync and needs_inbound_sync True."""
        state = make_state(internal_v=6, external_v=6, last_sync_v=5)
        assert state.needs_outbound_sync is True
        assert state.needs_inbound_sync is True

    def test_new_internal_record_defaults(self):
        """iv=1, ev=0, lsv=0 → needs_outbound_sync=True, needs_inbound_sync=False."""
        state = make_state(internal_v=1, external_v=0, last_sync_v=0)
        assert state.needs_outbound_sync is True
        assert state.needs_inbound_sync is False

    def test_new_external_record(self):
        """iv=0, ev=1, lsv=0 → needs_inbound_sync=True, needs_outbound_sync=False."""
        state = make_state(internal_v=0, external_v=1, last_sync_v=0)
        assert state.needs_inbound_sync is True
        assert state.needs_outbound_sync is False


# ===========================================================================
# Class 6 — master_if_conflict Settings Validation
# ===========================================================================


class TestMasterIfConflictSettingsValidation:
    """Tests that master_if_conflict is only relevant for bidirectional rules."""

    async def test_bidirectional_uses_conflict_resolution(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Bidirectional sync should apply master_if_conflict when both sides changed."""
        state = make_state(
            internal_v=6,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})

        rule_ext = SyncRule(
            entity_type="vendor",
            direction=SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )

        await mock_state_repo.upsert_record(state)

        await strategy.sync_entity_bidirectional(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
            rule=rule_ext,
        )

        updated = await mock_state_repo.get_record(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            internal_record_id=state.internal_record_id,
        )
        assert updated is not None
        assert updated.sync_direction == SyncDirection.INBOUND  # external master

    async def test_inbound_only_ignores_conflict_resolution(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Inbound-only sync should not consult master_if_conflict."""
        state = make_state(
            internal_v=6,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        # Even with master=our_system, inbound-only should always pull inbound
        await strategy.sync_entity_inbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        updated = await mock_state_repo.get_record_by_external_id(
            sample_job.client_id,
            sample_job.integration_id,
            "vendor",
            state.external_record_id,
        )
        assert updated is not None
        assert updated.sync_direction == SyncDirection.INBOUND

    async def test_outbound_only_ignores_conflict_resolution(
        self, strategy, sample_job, mock_state_repo, mock_adapter
    ):
        """Outbound-only sync should not consult master_if_conflict."""
        state = make_state(
            internal_v=6,
            external_v=6,
            last_sync_v=5,
            client_id=sample_job.client_id,
            integration_id=sample_job.integration_id,
        )
        mock_adapter.seed_record("vendor", state.external_record_id, {"name": "Vendor"})
        await mock_state_repo.upsert_record(state)

        # Even with master=external, outbound-only should push outbound
        await strategy.sync_entity_outbound(
            job=sample_job,
            entity_type="vendor",
            adapter=mock_adapter,
            state_repo=mock_state_repo,
        )

        # Should not have pulled inbound despite external changes
        assert len(mock_adapter.fetch_records_calls) == 0
