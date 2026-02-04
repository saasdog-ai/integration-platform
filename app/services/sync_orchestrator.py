"""Sync orchestration service."""

import json
from datetime import UTC, datetime, timedelta
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
    ChangeEvent,
    EntitySyncRequest,
    IntegrationHistoryRecord,
    IntegrationStateRecord,
    SyncJob,
    SyncJobMessage,
    SyncRule,
)
from app.domain.enums import (
    ChangeSourceType,
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
    SyncTriggerMode,
)
from app.domain.interfaces import (
    AdapterFactoryInterface,
    EncryptionServiceInterface,
    IntegrationAdapterInterface,
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    MessageQueueInterface,
    SyncJobRepositoryInterface,
)
from app.services.integration_service import IntegrationService

logger = get_logger(__name__)

# Strategy registry: integration name → strategy class
_SYNC_STRATEGIES: dict[str, type] = {}


def register_sync_strategy(integration_name: str, strategy_class: type) -> None:
    """Register a sync strategy for an integration."""
    _SYNC_STRATEGIES[integration_name] = strategy_class


def _init_strategies() -> None:
    """Register built-in strategies on first use."""
    if _SYNC_STRATEGIES:
        return
    try:
        from app.integrations.quickbooks.strategy import QuickBooksSyncStrategy

        register_sync_strategy("QuickBooks Online", QuickBooksSyncStrategy)
    except ImportError:
        pass


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
        _init_strategies()

    async def _write_history_entries(
        self, records: list[IntegrationStateRecord], job_id: UUID
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
            await self._state_repo.batch_create_history(entries)
        except Exception as e:
            logger.error(
                "Failed to write history entries",
                extra={
                    "job_id": str(job_id),
                    "records_count": len(records),
                    "error": str(e),
                },
            )

    async def _execute_with_strategy(
        self,
        strategy_class: type,
        job: SyncJob,
        enabled_rules: list[SyncRule],
        adapter: IntegrationAdapterInterface,
        record_ids_by_entity: dict[str, list[str]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Execute sync using an integration-specific strategy.

        Returns (entities_processed, errors).
        """
        strategy = strategy_class()
        full_sync = job.job_type == SyncJobType.FULL_SYNC
        entities_processed: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []

        # Determine primary direction from rules for ordering
        directions = {r.direction for r in enabled_rules}
        if SyncDirection.INBOUND in directions or SyncDirection.BIDIRECTIONAL in directions:
            primary_direction = SyncDirection.INBOUND
        else:
            primary_direction = SyncDirection.OUTBOUND

        ordered_rules = strategy.get_ordered_rules(enabled_rules, primary_direction)

        for rule in ordered_rules:
            entity_type = rule.entity_type
            direction = rule.direction
            record_ids = record_ids_by_entity.get(entity_type)

            # Get last sync time for incremental sync — use direction-appropriate cursor
            inbound_since = None
            outbound_since = None
            if not full_sync:
                entity_status = await self._state_repo.get_entity_sync_status(
                    job.client_id, job.integration_id, entity_type
                )
                if entity_status:
                    # Inbound: prefer QBO-clock cursor, fall back to our clock for pre-migration rows
                    inbound_since = (
                        entity_status.last_inbound_sync_at or entity_status.last_successful_sync_at
                    )
                    # Outbound: always our clock
                    outbound_since = entity_status.last_successful_sync_at

            try:
                result: dict[str, Any] = {}

                if direction == SyncDirection.BIDIRECTIONAL:
                    result = await strategy.sync_entity_bidirectional(
                        job=job,
                        entity_type=entity_type,
                        adapter=adapter,
                        state_repo=self._state_repo,
                        rule=rule,
                        since=inbound_since,
                        record_ids=record_ids,
                    )
                elif direction == SyncDirection.INBOUND:
                    result = await strategy.sync_entity_inbound(
                        job=job,
                        entity_type=entity_type,
                        adapter=adapter,
                        state_repo=self._state_repo,
                        since=inbound_since,
                        record_ids=record_ids,
                    )
                elif direction == SyncDirection.OUTBOUND:
                    result = await strategy.sync_entity_outbound(
                        job=job,
                        entity_type=entity_type,
                        adapter=adapter,
                        state_repo=self._state_repo,
                        since=outbound_since,
                        record_ids=record_ids,
                    )

                # Update entity sync status (before serializing datetime for JSON)
                total_synced = result.get("records_created", 0) + result.get("records_updated", 0)
                if total_synced > 0:
                    await self._state_repo.update_entity_sync_status(
                        job.client_id,
                        job.integration_id,
                        entity_type,
                        job.id,
                        total_synced,
                        last_inbound_sync_at=result.get("max_external_updated_at"),
                    )

                # Serialize datetime for JSONB storage
                ts = result.get("max_external_updated_at")
                if ts is not None:
                    result["max_external_updated_at"] = ts.isoformat()

                entities_processed[entity_type] = result

            except Exception as e:
                logger.error(
                    "Strategy entity sync failed",
                    extra={
                        "job_id": str(job.id),
                        "entity_type": entity_type,
                        "strategy": strategy_class.__name__,
                        "error": str(e),
                    },
                )
                errors.append({"entity_type": entity_type, "error": str(e)})

        return entities_processed, errors

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
        integration = await self._integration_repo.get_available_integration(integration_id)
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
            raise NotFoundError("UserIntegration", f"{client_id}/{integration_id}")

        if user_integration.status != IntegrationStatus.CONNECTED:
            raise SyncError(f"Integration is not connected (status: {user_integration.status})")

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
            job_params["entity_requests"] = [req.model_dump(mode="json") for req in entity_requests]

        # Create sync job with job_params (atomic check-and-create to prevent race conditions)
        now = datetime.now(UTC)
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
                details={
                    "existing_job_id": str(existing_job.id),
                    "status": existing_job.status.value,
                },
            )

        job = created_job

        # Dispatch job to queue (params come from job_params stored in DB)
        message = SyncJobMessage(
            job_id=job.id,
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            entity_types=job_params.get("entity_types") if job_params else None,
            entity_requests=(
                [EntitySyncRequest(**req) for req in job_params.get("entity_requests", [])]
                if job_params and job_params.get("entity_requests")
                else None
            ),
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

    @staticmethod
    def _resolve_requested_entity_types(
        job_params: dict[str, Any] | None,
    ) -> set[str] | None:
        """Resolve which entity types were requested in job params.

        Returns a set of entity type names to filter on, or None if no
        filtering was requested (run all enabled rules).

        Priority:
            1. entity_requests (with optional record_ids) -> extract entity types
            2. entity_types -> use directly
            3. Neither -> None (no filtering)
        """
        if not job_params:
            return None

        entity_requests = job_params.get("entity_requests")
        if entity_requests:
            return {req["entity_type"] for req in entity_requests}

        entity_types = job_params.get("entity_types")
        if entity_types:
            return set(entity_types)

        return None

    async def _ensure_valid_token(
        self,
        client_id: UUID,
        integration_id: UUID,
        creds_dict: dict,
    ) -> str:
        """Return a valid access token, refreshing if expired or about to expire.

        If ``expires_at`` is missing or malformed the existing token is returned
        as-is (graceful degradation for legacy credentials).
        """
        access_token = creds_dict.get("access_token", "")
        expires_at_raw = creds_dict.get("expires_at")

        if expires_at_raw is None:
            logger.warning(
                "No expires_at in credentials — skipping token refresh check",
                extra={"client_id": str(client_id), "integration_id": str(integration_id)},
            )
            return access_token

        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid expires_at format — skipping token refresh check",
                extra={
                    "client_id": str(client_id),
                    "integration_id": str(integration_id),
                    "expires_at": str(expires_at_raw),
                },
            )
            return access_token

        buffer = timedelta(minutes=5)
        if datetime.now(UTC) < expires_at - buffer:
            return access_token

        # Token expired or about to expire — refresh
        integration_service = IntegrationService(
            integration_repo=self._integration_repo,
            encryption_service=self._encryption,
            adapter_factory=self._adapter_factory,
        )

        max_attempts = 2
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                new_tokens = await integration_service.refresh_integration_token(
                    client_id,
                    integration_id,
                )
                logger.info(
                    "Token refreshed successfully",
                    extra={
                        "client_id": str(client_id),
                        "integration_id": str(integration_id),
                        "attempt": attempt,
                    },
                )
                return new_tokens.access_token
            except IntegrationError as exc:
                last_error = exc
                logger.warning(
                    "Token refresh attempt failed",
                    extra={
                        "client_id": str(client_id),
                        "integration_id": str(integration_id),
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

        raise SyncError(
            f"Token refresh failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    async def _get_enabled_rules_for_job(self, job: SyncJob) -> list[SyncRule]:
        """Load user settings and return enabled sync rules, filtered by job_params."""
        settings = await self._integration_repo.get_user_settings(job.client_id, job.integration_id)

        if not settings or not settings.sync_rules:
            raise SyncError("No sync rules configured")

        enabled_rules = [r for r in settings.sync_rules if r.enabled]
        if not enabled_rules:
            raise SyncError("No sync rules are enabled")

        requested_entity_types = self._resolve_requested_entity_types(job.job_params)
        if requested_entity_types is not None:
            enabled_rules = [r for r in enabled_rules if r.entity_type in requested_entity_types]
            if not enabled_rules:
                raise SyncError(
                    f"Requested entity types are not enabled in sync settings: "
                    f"{', '.join(sorted(requested_entity_types))}",
                )

        return enabled_rules

    async def _resolve_adapter_for_job(
        self,
        job: SyncJob,
    ) -> tuple[Any, type | None, dict[str, list[str]]]:
        """Resolve adapter, strategy class, and record_ids_by_entity for a job."""
        user_integration = await self._integration_repo.get_user_integration(
            job.client_id, job.integration_id
        )
        integration = await self._integration_repo.get_available_integration(job.integration_id)

        # Get credentials - allow mock token in development mode
        settings = get_settings()
        access_token = "mock_dev_token"  # Default for dev

        if user_integration and user_integration.credentials_encrypted:
            try:
                credentials = await self._encryption.decrypt(
                    user_integration.credentials_encrypted,
                    user_integration.credentials_key_id,
                )
                creds_dict = json.loads(credentials.decode())
                access_token = await self._ensure_valid_token(
                    job.client_id,
                    job.integration_id,
                    creds_dict,
                )
            except Exception as e:
                if settings.app_env != "development":
                    raise SyncError(f"Failed to decrypt credentials: {e}") from e
                logger.warning(
                    "Using mock token - credential decryption failed in dev mode",
                    extra={"error": str(e)},
                )
        elif settings.app_env != "development":
            raise SyncError("Integration credentials not found")
        else:
            logger.info("Using mock token - no credentials in dev mode")

        adapter = self._adapter_factory.get_adapter(
            integration,
            access_token,
            user_integration.external_account_id if user_integration else None,
        )

        strategy_class = _SYNC_STRATEGIES.get(integration.name) if integration else None

        record_ids_by_entity: dict[str, list[str]] = {}
        if job.job_params and job.job_params.get("entity_requests"):
            for req in job.job_params["entity_requests"]:
                if req.get("record_ids"):
                    record_ids_by_entity[req["entity_type"]] = req["record_ids"]

        return adapter, strategy_class, record_ids_by_entity

    async def _execute_entity_sync_loop(
        self,
        job: SyncJob,
        enabled_rules: list[SyncRule],
        adapter: Any,
        strategy_class: type | None,
        record_ids_by_entity: dict[str, list[str]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Run entity syncs via strategy or generic per-rule loop."""
        entities_processed: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []

        if strategy_class:
            entities_processed, errors = await self._execute_with_strategy(
                strategy_class,
                job,
                enabled_rules,
                adapter,
                record_ids_by_entity,
            )
        else:
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
                    errors.append({"entity_type": rule.entity_type, "error": str(e)})

        return entities_processed, errors

    async def _finalize_job_status(
        self,
        job: SyncJob,
        entities_processed: dict[str, Any],
        errors: list[dict[str, Any]],
        enabled_rules_count: int,
    ) -> SyncJob:
        """Update job status based on sync results."""
        if errors and len(errors) == enabled_rules_count:
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
            enabled_rules = await self._get_enabled_rules_for_job(job)
            adapter, strategy_class, record_ids_by_entity = await self._resolve_adapter_for_job(job)
            entities_processed, errors = await self._execute_entity_sync_loop(
                job,
                enabled_rules,
                adapter,
                strategy_class,
                record_ids_by_entity,
            )
            job = await self._finalize_job_status(
                job,
                entities_processed,
                errors,
                len(enabled_rules),
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

    async def _resolve_sync_cursors(
        self,
        job: SyncJob,
        entity_type: str,
        full_sync: bool,
    ) -> tuple[datetime | None, datetime | None]:
        """Return (inbound_since, outbound_since) cursors for incremental sync."""
        if full_sync:
            return None, None

        entity_status = await self._state_repo.get_entity_sync_status(
            job.client_id, job.integration_id, entity_type
        )
        if not entity_status:
            return None, None

        # Inbound: prefer QBO-clock cursor, fall back to our clock for pre-migration rows
        inbound_since = entity_status.last_inbound_sync_at or entity_status.last_successful_sync_at
        # Outbound: always our clock
        outbound_since = entity_status.last_successful_sync_at
        return inbound_since, outbound_since

    async def _prepare_inbound_state_record(
        self,
        job: SyncJob,
        entity_type: str,
        record: Any,
    ) -> tuple[IntegrationStateRecord, bool]:
        """Look up or create a state record for an inbound external record.

        Returns (state_record, is_new).
        """
        state = await self._state_repo.get_record_by_external_id(
            job.client_id,
            job.integration_id,
            entity_type,
            record.id,
        )

        if state:
            state.external_version_id += 1
            state.sync_status = RecordSyncStatus.PENDING
            state.last_job_id = job.id
            return state, False

        now = datetime.now(UTC)
        state = IntegrationStateRecord(
            id=uuid4(),
            client_id=job.client_id,
            integration_id=job.integration_id,
            entity_type=entity_type,
            internal_record_id=None,
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
        return state, True

    async def _flush_inbound_batch(
        self,
        records_to_upsert: list[IntegrationStateRecord],
        batch_created: int,
        batch_updated: int,
        result: dict[str, Any],
        job: SyncJob,
        entity_type: str,
    ) -> tuple[int, int]:
        """Flush accumulated records to DB and return (created, updated) counts."""
        if not records_to_upsert:
            return 0, 0

        created = batch_created
        updated = batch_updated
        try:
            upserted = await self._state_repo.batch_upsert_records(records_to_upsert)
            await self._write_history_entries(upserted, job.id)
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

        return created, updated

    async def _sync_entity_inbound(
        self,
        job: SyncJob,
        entity_type: str,
        adapter: Any,
        inbound_since: datetime | None,
        result: dict[str, Any],
    ) -> datetime | None:
        """Run paginated inbound sync and return max_external_updated_at."""
        BATCH_SIZE = 1000
        max_external_updated_at: datetime | None = None
        page_token = None
        records_to_upsert: list[IntegrationStateRecord] = []
        batch_created = 0
        batch_updated = 0

        while True:
            records, next_token = await adapter.fetch_records(
                entity_type, since=inbound_since, page_token=page_token
            )
            result["records_fetched"] += len(records)

            for record in records:
                # Track max external updated_at for inbound cursor
                if record.updated_at and (
                    max_external_updated_at is None or record.updated_at > max_external_updated_at
                ):
                    max_external_updated_at = record.updated_at

                try:
                    state, is_new = await self._prepare_inbound_state_record(
                        job,
                        entity_type,
                        record,
                    )
                    records_to_upsert.append(state)
                    if is_new:
                        batch_created += 1
                    else:
                        batch_updated += 1

                    # Flush batch when it reaches size limit
                    if len(records_to_upsert) >= BATCH_SIZE:
                        created, updated = await self._flush_inbound_batch(
                            records_to_upsert,
                            batch_created,
                            batch_updated,
                            result,
                            job,
                            entity_type,
                        )
                        result["records_created"] += created
                        result["records_updated"] += updated
                        records_to_upsert = []
                        batch_created = 0
                        batch_updated = 0

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
        created, updated = await self._flush_inbound_batch(
            records_to_upsert,
            batch_created,
            batch_updated,
            result,
            job,
            entity_type,
        )
        result["records_created"] += created
        result["records_updated"] += updated

        return max_external_updated_at

    async def _batch_mark_synced_with_fallback(
        self,
        successful_syncs: list[tuple[UUID, UUID, str | None]],
        successful_records: list[IntegrationStateRecord],
        job: SyncJob,
        entity_type: str,
        result: dict[str, Any],
    ) -> None:
        """Batch mark synced with individual-update fallback on failure."""
        try:
            await self._state_repo.batch_mark_synced(
                successful_syncs,
                client_id=job.client_id,
                integration_id=job.integration_id,
            )
            # Write history for successful outbound records
            for sr in successful_records:
                sr.sync_status = RecordSyncStatus.SYNCED
            await self._write_history_entries(successful_records, job.id)
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
                    await self._state_repo.mark_synced(record_id, client_id_param, external_id)
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

    async def _sync_entity_outbound(
        self,
        job: SyncJob,
        entity_type: str,
        adapter: Any,
        result: dict[str, Any],
    ) -> None:
        """Push pending internal records to external system."""
        pending_records = await self._state_repo.get_pending_records(
            job.client_id, job.integration_id, entity_type
        )

        # Collect successful syncs for batch update
        successful_syncs: list[tuple[UUID, UUID, str | None]] = []
        successful_records: list[IntegrationStateRecord] = []

        for state in pending_records:
            try:
                # Get record data from metadata (simplified - real impl would fetch from internal system)
                data = state.metadata.get("data", {}) if state.metadata else {}

                if state.external_record_id:
                    # Update existing external record
                    await adapter.update_record(entity_type, state.external_record_id, data)
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
                successful_syncs.append((state.id, job.client_id, state.external_record_id))
                successful_records.append(state)

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
                # Write history for failed record
                state.sync_status = RecordSyncStatus.FAILED
                state.error_message = str(e)
                await self._write_history_entries([state], job.id)
                result["records_failed"] += 1

        # Batch mark all successful syncs in a single transaction with advisory lock
        if successful_syncs:
            await self._batch_mark_synced_with_fallback(
                successful_syncs,
                successful_records,
                job,
                entity_type,
                result,
            )

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

        inbound_since, outbound_since = await self._resolve_sync_cursors(
            job,
            entity_type,
            full_sync,
        )

        max_external_updated_at: datetime | None = None

        if direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
            max_external_updated_at = await self._sync_entity_inbound(
                job,
                entity_type,
                adapter,
                inbound_since,
                result,
            )

        if direction in (SyncDirection.OUTBOUND, SyncDirection.BIDIRECTIONAL):
            await self._sync_entity_outbound(job, entity_type, adapter, result)

        # Update entity sync status
        total_synced = result["records_created"] + result["records_updated"]
        if total_synced > 0:
            await self._state_repo.update_entity_sync_status(
                job.client_id,
                job.integration_id,
                entity_type,
                job.id,
                total_synced,
                last_inbound_sync_at=max_external_updated_at,
            )

        return result

    async def handle_change_event(
        self,
        event: ChangeEvent,
    ) -> tuple[int, int, SyncJob | None]:
        """
        Handle a change notification (push or webhook).

        Always bumps version vectors. Optionally triggers a sync job
        based on the entity's sync_trigger setting.

        Args:
            event: The normalized change event.

        Returns:
            Tuple of (records_bumped, records_created, sync_job_or_none).
        """
        # Verify integration exists and is connected
        integration = await self._integration_repo.get_available_integration(event.integration_id)
        if not integration:
            raise NotFoundError("Integration", event.integration_id)

        user_integration = await self._integration_repo.get_user_integration(
            event.client_id, event.integration_id
        )
        if not user_integration:
            raise NotFoundError("UserIntegration", f"{event.client_id}/{event.integration_id}")

        if user_integration.status != IntegrationStatus.CONNECTED:
            raise SyncError(f"Integration is not connected (status: {user_integration.status})")

        # Validate entity_type is supported
        if event.entity_type not in integration.supported_entities:
            raise SyncError(
                f"Unsupported entity type: {event.entity_type}",
                details={"supported": integration.supported_entities},
            )

        # Look up SyncRule for sync_trigger mode
        sync_trigger = SyncTriggerMode.DEFERRED
        settings = await self._integration_repo.get_user_settings(
            event.client_id, event.integration_id
        )
        if settings:
            for rule in settings.sync_rules:
                if rule.entity_type == event.entity_type and rule.enabled:
                    sync_trigger = rule.sync_trigger
                    break

        # Bump version vectors — always happens
        bump_internal = event.source == ChangeSourceType.PUSH
        bump_external = event.source == ChangeSourceType.WEBHOOK
        records_bumped, records_created = await self._state_repo.bump_version_vectors(
            client_id=event.client_id,
            integration_id=event.integration_id,
            entity_type=event.entity_type,
            record_ids=event.record_ids,
            bump_internal=bump_internal,
            bump_external=bump_external,
        )

        logger.info(
            "Change event processed",
            extra={
                "client_id": str(event.client_id),
                "integration_id": str(event.integration_id),
                "entity_type": event.entity_type,
                "source": event.source.value,
                "event": event.event,
                "records_bumped": records_bumped,
                "records_created": records_created,
                "sync_trigger": sync_trigger.value,
            },
        )

        # Optionally trigger sync
        sync_job: SyncJob | None = None
        if sync_trigger == SyncTriggerMode.IMMEDIATE:
            triggered_by = (
                SyncJobTrigger.PUSH
                if event.source == ChangeSourceType.PUSH
                else SyncJobTrigger.WEBHOOK
            )
            try:
                sync_job = await self.trigger_sync(
                    client_id=event.client_id,
                    integration_id=event.integration_id,
                    job_type=SyncJobType.INCREMENTAL,
                    entity_requests=[
                        EntitySyncRequest(
                            entity_type=event.entity_type,
                            record_ids=event.record_ids,
                        )
                    ],
                    triggered_by=triggered_by,
                )
            except ConflictError:
                # A job is already running — version vectors are already bumped,
                # so the next sync will pick up the changes.
                logger.info(
                    "Sync job already running, skipping immediate trigger",
                    extra={
                        "client_id": str(event.client_id),
                        "integration_id": str(event.integration_id),
                    },
                )

        return records_bumped, records_created, sync_job

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

    async def get_jobs_paginated(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SyncJob], int]:
        """Get paginated sync jobs for a client. Returns (jobs, total_count)."""
        return await self._job_repo.get_jobs_for_client_paginated(
            client_id,
            integration_id=integration_id,
            status=status,
            since=since,
            page=page,
            page_size=page_size,
        )

    async def get_job_records(
        self,
        client_id: UUID,
        job_id: UUID,
        entity_type: str | None = None,
        status: RecordSyncStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationHistoryRecord], int]:
        """
        Get paginated records that were modified by a specific sync job.

        Args:
            client_id: The tenant/client ID.
            job_id: The sync job ID.
            entity_type: Optional filter by entity type.
            status: Optional filter by sync status.
            page: Page number (1-indexed).
            page_size: Number of records per page.

        Returns:
            Tuple of (history_records, total_count).
        """
        return await self._state_repo.get_history_by_job_id(
            client_id=client_id,
            job_id=job_id,
            entity_type=entity_type,
            status=status,
            page=page,
            page_size=page_size,
        )
