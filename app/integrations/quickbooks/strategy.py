"""QuickBooks Online sync strategy.

Orchestrates entity ordering, schema mapping between QBO and internal
formats, and reads/writes to the internal database.

The orchestrator delegates to this strategy for QBO-specific sync logic
while retaining responsibility for state tracking, history, and error handling.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.logging import get_logger
from app.domain.entities import ExternalRecord, IntegrationHistoryRecord, IntegrationStateRecord, SyncJob, SyncRule
from app.domain.enums import RecordSyncStatus, SyncDirection
from app.domain.interfaces import (
    IntegrationAdapterInterface,
    IntegrationStateRepositoryInterface,
)
from app.integrations.quickbooks.constants import (
    ENTITY_DISPLAY_NAMES,
    INBOUND_ENTITY_ORDER,
    OUTBOUND_ENTITY_ORDER,
    QBO_ENTITY_NAMES,
)
from app.integrations.quickbooks.internal_repo import InternalDataRepository
from app.integrations.quickbooks.mappers import INBOUND_MAPPERS, OUTBOUND_MAPPERS

logger = get_logger(__name__)


class QuickBooksSyncStrategy:
    """QBO-specific sync strategy.

    Handles entity ordering, schema mapping (QBO ↔ internal), and
    internal database reads/writes. The orchestrator calls this instead of
    doing generic entity sync.
    """

    def __init__(self) -> None:
        self._internal_repo = InternalDataRepository()

    # ------------------------------------------------------------------
    # Entity ordering
    # ------------------------------------------------------------------

    def get_entity_order(self, direction: SyncDirection) -> list[str]:
        """Return entity types in dependency order for the given direction."""
        if direction == SyncDirection.OUTBOUND:
            return list(OUTBOUND_ENTITY_ORDER)
        return list(INBOUND_ENTITY_ORDER)

    def get_ordered_rules(
        self, rules: list[SyncRule], direction: SyncDirection
    ) -> list[SyncRule]:
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
                    max_external_updated_at is None
                    or record.updated_at > max_external_updated_at
                ):
                    max_external_updated_at = record.updated_at

                try:
                    state_record = await self._process_inbound_record(
                        job=job,
                        entity_type=entity_type,
                        record=record,
                        mapper_fn=mapper_fn,
                        state_repo=state_repo,
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
    ) -> IntegrationStateRecord:
        """Map a single QBO record and write to internal database.

        Returns an IntegrationStateRecord ready for batch upsert.
        """
        # 1. Map QBO data to internal schema
        mapped_data = mapper_fn(record.data)

        # Tag with external_id so the internal repo can do upsert-by-external-id
        mapped_data["_external_id"] = record.id

        # 2. Write to internal database
        upsert_fn = self._get_internal_upsert_fn(entity_type)
        internal_record_id = await upsert_fn(job.client_id, mapped_data)

        # 3. Build IntegrationStateRecord
        existing = await state_repo.get_record_by_external_id(
            job.client_id, job.integration_id, entity_type, record.id
        )

        now = datetime.now(timezone.utc)

        if existing:
            # Preserve internal_record_id — never null it out (upsert guard)
            if internal_record_id:
                existing.internal_record_id = internal_record_id
            existing.external_version_id += 1
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
    ) -> dict[str, Any]:
        """Read from internal database, map to QBO schema, push to QBO.

        Returns a summary dict with counts.
        """
        display = ENTITY_DISPLAY_NAMES.get(entity_type, entity_type)
        mapper_fn = OUTBOUND_MAPPERS.get(entity_type)

        result: dict[str, Any] = {
            "direction": "outbound",
            "records_fetched": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
        }

        if not mapper_fn:
            logger.info(
                "No outbound mapper for entity type — skipping",
                extra={"entity_type": entity_type},
            )
            return result

        # 1. Get records from internal database
        getter_fn = self._get_internal_getter_fn(entity_type)
        internal_records = await getter_fn(
            job.client_id, since=since, record_ids=record_ids
        )
        result["records_fetched"] = len(internal_records)

        if not internal_records:
            logger.info(
                f"No {display} records to sync outbound",
                extra={"job_id": str(job.id), "entity_type": entity_type},
            )
            return result

        # 2. Process each record
        successful_syncs: list[tuple[UUID, UUID, str | None]] = []
        successful_states: list[IntegrationStateRecord] = []

        for internal_record in internal_records:
            try:
                state, external_id = await self._process_outbound_record(
                    job=job,
                    entity_type=entity_type,
                    internal_record=internal_record,
                    mapper_fn=mapper_fn,
                    adapter=adapter,
                    state_repo=state_repo,
                )

                successful_syncs.append(
                    (state.id, job.client_id, external_id)
                )
                successful_states.append(state)

            except Exception as e:
                internal_id = str(internal_record.get("id", "unknown"))
                logger.warning(
                    f"Failed to sync outbound {display} record",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "internal_id": internal_id,
                        "error": str(e),
                    },
                )
                result["records_failed"] += 1

        # 3. Batch mark synced + write history
        if successful_states:
            await self._write_history_entries(successful_states, state_repo, job.id)
        if successful_syncs:
            try:
                await state_repo.batch_mark_synced(
                    successful_syncs,
                    client_id=job.client_id,
                    integration_id=job.integration_id,
                )
                result["records_updated"] += len(successful_syncs)
            except Exception as e:
                logger.error(
                    "Outbound batch mark_synced failed — trying individually",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "count": len(successful_syncs),
                        "error": str(e),
                    },
                )
                for record_id, client_id, ext_id in successful_syncs:
                    try:
                        await state_repo.mark_synced(record_id, client_id, ext_id)
                        result["records_updated"] += 1
                    except Exception:
                        result["records_failed"] += 1

        logger.info(
            f"Outbound sync complete for {display}",
            extra={
                "job_id": str(job.id),
                "entity_type": entity_type,
                **result,
            },
        )
        return result

    async def _process_outbound_record(
        self,
        job: SyncJob,
        entity_type: str,
        internal_record: dict[str, Any],
        mapper_fn: Any,
        adapter: IntegrationAdapterInterface,
        state_repo: IntegrationStateRepositoryInterface,
    ) -> tuple[IntegrationStateRecord, str]:
        """Map a single internal record and push to QBO.

        Returns (IntegrationStateRecord, external_id).
        """
        internal_id = str(internal_record["id"])
        existing_external_id = internal_record.get("external_id")

        # 1. Map internal data to QBO schema
        qbo_payload = mapper_fn(internal_record)

        # 2. Create or update in QBO
        if existing_external_id:
            external_record = await adapter.update_record(
                entity_type, existing_external_id, qbo_payload
            )
            external_id = existing_external_id
        else:
            external_record = await adapter.create_record(
                entity_type, qbo_payload
            )
            external_id = external_record.id

            # Update external_id in internal database
            table = InternalDataRepository.ENTITY_TABLE_MAP.get(entity_type)
            if table:
                await self._internal_repo.set_external_id(
                    table, internal_id, external_id
                )

        # 3. Build / update IntegrationStateRecord
        existing_state = await state_repo.get_record(
            job.client_id, job.integration_id, entity_type,
            internal_record_id=internal_id,
        )

        now = datetime.now(timezone.utc)

        if existing_state:
            existing_state.external_record_id = external_id
            existing_state.sync_status = RecordSyncStatus.SYNCED
            existing_state.sync_direction = SyncDirection.OUTBOUND
            existing_state.last_synced_at = now
            existing_state.last_job_id = job.id
            existing_state.updated_at = now
            await state_repo.upsert_record(existing_state)
            return existing_state, external_id
        else:
            state = IntegrationStateRecord(
                id=uuid4(),
                client_id=job.client_id,
                integration_id=job.integration_id,
                entity_type=entity_type,
                internal_record_id=internal_id,
                external_record_id=external_id,
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.OUTBOUND,
                internal_version_id=1,
                external_version_id=1,
                last_sync_version_id=1,
                last_synced_at=now,
                last_job_id=job.id,
                metadata={"data": internal_record},
                created_at=now,
                updated_at=now,
            )
            await state_repo.upsert_record(state)
            return state, external_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _write_history_entries(
        self,
        records: list[IntegrationStateRecord],
        state_repo: IntegrationStateRepositoryInterface,
        job_id: UUID,
    ) -> None:
        """Write history snapshots for a batch of state records."""
        try:
            now = datetime.now(timezone.utc)
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
