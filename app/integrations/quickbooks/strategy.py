"""QuickBooks Online sync strategy.

Orchestrates entity ordering, schema mapping between QBO and internal
formats, and reads/writes to the internal database.

The orchestrator delegates to this strategy for QBO-specific sync logic
while retaining responsibility for state tracking, history, and error handling.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.domain.entities import (
    ExternalRecord,
    IntegrationHistoryRecord,
    IntegrationStateRecord,
    SyncJob,
    SyncRule,
)
from app.domain.enums import ChangeSourceType, ConflictResolution, RecordSyncStatus, SyncDirection
from app.domain.interfaces import (
    IntegrationAdapterInterface,
    IntegrationStateRepositoryInterface,
)
from app.integrations.quickbooks.constants import (
    ENTITY_DISPLAY_NAMES,
    INBOUND_ENTITY_ORDER,
    OUTBOUND_ENTITY_ORDER,
)
from app.integrations.quickbooks.mappers import (
    INBOUND_MAPPERS,
    OUTBOUND_MAPPERS,
    map_vendor_inbound,
)
from app.integrations.shared.internal_repo import InternalDataRepository

logger = get_logger(__name__)


class QuickBooksSyncStrategy:
    """QBO-specific sync strategy.

    Handles entity ordering, schema mapping (QBO ↔ internal), and
    internal database reads/writes. The orchestrator calls this instead of
    doing generic entity sync.
    """

    def __init__(self, internal_repo: Any | None = None) -> None:
        self._internal_repo = internal_repo or InternalDataRepository()

    # ------------------------------------------------------------------
    # Entity ordering
    # ------------------------------------------------------------------

    def get_entity_order(self, direction: SyncDirection) -> list[str]:
        """Return entity types in dependency order for the given direction."""
        if direction == SyncDirection.OUTBOUND:
            return list(OUTBOUND_ENTITY_ORDER)
        return list(INBOUND_ENTITY_ORDER)

    def get_ordered_rules(self, rules: list[SyncRule], direction: SyncDirection) -> list[SyncRule]:
        """Sort enabled rules according to QBO entity dependency order."""
        order = self.get_entity_order(direction)
        order_map = {et: idx for idx, et in enumerate(order)}

        enabled = [r for r in rules if r.enabled]
        return sorted(
            enabled,
            key=lambda r: order_map.get(r.entity_type, len(order)),
        )

    # ------------------------------------------------------------------
    # Inbound sync: QBO → internal database
    # ------------------------------------------------------------------

    async def sync_entity_inbound(
        self,
        job: SyncJob,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: IntegrationStateRepositoryInterface,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pull records from QBO, map to internal schema, write to internal database.

        Returns a summary dict with counts of fetched/created/updated/failed records.
        """
        display = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)
        mapper_fn = INBOUND_MAPPERS.get(entity_type)

        result: dict[str, Any] = {
            "direction": "inbound",
            "records_fetched": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
        }

        if not mapper_fn:
            logger.info(
                "No inbound mapper for entity type — skipping",
                extra={"entity_type": entity_type},
            )
            return result

        # Paginated fetch from QBO
        page_token = None
        records_to_upsert: list[IntegrationStateRecord] = []
        max_external_updated_at: datetime | None = None
        BATCH_SIZE = 200

        while True:
            records, next_token = await adapter.fetch_records(
                entity_type,
                since=since,
                page_token=page_token,
                record_ids=record_ids,
            )
            result["records_fetched"] += len(records)

            for record in records:
                if record.updated_at and (
                    max_external_updated_at is None or record.updated_at > max_external_updated_at
                ):
                    max_external_updated_at = record.updated_at

                try:
                    state_record = await self._process_inbound_record(
                        job=job,
                        entity_type=entity_type,
                        record=record,
                        mapper_fn=mapper_fn,
                        state_repo=state_repo,
                        adapter=adapter,
                    )
                    records_to_upsert.append(state_record)

                    # Flush batch
                    if len(records_to_upsert) >= BATCH_SIZE:
                        created, updated, failed = await self._flush_inbound_batch(
                            records_to_upsert, state_repo, job
                        )
                        result["records_created"] += created
                        result["records_updated"] += updated
                        result["records_failed"] += failed
                        records_to_upsert = []

                except Exception as e:
                    logger.warning(
                        f"Failed to process inbound {display} record",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": entity_type,
                            "external_id": record.id,
                            "error": str(e),
                        },
                    )
                    result["records_failed"] += 1
                    try:
                        entry = IntegrationHistoryRecord(
                            id=uuid4(),
                            client_id=job.client_id,
                            state_record_id=uuid4(),
                            integration_id=job.integration_id,
                            entity_type=entity_type,
                            internal_record_id=None,
                            external_record_id=record.id,
                            sync_status=RecordSyncStatus.FAILED,
                            sync_direction=SyncDirection.INBOUND,
                            job_id=job.id,
                            error_code="SYNC_FAILED",
                            error_message=str(e)[:500],
                            error_details=None,
                            created_at=datetime.now(UTC),
                        )
                        await state_repo.batch_create_history([entry])
                    except Exception:
                        pass

            if not next_token:
                break
            page_token = next_token

        # Flush remaining
        if records_to_upsert:
            created, updated, failed = await self._flush_inbound_batch(
                records_to_upsert, state_repo, job
            )
            result["records_created"] += created
            result["records_updated"] += updated
            result["records_failed"] += failed

        result["max_external_updated_at"] = max_external_updated_at

        logger.info(
            f"Inbound sync complete for {display}",
            extra={
                "job_id": str(job.id),
                "entity_type": entity_type,
                **{k: v for k, v in result.items() if k != "max_external_updated_at"},
            },
        )
        return result

    async def _process_inbound_record(
        self,
        job: SyncJob,
        entity_type: str,
        record: ExternalRecord,
        mapper_fn: Any,
        state_repo: IntegrationStateRepositoryInterface,
        adapter: IntegrationAdapterInterface | None = None,
    ) -> IntegrationStateRecord:
        """Map a single QBO record and write to internal database.

        Returns an IntegrationStateRecord ready for batch upsert.
        """
        # 1. Look up existing state to get internal record_id (if previously synced)
        existing = await state_repo.get_record_by_external_id(
            job.client_id, job.integration_id, entity_type, record.id
        )

        # Skip records flagged as do-not-sync: track external version but
        # don't write to the internal system
        if existing and existing.do_not_sync:
            existing.external_version_id += 1
            existing.last_sync_version_id = existing.external_version_id
            return existing

        record_id = existing.internal_record_id if existing else None

        # 2. Map QBO data to internal schema
        mapped_data = mapper_fn(record.data)

        # 3. Resolve FK references via integration_state before upsert
        if entity_type == "bill" and mapped_data.get("vendor_external_id") and adapter:
            await self._ensure_vendor_synced(
                job,
                mapped_data["vendor_external_id"],
                adapter,
                state_repo,
            )
            # Resolve vendor_external_id → vendor internal_record_id
            vendor_state = await state_repo.get_record_by_external_id(
                job.client_id, job.integration_id, "vendor", mapped_data["vendor_external_id"]
            )
            if vendor_state and vendor_state.internal_record_id:
                mapped_data["vendor_id"] = vendor_state.internal_record_id

        if entity_type == "invoice" and mapped_data.get("contact_external_id"):
            # Resolve contact_external_id → contact internal_record_id
            contact_state = await state_repo.get_record_by_external_id(
                job.client_id, job.integration_id, "vendor", mapped_data["contact_external_id"]
            )
            if contact_state and contact_state.internal_record_id:
                mapped_data["contact_id"] = contact_state.internal_record_id

        # 4. Write to internal database
        upsert_fn = self._get_internal_upsert_fn(entity_type)
        internal_record_id = await upsert_fn(job.client_id, mapped_data, record_id=record_id)

        # 5. Build IntegrationStateRecord
        now = datetime.now(UTC)

        if existing:
            # Preserve internal_record_id — never null it out (upsert guard)
            if internal_record_id:
                existing.internal_record_id = internal_record_id
            existing.external_version_id += 1
            existing.internal_version_id = existing.external_version_id
            existing.last_sync_version_id = existing.external_version_id
            existing.sync_status = RecordSyncStatus.SYNCED
            existing.sync_direction = SyncDirection.INBOUND
            existing.last_synced_at = now
            existing.last_job_id = job.id
            existing.metadata = {"data": record.data}
            existing.updated_at = now
            return existing
        else:
            return IntegrationStateRecord(
                id=uuid4(),
                client_id=job.client_id,
                integration_id=job.integration_id,
                entity_type=entity_type,
                internal_record_id=internal_record_id,
                external_record_id=record.id,
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.INBOUND,
                internal_version_id=1,
                external_version_id=1,
                last_sync_version_id=1,
                last_synced_at=now,
                last_job_id=job.id,
                metadata={"data": record.data},
                created_at=now,
                updated_at=now,
            )

    async def _flush_inbound_batch(
        self,
        records: list[IntegrationStateRecord],
        state_repo: IntegrationStateRepositoryInterface,
        job: SyncJob,
    ) -> tuple[int, int, int]:
        """Batch upsert state records and write history. Returns (created, updated, failed)."""
        created = sum(1 for r in records if r.created_at == r.updated_at)
        updated = len(records) - created

        try:
            await state_repo.batch_upsert_records(records)
            await self._write_history_entries(records, state_repo, job.id)
            return created, updated, 0
        except Exception as e:
            logger.error(
                "Inbound batch upsert failed",
                extra={
                    "job_id": str(job.id),
                    "batch_size": len(records),
                    "error": str(e),
                },
            )
            return 0, 0, len(records)

    # ------------------------------------------------------------------
    # Outbound sync: internal database → QBO
    # ------------------------------------------------------------------

    async def sync_entity_outbound(
        self,
        job: SyncJob,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: IntegrationStateRepositoryInterface,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
        rule: SyncRule | None = None,
    ) -> dict[str, Any]:
        """Push records needing outbound sync to QBO.

        For POLLING change detection: polls internal DB for records modified
        since last sync and bumps their internal_version_id first.

        For PUSH change detection: assumes internal_version_id was already
        bumped via the /notify endpoint.

        Then discovers records via version vectors in state_repo, pushes to
        the external system, and equalizes all three version fields.

        Returns a summary dict with counts.
        """
        display = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)

        result: dict[str, Any] = {
            "direction": "outbound",
            "records_fetched": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
        }

        # 0. Poll internal changes and bump internal_version_id (for POLLING mode)
        # PUSH and HYBRID modes have internal_version_id already bumped via /notify endpoint
        change_source = rule.change_source if rule else ChangeSourceType.POLLING
        if change_source == ChangeSourceType.POLLING:
            await self._poll_and_bump_internal_changes(
                job=job,
                entity_type=entity_type,
                state_repo=state_repo,
                since=since,
            )

        # 1. Find records needing outbound sync via state repo
        synced_records = await state_repo.get_records_by_status(
            job.client_id,
            job.integration_id,
            entity_type,
            RecordSyncStatus.SYNCED,
        )
        pending_records = await state_repo.get_records_by_status(
            job.client_id,
            job.integration_id,
            entity_type,
            RecordSyncStatus.PENDING,
        )
        outbound_records = [r for r in (synced_records + pending_records) if r.needs_outbound_sync]
        result["records_fetched"] = len(outbound_records)

        if not outbound_records:
            logger.info(
                f"No {display} records to sync outbound",
                extra={"job_id": str(job.id), "entity_type": entity_type},
            )
            return result

        # 2. Process each record
        now = datetime.now(UTC)
        successful_states: list[IntegrationStateRecord] = []

        for state in outbound_records:
            try:
                data = await self._prepare_outbound_data(job, entity_type, state, state_repo)

                if state.external_record_id:
                    await adapter.update_record(entity_type, state.external_record_id, data)
                else:
                    ext_record = await adapter.create_record(entity_type, data)
                    state.external_record_id = ext_record.id

                # Equalize version vectors
                max_v = max(state.internal_version_id, state.external_version_id)
                state.internal_version_id = max_v
                state.external_version_id = max_v
                state.last_sync_version_id = max_v
                state.sync_status = RecordSyncStatus.SYNCED
                state.sync_direction = SyncDirection.OUTBOUND
                state.last_synced_at = now
                state.last_job_id = job.id
                state.updated_at = now

                await state_repo.upsert_record(state)
                successful_states.append(state)
                result["records_updated"] += 1

            except Exception as e:
                logger.warning(
                    f"Failed to sync outbound {display} record",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "internal_id": state.internal_record_id,
                        "error": str(e),
                    },
                )
                result["records_failed"] += 1
                await self._write_failure_history(
                    state, state_repo, job.id, SyncDirection.OUTBOUND, e
                )

        # 3. Write history
        if successful_states:
            await self._write_history_entries(successful_states, state_repo, job.id)

        logger.info(
            f"Outbound sync complete for {display}",
            extra={
                "job_id": str(job.id),
                "entity_type": entity_type,
                **result,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Polling-based internal change detection
    # ------------------------------------------------------------------

    async def _poll_and_bump_internal_changes(
        self,
        job: SyncJob,
        entity_type: str,
        state_repo: IntegrationStateRepositoryInterface,
        since: datetime | None = None,
    ) -> int:
        """Poll internal DB for modified records and bump their internal_version_id.

        This implements polling-based change detection for outbound sync.
        For PUSH mode, this step is skipped as internal_version_id is already
        bumped via the /notify endpoint.

        Args:
            job: The sync job.
            entity_type: The entity type (e.g., "vendor").
            state_repo: The state repository.
            since: Only poll records modified after this timestamp.

        Returns:
            Number of records with internal_version_id bumped.
        """
        display = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)

        # Get internal records modified since last sync
        try:
            getter_fn = self._get_internal_getter_fn(entity_type)
        except ValueError:
            logger.debug(
                f"No internal getter for {display} — skipping internal change detection",
                extra={"job_id": str(job.id), "entity_type": entity_type},
            )
            return 0

        internal_records = await getter_fn(job.client_id, since=since)

        if not internal_records:
            logger.debug(
                f"No modified {display} records found in internal DB",
                extra={"job_id": str(job.id), "entity_type": entity_type, "since": str(since)},
            )
            return 0

        # Extract internal record IDs
        record_ids = [str(r["id"]) for r in internal_records]

        # Bump internal_version_id for these records
        bumped, created = await state_repo.bump_version_vectors(
            client_id=job.client_id,
            integration_id=job.integration_id,
            entity_type=entity_type,
            record_ids=record_ids,
            bump_internal=True,
            bump_external=False,
        )

        logger.info(
            f"Polled internal changes for {display}",
            extra={
                "job_id": str(job.id),
                "entity_type": entity_type,
                "records_found": len(internal_records),
                "records_bumped": bumped,
                "records_created": created,
                "since": str(since),
            },
        )

        return bumped + created

    # ------------------------------------------------------------------
    # Bidirectional sync: version-vector based classification
    # ------------------------------------------------------------------

    async def sync_entity_bidirectional(
        self,
        job: SyncJob,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: IntegrationStateRepositoryInterface,
        rule: SyncRule,
        since: datetime | None = None,
        outbound_since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Bidirectional sync using version vectors for conflict detection.

        Classifies each record as inbound, outbound, conflict, or in-sync
        based on version vectors, then delegates to the appropriate handler.

        For POLLING change detection: polls internal DB for records modified
        since outbound_since and bumps their internal_version_id.

        For PUSH change detection: assumes internal_version_id was already
        bumped via the /notify endpoint.

        Returns a summary dict with counts.
        """
        display = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)
        mapper_fn = INBOUND_MAPPERS.get(entity_type)

        result: dict[str, Any] = {
            "direction": "bidirectional",
            "records_fetched": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
        }

        now = datetime.now(UTC)

        # Track which state record IDs we've already processed
        processed_state_ids: set[UUID] = set()

        # Track records that need history written
        records_needing_history: list[IntegrationStateRecord] = []

        # 0. Poll internal changes and bump internal_version_id (for POLLING/WEBHOOK modes)
        # PUSH and HYBRID modes have internal_version_id already bumped via /notify endpoint
        if rule.change_source in (ChangeSourceType.POLLING, ChangeSourceType.WEBHOOK):
            await self._poll_and_bump_internal_changes(
                job=job,
                entity_type=entity_type,
                state_repo=state_repo,
                since=outbound_since,
            )

        # 1. Fetch external records from adapter
        page_token = None
        external_records = []
        max_external_updated_at: datetime | None = None

        while True:
            records, next_token = await adapter.fetch_records(
                entity_type,
                since=since,
                page_token=page_token,
                record_ids=record_ids,
            )
            result["records_fetched"] += len(records)

            for record in records:
                if record.updated_at and (
                    max_external_updated_at is None or record.updated_at > max_external_updated_at
                ):
                    max_external_updated_at = record.updated_at
                external_records.append(record)

            if not next_token:
                break
            page_token = next_token

        # 2. Classify and process each external record
        records_to_upsert: list[IntegrationStateRecord] = []
        BATCH_SIZE = 200

        for record in external_records:
            try:
                existing = await state_repo.get_record_by_external_id(
                    job.client_id, job.integration_id, entity_type, record.id
                )

                if not existing:
                    # New external record → inbound
                    if mapper_fn:
                        state_record = await self._process_inbound_record(
                            job=job,
                            entity_type=entity_type,
                            record=record,
                            mapper_fn=mapper_fn,
                            state_repo=state_repo,
                            adapter=adapter,
                        )
                        records_to_upsert.append(state_record)
                    continue

                processed_state_ids.add(existing.id)

                # The fact that QBO returned this record (filtered by `since`) means
                # it was modified externally. Bump external_version_id if not already
                # marked as changed (to avoid double-counting in push+poll hybrid).
                if existing.external_version_id <= existing.last_sync_version_id:
                    existing.external_version_id = existing.last_sync_version_id + 1

                needs_out = existing.needs_outbound_sync
                needs_in = existing.needs_inbound_sync

                if not needs_out and not needs_in:
                    # In sync — shouldn't happen after bump, but skip if so
                    continue

                if needs_out and needs_in:
                    # Both sides changed — conflict: use master_if_conflict
                    if rule.master_if_conflict == ConflictResolution.EXTERNAL:
                        direction = SyncDirection.INBOUND
                    else:
                        direction = SyncDirection.OUTBOUND
                elif needs_in:
                    # Only external changed — sync inbound
                    direction = SyncDirection.INBOUND
                else:
                    # Only internal changed — sync outbound
                    direction = SyncDirection.OUTBOUND

                if direction == SyncDirection.INBOUND:
                    # Write to internal database if mapper available
                    if mapper_fn:
                        mapped_data = mapper_fn(record.data)
                        upsert_fn = self._get_internal_upsert_fn(entity_type)
                        internal_record_id = await upsert_fn(
                            job.client_id, mapped_data, record_id=existing.internal_record_id
                        )
                        if internal_record_id and not existing.internal_record_id:
                            existing.internal_record_id = internal_record_id

                    # Equalize version vectors
                    max_v = max(existing.internal_version_id, existing.external_version_id)
                    existing.internal_version_id = max_v
                    existing.external_version_id = max_v
                    existing.last_sync_version_id = max_v
                    existing.sync_status = RecordSyncStatus.SYNCED
                    existing.sync_direction = SyncDirection.INBOUND
                    existing.last_synced_at = now
                    existing.last_job_id = job.id
                    existing.metadata = {"data": record.data}
                    existing.updated_at = now
                    await state_repo.upsert_record(existing)
                    records_needing_history.append(existing)
                    result["records_updated"] += 1

                elif direction == SyncDirection.OUTBOUND:
                    data = await self._prepare_outbound_data(
                        job, entity_type, existing, state_repo
                    )

                    if existing.external_record_id:
                        await adapter.update_record(entity_type, existing.external_record_id, data)
                    else:
                        ext_record = await adapter.create_record(entity_type, data)
                        existing.external_record_id = ext_record.id

                    # Equalize version vectors
                    max_v = max(existing.internal_version_id, existing.external_version_id)
                    existing.internal_version_id = max_v
                    existing.external_version_id = max_v
                    existing.last_sync_version_id = max_v
                    existing.sync_status = RecordSyncStatus.SYNCED
                    existing.sync_direction = SyncDirection.OUTBOUND
                    existing.last_synced_at = now
                    existing.last_job_id = job.id
                    existing.updated_at = now
                    await state_repo.upsert_record(existing)
                    records_needing_history.append(existing)
                    result["records_updated"] += 1

                # Flush inbound batch
                if len(records_to_upsert) >= BATCH_SIZE:
                    created, updated, failed = await self._flush_inbound_batch(
                        records_to_upsert, state_repo, job
                    )
                    result["records_created"] += created
                    result["records_updated"] += updated
                    result["records_failed"] += failed
                    records_to_upsert = []

            except Exception as e:
                logger.warning(
                    f"Failed to process bidirectional {display} record",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "external_id": record.id,
                        "error": str(e),
                    },
                )
                result["records_failed"] += 1
                try:
                    entry = IntegrationHistoryRecord(
                        id=uuid4(),
                        client_id=job.client_id,
                        state_record_id=None,
                        integration_id=job.integration_id,
                        entity_type=entity_type,
                        internal_record_id=None,
                        external_record_id=record.id,
                        sync_status=RecordSyncStatus.FAILED,
                        sync_direction=SyncDirection.INBOUND,
                        job_id=job.id,
                        error_code="SYNC_FAILED",
                        error_message=str(e)[:500],
                        error_details=None,
                        created_at=datetime.now(UTC),
                    )
                    await state_repo.batch_create_history([entry])
                except Exception:
                    pass

        # 3. Handle internal-only records (state with needs_outbound_sync
        #    but not seen in the external fetch above)
        synced_records = await state_repo.get_records_by_status(
            job.client_id,
            job.integration_id,
            entity_type,
            RecordSyncStatus.SYNCED,
        )
        pending_records = await state_repo.get_records_by_status(
            job.client_id,
            job.integration_id,
            entity_type,
            RecordSyncStatus.PENDING,
        )
        for state in synced_records + pending_records:
            if state.id in processed_state_ids:
                continue
            if not state.needs_outbound_sync:
                continue

            try:
                data = await self._prepare_outbound_data(job, entity_type, state, state_repo)

                if state.external_record_id:
                    await adapter.update_record(entity_type, state.external_record_id, data)
                else:
                    ext_record = await adapter.create_record(entity_type, data)
                    state.external_record_id = ext_record.id

                max_v = max(state.internal_version_id, state.external_version_id)
                state.internal_version_id = max_v
                state.external_version_id = max_v
                state.last_sync_version_id = max_v
                state.sync_status = RecordSyncStatus.SYNCED
                state.sync_direction = SyncDirection.OUTBOUND
                state.last_synced_at = now
                state.last_job_id = job.id
                state.updated_at = now
                await state_repo.upsert_record(state)
                records_needing_history.append(state)
                result["records_updated"] += 1

            except Exception as e:
                logger.warning(
                    f"Failed to sync outbound-only {display} record",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "internal_id": state.internal_record_id,
                        "error": str(e),
                    },
                )
                result["records_failed"] += 1
                await self._write_failure_history(
                    state, state_repo, job.id, SyncDirection.OUTBOUND, e
                )

        # 4. Flush remaining inbound records
        if records_to_upsert:
            created, updated, failed = await self._flush_inbound_batch(
                records_to_upsert, state_repo, job
            )
            result["records_created"] += created
            result["records_updated"] += updated
            result["records_failed"] += failed

        # 5. Write history entries for all synced records
        if records_needing_history:
            await self._write_history_entries(records_needing_history, state_repo, job.id)

        result["max_external_updated_at"] = max_external_updated_at

        logger.info(
            f"Bidirectional sync complete for {display}",
            extra={
                "job_id": str(job.id),
                "entity_type": entity_type,
                **{k: v for k, v in result.items() if k != "max_external_updated_at"},
            },
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _prepare_outbound_data(
        self,
        job: SyncJob,
        entity_type: str,
        state: IntegrationStateRecord,
        state_repo: IntegrationStateRepositoryInterface,
    ) -> dict:
        """Read current internal record and map to external format for outbound push.

        Falls back to state metadata if the internal record can't be read
        or no outbound mapper exists for this entity type.
        """
        fallback = state.metadata.get("data", {}) if state.metadata else {}
        outbound_mapper = OUTBOUND_MAPPERS.get(entity_type)
        if not outbound_mapper or not state.internal_record_id:
            return fallback

        try:
            getter_fn = self._get_internal_getter_fn(entity_type)
            internal_records = await getter_fn(
                job.client_id, record_ids=[state.internal_record_id]
            )
            if not internal_records:
                return fallback

            internal_data = dict(internal_records[0])

            # Resolve FK references needed by the outbound mapper
            if entity_type == "bill" and internal_data.get("vendor_id"):
                vendor_state = await state_repo.get_record(
                    job.client_id, job.integration_id, "vendor",
                    internal_record_id=internal_data["vendor_id"],
                )
                if vendor_state and vendor_state.external_record_id:
                    internal_data["vendor_external_id"] = vendor_state.external_record_id

            if entity_type == "invoice" and internal_data.get("contact_id"):
                contact_state = await state_repo.get_record(
                    job.client_id, job.integration_id, "vendor",
                    internal_record_id=internal_data["contact_id"],
                )
                if contact_state and contact_state.external_record_id:
                    internal_data["contact_external_id"] = contact_state.external_record_id

            return outbound_mapper(internal_data)
        except Exception as e:
            logger.warning(
                "Failed to read internal record for outbound mapping, using metadata fallback",
                extra={
                    "entity_type": entity_type,
                    "internal_record_id": state.internal_record_id,
                    "error": str(e),
                },
            )
            return fallback

    async def _ensure_vendor_synced(
        self,
        job: SyncJob,
        vendor_external_id: str,
        adapter: IntegrationAdapterInterface,
        state_repo: IntegrationStateRepositoryInterface,
    ) -> None:
        """Auto-fetch and sync a vendor if not already present in integration state."""
        existing = await state_repo.get_record_by_external_id(
            job.client_id,
            job.integration_id,
            "vendor",
            vendor_external_id,
        )
        if existing:
            return

        vendor_record = await adapter.get_record("vendor", vendor_external_id)
        if not vendor_record:
            logger.warning(
                "Vendor not found in QBO during bill dependency resolution",
                extra={
                    "job_id": str(job.id),
                    "vendor_external_id": vendor_external_id,
                },
            )
            return

        vendor_state = await self._process_inbound_record(
            job=job,
            entity_type="vendor",
            record=vendor_record,
            mapper_fn=map_vendor_inbound,
            state_repo=state_repo,
        )
        await state_repo.batch_upsert_records([vendor_state])
        await self._write_history_entries([vendor_state], state_repo, job.id)

    async def _write_history_entries(
        self,
        records: list[IntegrationStateRecord],
        state_repo: IntegrationStateRepositoryInterface,
        job_id: UUID,
    ) -> None:
        """Write history snapshots for a batch of state records."""
        try:
            now = datetime.now(UTC)
            entries = [
                IntegrationHistoryRecord(
                    id=uuid4(),
                    client_id=r.client_id,
                    state_record_id=r.id,
                    integration_id=r.integration_id,
                    entity_type=r.entity_type,
                    internal_record_id=r.internal_record_id,
                    external_record_id=r.external_record_id,
                    sync_status=r.sync_status,
                    sync_direction=r.sync_direction,
                    job_id=job_id,
                    error_code=r.error_code,
                    error_message=r.error_message,
                    error_details=r.error_details,
                    created_at=now,
                )
                for r in records
            ]
            await state_repo.batch_create_history(entries)
        except Exception as e:
            logger.error(
                "Failed to write history entries",
                extra={
                    "job_id": str(job_id),
                    "records_count": len(records),
                    "error": str(e),
                },
            )

    async def _write_failure_history(
        self,
        state: IntegrationStateRecord,
        state_repo: IntegrationStateRepositoryInterface,
        job_id: UUID,
        direction: SyncDirection,
        error: Exception,
    ) -> None:
        """Write a history entry for a failed sync attempt."""
        try:
            error_msg = str(error)[:500]
            entry = IntegrationHistoryRecord(
                id=uuid4(),
                client_id=state.client_id,
                state_record_id=state.id,
                integration_id=state.integration_id,
                entity_type=state.entity_type,
                internal_record_id=state.internal_record_id,
                external_record_id=state.external_record_id,
                sync_status=RecordSyncStatus.FAILED,
                sync_direction=direction,
                job_id=job_id,
                error_code="SYNC_FAILED",
                error_message=error_msg,
                error_details=None,
                created_at=datetime.now(UTC),
            )
            await state_repo.batch_create_history([entry])
        except Exception as hist_err:
            logger.error(
                "Failed to write failure history entry",
                extra={"job_id": str(job_id), "error": str(hist_err)},
            )

    def _get_internal_upsert_fn(self, entity_type: str):
        """Return the internal repo upsert function for an entity type."""
        fns = {
            "vendor": self._internal_repo.upsert_vendor,
            "bill": self._internal_repo.upsert_bill,
            "invoice": self._internal_repo.upsert_invoice,
            "chart_of_accounts": self._internal_repo.upsert_chart_of_accounts,
        }
        fn = fns.get(entity_type)
        if not fn:
            raise ValueError(f"No internal upsert function for entity type: {entity_type}")
        return fn

    def _get_internal_getter_fn(self, entity_type: str):
        """Return the internal repo getter function for an entity type."""
        fns = {
            "vendor": self._internal_repo.get_vendors,
            "bill": self._internal_repo.get_bills,
            "invoice": self._internal_repo.get_invoices,
            "chart_of_accounts": self._internal_repo.get_chart_of_accounts,
        }
        fn = fns.get(entity_type)
        if not fn:
            raise ValueError(f"No internal getter function for entity type: {entity_type}")
        return fn
