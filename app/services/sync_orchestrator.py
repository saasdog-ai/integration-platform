"""Sync orchestration service."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    SyncError,
)
from app.core.logging import get_logger
from app.domain.entities import (
    EntitySyncRequest,
    IntegrationStateRecord,
    SyncJob,
    SyncJobMessage,
    SyncRule,
)
from app.domain.enums import (
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.domain.interfaces import (
    AdapterFactoryInterface,
    EncryptionServiceInterface,
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    MessageQueueInterface,
    SyncJobRepositoryInterface,
)

logger = get_logger(__name__)


class SyncOrchestrator:
    """Orchestrates sync jobs between internal and external systems."""

    def __init__(
        self,
        integration_repo: IntegrationRepositoryInterface,
        job_repo: SyncJobRepositoryInterface,
        state_repo: IntegrationStateRepositoryInterface,
        queue: MessageQueueInterface,
        encryption_service: EncryptionServiceInterface,
        adapter_factory: AdapterFactoryInterface,
    ) -> None:
        """
        Initialize sync orchestrator.

        Args:
            integration_repo: Repository for integration data.
            job_repo: Repository for sync job data.
            state_repo: Repository for integration state data.
            queue: Message queue for async job dispatch.
            encryption_service: Service for credential encryption.
            adapter_factory: Factory for creating integration adapters.
        """
        self._integration_repo = integration_repo
        self._job_repo = job_repo
        self._state_repo = state_repo
        self._queue = queue
        self._encryption = encryption_service
        self._adapter_factory = adapter_factory

    async def trigger_sync(
        self,
        client_id: UUID,
        integration_id: UUID,
        job_type: SyncJobType = SyncJobType.INCREMENTAL,
        entity_types: list[str] | None = None,
        entity_requests: list[EntitySyncRequest] | None = None,
        triggered_by: SyncJobTrigger = SyncJobTrigger.USER,
        user_id: str | None = None,
    ) -> SyncJob:
        """
        Trigger a new sync job.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration to sync.
            job_type: Type of sync (full, incremental, entity).
            entity_types: Simple list of entity types to sync (optional).
            entity_requests: Detailed requests with optional record IDs (optional).
            triggered_by: What triggered the sync.
            user_id: Optional user ID for audit.

        Returns:
            The created sync job.
        """
        # Check global kill switch
        settings = get_settings()
        if settings.sync_globally_disabled:
            raise SyncError(
                "Sync is currently disabled globally",
                details={"reason": "feature_flag"},
            )

        # Verify integration exists and is connected
        integration = await self._integration_repo.get_available_integration(
            integration_id
        )
        if not integration:
            raise NotFoundError("Integration", integration_id)

        # Check if integration is disabled via feature flag
        if integration.name in settings.disabled_integrations:
            raise SyncError(
                f"Integration '{integration.name}' is currently disabled",
                details={"reason": "feature_flag", "integration": integration.name},
            )

        user_integration = await self._integration_repo.get_user_integration(
            client_id, integration_id
        )
        if not user_integration:
            raise NotFoundError(
                "UserIntegration", f"{client_id}/{integration_id}"
            )

        if user_integration.status != IntegrationStatus.CONNECTED:
            raise SyncError(
                f"Integration is not connected (status: {user_integration.status})"
            )

        # Validate entity types if provided
        if entity_types:
            supported = set(integration.supported_entities)
            invalid = [e for e in entity_types if e not in supported]
            if invalid:
                raise SyncError(
                    f"Invalid entity types: {', '.join(invalid)}",
                    details={"supported": list(supported)},
                )

        # Build job_params to store in DB (for idempotent retry if queue send fails)
        job_params: dict[str, Any] = {}
        if entity_types:
            job_params["entity_types"] = entity_types
        if entity_requests:
            job_params["entity_requests"] = [
                req.model_dump(mode="json") for req in entity_requests
            ]

        # Create sync job with job_params (atomic check-and-create to prevent race conditions)
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            status=SyncJobStatus.PENDING,
            triggered_by=triggered_by,
            job_params=job_params if job_params else None,
            created_at=now,
            updated_at=now,
            created_by=user_id,
        )

        # Atomic operation: check for running jobs and create if none exist
        created_job, existing_job = await self._job_repo.create_job_if_no_running(job)

        if existing_job:
            raise ConflictError(
                "A sync job is already running or pending for this integration",
                resource_type="SyncJob",
                details={"existing_job_id": str(existing_job.id), "status": existing_job.status.value},
            )

        job = created_job

        # Dispatch job to queue (params come from job_params stored in DB)
        message = SyncJobMessage(
            job_id=job.id,
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            entity_types=job_params.get("entity_types") if job_params else None,
            entity_requests=[
                EntitySyncRequest(**req) for req in job_params.get("entity_requests", [])
            ] if job_params and job_params.get("entity_requests") else None,
        )
        await self._queue.send_message(message.model_dump(mode="json"))

        logger.info(
            "Sync job triggered",
            extra={
                "job_id": str(job.id),
                "client_id": str(client_id),
                "integration_id": str(integration_id),
                "job_type": job_type.value,
                "triggered_by": triggered_by.value,
            },
        )

        return job

    async def execute_sync_job(self, job: SyncJob) -> SyncJob:
        """
        Execute a sync job (called by job runner).

        Args:
            job: The sync job to execute.

        Returns:
            The updated sync job.
        """
        # Update job status to running
        job = await self._job_repo.update_job_status(job.id, SyncJobStatus.RUNNING)

        try:
            # Get user settings to determine which entities to sync
            settings = await self._integration_repo.get_user_settings(
                job.client_id, job.integration_id
            )

            if not settings or not settings.sync_rules:
                raise SyncError("No sync rules configured")

            # Get enabled rules
            enabled_rules = [r for r in settings.sync_rules if r.enabled]
            if not enabled_rules:
                raise SyncError("No sync rules are enabled")

            # Get credentials and create adapter
            user_integration = await self._integration_repo.get_user_integration(
                job.client_id, job.integration_id
            )
            integration = await self._integration_repo.get_available_integration(
                job.integration_id
            )

            if not user_integration or not user_integration.credentials_encrypted:
                raise SyncError("Integration credentials not found")

            credentials = await self._encryption.decrypt(
                user_integration.credentials_encrypted,
                user_integration.credentials_key_id,
            )
            creds_dict = json.loads(credentials.decode())

            adapter = self._adapter_factory.get_adapter(
                integration,
                creds_dict["access_token"],
                user_integration.external_account_id,
            )

            # Process each enabled entity rule
            entities_processed: dict[str, Any] = {}
            errors: list[dict[str, Any]] = []

            for rule in enabled_rules:
                try:
                    result = await self._sync_entity(
                        job, rule, adapter, job.job_type == SyncJobType.FULL_SYNC
                    )
                    entities_processed[rule.entity_type] = result
                except Exception as e:
                    logger.error(
                        "Entity sync failed",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": rule.entity_type,
                            "error": str(e),
                        },
                    )
                    errors.append(
                        {"entity_type": rule.entity_type, "error": str(e)}
                    )

            # Update job status
            if errors and len(errors) == len(enabled_rules):
                # All entities failed
                job = await self._job_repo.update_job_status(
                    job.id,
                    SyncJobStatus.FAILED,
                    error_code="ALL_ENTITIES_FAILED",
                    error_message="All entity syncs failed",
                    error_details={"errors": errors},
                    entities_processed=entities_processed,
                )
            elif errors:
                # Partial failure - still mark as succeeded but with errors
                job = await self._job_repo.update_job_status(
                    job.id,
                    SyncJobStatus.SUCCEEDED,
                    entities_processed={
                        **entities_processed,
                        "_errors": errors,
                    },
                )
            else:
                job = await self._job_repo.update_job_status(
                    job.id,
                    SyncJobStatus.SUCCEEDED,
                    entities_processed=entities_processed,
                )

            logger.info(
                "Sync job completed",
                extra={
                    "job_id": str(job.id),
                    "status": job.status.value,
                    "entities_count": len(entities_processed),
                    "errors_count": len(errors),
                },
            )

        except Exception as e:
            logger.error(
                "Sync job failed",
                extra={"job_id": str(job.id), "error": str(e)},
            )
            job = await self._job_repo.update_job_status(
                job.id,
                SyncJobStatus.FAILED,
                error_code="SYNC_FAILED",
                error_message=str(e),
            )

        return job

    async def _sync_entity(
        self,
        job: SyncJob,
        rule: SyncRule,
        adapter: Any,
        full_sync: bool,
    ) -> dict[str, Any]:
        """
        Sync a specific entity type.

        Args:
            job: The sync job.
            rule: The sync rule for this entity.
            adapter: The integration adapter.
            full_sync: Whether this is a full sync.

        Returns:
            Summary of synced records.
        """
        entity_type = rule.entity_type
        direction = rule.direction

        result = {
            "direction": direction.value,
            "records_fetched": 0,
            "records_created": 0,
            "records_updated": 0,
            "records_failed": 0,
        }

        # Get last sync time for incremental sync
        since = None
        if not full_sync:
            entity_status = await self._state_repo.get_entity_sync_status(
                job.client_id, job.integration_id, entity_type
            )
            if entity_status and entity_status.last_successful_sync_at:
                since = entity_status.last_successful_sync_at

        # Inbound sync: fetch from external, update internal
        # Process in batches to prevent memory exhaustion with large datasets
        BATCH_SIZE = 1000  # Max records to hold in memory before flushing

        if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
            page_token = None
            records_to_upsert: list[IntegrationStateRecord] = []
            batch_created = 0
            batch_updated = 0

            async def flush_batch() -> tuple[int, int]:
                """Flush accumulated records to DB and return (created, updated) counts."""
                nonlocal records_to_upsert, batch_created, batch_updated
                if not records_to_upsert:
                    return 0, 0

                created = batch_created
                updated = batch_updated
                try:
                    await self._state_repo.batch_upsert_records(records_to_upsert)
                    logger.debug(
                        "Flushed inbound batch",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": entity_type,
                            "batch_size": len(records_to_upsert),
                        },
                    )
                except Exception as e:
                    logger.error(
                        "Batch upsert failed",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": entity_type,
                            "batch_size": len(records_to_upsert),
                            "error": str(e),
                        },
                    )
                    # Count these as failed
                    result["records_failed"] += created + updated
                    created, updated = 0, 0

                # Clear batch
                records_to_upsert = []
                batch_created = 0
                batch_updated = 0
                return created, updated

            while True:
                records, next_token = await adapter.fetch_records(
                    entity_type, since=since, page_token=page_token
                )
                result["records_fetched"] += len(records)

                for record in records:
                    try:
                        # Check if record exists
                        state = await self._state_repo.get_record(
                            job.client_id,
                            job.integration_id,
                            entity_type,
                            record.id,  # Using external ID as internal for demo
                        )

                        if state:
                            state.external_version_id += 1
                            state.sync_status = RecordSyncStatus.PENDING
                            records_to_upsert.append(state)
                            batch_updated += 1
                        else:
                            now = datetime.now(timezone.utc)
                            state = IntegrationStateRecord(
                                id=uuid4(),
                                client_id=job.client_id,
                                integration_id=job.integration_id,
                                entity_type=entity_type,
                                internal_record_id=record.id,
                                external_record_id=record.id,
                                sync_status=RecordSyncStatus.SYNCED,
                                sync_direction=SyncDirection.INBOUND,
                                internal_version_id=1,
                                external_version_id=1,
                                last_sync_version_id=1,
                                last_synced_at=now,
                                metadata={"data": record.data},
                                created_at=now,
                                updated_at=now,
                            )
                            records_to_upsert.append(state)
                            batch_created += 1

                        # Flush batch when it reaches size limit
                        if len(records_to_upsert) >= BATCH_SIZE:
                            created, updated = await flush_batch()
                            result["records_created"] += created
                            result["records_updated"] += updated

                    except Exception as e:
                        logger.warning(
                            "Failed to process inbound record",
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

            # Flush any remaining records
            created, updated = await flush_batch()
            result["records_created"] += created
            result["records_updated"] += updated

        # Outbound sync: push pending internal records to external
        # CRITICAL: We must update external_record_id immediately after external operation
        # to prevent duplicates if batch update fails
        if direction in (SyncDirection.OUTBOUND, SyncDirection.BIDIRECTIONAL):
            pending_records = await self._state_repo.get_pending_records(
                job.client_id, job.integration_id, entity_type
            )

            # Collect successful syncs for batch update
            successful_syncs: list[tuple[UUID, UUID, str | None]] = []

            for state in pending_records:
                try:
                    # Get record data from metadata (simplified - real impl would fetch from internal system)
                    data = state.metadata.get("data", {}) if state.metadata else {}

                    if state.external_record_id:
                        # Update existing external record
                        await adapter.update_record(
                            entity_type, state.external_record_id, data
                        )
                    else:
                        # Create new external record
                        external_record = await adapter.create_record(entity_type, data)
                        state.external_record_id = external_record.id

                        # CRITICAL: Immediately persist external_record_id to prevent duplicates
                        # If this fails but external create succeeded, we'll have a duplicate on retry
                        # But this is better than losing track of the external_record_id
                        try:
                            await self._state_repo.upsert_record(state)
                        except Exception as persist_err:
                            logger.error(
                                "Failed to persist external_record_id - duplicate risk on retry",
                                extra={
                                    "job_id": str(job.id),
                                    "entity_type": entity_type,
                                    "internal_id": state.internal_record_id,
                                    "external_id": state.external_record_id,
                                    "error": str(persist_err),
                                },
                            )
                            # Continue - we'll try to mark as synced in batch

                    # Collect for batch update
                    successful_syncs.append(
                        (state.id, job.client_id, state.external_record_id)
                    )

                except Exception as e:
                    logger.warning(
                        "Failed to process outbound record",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": entity_type,
                            "internal_id": state.internal_record_id,
                            "error": str(e),
                        },
                    )
                    await self._state_repo.update_sync_status(
                        state.id,
                        job.client_id,
                        RecordSyncStatus.FAILED,
                        error_message=str(e),
                    )
                    result["records_failed"] += 1

            # Batch mark all successful syncs in a single transaction with advisory lock
            if successful_syncs:
                try:
                    await self._state_repo.batch_mark_synced(
                        successful_syncs,
                        client_id=job.client_id,
                        integration_id=job.integration_id,
                    )
                    result["records_updated"] += len(successful_syncs)
                except Exception as e:
                    logger.error(
                        "Batch mark_synced failed - attempting individual updates",
                        extra={
                            "job_id": str(job.id),
                            "entity_type": entity_type,
                            "records_count": len(successful_syncs),
                            "error": str(e),
                        },
                    )
                    # Fallback: try individual updates to salvage what we can
                    for record_id, client_id_param, external_id in successful_syncs:
                        try:
                            await self._state_repo.mark_synced(
                                record_id, client_id_param, external_id
                            )
                            result["records_updated"] += 1
                        except Exception as individual_err:
                            logger.error(
                                "Individual mark_synced failed",
                                extra={
                                    "record_id": str(record_id),
                                    "external_id": external_id,
                                    "error": str(individual_err),
                                },
                            )
                            result["records_failed"] += 1

        # Update entity sync status
        total_synced = result["records_created"] + result["records_updated"]
        if total_synced > 0:
            await self._state_repo.update_entity_sync_status(
                job.client_id, job.integration_id, entity_type, job.id, total_synced
            )

        return result

    async def cancel_sync_job(
        self,
        client_id: UUID,
        job_id: UUID,
        user_id: str | None = None,
    ) -> SyncJob:
        """
        Cancel a running sync job.

        Args:
            client_id: The tenant/client ID.
            job_id: The job to cancel.
            user_id: Optional user ID for audit.

        Returns:
            The cancelled job.
        """
        job = await self._job_repo.get_job(job_id)
        if not job:
            raise NotFoundError("SyncJob", job_id)

        if job.client_id != client_id:
            raise NotFoundError("SyncJob", job_id)

        if job.status not in (SyncJobStatus.PENDING, SyncJobStatus.RUNNING):
            raise SyncError(
                f"Cannot cancel job with status {job.status.value}",
                details={"job_id": str(job_id), "current_status": job.status.value},
            )

        job = await self._job_repo.update_job_status(job_id, SyncJobStatus.CANCELLED)

        logger.info(
            "Sync job cancelled",
            extra={"job_id": str(job_id), "client_id": str(client_id)},
        )

        return job

    async def get_job(self, client_id: UUID, job_id: UUID) -> SyncJob:
        """Get a sync job by ID."""
        job = await self._job_repo.get_job(job_id)
        if not job or job.client_id != client_id:
            raise NotFoundError("SyncJob", job_id)
        return job

    async def get_jobs(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[SyncJob]:
        """Get sync jobs for a client."""
        return await self._job_repo.get_jobs_for_client(
            client_id,
            integration_id=integration_id,
            status=status,
            since=since,
            limit=limit,
        )
