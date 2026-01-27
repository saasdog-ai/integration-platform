"""FastAPI middleware for request processing."""

import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

logger = get_logger(__name__)

# Context variables for request tracking
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
client_id_ctx: ContextVar[str] = ContextVar("client_id", default="")


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_ctx.get()


def get_client_id() -> str:
    """Get current client ID from context."""
    return client_id_ctx.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to set up request context (request ID, client ID)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(request_id)

        # Extract client ID from auth context (set by auth middleware)
        # This will be populated after authentication
        client_id = getattr(request.state, "client_id", None)
        if client_id:
            client_id_ctx.set(str(client_id))

        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        request_id = get_request_id() or str(uuid.uuid4())

        # Log request
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params) if request.query_params else None,
            },
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
        log_extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        if response.status_code >= 500:
            logger.error("Request failed", extra=log_extra)
        elif response.status_code >= 400:
            logger.warning("Request error", extra=log_extra)
        else:
            logger.info("Request completed", extra=log_extra)

        return response


class ClientContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and validate client context from authenticated requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Client ID is typically set by authentication middleware
        # This middleware ensures it's propagated to the context var
        client_id = getattr(request.state, "client_id", None)
        if client_id:
            client_id_ctx.set(str(client_id))

        return await call_next(request)
