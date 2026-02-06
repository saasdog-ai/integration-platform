"""Integration management service."""

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID, uuid4

from app.core.exceptions import (
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.core.logging import get_logger
from app.domain.entities import (
    AvailableIntegration,
    OAuthTokens,
    UserIntegration,
)
from app.domain.enums import IntegrationStatus
from app.domain.interfaces import (
    AdapterFactoryInterface,
    EncryptionServiceInterface,
    IntegrationRepositoryInterface,
)
from app.services.oauth_state_store import get_oauth_state_store

logger = get_logger(__name__)

# Transient errors that should not mark integration as permanently failed
TRANSIENT_ERROR_PATTERNS = [
    r"timeout",
    r"connection.*refused",
    r"connection.*reset",
    r"temporary.*failure",
    r"service.*unavailable",
    r"too.*many.*requests",
    r"rate.*limit",
    r"network.*error",
    r"dns.*error",
    r"ssl.*error",
]


def _is_transient_error(error: Exception) -> bool:
    """Check if an error is transient (network/temporary) vs permanent."""
    error_msg = str(error).lower()
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if re.search(pattern, error_msg):
            return True
    # Also check exception type
    error_type = type(error).__name__.lower()
    if any(t in error_type for t in ["timeout", "connection", "network"]):
        return True
    return False


def _sanitize_error_for_log(error: Exception) -> str:
    """Sanitize error message to remove potential credentials."""
    error_msg = str(error)
    # Remove potential tokens/secrets from error messages
    # Pattern matches common token formats
    sanitized = re.sub(
        r'(token|bearer|key|secret|password|credential|auth)["\s:=]+[^\s"\'&]{10,}',
        r"\1=[REDACTED]",
        error_msg,
        flags=re.IGNORECASE,
    )
    # Also redact long base64-like strings that could be tokens
    sanitized = re.sub(
        r"[A-Za-z0-9+/=]{40,}",
        "[REDACTED_TOKEN]",
        sanitized,
    )
    return sanitized


class IntegrationService:
    """Service for managing integrations."""

    def __init__(
        self,
        integration_repo: IntegrationRepositoryInterface,
        encryption_service: EncryptionServiceInterface,
        adapter_factory: AdapterFactoryInterface,
    ) -> None:
        """
        Initialize integration service.

        Args:
            integration_repo: Repository for integration data access.
            encryption_service: Service for credential encryption.
            adapter_factory: Factory for creating integration adapters.
        """
        self._repo = integration_repo
        self._encryption = encryption_service
        self._adapter_factory = adapter_factory

    async def get_available_integrations(
        self, active_only: bool = True
    ) -> list[AvailableIntegration]:
        """Get all available integrations."""
        return await self._repo.get_available_integrations(active_only=active_only)

    async def get_available_integration(self, integration_id: UUID) -> AvailableIntegration:
        """Get a specific available integration."""
        integration = await self._repo.get_available_integration(integration_id)
        if not integration:
            raise NotFoundError("Integration", integration_id)
        return integration

    async def get_user_integrations(self, client_id: UUID) -> list[UserIntegration]:
        """Get all integrations for a user."""
        return await self._repo.get_user_integrations(client_id)

    async def get_user_integration(self, client_id: UUID, integration_id: UUID) -> UserIntegration:
        """Get a user's specific integration."""
        integration = await self._repo.get_user_integration(client_id, integration_id)
        if not integration:
            raise NotFoundError("UserIntegration", f"{client_id}/{integration_id}")
        return integration

    async def get_oauth_authorization_url(
        self,
        client_id: UUID,
        integration_id: UUID,
        redirect_uri: str,
        state: str | None = None,  # Now ignored - we generate our own
        allowed_redirect_uris: list[str] | None = None,
    ) -> str:
        """
        Get OAuth authorization URL for connecting an integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration to connect.
            redirect_uri: OAuth redirect URI.
            state: Ignored - state is now generated internally for CSRF protection.
            allowed_redirect_uris: Whitelist of allowed redirect URIs.

        Returns:
            The authorization URL to redirect the user to.
        """
        integration = await self.get_available_integration(integration_id)

        if not integration.connection_config:
            raise ValidationError(f"Integration {integration.name} has no connection config")

        # Validate redirect_uri against whitelist if provided
        if allowed_redirect_uris:
            if redirect_uri not in allowed_redirect_uris:
                raise ValidationError(
                    f"Invalid redirect_uri. Must be one of: {', '.join(allowed_redirect_uris)}"
                )

        # Check if already connected
        existing = await self._repo.get_user_integration(client_id, integration_id)
        if existing and existing.status == IntegrationStatus.CONNECTED:
            raise ConflictError(
                f"Integration {integration.name} is already connected",
                resource_type="UserIntegration",
            )

        # Generate and store state for CSRF protection
        state_store = get_oauth_state_store()
        generated_state = state_store.create_state(
            client_id=client_id,
            integration_id=integration_id,
            redirect_uri=redirect_uri,
        )

        # Build authorization URL with proper URL encoding
        connection_config = integration.connection_config
        params = {
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(connection_config.scopes),
            "state": generated_state,
        }

        # Add OAuth client_id from config if available
        if connection_config.client_id:
            params["client_id"] = connection_config.client_id

        # Use urlencode for proper URL encoding (prevents injection attacks)
        query = urlencode(params)
        auth_url = f"{connection_config.authorization_url}?{query}"

        logger.info(
            "Generated OAuth authorization URL",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
            },
        )

        return auth_url

    async def complete_oauth_callback(
        self,
        client_id: UUID,
        integration_id: UUID,
        auth_code: str,
        redirect_uri: str,
        state: str,
        realm_id: str | None = None,
        user_id: str | None = None,
    ) -> UserIntegration:
        """
        Complete OAuth flow by exchanging auth code for tokens.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration being connected.
            auth_code: The authorization code from OAuth callback.
            redirect_uri: The redirect URI used in the authorization request.
            state: The state parameter from OAuth callback (required for CSRF validation).
            realm_id: External account identifier (e.g. QBO realmId).
            user_id: Optional user ID for audit.

        Returns:
            The connected user integration.
        """
        # Validate state FIRST (CSRF protection)
        state_store = get_oauth_state_store()
        state_entry = state_store.validate_and_consume(state, client_id)

        if state_entry is None:
            raise ValidationError(
                "Invalid or expired OAuth state. Please restart the connection flow."
            )

        # Validate integration_id matches
        if state_entry.integration_id != integration_id:
            raise ValidationError("OAuth state mismatch. Please restart the connection flow.")

        # Validate redirect_uri matches
        if state_entry.redirect_uri != redirect_uri:
            raise ValidationError("Redirect URI mismatch. Please restart the connection flow.")

        logger.info(
            "OAuth callback started",
            extra={
                "client_id": str(client_id),
                "integration_id": str(integration_id),
                "realm_id": realm_id,
                "has_auth_code": bool(auth_code),
            },
        )

        integration = await self.get_available_integration(integration_id)

        # Get or create user integration
        existing = await self._repo.get_user_integration(client_id, integration_id)
        logger.info(
            "OAuth callback: existing connection lookup",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
                "has_existing": existing is not None,
            },
        )

        # Create adapter and exchange code for tokens
        try:
            # For new connections, we don't have tokens yet, so pass empty string
            adapter = self._adapter_factory.get_adapter(integration, "", None)
            logger.info(
                "OAuth callback: exchanging auth code for tokens",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "redirect_uri": redirect_uri,
                },
            )
            tokens = await adapter.authenticate(
                auth_code, redirect_uri, integration.connection_config
            )
            logger.info(
                "OAuth callback: token exchange succeeded",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "token_type": tokens.token_type,
                    "expires_in": tokens.expires_in,
                    "has_refresh_token": bool(tokens.refresh_token),
                    "scope": tokens.scope,
                },
            )
        except Exception as e:
            # Sanitize error to avoid credential exposure in logs
            sanitized_error = _sanitize_error_for_log(e)
            logger.error(
                "OAuth authentication failed",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "error": sanitized_error,
                    "error_type": type(e).__name__,
                },
            )
            raise IntegrationError(
                integration.name,
                f"OAuth authentication failed: {sanitized_error}",
            ) from e

        # Encrypt and store credentials
        credentials_json = json.dumps(
            {
                "access_token": tokens.access_token,
                "refresh_token": tokens.refresh_token,
                "token_type": tokens.token_type,
                "expires_in": tokens.expires_in,
                "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
                "scope": tokens.scope,
            }
        )
        logger.info(
            "OAuth callback: encrypting credentials",
            extra={"client_id": str(client_id), "integration": integration.name},
        )
        encrypted_creds, key_id = await self._encryption.encrypt(credentials_json.encode())
        logger.info(
            "OAuth callback: credentials encrypted",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
                "key_id": key_id,
            },
        )

        now = datetime.now(UTC)

        if existing:
            existing.status = IntegrationStatus.CONNECTED
            existing.credentials_encrypted = encrypted_creds
            existing.credentials_key_id = key_id
            existing.external_account_id = realm_id
            existing.last_connected_at = now
            existing.updated_by = user_id
            logger.info(
                "OAuth callback: updating existing connection",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "user_integration_id": str(existing.id),
                },
            )
            user_integration = await self._repo.update_user_integration(existing)
        else:
            user_integration = UserIntegration(
                id=uuid4(),
                client_id=client_id,
                integration_id=integration_id,
                status=IntegrationStatus.CONNECTED,
                credentials_encrypted=encrypted_creds,
                credentials_key_id=key_id,
                external_account_id=realm_id,
                last_connected_at=now,
                created_at=now,
                updated_at=now,
                created_by=user_id,
                updated_by=user_id,
            )
            logger.info(
                "OAuth callback: creating new connection",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "user_integration_id": str(user_integration.id),
                },
            )
            user_integration = await self._repo.create_user_integration(user_integration)

        logger.info(
            "Integration connected successfully",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
                "user_integration_id": str(user_integration.id),
                "realm_id": realm_id,
            },
        )

        return user_integration

    async def disconnect_integration(
        self,
        client_id: UUID,
        integration_id: UUID,
        user_id: str | None = None,
    ) -> bool:
        """
        Disconnect a user's integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration to disconnect.
            user_id: Optional user ID for audit.

        Returns:
            True if disconnected successfully.
        """
        integration = await self.get_available_integration(integration_id)
        existing = await self._repo.get_user_integration(client_id, integration_id)

        if not existing:
            raise NotFoundError("UserIntegration", f"{client_id}/{integration_id}")

        # Update status to revoked rather than deleting
        existing.status = IntegrationStatus.REVOKED
        existing.credentials_encrypted = None
        existing.credentials_key_id = None
        existing.external_account_id = None
        existing.disconnected_at = datetime.now(UTC)
        existing.updated_by = user_id
        await self._repo.update_user_integration(existing)

        logger.info(
            "Integration disconnected",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
            },
        )

        return True

    async def get_decrypted_credentials(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> OAuthTokens:
        """
        Get decrypted OAuth credentials for an integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.

        Returns:
            Decrypted OAuth tokens.
        """
        user_integration = await self.get_user_integration(client_id, integration_id)

        if user_integration.status != IntegrationStatus.CONNECTED:
            raise ValidationError(
                f"Integration is not connected (status: {user_integration.status})"
            )

        if not user_integration.credentials_encrypted or not user_integration.credentials_key_id:
            raise ValidationError("Integration has no stored credentials")

        # Decrypt credentials
        decrypted = await self._encryption.decrypt(
            user_integration.credentials_encrypted,
            user_integration.credentials_key_id,
        )
        credentials_dict = json.loads(decrypted.decode())

        return OAuthTokens(
            access_token=credentials_dict["access_token"],
            refresh_token=credentials_dict.get("refresh_token"),
            token_type=credentials_dict.get("token_type", "Bearer"),
            expires_in=credentials_dict.get("expires_in"),
            expires_at=(
                datetime.fromisoformat(credentials_dict["expires_at"])
                if credentials_dict.get("expires_at")
                else None
            ),
            scope=credentials_dict.get("scope"),
        )

    async def refresh_integration_token(
        self,
        client_id: UUID,
        integration_id: UUID,
    ) -> OAuthTokens:
        """
        Refresh OAuth token for an integration.

        Args:
            client_id: The tenant/client ID.
            integration_id: The integration ID.

        Returns:
            New OAuth tokens.
        """
        integration = await self.get_available_integration(integration_id)
        user_integration = await self.get_user_integration(client_id, integration_id)
        current_tokens = await self.get_decrypted_credentials(client_id, integration_id)

        if not current_tokens.refresh_token:
            raise ValidationError("No refresh token available")

        # Create adapter and refresh token
        try:
            adapter = self._adapter_factory.get_adapter(
                integration,
                current_tokens.access_token,
                user_integration.external_account_id,
            )
            new_tokens = await adapter.refresh_token(
                current_tokens.refresh_token, integration.connection_config
            )
        except Exception as e:
            # Sanitize error to avoid credential exposure in logs
            sanitized_error = _sanitize_error_for_log(e)
            is_transient = _is_transient_error(e)

            logger.error(
                "Token refresh failed",
                extra={
                    "client_id": str(client_id),
                    "integration": integration.name,
                    "error": sanitized_error,
                    "error_type": type(e).__name__,
                    "is_transient": is_transient,
                },
            )

            # Only mark as ERROR for permanent failures, not transient network issues
            if not is_transient:
                user_integration.status = IntegrationStatus.ERROR
                await self._repo.update_user_integration(user_integration)

            raise IntegrationError(
                integration.name,
                f"Token refresh failed: {sanitized_error}",
            ) from e

        # Encrypt and store new credentials
        credentials_json = json.dumps(
            {
                "access_token": new_tokens.access_token,
                "refresh_token": new_tokens.refresh_token or current_tokens.refresh_token,
                "token_type": new_tokens.token_type,
                "expires_in": new_tokens.expires_in,
                "expires_at": new_tokens.expires_at.isoformat() if new_tokens.expires_at else None,
                "scope": new_tokens.scope,
            }
        )
        encrypted_creds, key_id = await self._encryption.encrypt(credentials_json.encode())

        user_integration.credentials_encrypted = encrypted_creds
        user_integration.credentials_key_id = key_id
        await self._repo.update_user_integration(user_integration)

        logger.info(
            "Integration token refreshed",
            extra={
                "client_id": str(client_id),
                "integration": integration.name,
            },
        )

        return new_tokens
