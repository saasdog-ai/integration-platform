"""Unit tests for adapters."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.infrastructure.adapters.mock.client import MockAdapter
from tests.mocks.adapters import MockAdapterFactory, MockIntegrationAdapter


class TestMockAdapter:
    """Tests for MockAdapter."""

    @pytest.fixture
    def adapter(self) -> MockAdapter:
        """Create mock adapter."""
        return MockAdapter(integration_name="Test Integration")

    @pytest.mark.asyncio
    async def test_authenticate(self, adapter: MockAdapter):
        """Test mock authentication."""
        tokens = await adapter.authenticate("auth_code", "redirect_uri")

        assert tokens.access_token is not None
        assert tokens.refresh_token is not None
        assert tokens.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_refresh_token(self, adapter: MockAdapter):
        """Test mock token refresh."""
        tokens = await adapter.refresh_token("old_refresh_token")

        assert tokens.access_token is not None
        assert "mock_access" in tokens.access_token

    @pytest.mark.asyncio
    async def test_create_record(self, adapter: MockAdapter):
        """Test creating a record."""
        record = await adapter.create_record("bill", {"amount": 100})

        assert record.id is not None
        assert record.entity_type == "bill"
        assert record.data == {"amount": 100}

    @pytest.mark.asyncio
    async def test_fetch_records(self, adapter: MockAdapter):
        """Test fetching records."""
        # Seed some records
        adapter.seed_records("bill", count=5)

        records, next_token = await adapter.fetch_records("bill")

        assert len(records) == 5
        assert next_token is None  # Less than page size

    @pytest.mark.asyncio
    async def test_fetch_records_pagination(self, adapter: MockAdapter):
        """Test fetch records with pagination."""
        adapter.seed_records("invoice", count=15)

        records1, next_token = await adapter.fetch_records("invoice")
        assert len(records1) == 10
        assert next_token is not None

        records2, next_token2 = await adapter.fetch_records("invoice", page_token=next_token)
        assert len(records2) == 5
        assert next_token2 is None

    @pytest.mark.asyncio
    async def test_get_record(self, adapter: MockAdapter):
        """Test getting a single record."""
        created = await adapter.create_record("vendor", {"name": "Test"})
        retrieved = await adapter.get_record("vendor", created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_update_record(self, adapter: MockAdapter):
        """Test updating a record."""
        created = await adapter.create_record("bill", {"amount": 100})
        updated = await adapter.update_record("bill", created.id, {"amount": 200})

        assert updated.data["amount"] == 200
        assert int(updated.version) > int(created.version)

    @pytest.mark.asyncio
    async def test_delete_record(self, adapter: MockAdapter):
        """Test deleting a record."""
        created = await adapter.create_record("bill", {"amount": 100})
        deleted = await adapter.delete_record("bill", created.id)

        assert deleted is True

        retrieved = await adapter.get_record("bill", created.id)
        assert retrieved is None


class TestMockIntegrationAdapter:
    """Tests for MockIntegrationAdapter from test mocks."""

    @pytest.fixture
    def adapter(self) -> MockIntegrationAdapter:
        """Create mock adapter."""
        adapter = MockIntegrationAdapter()
        yield adapter
        adapter.reset()

    @pytest.mark.asyncio
    async def test_tracks_api_calls(self, adapter: MockIntegrationAdapter):
        """Test that API calls are tracked."""
        await adapter.authenticate("code", "redirect")
        await adapter.fetch_records("bill")
        await adapter.create_record("bill", {"amount": 100})

        assert len(adapter.authenticate_calls) == 1
        assert len(adapter.fetch_records_calls) == 1
        assert len(adapter.create_record_calls) == 1

    @pytest.mark.asyncio
    async def test_configurable_auth_failure(self, adapter: MockIntegrationAdapter):
        """Test configurable authentication failure."""
        adapter.should_fail_auth = True
        adapter.auth_error_message = "Custom auth error"

        with pytest.raises(Exception) as exc_info:
            await adapter.authenticate("code", "redirect")

        assert "Custom auth error" in str(exc_info.value)


class TestMockAdapterFactory:
    """Tests for MockAdapterFactory."""

    @pytest.fixture
    def factory(self) -> MockAdapterFactory:
        """Create mock adapter factory."""
        factory = MockAdapterFactory()
        yield factory
        factory.clear()

    def test_get_adapter_creates_new(self, factory: MockAdapterFactory):
        """Test that get_adapter creates a new adapter if not registered."""
        from app.domain.entities import AvailableIntegration

        now = datetime.now(UTC)
        integration = AvailableIntegration(
            id=uuid4(),
            name="New Integration",
            type="erp",
            supported_entities=["bill"],
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        adapter = factory.get_adapter(integration, "token")
        assert adapter is not None

    def test_register_and_get_adapter(self, factory: MockAdapterFactory):
        """Test registering and getting an adapter."""
        from app.domain.entities import AvailableIntegration

        now = datetime.now(UTC)
        mock_adapter = MockIntegrationAdapter(integration_name="Test")
        factory.register_adapter("Test", mock_adapter)

        integration = AvailableIntegration(
            id=uuid4(),
            name="Test",
            type="erp",
            supported_entities=["bill"],
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        adapter = factory.get_adapter(integration, "token")
        assert adapter is mock_adapter
