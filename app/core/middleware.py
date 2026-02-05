"""FastAPI middleware for request processing."""

import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
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


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit request body size.

    Prevents DOS attacks via large request payloads that could exhaust memory.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        max_size = settings.api_max_request_size

        # Check Content-Length header first (fast path)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_size:
                    logger.warning(
                        "Request rejected: Content-Length exceeds limit",
                        extra={
                            "content_length": content_length,
                            "max_size": max_size,
                            "path": request.url.path,
                        },
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": f"Request body too large. Maximum size is {max_size} bytes.",
                            "code": "REQUEST_TOO_LARGE",
                            "details": {"max_size": max_size},
                        },
                    )
            except ValueError:
                pass  # Invalid Content-Length, will be handled elsewhere

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting middleware using token bucket algorithm.

    NOTE: This is disabled by default (rate_limit_enabled=False in config).
    In production, rate limiting should be done at the API gateway level
    (Kong, AWS API Gateway, nginx) or via distributed rate limiting with Redis.

    This middleware is useful for:
    - Local development and testing
    - Single-instance deployments
    - Defense-in-depth as a secondary limit behind API gateway

    Rate limiting is per-client (identified by client_id from auth or IP address).
    """

    def __init__(self, app):
        super().__init__(app)
        # Store: {client_key: (tokens, last_update_time)}
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = None  # Will be initialized on first request

    def _get_client_key(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Try to get client_id from auth (set by auth middleware)
        client_id = getattr(request.state, "client_id", None)
        if client_id:
            return f"client:{client_id}"

        # Fall back to IP address for unauthenticated requests
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain (original client)
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _check_rate_limit(
        self, client_key: str, max_requests: int, burst: int
    ) -> tuple[bool, int, float]:
        """
        Check if request is allowed using token bucket algorithm.

        Args:
            client_key: Client identifier.
            max_requests: Max requests per minute.
            burst: Burst allowance.

        Returns:
            Tuple of (allowed, remaining_tokens, retry_after_seconds).
        """
        import time

        now = time.time()
        refill_rate = max_requests / 60.0  # Tokens per second
        max_tokens = max_requests + burst

        # Get current bucket state
        tokens, last_update = self._buckets.get(client_key, (max_tokens, now))

        # Refill tokens based on time passed
        time_passed = now - last_update
        tokens = min(max_tokens, tokens + time_passed * refill_rate)

        if tokens >= 1:
            # Allow request, consume one token
            self._buckets[client_key] = (tokens - 1, now)
            return True, int(tokens - 1), 0.0
        else:
            # Reject request, calculate retry time
            retry_after = (1 - tokens) / refill_rate
            self._buckets[client_key] = (tokens, now)
            return False, 0, retry_after

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from app.core.dependency_injection import get_container

        settings = get_settings()

        # Skip rate limiting if disabled
        if not get_container().feature_flag_service.is_rate_limit_enabled():
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/health/live", "/health/ready"):
            return await call_next(request)

        client_key = self._get_client_key(request)
        allowed, remaining, retry_after = self._check_rate_limit(
            client_key,
            settings.rate_limit_requests_per_minute,
            settings.rate_limit_burst,
        )

        if not allowed:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_key": client_key,
                    "path": request.url.path,
                    "retry_after": round(retry_after, 2),
                },
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded. Please slow down.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "details": {"retry_after_seconds": round(retry_after, 2)},
                },
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests_per_minute)

        return response
