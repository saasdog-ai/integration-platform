"""Tests for custom exceptions."""

from uuid import uuid4

import pytest

from app.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    EncryptionError,
    IntegrationAuthError,
    IntegrationError,
    IntegrationRateLimitError,
    NotFoundError,
    QueueError,
    SyncError,
    ValidationError,
)


class TestApplicationError:
    """Tests for ApplicationError."""

    def test_basic_exception(self):
        """Test creating a basic exception."""
        exc = ApplicationError(message="Something went wrong")

        assert str(exc) == "Something went wrong"
        assert exc.code == "INTERNAL_ERROR"
        assert exc.details == {}

    def test_exception_with_code_and_details(self):
        """Test exception with custom code and details."""
        exc = ApplicationError(
            message="Custom error",
            code="CUSTOM_CODE",
            details={"key": "value"},
        )

        assert exc.code == "CUSTOM_CODE"
        assert exc.details == {"key": "value"}


class TestNotFoundError:
    """Tests for NotFoundError."""

    def test_not_found_with_uuid(self):
        """Test NotFoundError with UUID resource ID."""
        resource_id = uuid4()
        exc = NotFoundError("Integration", resource_id)

        assert "Integration" in str(exc)
        assert str(resource_id) in str(exc)
        assert exc.code == "NOT_FOUND"

    def test_not_found_with_string_id(self):
        """Test NotFoundError with string resource ID."""
        exc = NotFoundError("User", "user-123")

        assert "User" in str(exc)
        assert "user-123" in str(exc)
        assert exc.code == "NOT_FOUND"

    def test_not_found_details(self):
        """Test NotFoundError details include resource info."""
        exc = NotFoundError("SyncJob", uuid4())

        assert "resource_type" in exc.details
        assert exc.details["resource_type"] == "SyncJob"


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_basic(self):
        """Test basic validation error."""
        exc = ValidationError("Invalid email format")

        assert "Invalid email format" in str(exc)
        assert exc.code == "VALIDATION_ERROR"

    def test_validation_error_with_field(self):
        """Test validation error with field info."""
        exc = ValidationError("Invalid value", field="email")

        assert exc.details["field"] == "email"

    def test_validation_error_with_details(self):
        """Test validation error with additional details."""
        exc = ValidationError(
            "Invalid value",
            details={"constraint": "format"},
        )

        assert exc.details["constraint"] == "format"


class TestConflictError:
    """Tests for ConflictError."""

    def test_conflict_error(self):
        """Test conflict error."""
        exc = ConflictError(
            "Resource already exists",
            resource_type="UserIntegration",
            details={"existing_id": str(uuid4())},
        )

        assert "already exists" in str(exc)
        assert exc.code == "CONFLICT"
        assert exc.details["resource_type"] == "UserIntegration"

    def test_conflict_error_without_resource_type(self):
        """Test conflict error without resource type."""
        exc = ConflictError("Duplicate entry")

        assert exc.code == "CONFLICT"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_authentication_error_default(self):
        """Test authentication error with default message."""
        exc = AuthenticationError()

        assert "Authentication" in str(exc)
        assert exc.code == "AUTHENTICATION_REQUIRED"

    def test_authentication_error_custom(self):
        """Test authentication error with custom message."""
        exc = AuthenticationError("Invalid token")

        assert "Invalid token" in str(exc)


class TestAuthorizationError:
    """Tests for AuthorizationError."""

    def test_authorization_error_default(self):
        """Test authorization error with default message."""
        exc = AuthorizationError()

        assert "denied" in str(exc).lower()
        assert exc.code == "ACCESS_DENIED"

    def test_authorization_error_with_details(self):
        """Test authorization error with details."""
        exc = AuthorizationError(
            "Access denied",
            details={"required_scope": "admin"},
        )

        assert exc.details["required_scope"] == "admin"


class TestSyncError:
    """Tests for SyncError."""

    def test_sync_error_basic(self):
        """Test basic sync error."""
        exc = SyncError("Sync failed due to timeout")

        assert "timeout" in str(exc).lower()
        assert exc.code == "SYNC_ERROR"

    def test_sync_error_with_entity_info(self):
        """Test sync error with entity info."""
        exc = SyncError(
            "Failed to sync record",
            entity_type="bill",
            record_id="123",
            details={"reason": "validation_failed"},
        )

        assert exc.details["entity_type"] == "bill"
        assert exc.details["record_id"] == "123"
        assert exc.details["reason"] == "validation_failed"


class TestIntegrationError:
    """Tests for IntegrationError."""

    def test_integration_error(self):
        """Test integration error."""
        exc = IntegrationError(
            "QuickBooks",
            "Failed to connect",
            details={"http_status": 500},
        )

        assert "QuickBooks" in str(exc)
        assert "Failed to connect" in str(exc)
        assert exc.code == "INTEGRATION_ERROR"
        assert exc.details["integration"] == "QuickBooks"


class TestIntegrationAuthError:
    """Tests for IntegrationAuthError."""

    def test_integration_auth_error(self):
        """Test integration auth error."""
        exc = IntegrationAuthError("QuickBooks")

        assert "QuickBooks" in str(exc)
        assert exc.code == "INTEGRATION_AUTH_ERROR"

    def test_integration_auth_error_custom_message(self):
        """Test integration auth error with custom message."""
        exc = IntegrationAuthError("Xero", message="Token expired")

        assert "Token expired" in str(exc)


class TestIntegrationRateLimitError:
    """Tests for IntegrationRateLimitError."""

    def test_integration_rate_limit_error(self):
        """Test integration rate limit error."""
        exc = IntegrationRateLimitError("QuickBooks", retry_after=60)

        assert "Rate limit" in str(exc)
        assert exc.code == "INTEGRATION_RATE_LIMIT"
        assert exc.details["retry_after"] == 60

    def test_integration_rate_limit_error_without_retry(self):
        """Test integration rate limit error without retry_after."""
        exc = IntegrationRateLimitError("QuickBooks")

        assert exc.details["retry_after"] is None


class TestEncryptionError:
    """Tests for EncryptionError."""

    def test_encryption_error(self):
        """Test encryption error."""
        exc = EncryptionError("Failed to decrypt credentials")

        assert "decrypt" in str(exc)
        assert exc.code == "ENCRYPTION_ERROR"


class TestQueueError:
    """Tests for QueueError."""

    def test_queue_error(self):
        """Test queue error."""
        exc = QueueError("Failed to send message", details={"queue_name": "sync-jobs"})

        assert "send message" in str(exc)
        assert exc.code == "QUEUE_ERROR"
        assert exc.details["queue_name"] == "sync-jobs"
