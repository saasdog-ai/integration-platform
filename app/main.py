"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
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
from app.core.middleware import LoggingMiddleware, RequestContextMiddleware
from app.infrastructure.db.database import close_db, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    setup_logging()
    logger.info("Starting application...")

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")
    await close_db()


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

    # Add custom middleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(health_router)
    app.include_router(integrations_router)
    app.include_router(settings_router)
    app.include_router(sync_jobs_router)

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
    async def validation_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
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
    async def auth_error_handler(
        request: Request, exc: AuthenticationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authz_error_handler(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
            },
        )

    @app.exception_handler(ApplicationError)
    async def app_error_handler(
        request: Request, exc: ApplicationError
    ) -> JSONResponse:
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
