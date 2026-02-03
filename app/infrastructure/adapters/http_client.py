"""HTTP client with timeout configuration for external API calls."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_timeout_config() -> httpx.Timeout:
    """Get httpx timeout configuration from settings."""
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.api_connect_timeout,
        read=settings.api_read_timeout,
        write=settings.api_read_timeout,  # Use read timeout for writes too
        pool=settings.api_connect_timeout,
    )


@asynccontextmanager
async def get_http_client(
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Get a configured async HTTP client with proper timeouts.

    This client should be used for all external API calls to ensure
    requests don't hang indefinitely.

    Args:
        base_url: Optional base URL for the client.
        headers: Optional default headers.
        timeout: Optional custom timeout (defaults to settings).

    Yields:
        Configured httpx.AsyncClient.

    Example:
        async with get_http_client(base_url="https://api.example.com") as client:
            response = await client.get("/endpoint")
    """
    if timeout is None:
        timeout = get_timeout_config()

    client_kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
    }
    if base_url is not None:
        client_kwargs["base_url"] = base_url
    if headers is not None:
        client_kwargs["headers"] = headers

    async with httpx.AsyncClient(**client_kwargs) as client:
        yield client


async def make_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    """
    Make a single HTTP request with proper timeout configuration.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        url: Full URL for the request.
        headers: Optional request headers.
        json: Optional JSON body.
        params: Optional query parameters.
        timeout: Optional custom timeout.

    Returns:
        httpx.Response object.

    Raises:
        httpx.TimeoutException: If the request times out.
        httpx.HTTPError: For other HTTP errors.
    """
    if timeout is None:
        timeout = get_timeout_config()

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            params=params,
        )
        return response
