"""Application exceptions and error handling."""

from typing import Any
from uuid import UUID


class ApplicationError(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class NotFoundError(ApplicationError):
    """Resource not found."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str | UUID,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            code="NOT_FOUND",
            details={
                "resource_type": resource_type,
                "resource_id": str(resource_id),
                **(details or {}),
            },
        )


class ValidationError(ApplicationError):
    """Validation failed."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field, **(details or {})} if field else details,
        )


class ConflictError(ApplicationError):
    """Resource conflict (e.g., duplicate)."""

    def __init__(
        self,
        message: str,
        resource_type: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="CONFLICT",
            details=(
                {"resource_type": resource_type, **(details or {})} if resource_type else details
            ),
        )


class AuthenticationError(ApplicationError):
    """Authentication failed."""

    def __init__(
        self,
        message: str = "Authentication required",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="AUTHENTICATION_REQUIRED",
            details=details,
        )


class AuthorizationError(ApplicationError):
    """Authorization failed."""

    def __init__(
        self,
        message: str = "Access denied",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="ACCESS_DENIED",
            details=details,
        )


class IntegrationError(ApplicationError):
    """External integration error."""

    def __init__(
        self,
        integration_name: str,
        message: str,
        code: str = "INTEGRATION_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"{integration_name}: {message}",
            code=code,
            details={"integration": integration_name, **(details or {})},
        )


class IntegrationAuthError(IntegrationError):
    """External integration authentication error."""

    def __init__(
        self,
        integration_name: str,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            integration_name=integration_name,
            message=message,
            code="INTEGRATION_AUTH_ERROR",
            details=details,
        )


class IntegrationRateLimitError(IntegrationError):
    """External integration rate limit exceeded."""

    def __init__(
        self,
        integration_name: str,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            integration_name=integration_name,
            message="Rate limit exceeded",
            code="INTEGRATION_RATE_LIMIT",
            details={"retry_after": retry_after, **(details or {})},
        )


class EncryptionError(ApplicationError):
    """Encryption/decryption error."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="ENCRYPTION_ERROR",
            details=details,
        )


class QueueError(ApplicationError):
    """Message queue error."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="QUEUE_ERROR",
            details=details,
        )


class SyncError(ApplicationError):
    """Sync operation error."""

    def __init__(
        self,
        message: str,
        entity_type: str | None = None,
        record_id: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        extra = {}
        if entity_type:
            extra["entity_type"] = entity_type
        if record_id:
            extra["record_id"] = record_id
        super().__init__(
            message=message,
            code="SYNC_ERROR",
            details={**extra, **(details or {})},
        )
