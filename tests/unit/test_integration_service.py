"""Tests for integration service."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.entities import (
    AvailableIntegration,
    OAuthConfig,
    UserIntegration,
)
from app.domain.enums import IntegrationStatus
from app.services.integration_service import IntegrationService
from tests.mocks.adapters import MockIntegrationAdapter
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.repositories import MockIntegrationRepository


@pytest.fixture
def mock_repo():
    """Create mock integration repository."""
    repo = MockIntegrationRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_encryption():
    """Create mock encryption service."""
    service = MockEncryptionService()
    yield service
    service.reset()


@pytest.fixture
def mock_adapter_factory():
    """Create mock adapter factory."""
    factory = MagicMock()
    return factory


@pytest.fixture
def service(mock_repo, mock_encryption, mock_adapter_factory):
    """Create integration service with mocks."""
    return IntegrationService(
        integration_repo=mock_repo,
        encryption_service=mock_encryption,
        adapter_factory=mock_adapter_factory,
    )


@pytest.fixture
def sample_client_id():
    """Sample client ID."""
    return uuid4()


@pytest.fixture
def sample_integration(mock_repo) -> AvailableIntegration:
    """Create a sample available integration."""
    return mock_repo.seed_available_integration(
        name="QuickBooks Online",
        type="erp",
        supported_entities=["bill", "invoice", "vendor"],
        oauth_config=OAuthConfig(
            authorization_url="https://oauth.example.com/authorize",
            token_url="https://oauth.example.com/token",
            scopes=["read", "write"],
        ),
    )


@pytest.fixture
def sample_user_integration(sample_client_id, sample_integration) -> UserIntegration:
    """Create a sample user integration."""
    now = datetime.now(UTC)
    return UserIntegration(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_integration.id,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=b"encrypted_creds",
        credentials_key_id="test-key-id",
        external_account_id="ext-account-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
    )


class TestIntegrationServiceBasics:
    """Test basic integration service operations."""

    async def test_get_available_integrations(self, service, sample_integration):
        """Test getting all available integrations."""
        integrations = await service.get_available_integrations()
        assert len(integrations) == 1
        assert integrations[0].name == "QuickBooks Online"

    async def test_get_available_integrations_active_only(self, service, mock_repo):
        """Test getting only active integrations."""
        # Add an inactive integration
        mock_repo.seed_available_integration(
            name="Inactive Integration",
            type="crm",
            supported_entities=["contact"],
            is_active=False,
        )
        mock_repo.seed_available_integration(
            name="Active Integration",
            type="erp",
            supported_entities=["bill"],
            is_active=True,
        )

        active_integrations = await service.get_available_integrations(active_only=True)
        all_integrations = await service.get_available_integrations(active_only=False)

        assert len(active_integrations) == 1
        assert len(all_integrations) == 2

    async def test_get_available_integration(self, service, sample_integration):
        """Test getting a specific available integration."""
        integration = await service.get_available_integration(sample_integration.id)
        assert integration.id == sample_integration.id
        assert integration.name == "QuickBooks Online"

    async def test_get_available_integration_not_found(self, service):
        """Test getting non-existent integration raises error."""
        with pytest.raises(NotFoundError):
            await service.get_available_integration(uuid4())

    async def test_get_user_integrations(
        self, service, mock_repo, sample_client_id, sample_user_integration
    ):
        """Test getting user's integrations."""
        await mock_repo.create_user_integration(sample_user_integration)

        integrations = await service.get_user_integrations(sample_client_id)
        assert len(integrations) == 1
        assert integrations[0].client_id == sample_client_id

    async def test_get_user_integration(
        self, service, mock_repo, sample_client_id, sample_user_integration, sample_integration
    ):
        """Test getting a specific user integration."""
        await mock_repo.create_user_integration(sample_user_integration)

        integration = await service.get_user_integration(sample_client_id, sample_integration.id)
        assert integration.id == sample_user_integration.id

    async def test_get_user_integration_not_found(
        self, service, sample_client_id, sample_integration
    ):
        """Test getting non-existent user integration raises error."""
        with pytest.raises(NotFoundError):
            await service.get_user_integration(sample_client_id, sample_integration.id)


