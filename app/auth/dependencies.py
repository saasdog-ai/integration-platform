"""Authentication dependencies for FastAPI."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import verify_token
from app.core.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer scheme for JWT tokens
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedClient:
    """Represents an authenticated client from JWT token."""

    def __init__(
        self, client_id: UUID, user_id: str | None = None, scopes: list[str] | None = None
    ):
        self.client_id = client_id
        self.user_id = user_id
        self.scopes = scopes or []


async def get_current_client(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedClient:
    """
    Extract and validate client from JWT token.

    When auth is disabled (development), uses a fixed test client ID.
    When auth is enabled, requires valid JWT token with client_id claim.
    """
    from app.core.dependency_injection import get_container

    # Development mode: auth disabled
    if not get_container().feature_flag_service.is_auth_enabled():
        # Use a consistent test client ID in development
        # This is safer than random UUID - at least data is consistent
        test_client_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        logger.debug(
            "Auth disabled, using test client_id", extra={"client_id": str(test_client_id)}
        )
        return AuthenticatedClient(client_id=test_client_id)

    # Production mode: require valid token
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_token(credentials.credentials)
    except ValueError as e:
        logger.warning("Token verification failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Extract client_id from token
    if not payload.client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing client_id claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedClient(
        client_id=payload.client_id,
        user_id=payload.sub,
        scopes=payload.scopes,
    )


def get_client_id(
    client: Annotated[AuthenticatedClient, Depends(get_current_client)],
) -> UUID:
    """
    Dependency to get just the client_id from authenticated client.

    Use this when you only need the client_id, not the full client info.
    """
    return client.client_id
