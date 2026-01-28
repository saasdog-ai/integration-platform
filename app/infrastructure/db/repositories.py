"""Repository implementations for database access."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import (
    AvailableIntegration,
    EntitySyncStatus,
    IntegrationStateRecord,
    OAuthConfig,
    SyncJob,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
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
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    SyncJobRepositoryInterface,
)
from app.infrastructure.db.database import advisory_lock, get_session_context
from app.infrastructure.db.models import (
    AvailableIntegrationModel,
    EntitySyncStatusModel,
    IntegrationStateModel,
    SyncJobModel,
    SystemIntegrationSettingsModel,
    UserIntegrationModel,
    UserIntegrationSettingsModel,
)


def _model_to_available_integration(
    model: AvailableIntegrationModel,
) -> AvailableIntegration:
    """Convert model to domain entity."""
    oauth_config = None
    if model.oauth_config:
        oauth_config = OAuthConfig(**model.oauth_config)

    return AvailableIntegration(
        id=model.id,
        name=model.name,
        type=model.type,
        description=model.description,
        supported_entities=model.supported_entities or [],
        oauth_config=oauth_config,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by=model.created_by,
        updated_by=model.updated_by,
    )


def _model_to_user_integration(model: UserIntegrationModel) -> UserIntegration:
    """Convert model to domain entity."""
    integration = None
    if model.integration:
        integration = _model_to_available_integration(model.integration)

    settings = None
    if model.settings:
        settings = _settings_dict_to_entity(model.settings.settings)

    return UserIntegration(
        id=model.id,
        client_id=model.client_id,
        integration_id=model.integration_id,
        status=IntegrationStatus(model.status),
        credentials_encrypted=model.credentials_encrypted,
        credentials_key_id=model.credentials_key_id,
        external_account_id=model.external_account_id,
        last_connected_at=model.last_connected_at,
        disconnected_at=model.disconnected_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by=model.created_by,
        updated_by=model.updated_by,
        integration=integration,
        settings=settings,
    )


def _settings_dict_to_entity(
    settings_dict: dict[str, Any],
) -> UserIntegrationSettings:
    """Convert settings dict to domain entity."""
    sync_rules = []
    for rule in settings_dict.get("sync_rules", []):
        sync_rules.append(
            SyncRule(
                entity_type=rule["entity_type"],
                direction=SyncDirection(rule["direction"]),
                enabled=rule.get("enabled", True),
                field_mappings=rule.get("field_mappings"),
            )
        )

    return UserIntegrationSettings(
        sync_rules=sync_rules,
        sync_frequency=settings_dict.get("sync_frequency"),
        auto_sync_enabled=settings_dict.get("auto_sync_enabled", False),
    )


def _settings_entity_to_dict(settings: UserIntegrationSettings) -> dict[str, Any]:
    """Convert settings entity to dict for storage."""
    return {
        "sync_rules": [
            {
                "entity_type": rule.entity_type,
                "direction": rule.direction.value,
                "enabled": rule.enabled,
                "field_mappings": rule.field_mappings,
            }
            for rule in settings.sync_rules
        ],
        "sync_frequency": settings.sync_frequency,
        "auto_sync_enabled": settings.auto_sync_enabled,
    }


def _model_to_sync_job(model: SyncJobModel) -> SyncJob:
    """Convert model to domain entity."""
    integration = None
    if model.integration:
        integration = _model_to_available_integration(model.integration)

    return SyncJob(
        id=model.id,
        client_id=model.client_id,
        integration_id=model.integration_id,
        job_type=SyncJobType(model.job_type),
        status=SyncJobStatus(model.status),
        started_at=model.started_at,
        completed_at=model.completed_at,
        entities_processed=model.entities_processed,
        error_code=model.error_code,
        error_message=model.error_message,
        error_details=model.error_details,
        triggered_by=SyncJobTrigger(model.triggered_by),
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by=model.created_by,
        updated_by=model.updated_by,
        integration=integration,
    )


def _model_to_integration_state(
    model: IntegrationStateModel,
) -> IntegrationStateRecord:
    """Convert model to domain entity."""
    return IntegrationStateRecord(
        id=model.id,
        client_id=model.client_id,
        integration_id=model.integration_id,
        entity_type=model.entity_type,
        internal_record_id=model.internal_record_id,
        external_record_id=model.external_record_id,
        sync_status=RecordSyncStatus(model.sync_status),
        sync_direction=SyncDirection(model.sync_direction) if model.sync_direction else None,
        internal_version_id=model.internal_version_id,
        external_version_id=model.external_version_id,
        last_sync_version_id=model.last_sync_version_id,
        last_synced_at=model.last_synced_at,
        error_code=model.error_code,
        error_message=model.error_message,
        error_details=model.error_details,
        metadata=model.metadata_,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _model_to_entity_sync_status(model: EntitySyncStatusModel) -> EntitySyncStatus:
    """Convert model to domain entity."""
    return EntitySyncStatus(
        id=model.id,
        client_id=model.client_id,
        integration_id=model.integration_id,
        entity_type=model.entity_type,
        last_successful_sync_at=model.last_successful_sync_at,
        last_sync_job_id=model.last_sync_job_id,
        records_synced_count=model.records_synced_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
        created_by=model.created_by,
        updated_by=model.updated_by,
    )


class IntegrationRepository(IntegrationRepositoryInterface):
    """PostgreSQL implementation of IntegrationRepositoryInterface."""

    async def get_available_integrations(
        self, active_only: bool = True
    ) -> list[AvailableIntegration]:
        async with get_session_context() as session:
            query = select(AvailableIntegrationModel)
            if active_only:
                query = query.where(AvailableIntegrationModel.is_active.is_(True))
            result = await session.execute(query)
            models = result.scalars().all()
            return [_model_to_available_integration(m) for m in models]

    async def get_available_integration(
        self, integration_id: UUID
    ) -> AvailableIntegration | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(AvailableIntegrationModel).where(
                    AvailableIntegrationModel.id == integration_id
                )
            )
            model = result.scalar_one_or_none()
            return _model_to_available_integration(model) if model else None

    async def get_available_integration_by_name(
        self, name: str
    ) -> AvailableIntegration | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(AvailableIntegrationModel).where(
                    AvailableIntegrationModel.name == name
                )
            )
            model = result.scalar_one_or_none()
            return _model_to_available_integration(model) if model else None

    async def get_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegration | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(UserIntegrationModel)
                .options(
                    selectinload(UserIntegrationModel.integration),
                    selectinload(UserIntegrationModel.settings),
                )
                .where(
                    and_(
                        UserIntegrationModel.client_id == client_id,
                        UserIntegrationModel.integration_id == integration_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            return _model_to_user_integration(model) if model else None

    async def get_user_integrations(self, client_id: UUID) -> list[UserIntegration]:
        async with get_session_context() as session:
            result = await session.execute(
                select(UserIntegrationModel)
                .options(
                    selectinload(UserIntegrationModel.integration),
                    selectinload(UserIntegrationModel.settings),
                )
                .where(UserIntegrationModel.client_id == client_id)
            )
            models = result.scalars().all()
            return [_model_to_user_integration(m) for m in models]

    async def create_user_integration(
        self, integration: UserIntegration
    ) -> UserIntegration:
        async with get_session_context() as session:
            model = UserIntegrationModel(
                id=integration.id,
                client_id=integration.client_id,
                integration_id=integration.integration_id,
                status=integration.status.value,
                credentials_encrypted=integration.credentials_encrypted,
                credentials_key_id=integration.credentials_key_id,
                external_account_id=integration.external_account_id,
                last_connected_at=integration.last_connected_at,
                created_by=integration.created_by,
                updated_by=integration.updated_by,
            )
            session.add(model)
            await session.flush()
            await session.refresh(model)
            return _model_to_user_integration(model)

    async def update_user_integration(
        self, integration: UserIntegration
    ) -> UserIntegration:
        async with get_session_context() as session:
            await session.execute(
                update(UserIntegrationModel)
                .where(UserIntegrationModel.id == integration.id)
                .values(
                    status=integration.status.value,
                    credentials_encrypted=integration.credentials_encrypted,
                    credentials_key_id=integration.credentials_key_id,
                    external_account_id=integration.external_account_id,
                    last_connected_at=integration.last_connected_at,
                    disconnected_at=integration.disconnected_at,
                    updated_by=integration.updated_by,
                )
            )
            # Commit before reading back so new session can see changes
            await session.commit()
        # Read from a new session after commit
        return await self.get_user_integration(
            integration.client_id, integration.integration_id
        )

    async def delete_user_integration(
        self, client_id: UUID, integration_id: UUID
    ) -> bool:
        async with get_session_context() as session:
            result = await session.execute(
                select(UserIntegrationModel).where(
                    and_(
                        UserIntegrationModel.client_id == client_id,
                        UserIntegrationModel.integration_id == integration_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            if model:
                await session.delete(model)
                await session.flush()  # Ensure delete is queued before commit
                return True
            return False

    async def get_user_settings(
        self, client_id: UUID, integration_id: UUID
    ) -> UserIntegrationSettings | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(UserIntegrationSettingsModel).where(
                    and_(
                        UserIntegrationSettingsModel.client_id == client_id,
                        UserIntegrationSettingsModel.integration_id == integration_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            return _settings_dict_to_entity(model.settings) if model else None

    async def upsert_user_settings(
        self,
        client_id: UUID,
        integration_id: UUID,
        settings: UserIntegrationSettings,
    ) -> UserIntegrationSettings:
        async with get_session_context() as session:
            result = await session.execute(
                select(UserIntegrationSettingsModel).where(
                    and_(
                        UserIntegrationSettingsModel.client_id == client_id,
                        UserIntegrationSettingsModel.integration_id == integration_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            settings_dict = _settings_entity_to_dict(settings)

            if model:
                model.settings = settings_dict
            else:
                model = UserIntegrationSettingsModel(
                    client_id=client_id,
                    integration_id=integration_id,
                    settings=settings_dict,
                )
                session.add(model)

            await session.flush()
            return settings

    async def get_system_settings(
        self, integration_id: UUID
    ) -> UserIntegrationSettings | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(SystemIntegrationSettingsModel).where(
                    SystemIntegrationSettingsModel.integration_id == integration_id
                )
            )
            model = result.scalar_one_or_none()
            return _settings_dict_to_entity(model.settings) if model else None


class SyncJobRepository(SyncJobRepositoryInterface):
    """PostgreSQL implementation of SyncJobRepositoryInterface."""

    async def create_job(self, job: SyncJob) -> SyncJob:
        async with get_session_context() as session:
            model = SyncJobModel(
                id=job.id,
                client_id=job.client_id,
                integration_id=job.integration_id,
                job_type=job.job_type.value,
                status=job.status.value,
                started_at=job.started_at,
                completed_at=job.completed_at,
                entities_processed=job.entities_processed,
                error_code=job.error_code,
                error_message=job.error_message,
                error_details=job.error_details,
                triggered_by=job.triggered_by.value,
                created_by=job.created_by,
                updated_by=job.updated_by,
            )
            session.add(model)
            await session.flush()
            # Re-fetch with relationship loaded
            result = await session.execute(
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(SyncJobModel.id == model.id)
            )
            model = result.scalar_one()
            return _model_to_sync_job(model)

    async def get_job(self, job_id: UUID) -> SyncJob | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(SyncJobModel.id == job_id)
            )
            model = result.scalar_one_or_none()
            return _model_to_sync_job(model) if model else None

    async def get_jobs_for_client(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[SyncJob]:
        async with get_session_context() as session:
            query = (
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(SyncJobModel.client_id == client_id)
            )

            if integration_id:
                query = query.where(SyncJobModel.integration_id == integration_id)
            if status:
                query = query.where(SyncJobModel.status == status.value)
            if since:
                query = query.where(SyncJobModel.created_at >= since)

            query = query.order_by(SyncJobModel.created_at.desc()).limit(limit)
            result = await session.execute(query)
            models = result.scalars().all()
            return [_model_to_sync_job(m) for m in models]

    async def get_jobs_for_client_paginated(
        self,
        client_id: UUID,
        integration_id: UUID | None = None,
        status: SyncJobStatus | None = None,
        since: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SyncJob], int]:
        """Get paginated jobs for a client. Returns (jobs, total_count)."""
        from sqlalchemy import func

        async with get_session_context() as session:
            # Build base query conditions
            conditions = [SyncJobModel.client_id == client_id]
            if integration_id:
                conditions.append(SyncJobModel.integration_id == integration_id)
            if status:
                conditions.append(SyncJobModel.status == status.value)
            if since:
                conditions.append(SyncJobModel.created_at >= since)

            # Count total
            count_query = select(func.count()).select_from(SyncJobModel).where(*conditions)
            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0

            # Get paginated results
            offset = (page - 1) * page_size
            query = (
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(*conditions)
                .order_by(SyncJobModel.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(query)
            models = result.scalars().all()

            return [_model_to_sync_job(m) for m in models], total

    async def update_job_status(
        self,
        job_id: UUID,
        status: SyncJobStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
        entities_processed: dict[str, Any] | None = None,
    ) -> SyncJob:
        async with get_session_context() as session:
            now = datetime.now(timezone.utc)
            values: dict[str, Any] = {"status": status.value}

            if status == SyncJobStatus.RUNNING:
                values["started_at"] = now
            elif status in (
                SyncJobStatus.SUCCEEDED,
                SyncJobStatus.FAILED,
                SyncJobStatus.CANCELLED,
            ):
                values["completed_at"] = now

            if error_code is not None:
                values["error_code"] = error_code
            if error_message is not None:
                values["error_message"] = error_message
            if error_details is not None:
                values["error_details"] = error_details
            if entities_processed is not None:
                values["entities_processed"] = entities_processed

            await session.execute(
                update(SyncJobModel).where(SyncJobModel.id == job_id).values(**values)
            )

            return await self.get_job(job_id)

    async def get_running_jobs(
        self, client_id: UUID, integration_id: UUID
    ) -> list[SyncJob]:
        async with get_session_context() as session:
            result = await session.execute(
                select(SyncJobModel).where(
                    and_(
                        SyncJobModel.client_id == client_id,
                        SyncJobModel.integration_id == integration_id,
                        SyncJobModel.status == SyncJobStatus.RUNNING.value,
                    )
                )
            )
            models = result.scalars().all()
            return [_model_to_sync_job(m) for m in models]

    async def create_job_if_no_running(
        self, job: SyncJob
    ) -> tuple[SyncJob | None, SyncJob | None]:
        """
        Atomically check for running jobs and create a new job if none exist.

        Uses database-level advisory lock to prevent race conditions.
        """
        async with get_session_context() as session:
            # Acquire advisory lock for this client/integration combination
            async with advisory_lock(session, job.client_id, job.integration_id):
                # Check for running or pending jobs
                result = await session.execute(
                    select(SyncJobModel)
                    .options(selectinload(SyncJobModel.integration))
                    .where(
                        and_(
                            SyncJobModel.client_id == job.client_id,
                            SyncJobModel.integration_id == job.integration_id,
                            SyncJobModel.status.in_([
                                SyncJobStatus.RUNNING.value,
                                SyncJobStatus.PENDING.value,
                            ]),
                        )
                    )
                )
                existing_job = result.scalar_one_or_none()

                if existing_job:
                    # Return the existing running/pending job
                    return None, _model_to_sync_job(existing_job)

                # No running job, create the new one
                model = SyncJobModel(
                    id=job.id,
                    client_id=job.client_id,
                    integration_id=job.integration_id,
                    job_type=job.job_type.value,
                    status=job.status.value,
                    job_params=job.job_params,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                    entities_processed=job.entities_processed,
                    error_code=job.error_code,
                    error_message=job.error_message,
                    error_details=job.error_details,
                    triggered_by=job.triggered_by.value,
                    created_by=job.created_by,
                    updated_by=job.updated_by,
                )
                session.add(model)
                await session.flush()
                # Re-fetch with relationship loaded
                result = await session.execute(
                    select(SyncJobModel)
                    .options(selectinload(SyncJobModel.integration))
                    .where(SyncJobModel.id == model.id)
                )
                model = result.scalar_one()
                return _model_to_sync_job(model), None

    async def get_stuck_jobs(
        self,
        stuck_threshold_minutes: int = 60,
    ) -> list[SyncJob]:
        """Find jobs that have been running longer than the threshold."""
        from datetime import timedelta

        async with get_session_context() as session:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=stuck_threshold_minutes)

            result = await session.execute(
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(
                    and_(
                        SyncJobModel.status == SyncJobStatus.RUNNING.value,
                        SyncJobModel.started_at < cutoff_time,
                    )
                )
            )
            models = result.scalars().all()
            return [_model_to_sync_job(m) for m in models]

    async def terminate_stuck_job(
        self,
        job_id: UUID,
        reason: str = "Job exceeded maximum runtime",
    ) -> SyncJob | None:
        """Terminate a stuck job by marking it as failed."""
        async with get_session_context() as session:
            result = await session.execute(
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(
                    and_(
                        SyncJobModel.id == job_id,
                        SyncJobModel.status == SyncJobStatus.RUNNING.value,
                    )
                )
            )
            model = result.scalar_one_or_none()

            if not model:
                return None

            now = datetime.now(timezone.utc)
            model.status = SyncJobStatus.FAILED.value
            model.completed_at = now
            model.error_code = "JOB_TIMEOUT"
            model.error_message = reason
            model.error_details = {
                "terminated_at": now.isoformat(),
                "started_at": model.started_at.isoformat() if model.started_at else None,
                "reason": "automatic_termination",
            }

            await session.flush()
            # Re-fetch with relationship loaded
            result = await session.execute(
                select(SyncJobModel)
                .options(selectinload(SyncJobModel.integration))
                .where(SyncJobModel.id == model.id)
            )
            model = result.scalar_one()
            return _model_to_sync_job(model)


class IntegrationStateRepository(IntegrationStateRepositoryInterface):
    """PostgreSQL implementation of IntegrationStateRepositoryInterface."""

    async def get_record(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_id: str,
    ) -> IntegrationStateRecord | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(IntegrationStateModel).where(
                    and_(
                        IntegrationStateModel.client_id == client_id,
                        IntegrationStateModel.integration_id == integration_id,
                        IntegrationStateModel.entity_type == entity_type,
                        IntegrationStateModel.internal_record_id == internal_record_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            return _model_to_integration_state(model) if model else None

    async def get_records_by_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        status: RecordSyncStatus,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        async with get_session_context() as session:
            result = await session.execute(
                select(IntegrationStateModel)
                .where(
                    and_(
                        IntegrationStateModel.client_id == client_id,
                        IntegrationStateModel.integration_id == integration_id,
                        IntegrationStateModel.entity_type == entity_type,
                        IntegrationStateModel.sync_status == status.value,
                    )
                )
                .limit(limit)
            )
            models = result.scalars().all()
            return [_model_to_integration_state(m) for m in models]

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

    async def upsert_record(
        self, record: IntegrationStateRecord
    ) -> IntegrationStateRecord:
        async with get_session_context() as session:
            result = await session.execute(
                select(IntegrationStateModel).where(
                    and_(
                        IntegrationStateModel.client_id == record.client_id,
                        IntegrationStateModel.integration_id == record.integration_id,
                        IntegrationStateModel.entity_type == record.entity_type,
                        IntegrationStateModel.internal_record_id == record.internal_record_id,
                    )
                )
            )
            model = result.scalar_one_or_none()

            if model:
                model.external_record_id = record.external_record_id
                model.sync_status = record.sync_status.value
                model.sync_direction = record.sync_direction.value if record.sync_direction else None
                model.internal_version_id = record.internal_version_id
                model.external_version_id = record.external_version_id
                model.last_sync_version_id = record.last_sync_version_id
                model.last_synced_at = record.last_synced_at
                model.error_code = record.error_code
                model.error_message = record.error_message
                model.error_details = record.error_details
                model.metadata_ = record.metadata
            else:
                model = IntegrationStateModel(
                    id=record.id,
                    client_id=record.client_id,
                    integration_id=record.integration_id,
                    entity_type=record.entity_type,
                    internal_record_id=record.internal_record_id,
                    external_record_id=record.external_record_id,
                    sync_status=record.sync_status.value,
                    sync_direction=record.sync_direction.value if record.sync_direction else None,
                    internal_version_id=record.internal_version_id,
                    external_version_id=record.external_version_id,
                    last_sync_version_id=record.last_sync_version_id,
                    last_synced_at=record.last_synced_at,
                    error_code=record.error_code,
                    error_message=record.error_message,
                    error_details=record.error_details,
                    metadata_=record.metadata,
                )
                session.add(model)

            await session.flush()
            await session.refresh(model)
            return _model_to_integration_state(model)

    async def update_sync_status(
        self,
        record_id: UUID,
        client_id: UUID,
        status: RecordSyncStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        async with get_session_context() as session:
            values: dict[str, Any] = {"sync_status": status.value}
            if error_code is not None:
                values["error_code"] = error_code
            if error_message is not None:
                values["error_message"] = error_message
            if error_details is not None:
                values["error_details"] = error_details

            await session.execute(
                update(IntegrationStateModel)
                .where(
                    and_(
                        IntegrationStateModel.id == record_id,
                        IntegrationStateModel.client_id == client_id,
                    )
                )
                .values(**values)
            )

    async def mark_synced(
        self,
        record_id: UUID,
        client_id: UUID,
        external_record_id: str | None = None,
    ) -> None:
        async with get_session_context() as session:
            result = await session.execute(
                select(IntegrationStateModel).where(
                    and_(
                        IntegrationStateModel.id == record_id,
                        IntegrationStateModel.client_id == client_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            if model:
                model.sync_status = RecordSyncStatus.SYNCED.value
                model.last_synced_at = datetime.now(timezone.utc)
                model.last_sync_version_id = max(
                    model.internal_version_id, model.external_version_id
                )
                model.error_code = None
                model.error_message = None
                model.error_details = None
                if external_record_id:
                    model.external_record_id = external_record_id
                await session.flush()  # Ensure changes are queued before commit

    async def get_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
    ) -> EntitySyncStatus | None:
        async with get_session_context() as session:
            result = await session.execute(
                select(EntitySyncStatusModel).where(
                    and_(
                        EntitySyncStatusModel.client_id == client_id,
                        EntitySyncStatusModel.integration_id == integration_id,
                        EntitySyncStatusModel.entity_type == entity_type,
                    )
                )
            )
            model = result.scalar_one_or_none()
            return _model_to_entity_sync_status(model) if model else None

    async def update_entity_sync_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        job_id: UUID,
        records_count: int,
    ) -> EntitySyncStatus:
        async with get_session_context() as session:
            result = await session.execute(
                select(EntitySyncStatusModel).where(
                    and_(
                        EntitySyncStatusModel.client_id == client_id,
                        EntitySyncStatusModel.integration_id == integration_id,
                        EntitySyncStatusModel.entity_type == entity_type,
                    )
                )
            )
            model = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)

            if model:
                model.last_successful_sync_at = now
                model.last_sync_job_id = job_id
                model.records_synced_count += records_count
                await session.flush()  # Flush updates before refresh
            else:
                model = EntitySyncStatusModel(
                    client_id=client_id,
                    integration_id=integration_id,
                    entity_type=entity_type,
                    last_successful_sync_at=now,
                    last_sync_job_id=job_id,
                    records_synced_count=records_count,
                )
                session.add(model)
                await session.flush()  # Flush insert before refresh

            await session.refresh(model)
            return _model_to_entity_sync_status(model)

    async def batch_upsert_records(
        self,
        records: list[IntegrationStateRecord],
    ) -> list[IntegrationStateRecord]:
        """
        Upsert multiple records in a single transaction with advisory lock.

        Uses advisory lock to prevent concurrent batch operations on the same
        client/integration combination from racing and potentially overwriting
        each other's changes.

        If any record fails, all changes are rolled back.
        """
        if not records:
            return []

        results: list[IntegrationStateRecord] = []
        async with get_session_context() as session:
            # All records in a batch should be for the same client/integration
            # Use advisory lock to prevent concurrent batch operations racing
            first_record = records[0]
            async with advisory_lock(session, first_record.client_id, first_record.integration_id):
                for record in records:
                    # Check if record exists
                    existing = await session.execute(
                        select(IntegrationStateModel).where(
                            and_(
                                IntegrationStateModel.client_id == record.client_id,
                                IntegrationStateModel.integration_id == record.integration_id,
                                IntegrationStateModel.entity_type == record.entity_type,
                                IntegrationStateModel.internal_record_id == record.internal_record_id,
                            )
                        )
                    )
                    model = existing.scalar_one_or_none()

                    if model:
                        # Update existing
                        model.external_record_id = record.external_record_id
                        model.sync_status = record.sync_status.value
                        model.sync_direction = record.sync_direction.value if record.sync_direction else None
                        model.internal_version_id = record.internal_version_id
                        model.external_version_id = record.external_version_id
                        model.last_sync_version_id = record.last_sync_version_id
                        model.last_synced_at = record.last_synced_at
                        model.error_code = record.error_code
                        model.error_message = record.error_message
                        model.error_details = record.error_details
                        model.metadata_ = record.metadata
                    else:
                        # Insert new
                        model = IntegrationStateModel(
                            id=record.id,
                            client_id=record.client_id,
                            integration_id=record.integration_id,
                            entity_type=record.entity_type,
                            internal_record_id=record.internal_record_id,
                            external_record_id=record.external_record_id,
                            sync_status=record.sync_status.value,
                            sync_direction=record.sync_direction.value if record.sync_direction else None,
                            internal_version_id=record.internal_version_id,
                            external_version_id=record.external_version_id,
                            last_sync_version_id=record.last_sync_version_id,
                            last_synced_at=record.last_synced_at,
                            error_code=record.error_code,
                            error_message=record.error_message,
                            error_details=record.error_details,
                            metadata_=record.metadata,
                        )
                        session.add(model)

                # Flush all changes at once (still within transaction)
                await session.flush()

                # Refresh all models and convert to entities
                for record in records:
                    result = await session.execute(
                        select(IntegrationStateModel).where(
                            and_(
                                IntegrationStateModel.client_id == record.client_id,
                                IntegrationStateModel.integration_id == record.integration_id,
                                IntegrationStateModel.entity_type == record.entity_type,
                                IntegrationStateModel.internal_record_id == record.internal_record_id,
                            )
                        )
                    )
                    model = result.scalar_one()
                    results.append(_model_to_integration_state(model))

        return results

    async def batch_mark_synced(
        self,
        updates: list[tuple[UUID, UUID, str | None]],  # (record_id, client_id, external_record_id)
        client_id: UUID | None = None,
        integration_id: UUID | None = None,
    ) -> None:
        """
        Mark multiple records as synced in a single transaction with advisory lock.

        Uses advisory lock when client_id and integration_id are provided to prevent
        concurrent batch operations from racing.

        If any update fails, all changes are rolled back.

        Args:
            updates: List of (record_id, client_id, external_record_id) tuples.
            client_id: Optional client_id for advisory lock (recommended).
            integration_id: Optional integration_id for advisory lock (recommended).
        """
        if not updates:
            return

        async with get_session_context() as session:
            # Use advisory lock if client_id and integration_id provided
            if client_id and integration_id:
                async with advisory_lock(session, client_id, integration_id):
                    await self._do_batch_mark_synced(session, updates)
            else:
                await self._do_batch_mark_synced(session, updates)

    async def _do_batch_mark_synced(
        self,
        session: AsyncSession,
        updates: list[tuple[UUID, UUID, str | None]],
    ) -> None:
        """Internal method to perform batch mark synced operations."""
        now = datetime.now(timezone.utc)

        for record_id, client_id, external_record_id in updates:
            result = await session.execute(
                select(IntegrationStateModel).where(
                    and_(
                        IntegrationStateModel.id == record_id,
                        IntegrationStateModel.client_id == client_id,
                    )
                )
            )
            model = result.scalar_one_or_none()
            if model:
                model.sync_status = RecordSyncStatus.SYNCED.value
                model.last_synced_at = now
                model.last_sync_version_id = max(
                    model.internal_version_id, model.external_version_id
                )
                model.error_code = None
                model.error_message = None
                model.error_details = None
                if external_record_id:
                    model.external_record_id = external_record_id

        # Flush all changes at once (within single transaction)
        await session.flush()
