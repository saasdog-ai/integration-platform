#!/usr/bin/env python3
"""
Demo: QuickBooks Sync Job via SQS Queue

This script demonstrates the complete sync job workflow:
1. User triggers a sync (simulating UI button click)
2. Job request is sent to the message queue (SQS)
3. Job runner consumes the message and processes the job
4. The appropriate adapter (QuickBooks) is selected based on integration ID
5. Mock sync activity is printed to the console

Usage:
    python scripts/demo_sync_job.py
    python scripts/demo_sync_job.py --entity-types vendor,bill
    python scripts/demo_sync_job.py --specific-records vendor:QBO-V-1001,QBO-V-1002 bill:QBO-B-2001
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

# Add parent directory to path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.domain.entities import (
    AvailableIntegration,
    EntitySyncRequest,
    OAuthConfig,
    SyncJob,
    SyncJobMessage,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    ConflictResolution,
    IntegrationStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.infrastructure.adapters.factory import get_adapter_factory
from app.infrastructure.queue.memory_queue import InMemoryQueue
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)

logger = get_logger(__name__)


# Sample data IDs
QUICKBOOKS_INTEGRATION_ID = UUID("11111111-1111-1111-1111-111111111111")
XERO_INTEGRATION_ID = UUID("22222222-2222-2222-2222-222222222222")
SAMPLE_CLIENT_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def print_banner(text: str) -> None:
    """Print a formatted banner."""
    width = 70
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_section(text: str) -> None:
    """Print a section header."""
    print(f"\n>>> {text}")
    print("-" * 50)


async def setup_mock_data(
    integration_repo: MockIntegrationRepository,
    encryption_service: MockEncryptionService,
) -> None:
    """Set up mock integration data."""
    now = datetime.now(timezone.utc)

    # Create QuickBooks integration using seed method (sets ID correctly)
    quickbooks = AvailableIntegration(
        id=QUICKBOOKS_INTEGRATION_ID,
        name="QuickBooks Online",
        type="erp",
        description="Intuit QuickBooks Online accounting software",
        supported_entities=["vendor", "bill", "invoice", "customer", "chart_of_accounts", "payment"],
        oauth_config=OAuthConfig(
            authorization_url="https://appcenter.intuit.com/connect/oauth2",
            token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            scopes=["com.intuit.quickbooks.accounting"],
        ),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    # Directly add to internal storage with correct ID
    integration_repo._available_integrations[QUICKBOOKS_INTEGRATION_ID] = quickbooks

    # Create Xero integration
    xero = AvailableIntegration(
        id=XERO_INTEGRATION_ID,
        name="Xero",
        type="erp",
        description="Xero cloud accounting platform",
        supported_entities=["bill", "invoice", "contact", "account", "payment"],
        oauth_config=OAuthConfig(
            authorization_url="https://login.xero.com/identity/connect/authorize",
            token_url="https://identity.xero.com/connect/token",
            scopes=["accounting.transactions", "accounting.contacts"],
        ),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    integration_repo._available_integrations[XERO_INTEGRATION_ID] = xero

    # Create user's QuickBooks connection
    credentials = json.dumps({
        "access_token": "mock_access_token_12345",
        "refresh_token": "mock_refresh_token_67890",
    }).encode()
    encrypted_creds, key_id = await encryption_service.encrypt(credentials)

    user_integration = UserIntegration(
        id=uuid4(),
        client_id=SAMPLE_CLIENT_ID,
        integration_id=QUICKBOOKS_INTEGRATION_ID,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=encrypted_creds,
        credentials_key_id=key_id,
        external_account_id="realm-123456",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
    )
    await integration_repo.create_user_integration(user_integration)

    # Create user's sync settings
    settings = UserIntegrationSettings(
        sync_rules=[
            SyncRule(
                entity_type="vendor",
                direction=SyncDirection.INBOUND,
                enabled=True,
                master_if_conflict=ConflictResolution.EXTERNAL,
            ),
            SyncRule(
                entity_type="bill",
                direction=SyncDirection.INBOUND,
                enabled=True,
                master_if_conflict=ConflictResolution.EXTERNAL,
            ),
            SyncRule(
                entity_type="invoice",
                direction=SyncDirection.OUTBOUND,
                enabled=True,
                master_if_conflict=ConflictResolution.OUR_SYSTEM,
            ),
        ],
        sync_frequency="0 */6 * * *",
        auto_sync_enabled=True,
    )
    await integration_repo.upsert_user_settings(
        SAMPLE_CLIENT_ID, QUICKBOOKS_INTEGRATION_ID, settings
    )


async def trigger_sync_job(
    queue: InMemoryQueue,
    job_repo: MockSyncJobRepository,
    client_id: UUID,
    integration_id: UUID,
    job_type: SyncJobType,
    entity_types: list[str] | None = None,
    entity_requests: list[EntitySyncRequest] | None = None,
) -> SyncJob:
    """
    Trigger a sync job by sending a message to the queue.

    This simulates what happens when a user clicks "Sync Now" in the UI.
    """
    print_section("Step 1: User Triggers Sync (UI Button Click)")

    now = datetime.now(timezone.utc)

    # Create the sync job record
    job = SyncJob(
        id=uuid4(),
        client_id=client_id,
        integration_id=integration_id,
        job_type=job_type,
        status=SyncJobStatus.PENDING,
        triggered_by=SyncJobTrigger.USER,
        created_at=now,
        updated_at=now,
    )
    job = await job_repo.create_job(job)

    print(f"Created sync job:")
    print(f"  Job ID: {job.id}")
    print(f"  Client ID: {client_id}")
    print(f"  Integration ID: {integration_id}")
    print(f"  Job Type: {job_type.value}")
    print(f"  Status: {job.status.value}")

    # Create the queue message
    message = SyncJobMessage(
        job_id=job.id,
        client_id=client_id,
        integration_id=integration_id,
        job_type=job_type,
        entity_types=entity_types,
        entity_requests=entity_requests,
    )

    print_section("Step 2: Send Job Request to Queue (SQS)")

    message_dict = message.model_dump(mode="json")
    print(f"Queue message (JSON):")
    print(json.dumps(message_dict, indent=2, default=str))

    # Send to queue
    message_id = await queue.send_message(message_dict)
    print(f"\nMessage sent to queue!")
    print(f"  Message ID: {message_id}")
    print(f"  Queue depth: {queue.message_count}")

    return job


async def process_job_from_queue(
    queue: InMemoryQueue,
    job_repo: MockSyncJobRepository,
    integration_repo: MockIntegrationRepository,
    state_repo: MockIntegrationStateRepository,
    encryption_service: MockEncryptionService,
) -> None:
    """
    Process the sync job from the queue.

    This simulates what the job runner does when it consumes a message.
    """
    print_section("Step 3: Job Runner Receives Message from Queue")

    # Receive message from queue
    messages = await queue.receive_messages(max_messages=1, wait_time_seconds=1)

    if not messages:
        print("No messages in queue!")
        return

    message = messages[0]
    print(f"Received message:")
    print(f"  Message ID: {message.message_id}")
    print(f"  Receipt Handle: {message.receipt_handle[:20]}...")

    # Parse the message
    job_message = SyncJobMessage(
        job_id=message.body["job_id"],
        client_id=message.body["client_id"],
        integration_id=message.body["integration_id"],
        job_type=SyncJobType(message.body["job_type"]),
        entity_types=message.body.get("entity_types"),
        entity_requests=[
            EntitySyncRequest(**req)
            for req in message.body.get("entity_requests", [])
        ] if message.body.get("entity_requests") else None,
    )

    print_section("Step 4: Identify Integration and Select Adapter")

    # Get the integration details
    integration = await integration_repo.get_available_integration(job_message.integration_id)
    print(f"Integration: {integration.name}")
    print(f"Type: {integration.type}")
    print(f"Supported entities: {', '.join(integration.supported_entities)}")

    # Get adapter from factory (this routes to the correct adapter based on integration name)
    adapter_factory = get_adapter_factory()
    user_integration = await integration_repo.get_user_integration(
        job_message.client_id, job_message.integration_id
    )

    # Decrypt credentials
    credentials = await encryption_service.decrypt(
        user_integration.credentials_encrypted,
        user_integration.credentials_key_id,
    )
    creds_dict = json.loads(credentials.decode())

    print(f"\nGetting adapter for: {integration.name}")
    adapter = adapter_factory.get_adapter(
        integration,
        creds_dict["access_token"],
        user_integration.external_account_id,
    )
    print(f"Adapter class: {adapter.__class__.__name__}")

    print_section("Step 5: Execute Sync Job")

    # Get job from repo
    job = await job_repo.get_job(job_message.job_id)

    # Update job status to running
    job = await job_repo.update_job_status(job.id, SyncJobStatus.RUNNING)
    print(f"Job status updated to: {job.status.value}")

    # Get user settings to determine which entities to sync
    settings = await integration_repo.get_user_settings(
        job_message.client_id, job_message.integration_id
    )

    # Determine which entities to sync
    entities_to_sync: list[tuple[str, list[str] | None]] = []

    if job_message.entity_requests:
        # Use specific entity requests with optional record IDs
        for req in job_message.entity_requests:
            entities_to_sync.append((req.entity_type, req.record_ids))
    elif job_message.entity_types:
        # Use simple entity type list
        for entity_type in job_message.entity_types:
            entities_to_sync.append((entity_type, None))
    else:
        # Sync all enabled entities from settings
        for rule in settings.sync_rules:
            if rule.enabled:
                entities_to_sync.append((rule.entity_type, None))

    print(f"\nEntities to sync:")
    for entity_type, record_ids in entities_to_sync:
        if record_ids:
            print(f"  - {entity_type}: {len(record_ids)} specific records ({', '.join(record_ids[:3])}{'...' if len(record_ids) > 3 else ''})")
        else:
            print(f"  - {entity_type}: all records")

    # Execute sync for each entity
    print_section("Step 6: Sync Records (Mock)")

    results = {}
    for entity_type, record_ids in entities_to_sync:
        # Find the sync rule for this entity
        rule = next((r for r in settings.sync_rules if r.entity_type == entity_type), None)
        if not rule:
            print(f"\n[Warning] No sync rule found for {entity_type}, skipping...")
            continue

        print(f"\nSync direction for {entity_type}: {rule.direction.value}")
        print(f"Conflict resolution: {rule.master_if_conflict.value}")

        # Fetch records from external system
        records, _ = await adapter.fetch_records(
            entity_type,
            since=None,  # Full sync for demo
            record_ids=record_ids,
        )

        results[entity_type] = {
            "records_fetched": len(records),
            "records_synced": len(records),
            "direction": rule.direction.value,
        }

    # Update job to succeeded
    job = await job_repo.update_job_status(
        job.id,
        SyncJobStatus.SUCCEEDED,
        entities_processed=results,
    )

    # Delete message from queue
    await queue.delete_message(message.receipt_handle)

    print_section("Step 7: Job Complete")
    print(f"Job ID: {job.id}")
    print(f"Final Status: {job.status.value}")
    print(f"Results:")
    print(json.dumps(results, indent=2))


def parse_specific_records(records_str: list[str]) -> list[EntitySyncRequest]:
    """Parse specific record arguments like 'vendor:QBO-V-1001,QBO-V-1002'."""
    requests = []
    for item in records_str:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid format: {item}. Use entity_type:id1,id2,...")
        entity_type = parts[0]
        record_ids = parts[1].split(",")
        requests.append(EntitySyncRequest(entity_type=entity_type, record_ids=record_ids))
    return requests


async def main() -> None:
    """Run the sync job demo."""
    parser = argparse.ArgumentParser(description="Demo: QuickBooks Sync Job via SQS Queue")
    parser.add_argument(
        "--entity-types",
        help="Comma-separated list of entity types to sync (e.g., vendor,bill)",
    )
    parser.add_argument(
        "--specific-records",
        nargs="*",
        help="Specific records to sync in format entity_type:id1,id2 (e.g., vendor:QBO-V-1001,QBO-V-1002)",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Run a full sync instead of incremental",
    )
    args = parser.parse_args()

    print_banner("QuickBooks Sync Job Demo")
    print("\nThis demo shows how a sync job flows through the system:")
    print("  1. User triggers sync via UI")
    print("  2. Job request is sent to message queue (SQS)")
    print("  3. Job runner consumes the message")
    print("  4. System identifies the integration and selects the right adapter")
    print("  5. Adapter syncs records with the external system")
    print("  6. Job completes and results are recorded")

    # Set up mock infrastructure
    print_section("Setting up mock infrastructure...")
    queue = InMemoryQueue()
    job_repo = MockSyncJobRepository()
    integration_repo = MockIntegrationRepository()
    state_repo = MockIntegrationStateRepository()
    encryption_service = MockEncryptionService()

    # Set up sample data
    await setup_mock_data(integration_repo, encryption_service)
    print("Mock data ready!")

    # Parse arguments
    entity_types = args.entity_types.split(",") if args.entity_types else None
    entity_requests = parse_specific_records(args.specific_records) if args.specific_records else None
    job_type = SyncJobType.FULL_SYNC if args.full_sync else SyncJobType.INCREMENTAL

    # Trigger the sync job
    await trigger_sync_job(
        queue=queue,
        job_repo=job_repo,
        client_id=SAMPLE_CLIENT_ID,
        integration_id=QUICKBOOKS_INTEGRATION_ID,
        job_type=job_type,
        entity_types=entity_types,
        entity_requests=entity_requests,
    )

    # Process the job from the queue
    await process_job_from_queue(
        queue=queue,
        job_repo=job_repo,
        integration_repo=integration_repo,
        state_repo=state_repo,
        encryption_service=encryption_service,
    )

    print_banner("Demo Complete!")
    print("\nThe sync job has been processed successfully.")
    print("In production, this flow would:")
    print("  - Use AWS SQS instead of in-memory queue")
    print("  - Make real API calls to QuickBooks")
    print("  - Store sync state in PostgreSQL")
    print("  - Handle errors, retries, and dead-letter queues")


if __name__ == "__main__":
    asyncio.run(main())
