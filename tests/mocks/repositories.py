"""In-memory mock repositories for unit testing."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.entities import (
    AuditLogEntry,
    AvailableIntegration,
    EntitySyncStatus,
    IntegrationHistoryRecord,
    IntegrationStateRecord,
    SyncJob,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    RecordSyncStatus,
    SyncJobStatus,
)
from app.domain.interfaces import (
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    SyncJobRepositoryInterface,
)


class MockIntegrationRepository(IntegrationRepositoryInterface):
    """In-memory mock implementation of IntegrationRepositoryInterface."""

    def __init__(self) -> None:
        self._available_integrations: dict[UUID, AvailableIntegration] = {}
        self._user_integrations: dict[tuple[UUID, UUID], UserIntegration] = {}
        self._user_settings: dict[tuple[UUID, UUID], UserIntegrationSettings] = {}
        self._system_settings: dict[UUID, UserIntegrationSettings] = {}

    def seed_available_integration(
        self,
        name: str,
        type: str = "erp",
        supported_entities: list[str] | None = None,
        is_active: bool = True,
        connection_config: Any | None = None,
    ) -> AvailableIntegration:
        """Seed an available integration for testing."""
        integration = AvailableIntegration(
            id=uuid4(),
            name=name,
            type=type,
            description=f"Test {name} integration",
            supported_entities=supported_entities or ["bill", "invoice", "vendor"],
            connection_config=connection_config,
            is_active=is_active,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._available_integrations[integration.id] = integration
        return integration

    async def get_available_integrations(
        self, active_only: bool = True
    ) -> list[AvailableIntegration]:
        integrations = list(self._available_integrations.values())
        if active_only:
            integrations = [i for i in integrations if i.is_active]
        return integrations

    async def get_available_integration(self, integration_id: UUID) -> AvailableIntegration | None:
        return self._available_integrations.get(integration_id)

    async def get_available_integration_by_name(self, name: str) -> AvailableIntegration | None:
        for integration in self._available_integrations.values():
            if integration.name == name:
                return integration
        return None

    async def create_available_integration(
        self, integration: AvailableIntegration
    ) -> AvailableIntegration:
        # Check name uniqueness
        for existing in self._available_integrations.values():
            if existing.name == integration.name:
                raise ValueError(f"Integration with name '{integration.name}' already exists")
        self._available_integrations[integration.id] = integration
        return integration

    async def update_available_integration(
        self, integration: AvailableIntegration
    ) -> AvailableIntegration:
        if integration.id not in self._available_integrations:
            raise ValueError(f"Integration not found: {integration.id}")
        existing = self._available_integrations[integration.id]
        # If name changed, check uniqueness
        if integration.name != existing.name:
            for other in self._available_integrations.values():
                if other.id != integration.id and other.name == integration.name:
                    raise ValueError(f"Integration with name '{integration.name}' already exists")
        integration.updated_at = datetime.now(UTC)
        self._available_integrations[integration.id] = integration
        return integration

    async def get_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegration | None:
        return self._user_integrations.get((client_id, integration_id))

    async def get_user_integrations(self, client_id: UUID) -> list[UserIntegration]:
        return [ui for (cid, _), ui in self._user_integrations.items() if cid == client_id]

    async def get_all_user_integrations(self, limit: int = 1000) -> list[UserIntegration]:
        return list(self._user_integrations.values())[:limit]

    async def create_user_integration(self, integration: UserIntegration) -> UserIntegration:
        key = (integration.client_id, integration.integration_id)
        self._user_integrations[key] = integration
        return integration

    async def update_user_integration(self, integration: UserIntegration) -> UserIntegration:
        key = (integration.client_id, integration.integration_id)
        integration.updated_at = datetime.now(UTC)
        self._user_integrations[key] = integration
        return integration

    async def delete_user_integration(self, client_id: UUID, integration_id: UUID) -> bool:
        key = (client_id, integration_id)
        if key in self._user_integrations:
            del self._user_integrations[key]
            return True
        return False

    async def get_user_settings(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegrationSettings | None:
        return self._user_settings.get((client_id, integration_id))

    async def upsert_user_settings(
        self, client_id: UUID, integration_id: UUID, settings: UserIntegrationSettings
    ) -> UserIntegrationSettings:
        self._user_settings[(client_id, integration_id)] = settings
        return settings

    async def get_system_settings(self, integration_id: UUID) -> UserIntegrationSettings | None:
        return self._system_settings.get(integration_id)

    async def upsert_system_settings(
        self,
        integration_id: UUID,
        settings: UserIntegrationSettings,
    ) -> UserIntegrationSettings:
        self._system_settings[integration_id] = settings
        return settings

    def clear(self) -> None:
        """Clear all data (for test isolation)."""
        self._available_integrations.clear()
        self._user_integrations.clear()
        self._user_settings.clear()
        self._system_settings.clear()


class MockSyncJobRepository(SyncJobRepositoryInterface):
    """In-memory mock implementation of SyncJobRepositoryInterface."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, SyncJob] = {}

    async def create_job(self, job: SyncJob) -> SyncJob:
        self._jobs[job.id] = job
        return job

    async def get_job(self, job_id: UUID) -> SyncJob | None:
        return self._jobs.get(job_id)

    async def get_jobs_for_client(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[SyncJob]:
        jobs = [j for j in self._jobs.values() if j.client_id == client_id]

        if integration_id:
            jobs = [j for j in jobs if j.integration_id == integration_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        if since:
            jobs = [j for j in jobs if j.created_at >= since]

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    async def get_jobs_for_client_paginated(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SyncJob], int]:
        """Get paginated jobs for a client."""
        jobs = [j for j in self._jobs.values() if j.client_id == client_id]

        if integration_id:
            jobs = [j for j in jobs if j.integration_id == integration_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        if since:
            jobs = [j for j in jobs if j.created_at >= since]

        jobs.sort(key=lambda j: j.created_at, reverse=True)
        total = len(jobs)
        offset = (page - 1) * page_size
        paginated = jobs[offset : offset + page_size]
        return paginated, total

    async def update_job_status(
        self,
        job_id: UUID,
        status: SyncJobStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
        entities_processed: dict[str, Any] | None = None,
    ) -> SyncJob:
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        now = datetime.now(UTC)
        job.status = status
        job.updated_at = now

        if status == SyncJobStatus.RUNNING:
            job.started_at = now
        elif status in (
            SyncJobStatus.SUCCEEDED,
            SyncJobStatus.FAILED,
            SyncJobStatus.CANCELLED,
        ):
            job.completed_at = now

        if error_code is not None:
            job.error_code = error_code
        if error_message is not None:
            job.error_message = error_message
        if error_details is not None:
            job.error_details = error_details
        if entities_processed is not None:
            job.entities_processed = entities_processed

        return job

    async def get_running_jobs(self, client_id: UUID, integration_id: UUID) -> list[SyncJob]:
        return [
            j
            for j in self._jobs.values()
            if j.client_id == client_id
            and j.integration_id == integration_id
            and j.status == SyncJobStatus.RUNNING
        ]

    async def create_job_if_no_running(self, job: SyncJob) -> tuple[SyncJob | None, SyncJob | None]:
        """
        Atomically check for running/pending jobs and create a new job if none exist.

        In this mock, we simulate the atomic behavior by checking and creating
        in a single operation (no real concurrency in tests).
        """
        # Check for running or pending jobs
        existing_jobs = [
            j
            for j in self._jobs.values()
            if j.client_id == job.client_id
            and j.integration_id == job.integration_id
            and j.status in (SyncJobStatus.RUNNING, SyncJobStatus.PENDING)
        ]

        if existing_jobs:
            return None, existing_jobs[0]

        # No existing job, create the new one
        self._jobs[job.id] = job
        return job, None

    async def get_pending_jobs(
        self,
        stale_seconds: int = 30,
    ) -> list[SyncJob]:
        """Find jobs stuck in PENDING status longer than stale_seconds."""
        from datetime import timedelta

        cutoff_time = datetime.now(UTC) - timedelta(seconds=stale_seconds)

        return [
            j
            for j in self._jobs.values()
            if j.status == SyncJobStatus.PENDING and j.created_at < cutoff_time
        ]

    async def get_stuck_jobs(
        self,
        stuck_threshold_minutes: int = 60,
    ) -> list[SyncJob]:
        """Find jobs that have been running longer than the threshold."""
        from datetime import timedelta

        cutoff_time = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)

        stuck_jobs = [
            j
            for j in self._jobs.values()
            if j.status == SyncJobStatus.RUNNING
            and j.started_at is not None
            and j.started_at < cutoff_time
        ]
        return stuck_jobs

    async def terminate_stuck_job(
        self,
        job_id: UUID,
        reason: str = "Job exceeded maximum runtime",
    ) -> SyncJob | None:
        """Terminate a stuck job by marking it as failed."""
        job = self._jobs.get(job_id)
        if not job or job.status != SyncJobStatus.RUNNING:
            return None

        now = datetime.now(UTC)
        job.status = SyncJobStatus.FAILED
        job.completed_at = now
        job.error_code = "JOB_TIMEOUT"
        job.error_message = reason
        job.error_details = {
            "terminated_at": now.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "reason": "automatic_termination",
        }
        job.updated_at = now

        return job

    def clear(self) -> None:
        """Clear all data (for test isolation)."""
        self._jobs.clear()


class MockIntegrationStateRepository(IntegrationStateRepositoryInterface):
    """In-memory mock implementation of IntegrationStateRepositoryInterface."""

    def __init__(self) -> None:
        # Keyed by (client_id, record.id) matching the DB composite PK
        self._records: dict[tuple[UUID, UUID], IntegrationStateRecord] = {}
        self._entity_sync_status: dict[tuple[UUID, UUID, str], EntitySyncStatus] = {}
        self._history: dict[tuple[UUID, UUID], IntegrationHistoryRecord] = {}
        self._audit_log: list[AuditLogEntry] = []

    async def get_record(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_id: str | None = None,
    ) -> IntegrationStateRecord | None:
        if internal_record_id is None:
            return None
        for record in self._records.values():
            if (
                record.client_id == client_id
                and record.integration_id == integration_id
                and record.entity_type == entity_type
                and record.internal_record_id == internal_record_id
            ):
                return record
        return None

    async def get_record_by_external_id(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        external_record_id: str,
    ) -> IntegrationStateRecord | None:
        for record in self._records.values():
            if (
                record.client_id == client_id
                and record.integration_id == integration_id
                and record.entity_type == entity_type
                and record.external_record_id == external_record_id
            ):
                return record
        return None

    async def get_records_by_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        status: RecordSyncStatus,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        records = [
            r
            for r in self._records.values()
            if r.client_id == client_id
            and r.integration_id == integration_id
            and r.entity_type == entity_type
            and r.sync_status == status
            and not r.do_not_sync
        ]
        return records[:limit]

    async def get_pending_records(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        return await self.get_records_by_status(
            client_id, integration_id, entity_type, RecordSyncStatus.PENDING, limit
        )

    async def upsert_record(self, record: IntegrationStateRecord) -> IntegrationStateRecord:
        # Dual-path lookup: try internal ID first, then external ID
        existing = None
        if record.internal_record_id is not None:
            existing = await self.get_record(
                record.client_id,
                record.integration_id,
                record.entity_type,
                record.internal_record_id,
            )
        if existing is None and record.external_record_id is not None:
            existing = await self.get_record_by_external_id(
                record.client_id,
                record.integration_id,
                record.entity_type,
                record.external_record_id,
            )

        if existing is not None:
            # Update existing record in place
            if record.internal_record_id is not None:
                existing.internal_record_id = record.internal_record_id
            existing.external_record_id = record.external_record_id
            existing.sync_status = record.sync_status
            existing.sync_direction = record.sync_direction
            existing.internal_version_id = record.internal_version_id
            existing.external_version_id = record.external_version_id
            existing.last_sync_version_id = record.last_sync_version_id
            existing.last_synced_at = record.last_synced_at
            existing.last_job_id = record.last_job_id
            existing.error_code = record.error_code
            existing.error_message = record.error_message
            existing.error_details = record.error_details
            existing.metadata = record.metadata
            existing.updated_at = datetime.now(UTC)
            return existing

        record.updated_at = datetime.now(UTC)
        self._records[(record.client_id, record.id)] = record
        return record

    async def update_sync_status(
        self,
        record_id: UUID,
        client_id: UUID,
        status: RecordSyncStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        record = self._records.get((client_id, record_id))
        if record:
            record.sync_status = status
            record.updated_at = datetime.now(UTC)
            if error_code is not None:
                record.error_code = error_code
            if error_message is not None:
                record.error_message = error_message
            if error_details is not None:
                record.error_details = error_details

    async def mark_synced(
        self,
        record_id: UUID,
        client_id: UUID,
        external_record_id: str | None = None,
        job_id: UUID | None = None,
    ) -> None:
        record = self._records.get((client_id, record_id))
        if record:
            record.sync_status = RecordSyncStatus.SYNCED
            record.last_synced_at = datetime.now(UTC)
            record.last_sync_version_id = max(
                record.internal_version_id, record.external_version_id
            )
            record.error_code = None
            record.error_message = None
            record.error_details = None
            if external_record_id:
                record.external_record_id = external_record_id
            if job_id:
                record.last_job_id = job_id

    async def list_entity_sync_statuses(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> list[EntitySyncStatus]:
        return [
            status
            for (cid, iid, _), status in self._entity_sync_status.items()
            if cid == client_id and iid == integration_id
        ]

    async def get_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
    ) -> EntitySyncStatus | None:
        return self._entity_sync_status.get((client_id, integration_id, entity_type))

    async def update_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        job_id: UUID,
        records_count: int,
        last_inbound_sync_at: datetime | None = None,
    ) -> EntitySyncStatus:
        key = (client_id, integration_id, entity_type)
        now = datetime.now(UTC)

        existing = self._entity_sync_status.get(key)
        if existing:
            existing.last_successful_sync_at = now
            existing.last_sync_job_id = job_id
            existing.records_synced_count += records_count
            if last_inbound_sync_at is not None:
                existing.last_inbound_sync_at = last_inbound_sync_at
            existing.updated_at = now
            return existing
        else:
            status = EntitySyncStatus(
                id=uuid4(),
                client_id=client_id,
                integration_id=integration_id,
                entity_type=entity_type,
                last_successful_sync_at=now,
                last_sync_job_id=job_id,
                records_synced_count=records_count,
                last_inbound_sync_at=last_inbound_sync_at,
                created_at=now,
                updated_at=now,
            )
            self._entity_sync_status[key] = status
            return status

    async def reset_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        reset_inbound_sync_time: bool = True,
        reset_last_sync_time: bool = True,
    ) -> EntitySyncStatus | None:
        key = (client_id, integration_id, entity_type)
        existing = self._entity_sync_status.get(key)
        if not existing:
            return None
        if reset_inbound_sync_time:
            existing.last_inbound_sync_at = None
        if reset_last_sync_time:
            existing.last_successful_sync_at = None
        existing.records_synced_count = 0
        existing.updated_at = datetime.now(UTC)
        return existing

    async def resolve_record_ids(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_ids: list[str] | None = None,
        external_record_ids: list[str] | None = None,
    ) -> list[UUID]:
        """Resolve internal or external record IDs to state record UUIDs."""
        result = []
        for (_cid, _rid), record in self._records.items():
            if record.client_id != client_id or record.integration_id != integration_id:
                continue
            if record.entity_type != entity_type:
                continue
            if internal_record_ids and record.internal_record_id in internal_record_ids:
                result.append(record.id)
            elif external_record_ids and record.external_record_id in external_record_ids:
                result.append(record.id)
        return result

    async def force_sync_records(
        self,
        client_id: UUID,
        integration_id: UUID,
        state_ids: list[UUID],
    ) -> tuple[int, list[dict]]:
        """Bulk force-sync: clear errors, equalize vectors, mark SYNCED."""
        updated = 0
        skipped: list[dict] = []
        for sid in state_ids:
            key = (client_id, sid)
            record = self._records.get(key)
            if not record or record.integration_id != integration_id:
                skipped.append({"state_id": str(sid), "reason": "Record not found"})
                continue
            if record.sync_status not in (RecordSyncStatus.FAILED, RecordSyncStatus.CONFLICT):
                skipped.append({
                    "state_id": str(sid),
                    "reason": f"Record status is '{record.sync_status.value}', not failed or conflict",
                })
                continue
            max_v = max(record.internal_version_id, record.external_version_id)
            record.internal_version_id = max_v
            record.external_version_id = max_v
            record.last_sync_version_id = max_v
            record.sync_status = RecordSyncStatus.SYNCED
            record.error_code = None
            record.error_message = None
            record.error_details = None
            record.force_synced_at = datetime.now(UTC)
            record.last_synced_at = datetime.now(UTC)
            updated += 1
        return updated, skipped

    async def set_do_not_sync(
        self,
        client_id: UUID,
        integration_id: UUID,
        state_ids: list[UUID],
        do_not_sync: bool,
    ) -> tuple[int, list[dict]]:
        """Bulk set do_not_sync flag."""
        updated = 0
        skipped: list[dict] = []
        for sid in state_ids:
            key = (client_id, sid)
            record = self._records.get(key)
            if not record or record.integration_id != integration_id:
                skipped.append({"state_id": str(sid), "reason": "Record not found"})
                continue
            record.do_not_sync = do_not_sync
            if do_not_sync:
                record.error_code = None
                record.error_message = None
                record.error_details = None
            else:
                if not record.is_in_sync:
                    record.sync_status = RecordSyncStatus.PENDING
            updated += 1
        return updated, skipped

    async def get_records_paginated(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str | None = None,
        sync_status: RecordSyncStatus | None = None,
        do_not_sync: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationStateRecord], int]:
        """Get paginated records for the records browser."""
        filtered = []
        for record in self._records.values():
            if record.client_id != client_id or record.integration_id != integration_id:
                continue
            if entity_type and record.entity_type != entity_type:
                continue
            if sync_status and record.sync_status != sync_status:
                continue
            if do_not_sync is not None and record.do_not_sync != do_not_sync:
                continue
            filtered.append(record)
        total = len(filtered)
        start = (page - 1) * page_size
        return filtered[start : start + page_size], total

    async def write_audit_entry(self, entry: AuditLogEntry) -> None:
        """Write a single audit log entry."""
        self._audit_log.append(entry)

    async def bump_version_vectors(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        record_ids: list[str],
        bump_internal: bool = False,
        bump_external: bool = False,
    ) -> tuple[int, int]:
        """Bump version vectors, creating records if not found."""
        records_bumped = 0
        records_created = 0

        for record_id in record_ids:
            existing = None

            # Look up by internal_record_id for push
            if bump_internal:
                existing = await self.get_record(client_id, integration_id, entity_type, record_id)

            # Look up by external_record_id for webhook
            if bump_external and existing is None:
                existing = await self.get_record_by_external_id(
                    client_id, integration_id, entity_type, record_id
                )

            if existing:
                if bump_internal:
                    existing.internal_version_id += 1
                if bump_external:
                    existing.external_version_id += 1
                existing.sync_status = RecordSyncStatus.PENDING
                existing.updated_at = datetime.now(UTC)
                records_bumped += 1
            else:
                now = datetime.now(UTC)
                new_record = IntegrationStateRecord(
                    id=uuid4(),
                    client_id=client_id,
                    integration_id=integration_id,
                    entity_type=entity_type,
                    internal_record_id=record_id if bump_internal else None,
                    external_record_id=record_id if bump_external else None,
                    sync_status=RecordSyncStatus.PENDING,
                    internal_version_id=2 if bump_internal else 1,
                    external_version_id=2 if bump_external else 0,
                    last_sync_version_id=0,
                    created_at=now,
                    updated_at=now,
                )
                self._records[(client_id, new_record.id)] = new_record
                records_created += 1

        return records_bumped, records_created

    async def batch_upsert_records(
        self,
        records: list[IntegrationStateRecord],
    ) -> list[IntegrationStateRecord]:
        """Upsert multiple records (mock - delegates to upsert_record)."""
        results: list[IntegrationStateRecord] = []
        for record in records:
            result = await self.upsert_record(record)
            results.append(result)
        return results

    async def batch_mark_synced(
        self,
        updates: list[tuple[UUID, UUID, str | None]],  # (record_id, client_id, external_record_id)
        client_id: UUID | None = None,
        integration_id: UUID | None = None,
    ) -> None:
        """Mark multiple records as synced (mock - atomic operation)."""
        for record_id, record_client_id, external_record_id in updates:
            record = self._records.get((record_client_id, record_id))
            if record:
                record.sync_status = RecordSyncStatus.SYNCED
                record.last_synced_at = datetime.now(UTC)
                record.last_sync_version_id = max(
                    record.internal_version_id, record.external_version_id
                )
                record.error_code = None
                record.error_message = None
                record.error_details = None
                if external_record_id:
                    record.external_record_id = external_record_id

    async def get_records_by_job_id(
        self,
        client_id: UUID,
        job_id: UUID,
        entity_type: str | None = None,
        status: RecordSyncStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationStateRecord], int]:
        """Get paginated records that were modified by a specific sync job."""
        records = [
            r
            for r in self._records.values()
            if r.client_id == client_id and r.last_job_id == job_id
        ]

        if entity_type:
            records = [r for r in records if r.entity_type == entity_type]
        if status:
            records = [r for r in records if r.sync_status == status]

        records.sort(key=lambda r: r.updated_at, reverse=True)

        total = len(records)
        offset = (page - 1) * page_size
        paginated = records[offset : offset + page_size]

        return paginated, total

    async def create_history_entry(
        self, entry: IntegrationHistoryRecord
    ) -> IntegrationHistoryRecord:
        self._history[(entry.client_id, entry.id)] = entry
        return entry

    async def batch_create_history(self, entries: list[IntegrationHistoryRecord]) -> None:
        for entry in entries:
            self._history[(entry.client_id, entry.id)] = entry

    async def get_history_by_job_id(
        self,
        client_id: UUID,
        job_id: UUID,
        entity_type: str | None = None,
        status: RecordSyncStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntegrationHistoryRecord], int]:
        records = [
            r for r in self._history.values() if r.client_id == client_id and r.job_id == job_id
        ]

        if entity_type:
            records = [r for r in records if r.entity_type == entity_type]
        if status:
            records = [r for r in records if r.sync_status == status]

        records.sort(key=lambda r: r.created_at, reverse=True)

        total = len(records)
        offset = (page - 1) * page_size
        paginated = records[offset : offset + page_size]

        return paginated, total

    async def cleanup_old_history(
        self,
        retention_days: int,
        batch_size: int = 10000,
    ) -> int:
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        to_delete = [key for key, entry in self._history.items() if entry.created_at < cutoff]
        for key in to_delete:
            del self._history[key]
        return len(to_delete)

    def clear(self) -> None:
        """Clear all data (for test isolation)."""
        self._records.clear()
        self._entity_sync_status.clear()
        self._history.clear()
