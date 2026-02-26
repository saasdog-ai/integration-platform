"""End-to-end integration tests for vendor sync: outbound → inbound → bidirectional.

Exercises the full orchestrator → strategy pipeline using mock infrastructure
(mock adapter, mock repos, mock encryption). No real database or QBO calls.

Each test phase operates on the *same* vendor, chained so state carries over:
  Phase 1  Set direction=OUTBOUND, modify vendor internally, sync → pushed to QBO.
  Phase 2  Set direction=INBOUND, modify vendor in QBO, sync → pulled to our DB.
  Phase 3  Set direction=BIDIRECTIONAL (master=EXTERNAL), modify BOTH sides,
           sync → QBO version wins.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.entities import (
    AvailableIntegration,
    ConnectionConfig,
    IntegrationStateRecord,
    SyncJob,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    ConflictResolution,
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobType,
)
from app.infrastructure.queue.memory_queue import InMemoryQueue
from app.integrations.quickbooks.strategy import QuickBooksSyncStrategy
from app.services.sync_orchestrator import SyncOrchestrator, register_sync_strategy
from tests.mocks.adapters import MockAdapterFactory, MockIntegrationAdapter
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEGRATION_ID = UUID("11111111-1111-1111-1111-111111111111")
CLIENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ---------------------------------------------------------------------------
# Mock internal repo (same as in unit tests)
# ---------------------------------------------------------------------------


class _MockInternalRepo:
    """Fake internal DB so the strategy never touches a real database."""

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


class _TestableStrategy(QuickBooksSyncStrategy):
    """Strategy subclass that uses a mock internal repo."""

    def __init__(self) -> None:
        super().__init__(internal_repo=_MockInternalRepo())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _banner(text: str) -> None:
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}")


def _section(text: str) -> None:
    print(f"\n>>> {text}\n{'-' * 50}")


def _show_state(label: str, state: IntegrationStateRecord) -> None:
    print(f"  [{label}]")
    print(f"    internal_record_id : {state.internal_record_id}")
    print(f"    external_record_id : {state.external_record_id}")
    print(
        f"    iv / ev / lsv      : {state.internal_version_id} / {state.external_version_id} / {state.last_sync_version_id}"
    )
    print(f"    sync_status        : {state.sync_status.value}")
    print(
        f"    sync_direction     : {state.sync_direction.value if state.sync_direction else None}"
    )
    print(f"    is_in_sync         : {state.is_in_sync}")
    print(f"    metadata.data.name : {(state.metadata or {}).get('data', {}).get('name', 'N/A')}")


def _show_job(job: SyncJob) -> None:
    print(f"  Job {job.id}")
    print(f"    status             : {job.status.value}")
    print(f"    entities_processed : {json.dumps(job.entities_processed, indent=6, default=str)}")


# ---------------------------------------------------------------------------
# Fixture: full mock infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture
async def infra():
    """Set up mock infrastructure and wire the orchestrator."""
    now = datetime.now(UTC)

    # Repos
    integration_repo = MockIntegrationRepository()
    job_repo = MockSyncJobRepository()
    state_repo = MockIntegrationStateRepository()
    encryption_service = MockEncryptionService()
    queue = InMemoryQueue()

    # Register QBO integration
    qbo = AvailableIntegration(
        id=INTEGRATION_ID,
        name="QuickBooks Online",
        type="erp",
        description="QuickBooks Online",
        supported_entities=["vendor", "bill", "invoice", "chart_of_accounts"],
        connection_config=ConnectionConfig(
            authorization_url="https://example.com/auth",
            token_url="https://example.com/token",
            scopes=["accounting"],
        ),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    integration_repo._available_integrations[INTEGRATION_ID] = qbo

    # Create user integration (connected)
    creds = json.dumps({"access_token": "mock_token", "refresh_token": "mock_rt"}).encode()
    enc_creds, key_id = await encryption_service.encrypt(creds)

    user_integration = UserIntegration(
        id=uuid4(),
        client_id=CLIENT_ID,
        integration_id=INTEGRATION_ID,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=enc_creds,
        credentials_key_id=key_id,
        external_account_id="realm-test-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
    )
    await integration_repo.create_user_integration(user_integration)

    # Mock adapter factory — use a shared adapter so test can inspect/modify it
    adapter = MockIntegrationAdapter(integration_name="QuickBooks Online")
    adapter_factory = MockAdapterFactory()
    adapter_factory.register_adapter("QuickBooks Online", adapter)

    # Register the testable strategy (with mock internal repo)
    register_sync_strategy("QuickBooks Online", _TestableStrategy)

    orchestrator = SyncOrchestrator(
        integration_repo=integration_repo,
        job_repo=job_repo,
        state_repo=state_repo,
        queue=queue,
        encryption_service=encryption_service,
        adapter_factory=adapter_factory,
    )

    return {
        "orchestrator": orchestrator,
        "integration_repo": integration_repo,
        "job_repo": job_repo,
        "state_repo": state_repo,
        "adapter": adapter,
        "now": now,
    }


async def _update_vendor_settings(
    integration_repo: MockIntegrationRepository,
    direction: SyncDirection,
    master_if_conflict: ConflictResolution = ConflictResolution.EXTERNAL,
) -> None:
    """Helper: upsert vendor sync rule with the given direction."""
    settings = UserIntegrationSettings(
        sync_rules=[
            SyncRule(
                entity_type="vendor",
                direction=direction,
                enabled=True,
                master_if_conflict=master_if_conflict,
            ),
        ],
        sync_frequency="manual",
        auto_sync_enabled=False,
    )
    await integration_repo.upsert_user_settings(CLIENT_ID, INTEGRATION_ID, settings)


async def _create_and_execute_job(
    orchestrator: SyncOrchestrator,
    job_repo: MockSyncJobRepository,
) -> SyncJob:
    """Helper: create a sync job and execute it immediately."""
    now = datetime.now(UTC)
    job = SyncJob(
        id=uuid4(),
        client_id=CLIENT_ID,
        integration_id=INTEGRATION_ID,
        job_type=SyncJobType.FULL_SYNC,
        status=SyncJobStatus.PENDING,
        triggered_by="user",
        job_params={"entity_types": ["vendor"]},
        created_at=now,
        updated_at=now,
    )
    await job_repo.create_job(job)
    return await orchestrator.execute_sync_job(job)


# ---------------------------------------------------------------------------
# THE TEST: three phases on one vendor
# ---------------------------------------------------------------------------


class TestVendorSyncLifecycle:
    """Full lifecycle: outbound → inbound → bidirectional (external wins)."""

    @pytest.mark.asyncio
    async def test_phase1_outbound_sync(self, infra):
        """Set vendors to OUTBOUND. Modify a vendor internally. Sync pushes to QBO."""
        _banner("PHASE 1 — OUTBOUND SYNC")
        orchestrator = infra["orchestrator"]
        integration_repo = infra["integration_repo"]
        job_repo = infra["job_repo"]
        state_repo = infra["state_repo"]
        adapter = infra["adapter"]
        now = infra["now"]

        # 1. Configure: vendor direction = OUTBOUND
        _section("Configure vendor sync: OUTBOUND")
        await _update_vendor_settings(integration_repo, SyncDirection.OUTBOUND)
        print("  Settings updated: vendor → outbound")

        # 2. Simulate: vendor modified in our DB
        #    Create a state record with iv > lsv (needs outbound)
        _section("Simulate internal vendor modification")
        vendor_internal_id = str(uuid4())
        vendor_data = {
            "name": "Acme Manufacturing Co.",
            "email_address": "accounts@acme.com",
            "phone": "(555) 123-4567",
            "status": "ACTIVE",
        }
        state = IntegrationStateRecord(
            id=uuid4(),
            client_id=CLIENT_ID,
            integration_id=INTEGRATION_ID,
            entity_type="vendor",
            internal_record_id=vendor_internal_id,
            external_record_id=None,  # Never synced before
            sync_status=RecordSyncStatus.SYNCED,
            sync_direction=None,
            internal_version_id=2,  # Internal changed
            external_version_id=1,
            last_sync_version_id=1,  # Last sync was at v1
            last_synced_at=None,
            metadata={"data": vendor_data},
            created_at=now,
            updated_at=now,
        )
        await state_repo.upsert_record(state)
        _show_state("Before sync", state)
        assert state.needs_outbound_sync is True

        # 3. Run sync
        _section("Execute outbound sync job")
        job = await _create_and_execute_job(orchestrator, job_repo)
        _show_job(job)

        # 4. Verify
        _section("Verify results")
        updated = await state_repo.get_record(
            CLIENT_ID,
            INTEGRATION_ID,
            "vendor",
            internal_record_id=vendor_internal_id,
        )
        assert updated is not None, "State record should still exist"
        _show_state("After sync", updated)

        # Vendor was pushed to QBO (create, since no external_record_id)
        assert len(adapter.create_record_calls) == 1, "Should have created record in QBO"
        assert adapter.create_record_calls[0][0] == "vendor"
        print(
            f"  Adapter calls: create={len(adapter.create_record_calls)}, update={len(adapter.update_record_calls)}"
        )

        # External record ID should be set
        assert updated.external_record_id is not None, "External ID should be assigned"
        print(f"  External record ID assigned: {updated.external_record_id}")

        # Version vectors equalized
        assert (
            updated.internal_version_id
            == updated.external_version_id
            == updated.last_sync_version_id
        )
        print(f"  Version vectors equalized: iv=ev=lsv={updated.internal_version_id}")

        # Direction is OUTBOUND
        assert updated.sync_direction == SyncDirection.OUTBOUND
        assert updated.sync_status == RecordSyncStatus.SYNCED
        assert updated.is_in_sync is True

        # Job succeeded
        assert job.status == SyncJobStatus.SUCCEEDED
        print("\n  ✓ Phase 1 PASSED: vendor synced outbound to QBO")

        # Return state for next phase
        return updated

    @pytest.mark.asyncio
    async def test_phase2_inbound_sync(self, infra):
        """Set vendors to INBOUND. Modify vendor in QBO. Sync pulls to our DB."""
        # First run phase 1 to get the vendor into synced state
        updated = await self.test_phase1_outbound_sync(infra)

        _banner("PHASE 2 — INBOUND SYNC")
        orchestrator = infra["orchestrator"]
        integration_repo = infra["integration_repo"]
        job_repo = infra["job_repo"]
        state_repo = infra["state_repo"]
        adapter = infra["adapter"]

        # 1. Configure: vendor direction = INBOUND
        _section("Configure vendor sync: INBOUND")
        await _update_vendor_settings(integration_repo, SyncDirection.INBOUND)
        print("  Settings updated: vendor → inbound")

        # 2. Simulate: vendor modified in QBO
        _section("Simulate QBO vendor modification")
        qbo_vendor_data = {
            "name": "Acme Manufacturing Co. (Updated in QBO)",
            "email_address": "billing@acme.com",
            "phone": "(555) 999-8888",
            "status": "ACTIVE",
            "DisplayName": "Acme Manufacturing Co. (Updated in QBO)",
        }
        # Seed/update the record in the mock adapter
        adapter.seed_record("vendor", updated.external_record_id, qbo_vendor_data)
        print(f"  Modified vendor in mock QBO: {updated.external_record_id}")
        print(f"  New name: {qbo_vendor_data['name']}")

        # Record version vectors before sync
        v_before = (
            updated.internal_version_id,
            updated.external_version_id,
            updated.last_sync_version_id,
        )
        print(f"  Version vectors before: iv={v_before[0]}, ev={v_before[1]}, lsv={v_before[2]}")

        # 3. Run sync
        _section("Execute inbound sync job")
        job = await _create_and_execute_job(orchestrator, job_repo)
        _show_job(job)

        # 4. Verify
        _section("Verify results")
        after = await state_repo.get_record_by_external_id(
            CLIENT_ID,
            INTEGRATION_ID,
            "vendor",
            updated.external_record_id,
        )
        assert after is not None, "State record should still exist"
        _show_state("After sync", after)

        # Direction is INBOUND
        assert after.sync_direction == SyncDirection.INBOUND
        assert after.sync_status == RecordSyncStatus.SYNCED

        # Version vectors equalized (bumped by 1 from before)
        assert after.internal_version_id == after.external_version_id == after.last_sync_version_id
        assert after.internal_version_id > v_before[0], "Versions should have bumped"
        print(f"  Version vectors equalized: iv=ev=lsv={after.internal_version_id}")

        # Metadata updated with QBO data
        after_name = (after.metadata or {}).get("data", {}).get("name", "")
        assert "Updated in QBO" in after_name, (
            f"Metadata should reflect QBO change, got: {after_name}"
        )
        print(f"  Metadata updated: name={after_name}")

        assert after.is_in_sync is True

        # Job succeeded
        assert job.status == SyncJobStatus.SUCCEEDED
        print("\n  ✓ Phase 2 PASSED: vendor synced inbound from QBO")

        return after

    @pytest.mark.asyncio
    async def test_phase3_bidirectional_external_wins(self, infra):
        """Set vendors to BIDIRECTIONAL (master=EXTERNAL). Both sides changed. QBO wins."""
        # Run phases 1 + 2 first to get the vendor into a clean synced state
        after_inbound = await self.test_phase2_inbound_sync(infra)

        _banner("PHASE 3 — BIDIRECTIONAL SYNC (external wins)")
        orchestrator = infra["orchestrator"]
        integration_repo = infra["integration_repo"]
        job_repo = infra["job_repo"]
        state_repo = infra["state_repo"]
        adapter = infra["adapter"]

        # 1. Configure: vendor direction = BIDIRECTIONAL, master = EXTERNAL
        _section("Configure vendor sync: BIDIRECTIONAL (master=external)")
        await _update_vendor_settings(
            integration_repo,
            SyncDirection.BIDIRECTIONAL,
            master_if_conflict=ConflictResolution.EXTERNAL,
        )
        print("  Settings updated: vendor → bidirectional, conflict master = external (QBO)")

        # 2. Simulate: BOTH sides change the vendor
        _section("Simulate changes on BOTH sides")

        # a) Internal change: bump internal_version_id
        v_synced = after_inbound.internal_version_id
        after_inbound.internal_version_id = v_synced + 1
        after_inbound.metadata = {
            "data": {
                "name": "Acme Manufacturing — OUR INTERNAL UPDATE",
                "email_address": "internal@acme.com",
                "phone": "(555) 111-2222",
                "status": "ACTIVE",
            }
        }
        await state_repo.upsert_record(after_inbound)
        print(f"  Internal change: iv bumped to {after_inbound.internal_version_id}")
        print(f"  Internal name: {after_inbound.metadata['data']['name']}")

        # b) External change: bump external_version_id + update adapter data
        after_inbound.external_version_id = v_synced + 1
        await state_repo.upsert_record(after_inbound)

        qbo_conflict_data = {
            "name": "Acme Manufacturing — QBO WINS",
            "email_address": "qbo-wins@acme.com",
            "phone": "(555) 777-0000",
            "status": "ACTIVE",
            "DisplayName": "Acme Manufacturing — QBO WINS",
        }
        adapter.seed_record("vendor", after_inbound.external_record_id, qbo_conflict_data)
        print(f"  External change: ev bumped to {after_inbound.external_version_id}")
        print(f"  QBO name: {qbo_conflict_data['name']}")

        # Confirm conflict
        assert after_inbound.needs_outbound_sync is True
        assert after_inbound.needs_inbound_sync is True
        print(
            f"  Conflict detected: needs_outbound={after_inbound.needs_outbound_sync}, needs_inbound={after_inbound.needs_inbound_sync}"
        )

        # 3. Run sync
        _section("Execute bidirectional sync job")
        job = await _create_and_execute_job(orchestrator, job_repo)
        _show_job(job)

        # 4. Verify
        _section("Verify results")
        final = await state_repo.get_record_by_external_id(
            CLIENT_ID,
            INTEGRATION_ID,
            "vendor",
            after_inbound.external_record_id,
        )
        assert final is not None, "State record should still exist"
        _show_state("After sync", final)

        # QBO should win → direction = INBOUND
        assert final.sync_direction == SyncDirection.INBOUND, (
            f"External should win — expected INBOUND, got {final.sync_direction}"
        )
        print("  Winner: QBO (sync_direction = INBOUND)")

        # Version vectors equalized
        assert final.internal_version_id == final.external_version_id == final.last_sync_version_id
        print(f"  Version vectors equalized: iv=ev=lsv={final.internal_version_id}")

        # Metadata should reflect QBO data (not our internal update)
        final_name = (final.metadata or {}).get("data", {}).get("name", "")
        assert "QBO WINS" in final_name, f"Expected QBO data to win, got: {final_name}"
        print(f"  Metadata: name={final_name}")

        assert final.sync_status == RecordSyncStatus.SYNCED
        assert final.is_in_sync is True

        # Job succeeded
        assert job.status == SyncJobStatus.SUCCEEDED
        print("\n  ✓ Phase 3 PASSED: bidirectional conflict resolved — QBO won")
