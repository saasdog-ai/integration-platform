"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin_router,
    health_router,
    integrations_router,
    settings_router,
    sync_jobs_router,
)
from app.core.config import get_settings
from app.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger, setup_logging
from app.core.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)
from app.infrastructure.db.database import close_db, init_db

logger = get_logger(__name__)

# Global references for job runner
_job_runner_task: asyncio.Task | None = None
_job_runner_watchdog: asyncio.Task | None = None
_shutdown_requested = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _job_runner_task, _job_runner_watchdog, _shutdown_requested

    _shutdown_requested = False

    # Startup
    setup_logging()
    logger.info("Starting application...")

    settings = get_settings()

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Start job runner as background task (shares in-memory queue with API)
    from app.core.dependency_injection import get_container

    container = get_container()

    if container.feature_flag_service.is_job_runner_enabled():
        _job_runner_task = asyncio.create_task(_run_job_runner())
        _job_runner_watchdog = asyncio.create_task(_watch_job_runner())
        logger.info(
            "Job runner started as background task",
            extra={"max_workers": settings.job_runner_max_workers},
        )

    # Start scheduler if enabled
    if container.feature_flag_service.is_scheduler_enabled():
        scheduler = container.scheduler
        await scheduler.start()
        logger.info(
            "Scheduler started",
            extra={"timezone": settings.scheduler_timezone},
        )

    yield

    # Shutdown
    _shutdown_requested = True
    logger.info("Shutting down application...")

    # Stop scheduler
    if container.feature_flag_service.is_scheduler_enabled():
        logger.info("Stopping scheduler...")
        await container.scheduler.stop()
        logger.info("Scheduler stopped")

    # Stop watchdog
    if _job_runner_watchdog and not _job_runner_watchdog.done():
        _job_runner_watchdog.cancel()
        try:
            await _job_runner_watchdog
        except asyncio.CancelledError:
            pass

    # Stop job runner
    if _job_runner_task and not _job_runner_task.done():
        logger.info("Stopping job runner...")
        _job_runner_task.cancel()
        try:
            await _job_runner_task
        except asyncio.CancelledError:
            pass
        logger.info("Job runner stopped")

    await close_db()


async def _run_job_runner() -> None:
    """Run the job runner in the same process as the API."""
    from app.core.dependency_injection import get_container
    from app.infrastructure.adapters.factory import get_adapter_factory
    from app.services.sync_job_runner import SyncJobRunner

    settings = get_settings()
    container = get_container()

    runner = SyncJobRunner(
        queue=container.message_queue,
        integration_repo=container.integration_repository,
        job_repo=container.sync_job_repository,
        state_repo=container.integration_state_repository,
        encryption_service=container.encryption_service,
        adapter_factory=get_adapter_factory(),
        max_workers=settings.job_runner_max_workers,
    )

    try:
        await runner.start()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Job runner crashed: {e}", exc_info=True)


async def _watch_job_runner() -> None:
    """Restart the job runner if it dies unexpectedly."""
    global _job_runner_task

    while not _shutdown_requested:
        await asyncio.sleep(10)
        if _shutdown_requested:
            break
        if _job_runner_task and _job_runner_task.done():
            logger.warning("Job runner task died — restarting")
            _job_runner_task = asyncio.create_task(_run_job_runner())


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Integration Platform",
        description="Generic, production-ready integration platform for syncing data between SaaS products and external systems",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add custom middleware (order matters - first added = last to execute on request)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware)  # Rate limit after context is set
    app.add_middleware(RequestSizeLimitMiddleware)  # Check size early, before processing

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(health_router)
    app.include_router(integrations_router)
    app.include_router(settings_router)
    app.include_router(sync_jobs_router)
    app.include_router(admin_router)

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authz_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(ApplicationError)
    async def app_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", extra={"error": str(exc)})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
                "details": None,
            },
        )


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
    )
