"""Admin API authentication."""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def require_admin_api_key(
    api_key: str | None = Security(api_key_header),
) -> None:
    """Require valid admin API key for admin endpoints."""
    settings = get_settings()

    # In development with no key configured, allow access
    if settings.is_development and not settings.admin_api_key:
        return

    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured",
        )

    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key",
        )
