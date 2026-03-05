"""Health check endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.api.dto import HealthDetailResponse, HealthResponse
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
)
async def health_check() -> HealthResponse:
    """Basic health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/ready",
    response_model=HealthDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness check with dependency status",
)
async def readiness_check() -> HealthDetailResponse:
    """
    Detailed readiness check that verifies all dependencies.

    Checks database, queue, and encryption service connectivity.
    """
    db_status = "healthy"
    queue_status = "healthy"
    encryption_status = "healthy"

    # Check database
    try:
        from app.infrastructure.db.database import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
    except Exception as e:
        logger.error("Database health check failed", extra={"error": str(e)})
        db_status = "unhealthy"

    # Check queue (just verify it's configured)
    try:
        from app.infrastructure.queue.factory import get_message_queue

        get_message_queue()
        # Queue is healthy if it's instantiated
    except Exception as e:
        logger.error("Queue health check failed", extra={"error": str(e)})
        queue_status = "unhealthy"

    # Check encryption (just verify it's configured)
    try:
        from app.infrastructure.encryption.factory import get_encryption_service

        get_encryption_service()
        # Encryption is healthy if it's instantiated
    except Exception as e:
        logger.error("Encryption health check failed", extra={"error": str(e)})
        encryption_status = "unhealthy"

    overall_status = "healthy"
    if any(s.startswith("unhealthy") for s in [db_status, queue_status, encryption_status]):
        overall_status = "degraded"

    return HealthDetailResponse(
        status=overall_status,
        version="0.1.0",
        timestamp=datetime.now(UTC),
        database=db_status,
        queue=queue_status,
        encryption=encryption_status,
    )


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
)
async def liveness_check() -> dict:
    """Simple liveness check - just confirms the app is running."""
    return {"status": "alive"}
