"""Sync job management endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dto import (
    SyncJobResponse,
    SyncJobsResponse,
    TriggerSyncRequest,
)
from app.auth import get_client_id
from app.core.exceptions import ConflictError, NotFoundError, SyncError
from app.core.logging import get_logger
from app.domain.entities import SyncJob
from app.domain.enums import SyncJobStatus, SyncJobTrigger
from app.services.sync_orchestrator import SyncOrchestrator

logger = get_logger(__name__)

router = APIRouter(prefix="/sync-jobs", tags=["sync-jobs"])


def get_sync_orchestrator() -> SyncOrchestrator:
    """Dependency to get sync orchestrator."""
    from app.core.dependency_injection import get_container
    from app.infrastructure.adapters.factory import get_adapter_factory

    container = get_container()
    return SyncOrchestrator(
        integration_repo=container.integration_repository,
        job_repo=container.sync_job_repository,
        state_repo=container.integration_state_repository,
        queue=container.message_queue,
        encryption_service=container.encryption_service,
        adapter_factory=get_adapter_factory(),
    )


def _to_sync_job_response(job: SyncJob) -> SyncJobResponse:
    """Convert domain entity to response DTO."""
    return SyncJobResponse(
        id=job.id,
        client_id=job.client_id,
        integration_id=job.integration_id,
        integration_name=job.integration.name if job.integration else None,
        job_type=job.job_type,
        status=job.status,
        triggered_by=job.triggered_by,
        started_at=job.started_at,
        completed_at=job.completed_at,
        entities_processed=job.entities_processed,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post(
    "",
    response_model=SyncJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a sync job",
)
async def trigger_sync(
    request: TriggerSyncRequest,
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> SyncJobResponse:
    """
    Trigger a new sync job.

    The job is queued for async processing by the job runner.
    """
    try:
        job = await orchestrator.trigger_sync(
            client_id=client_id,
            integration_id=request.integration_id,
            job_type=request.job_type,
            entity_types=request.entity_types,
            triggered_by=SyncJobTrigger.USER,
        )
        return _to_sync_job_response(job)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SyncError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "",
    response_model=SyncJobsResponse,
    summary="List sync jobs",
)
async def list_sync_jobs(
    integration_id: UUID | None = Query(default=None),
    job_status: SyncJobStatus | None = Query(default=None, alias="status"),
    since: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> SyncJobsResponse:
    """List sync jobs with optional filters and pagination."""
    jobs, total = await orchestrator.get_jobs_paginated(
        client_id=client_id,
        integration_id=integration_id,
        status=job_status,
        since=since,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size  # Ceiling division
    return SyncJobsResponse(
        jobs=[_to_sync_job_response(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{job_id}",
    response_model=SyncJobResponse,
    summary="Get sync job details",
)
async def get_sync_job(
    job_id: UUID,
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> SyncJobResponse:
    """Get details of a specific sync job."""
    try:
        job = await orchestrator.get_job(client_id, job_id)
        return _to_sync_job_response(job)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job not found: {job_id}",
        )


@router.post(
    "/{job_id}/cancel",
    response_model=SyncJobResponse,
    summary="Cancel a sync job",
)
async def cancel_sync_job(
    job_id: UUID,
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> SyncJobResponse:
    """Cancel a running or pending sync job."""
    try:
        job = await orchestrator.cancel_sync_job(client_id, job_id)
        return _to_sync_job_response(job)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job not found: {job_id}",
        )
    except SyncError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{job_id}/execute",
    response_model=SyncJobResponse,
    summary="Execute a sync job immediately (dev/demo only)",
)
async def execute_sync_job(
    job_id: UUID,
    client_id: UUID = Depends(get_client_id),
    orchestrator: SyncOrchestrator = Depends(get_sync_orchestrator),
) -> SyncJobResponse:
    """
    Execute a pending sync job immediately.

    This bypasses the queue and executes the job synchronously.
    Intended for development and demo purposes only.
    """
    try:
        # Get the job
        job = await orchestrator.get_job(client_id, job_id)

        # Check if job is pending
        if job.status != SyncJobStatus.PENDING:
            raise SyncError(f"Job is not pending (current status: {job.status.value})")

        # Execute immediately
        result = await orchestrator.execute_sync_job(job)
        return _to_sync_job_response(result)

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job not found: {job_id}",
        )
    except SyncError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
