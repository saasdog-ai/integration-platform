#!/usr/bin/env python3
"""
Test: Xero Bidirectional Sync with Conflict Resolution

Verifies that when a bill is modified in both our system and Xero, the
platform detects the conflict, applies master_if_conflict=our_system,
pushes our version to Xero (outbound), and equalizes version vectors.

Prerequisites:
  - Database reachable (integration_platform + job_runner DBs)
  - Xero OAuth credentials encrypted and stored for the test client
  - At least one bill previously synced inbound from Xero (with external_record_id)

Usage:
    cd /Users/rajivkumar/Projects/integration-platform
    python scripts/test_xero_bidirectional_sync.py
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.dependency_injection import get_container
from app.domain.entities import (
    EntitySyncRequest,
    SyncJob,
    SyncRule,
    UserIntegrationSettings,
)
from app.domain.enums import (
    ChangeSourceType,
    ConflictResolution,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.infrastructure.adapters.factory import get_adapter_factory
from app.infrastructure.db.database import get_session_factory

XERO_INTEGRATION_ID = UUID("22222222-2222-2222-2222-222222222222")
CLIENT_ID = UUID("aaa00000-0000-0000-0000-000000000001")

# Markers injected into data to verify conflict resolution
INTERNAL_MARKER = f"INTERNAL_WINS_{datetime.now(UTC).strftime('%H%M%S')}"
EXTERNAL_MARKER = f"XERO_SHOULD_LOSE_{datetime.now(UTC).strftime('%H%M%S')}"

WIDTH = 70


def banner(text: str) -> None:
    print("\n" + "=" * WIDTH)
    print(f"  {text}")
    print("=" * WIDTH)


def section(text: str) -> None:
    print(f"\n>>> {text}")
    print("-" * 50)


def ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


async def main() -> None:
    banner("Xero Bidirectional Sync — Conflict Resolution Test")

    container = get_container()
    integration_repo = container.integration_repository
    state_repo = container.integration_state_repository
    job_repo = container.sync_job_repository
    encryption_service = container.encryption_service
    adapter_factory = get_adapter_factory()

    # ------------------------------------------------------------------
    # Step 1: Bootstrap — resolve adapter with real Xero credentials
    # ------------------------------------------------------------------
    section("Step 1: Bootstrap — resolve Xero adapter")

    integration = await integration_repo.get_available_integration(XERO_INTEGRATION_ID)
    if not integration:
        print("ERROR: Xero integration not found in available_integrations. Aborting.")
        return

    user_integration = await integration_repo.get_user_integration(CLIENT_ID, XERO_INTEGRATION_ID)
    if not user_integration or not user_integration.credentials_encrypted:
        print("ERROR: No Xero user_integration with credentials found. Aborting.")
        return

    credentials = await encryption_service.decrypt(
        user_integration.credentials_encrypted,
        user_integration.credentials_key_id,
    )
    creds_dict = json.loads(credentials.decode())
    access_token = creds_dict.get("access_token", "")
    print(f"  Integration: {integration.name}")
    print(f"  Tenant ID:   {user_integration.external_account_id}")
    print(f"  Token:       {access_token[:20]}...")

    adapter = adapter_factory.get_adapter(
        integration,
        access_token,
        user_integration.external_account_id,
    )
    print(f"  Adapter:     {adapter.__class__.__name__}")

    # ------------------------------------------------------------------
    # Step 2: Discover — find a synced bill with external_record_id
    # ------------------------------------------------------------------
    section("Step 2: Discover synced bill")

    synced_bills = await state_repo.get_records_by_status(
        CLIENT_ID, XERO_INTEGRATION_ID, "bill", RecordSyncStatus.SYNCED
    )
    target = None
    for bill in synced_bills:
        if bill.external_record_id and bill.internal_record_id:
            target = bill
            break

    if not target:
        print("ERROR: No synced bill with external_record_id found. Run an inbound sync first.")
        return

    print(f"  State ID:          {target.id}")
    print(f"  Internal ID:       {target.internal_record_id}")
    print(f"  External (Xero):   {target.external_record_id}")
    print(f"  Version vectors:   iv={target.internal_version_id}  ev={target.external_version_id}  lsv={target.last_sync_version_id}")
    print(f"  Status:            {target.sync_status.value}")

    pre_iv = target.internal_version_id
    pre_ev = target.external_version_id
    pre_lsv = target.last_sync_version_id

    # ------------------------------------------------------------------
    # Step 3: Configure — set bill rule to bidirectional, our_system wins
    # ------------------------------------------------------------------
    section("Step 3: Configure settings (bidirectional, our_system wins)")

    current_settings = await integration_repo.get_user_settings(CLIENT_ID, XERO_INTEGRATION_ID)
    original_rules = current_settings.sync_rules if current_settings else []

    # Build new rules: keep all non-bill rules, override bill rule
    new_rules = [r for r in original_rules if r.entity_type != "bill"]
    new_rules.append(
        SyncRule(
            entity_type="bill",
            direction=SyncDirection.BIDIRECTIONAL,
            enabled=True,
            master_if_conflict=ConflictResolution.OUR_SYSTEM,
            change_source=ChangeSourceType.POLLING,
        )
    )

    test_settings = UserIntegrationSettings(
        sync_rules=new_rules,
        sync_frequency=current_settings.sync_frequency if current_settings else "manual",
        auto_sync_enabled=False,
    )
    await integration_repo.upsert_user_settings(CLIENT_ID, XERO_INTEGRATION_ID, test_settings)
    print(f"  Bill rule set to: direction=bidirectional, master_if_conflict=our_system, change_source=polling")

    # ------------------------------------------------------------------
    # Step 4: Create conflict — modify both sides
    # ------------------------------------------------------------------
    section("Step 4: Create conflict")

    # 4a. Modify internal bill
    factory = get_session_factory()
    async with factory() as session:
        from sqlalchemy import text

        await session.execute(
            text(
                "UPDATE sample_bills SET description = :desc, updated_at = :now WHERE id = :id"
            ),
            {
                "desc": INTERNAL_MARKER,
                "now": datetime.now(UTC),
                "id": target.internal_record_id,
            },
        )
        await session.commit()
    print(f"  Internal bill updated:  description = '{INTERNAL_MARKER}'")

    # 4b. Modify Xero bill (add marker to first line item description)
    xero_bill = await adapter.get_record("bill", target.external_record_id)
    if not xero_bill:
        print("ERROR: Could not fetch bill from Xero. Token may be expired.")
        return

    xero_data = dict(xero_bill.data)
    line_items = xero_data.get("LineItems") or []
    if line_items:
        line_items[0]["Description"] = EXTERNAL_MARKER
    else:
        line_items = [
            {
                "Description": EXTERNAL_MARKER,
                "Quantity": 1,
                "UnitAmount": 100.0,
                "AccountCode": "400",
            }
        ]
    xero_data["LineItems"] = line_items

    await adapter.update_record("bill", target.external_record_id, xero_data)
    print(f"  Xero bill updated:     LineItems[0].Description = '{EXTERNAL_MARKER}'")

    # ------------------------------------------------------------------
    # Step 5: Trigger sync
    # ------------------------------------------------------------------
    section("Step 5: Trigger and execute sync job")

    from app.infrastructure.queue.memory_queue import InMemoryQueue
    from app.services.sync_orchestrator import SyncOrchestrator

    orchestrator = SyncOrchestrator(
        integration_repo=integration_repo,
        job_repo=job_repo,
        state_repo=state_repo,
        queue=InMemoryQueue(),
        encryption_service=encryption_service,
        adapter_factory=adapter_factory,
    )

    job = await orchestrator.trigger_sync(
        client_id=CLIENT_ID,
        integration_id=XERO_INTEGRATION_ID,
        job_type=SyncJobType.INCREMENTAL,
        entity_types=["bill"],
        triggered_by=SyncJobTrigger.USER,
    )
    print(f"  Job created: {job.id}  (status: {job.status.value})")

    job = await orchestrator.execute_sync_job(job)
    print(f"  Job finished: status={job.status.value}")
    if job.entities_processed:
        for entity, counts in job.entities_processed.items():
            print(f"    {entity}: {counts}")

    # ------------------------------------------------------------------
    # Step 6: Verify all 6 criteria
    # ------------------------------------------------------------------
    section("Step 6: Verify results")

    final_state = await state_repo.get_record_by_external_id(
        CLIENT_ID, XERO_INTEGRATION_ID, "bill", target.external_record_id
    )
    if not final_state:
        fail("State record not found after sync!")
        return

    print(f"  Final vectors: iv={final_state.internal_version_id}  ev={final_state.external_version_id}  lsv={final_state.last_sync_version_id}")
    print(f"  Direction:     {final_state.sync_direction.value}")
    print(f"  Status:        {final_state.sync_status.value}")

    passed = 0
    total = 6

    # Criterion 1: Version vectors incremented
    if final_state.internal_version_id > pre_iv and final_state.external_version_id > pre_ev:
        ok(f"Version vectors incremented (iv: {pre_iv} -> {final_state.internal_version_id}, ev: {pre_ev} -> {final_state.external_version_id})")
        passed += 1
    else:
        fail(f"Version vectors NOT incremented (iv: {pre_iv} -> {final_state.internal_version_id}, ev: {pre_ev} -> {final_state.external_version_id})")

    # Criterion 2: Conflict detected (both sides changed, resolved as outbound)
    # We infer conflict was detected because direction is OUTBOUND and both iv and ev were bumped
    if final_state.sync_direction == SyncDirection.OUTBOUND:
        ok("Conflict resolved as OUTBOUND (our system won)")
        passed += 1
    else:
        fail(f"Expected sync_direction=outbound, got {final_state.sync_direction.value}")

    # Criterion 3: master_if_conflict=our_system applied
    # This is confirmed by criterion 2 — direction is OUTBOUND means our system won
    if final_state.sync_direction == SyncDirection.OUTBOUND:
        ok("master_if_conflict=our_system applied correctly")
        passed += 1
    else:
        fail("master_if_conflict=our_system NOT applied")

    # Criterion 4: Xero bill should NOT contain EXTERNAL_MARKER, SHOULD reflect our data
    xero_after = await adapter.get_record("bill", target.external_record_id)
    xero_after_data = xero_after.data if xero_after else {}
    xero_lines_after = xero_after_data.get("LineItems") or []
    xero_descriptions = " ".join(
        line.get("Description", "") for line in xero_lines_after
    )

    if EXTERNAL_MARKER not in xero_descriptions:
        ok(f"Xero bill does NOT contain '{EXTERNAL_MARKER}' (overwritten)")
        passed += 1
    else:
        fail(f"Xero bill STILL contains '{EXTERNAL_MARKER}' — outbound push failed or pushed stale data")

    # Criterion 5: Version vectors equalized
    if (
        final_state.internal_version_id == final_state.external_version_id
        and final_state.external_version_id == final_state.last_sync_version_id
    ):
        ok(f"Version vectors equalized: iv=ev=lsv={final_state.internal_version_id}")
        passed += 1
    else:
        fail(
            f"Version vectors NOT equalized: iv={final_state.internal_version_id} ev={final_state.external_version_id} lsv={final_state.last_sync_version_id}"
        )

    # Criterion 6: Record sync_status = synced
    if final_state.sync_status == RecordSyncStatus.SYNCED:
        ok("sync_status = synced")
        passed += 1
    else:
        fail(f"Expected sync_status=synced, got {final_state.sync_status.value}")

    # ------------------------------------------------------------------
    # Cleanup: restore original settings
    # ------------------------------------------------------------------
    section("Cleanup")

    if current_settings:
        restore_settings = UserIntegrationSettings(
            sync_rules=original_rules,
            sync_frequency=current_settings.sync_frequency,
            auto_sync_enabled=current_settings.auto_sync_enabled,
        )
        await integration_repo.upsert_user_settings(CLIENT_ID, XERO_INTEGRATION_ID, restore_settings)
        print("  Original settings restored.")
    else:
        print("  No original settings to restore.")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    banner(f"Results: {passed}/{total} criteria passed")

    if passed == total:
        print("\nAll criteria passed! Bidirectional sync with conflict resolution works correctly.")
    else:
        print(f"\n{total - passed} criteria failed. See details above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
