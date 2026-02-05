"""Pytest fixtures for testing."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.domain.entities import AvailableIntegration, SyncJob, UserIntegration
from app.domain.enums import IntegrationStatus, SyncJobStatus, SyncJobTrigger, SyncJobType
from app.infrastructure.queue.memory_queue import InMemoryQueue
from tests.mocks.adapters import MockAdapterFactory, MockIntegrationAdapter
from tests.mocks.encryption import MockEncryptionService
from tests.mocks.feature_flags import MockFeatureFlagService
from tests.mocks.repositories import (
    MockIntegrationRepository,
    MockIntegrationStateRepository,
    MockSyncJobRepository,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        app_env="development",
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        auth_enabled=False,
        cloud_provider=None,
    )


@pytest.fixture
def mock_integration_repo() -> MockIntegrationRepository:
    """Create a mock integration repository."""
    repo = MockIntegrationRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_sync_job_repo() -> MockSyncJobRepository:
    """Create a mock sync job repository."""
    repo = MockSyncJobRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_state_repo() -> MockIntegrationStateRepository:
    """Create a mock integration state repository."""
    repo = MockIntegrationStateRepository()
    yield repo
    repo.clear()


@pytest.fixture
def mock_queue() -> InMemoryQueue:
    """Create an in-memory queue for testing."""
    queue = InMemoryQueue()
    yield queue


@pytest.fixture
def mock_encryption() -> MockEncryptionService:
    """Create a mock encryption service."""
    service = MockEncryptionService()
    yield service
    service.reset()


@pytest.fixture
def mock_adapter_factory() -> MockAdapterFactory:
    """Create a mock adapter factory."""
    factory = MockAdapterFactory()
    yield factory
    factory.clear()


@pytest.fixture
def mock_feature_flags() -> MockFeatureFlagService:
    """Create a mock feature flag service."""
    service = MockFeatureFlagService()
    yield service
    service.reset()


@pytest.fixture
def mock_adapter() -> MockIntegrationAdapter:
    """Create a mock integration adapter."""
    adapter = MockIntegrationAdapter()
    yield adapter
    adapter.reset()


@pytest.fixture
def sample_client_id() -> Any:
    """Generate a sample client ID."""
    return uuid4()


@pytest.fixture
def sample_available_integration(
    mock_integration_repo: MockIntegrationRepository,
) -> AvailableIntegration:
    """Create a sample available integration."""
    return mock_integration_repo.seed_available_integration(
        name="QuickBooks Online",
        type="erp",
        supported_entities=["bill", "invoice", "vendor", "chart_of_accounts"],
    )


@pytest.fixture
def sample_user_integration(
    sample_client_id: Any,
    sample_available_integration: AvailableIntegration,
) -> UserIntegration:
    """Create a sample user integration."""
    now = datetime.now(UTC)
    return UserIntegration(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_available_integration.id,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=b"encrypted_credentials",
        credentials_key_id="test-key",
        external_account_id="ext-account-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
        integration=sample_available_integration,
    )


@pytest.fixture
def sample_sync_job(
    sample_client_id: Any,
    sample_available_integration: AvailableIntegration,
) -> SyncJob:
    """Create a sample sync job."""
    now = datetime.now(UTC)
    return SyncJob(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_available_integration.id,
        job_type=SyncJobType.FULL_SYNC,
        status=SyncJobStatus.PENDING,
        triggered_by=SyncJobTrigger.USER,
        created_at=now,
        updated_at=now,
    )


# Integration test fixtures (require real database)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for API testing."""
    # Import here to avoid import errors when app isn't fully set up
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
