"""Sync orchestration service."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    SyncError,
)
from app.core.logging import get_logger
from app.domain.entities import (
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
        triggered_by: SyncJobTrigger = SyncJobTrigger.USER,
        user_id: str | None = None,
    ) -> SyncJob:
        """
        Trigger a new sync job.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration to sync.
            job_type: Type of sync (full, incremental, entity).
            entity_types: Specific entity types to sync (optional).
            triggered_by: What triggered the sync.
            user_id: Optional user ID for audit.

        Returns:
            The created sync job.
        """
        # Verify integration exists and is connected
        integration = await self._integration_repo.get_available_integration(
            integration_id
        )
        if not integration:
            raise NotFoundError("Integration", integration_id)

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

        # Check for running jobs
        running_jobs = await self._job_repo.get_running_jobs(client_id, integration_id)
        if running_jobs:
            raise ConflictError(
                f"A sync job is already running for this integration",
                resource_type="SyncJob",
                details={"running_job_id": str(running_jobs[0].id)},
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

        # Create sync job
        now = datetime.now(timezone.utc)
        job = SyncJob(
            id=uuid4(),
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            status=SyncJobStatus.PENDING,
            triggered_by=triggered_by,
            created_at=now,
            updated_at=now,
            created_by=user_id,
        )
        job = await self._job_repo.create_job(job)

        # Dispatch job to queue
        message = SyncJobMessage(
            job_id=job.id,
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            entity_types=entity_types,
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
        if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
            page_token = None
            while True:
                records, next_token = await adapter.fetch_records(
                    entity_type, since=since, page_token=page_token
                )
                result["records_fetched"] += len(records)

                for record in records:
                    try:
                        # Upsert integration state record
                        state = await self._state_repo.get_record(
                            job.client_id,
                            job.integration_id,
                            entity_type,
                            record.id,  # Using external ID as internal for demo
                        )

                        if state:
                            state.external_version_id += 1
                            state.sync_status = RecordSyncStatus.PENDING
                            await self._state_repo.upsert_record(state)
                            result["records_updated"] += 1
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
                            await self._state_repo.upsert_record(state)
                            result["records_created"] += 1

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

        # Outbound sync: push pending internal records to external
        if direction in (SyncDirection.OUTBOUND, SyncDirection.BIDIRECTIONAL):
            pending_records = await self._state_repo.get_pending_records(
                job.client_id, job.integration_id, entity_type
            )

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

                    # Mark as synced
                    await self._state_repo.mark_synced(
                        state.id, job.client_id, state.external_record_id
                    )
                    result["records_updated"] += 1

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