class TestOAuthFlow:
    """Test OAuth connection flow."""

    async def test_get_oauth_authorization_url(self, service, sample_client_id, sample_integration):
        """Test generating OAuth authorization URL."""
        auth_url = await service.get_oauth_authorization_url(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            redirect_uri="https://app.example.com/callback",
            state="csrf-token-123",
        )

        assert "oauth.example.com/authorize" in auth_url
        # URL-encoded redirect_uri for security
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in auth_url
        assert "state=csrf-token-123" in auth_url
        # Scope with space encoded as + (urlencode default)
        assert "scope=read+write" in auth_url

    async def test_get_oauth_authorization_url_no_oauth_config(
        self, service, mock_repo, sample_client_id
    ):
        """Test error when integration doesn't support OAuth."""
        integration = mock_repo.seed_available_integration(
            name="No OAuth Integration",
            type="erp",
            supported_entities=["bill"],
            oauth_config=None,
        )

        with pytest.raises(ValidationError):
            await service.get_oauth_authorization_url(
                client_id=sample_client_id,
                integration_id=integration.id,
                redirect_uri="https://app.example.com/callback",
            )

    async def test_get_oauth_authorization_url_already_connected(
        self, service, mock_repo, sample_client_id, sample_integration, sample_user_integration
    ):
        """Test error when integration is already connected."""
        await mock_repo.create_user_integration(sample_user_integration)

        with pytest.raises(ConflictError):
            await service.get_oauth_authorization_url(
                client_id=sample_client_id,
                integration_id=sample_integration.id,
                redirect_uri="https://app.example.com/callback",
            )

    async def test_complete_oauth_callback(
        self,
        service,
        mock_repo,
        mock_encryption,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
    ):
        """Test completing OAuth callback."""
        # Setup mock adapter
        mock_adapter = MockIntegrationAdapter()
        mock_adapter_factory.get_adapter.return_value = mock_adapter

        # Complete OAuth
        user_integration = await service.complete_oauth_callback(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            auth_code="auth_code_123",
            redirect_uri="https://app.example.com/callback",
        )

        assert user_integration.status == IntegrationStatus.CONNECTED
        assert user_integration.credentials_encrypted is not None
        assert user_integration.credentials_key_id is not None

        # Verify encryption was called
        assert len(mock_encryption.encrypt_calls) == 1

    async def test_complete_oauth_callback_update_existing(
        self,
        service,
        mock_repo,
        mock_adapter_factory,
        sample_client_id,
        sample_integration,
    ):
        """Test completing OAuth callback updates existing integration."""
        # Create existing pending integration
        now = datetime.now(UTC)
        existing = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            status=IntegrationStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        await mock_repo.create_user_integration(existing)

        # Setup mock adapter
        mock_adapter = MockIntegrationAdapter()
        mock_adapter_factory.get_adapter.return_value = mock_adapter

        # Complete OAuth
        user_integration = await service.complete_oauth_callback(
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            auth_code="auth_code_123",
            redirect_uri="https://app.example.com/callback",
        )

        assert user_integration.id == existing.id
        assert user_integration.status == IntegrationStatus.CONNECTED


class TestDisconnect:
    """Test disconnecting integrations."""

    async def test_disconnect_integration(
        self, service, mock_repo, sample_client_id, sample_integration, sample_user_integration
    ):
        """Test disconnecting an integration."""
        await mock_repo.create_user_integration(sample_user_integration)

        result = await service.disconnect_integration(sample_client_id, sample_integration.id)

        assert result is True

        # Verify status updated
        updated = await mock_repo.get_user_integration(sample_client_id, sample_integration.id)
        assert updated.status == IntegrationStatus.REVOKED
        assert updated.credentials_encrypted is None

    async def test_disconnect_integration_not_found(
        self, service, sample_client_id, sample_integration
    ):
        """Test disconnecting non-existent integration raises error."""
        with pytest.raises(NotFoundError):
            await service.disconnect_integration(sample_client_id, sample_integration.id)


class TestCredentialManagement:
    """Test credential encryption/decryption."""

    async def test_get_decrypted_credentials(
        self, service, mock_repo, mock_encryption, sample_client_id, sample_integration
    ):
        """Test getting decrypted credentials."""
        # Create user integration with encrypted credentials
        now = datetime.now(UTC)
        creds_json = json.dumps(
            {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "expires_at": now.isoformat(),
                "scope": "read write",
            }
        )
        encrypted, key_id = await mock_encryption.encrypt(creds_json.encode())

        user_integration = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            status=IntegrationStatus.CONNECTED,
            credentials_encrypted=encrypted,
            credentials_key_id=key_id,
            created_at=now,
            updated_at=now,
        )
        await mock_repo.create_user_integration(user_integration)

        # Get decrypted credentials
        tokens = await service.get_decrypted_credentials(sample_client_id, sample_integration.id)

        assert tokens.access_token == "test_access_token"
        assert tokens.refresh_token == "test_refresh_token"

    async def test_get_decrypted_credentials_not_connected(
        self, service, mock_repo, sample_client_id, sample_integration
    ):
        """Test error when integration not connected."""
        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            status=IntegrationStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        await mock_repo.create_user_integration(user_integration)

        with pytest.raises(ValidationError):
            await service.get_decrypted_credentials(sample_client_id, sample_integration.id)

    async def test_get_decrypted_credentials_no_credentials(
        self, service, mock_repo, sample_client_id, sample_integration
    ):
        """Test error when no credentials stored."""
        now = datetime.now(UTC)
        user_integration = UserIntegration(
            id=uuid4(),
            client_id=sample_client_id,
            integration_id=sample_integration.id,
            status=IntegrationStatus.CONNECTED,
            credentials_encrypted=None,
            credentials_key_id=None,
            created_at=now,
            updated_at=now,
        )
        await mock_repo.create_user_integration(user_integration)

        with pytest.raises(ValidationError):
            await service.get_decrypted_credentials(sample_client_id, sample_integration.id)
