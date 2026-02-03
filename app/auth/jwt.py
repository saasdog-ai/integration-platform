"""JWT token verification."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class JWTPayload(BaseModel):
    """Parsed JWT token payload."""

    sub: str | None = None  # Subject (user ID)
    client_id: UUID | None = None  # Tenant/client ID
    exp: datetime | None = None  # Expiration time
    iat: datetime | None = None  # Issued at
    iss: str | None = None  # Issuer
    aud: str | list[str] | None = None  # Audience
    scopes: list[str] = []  # Permission scopes


def verify_token(token: str) -> JWTPayload:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        Parsed JWT payload.

    Raises:
        ValueError: If token is invalid or expired.
    """
    settings = get_settings()

    try:
        # Decode and verify token
        options = {
            "verify_exp": True,
            "verify_iat": True,
            "require_exp": True,
        }

        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options=options,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )

        # Check required claims
        if "client_id" not in payload:
            raise ValueError("Token missing required claim: client_id")

    except ExpiredSignatureError:
        raise ValueError("Token has expired") from None
    except JWTClaimsError as e:
        raise ValueError(f"Invalid token claims: {e}") from e
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e

    # Parse client_id as UUID
    client_id_str = payload.get("client_id")
    client_id = None
    if client_id_str:
        try:
            client_id = UUID(client_id_str)
        except (ValueError, TypeError):
            raise ValueError("Invalid client_id format in token") from None

    # Parse expiration time
    exp = None
    if payload.get("exp"):
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)

    # Parse issued at time
    iat = None
    if payload.get("iat"):
        iat = datetime.fromtimestamp(payload["iat"], tz=UTC)

    return JWTPayload(
        sub=payload.get("sub"),
        client_id=client_id,
        exp=exp,
        iat=iat,
        iss=payload.get("iss"),
        aud=payload.get("aud"),
        scopes=payload.get("scopes", []),
    )


def create_token(
    client_id: UUID,
    user_id: str | None = None,
    scopes: list[str] | None = None,
    expires_in_seconds: int = 3600,
) -> str:
    """
    Create a JWT token (for testing purposes).

    Args:
        client_id: The tenant/client ID.
        user_id: Optional user ID.
        scopes: Optional permission scopes.
        expires_in_seconds: Token expiration time.

    Returns:
        Encoded JWT token.
    """
    settings = get_settings()
    now = datetime.now(UTC)

    payload: dict[str, Any] = {
        "client_id": str(client_id),
        "iat": now,
        "exp": datetime.fromtimestamp(now.timestamp() + expires_in_seconds, tz=UTC),
    }

    if user_id:
        payload["sub"] = user_id
    if scopes:
        payload["scopes"] = scopes
    if settings.jwt_issuer:
        payload["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
