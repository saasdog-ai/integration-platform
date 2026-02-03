"""Mock adapters for external system testing."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.domain.entities import (
    AvailableIntegration,
    ExternalRecord,
    OAuthTokens,
)
from app.domain.interfaces import (
    AdapterFactoryInterface,
    IntegrationAdapterInterface,
)


class MockIntegrationAdapter(IntegrationAdapterInterface):
    """Mock integration adapter for testing."""

    def __init__(
        self,
        integration_name: str = "Mock Integration",
        records: dict[str, list[ExternalRecord]] | None = None,
    ) -> None:
        """
        Initialize mock adapter.

        Args:
            integration_name: Name of the integration being mocked.
            records: Pre-seeded records by entity type.
        """
        self._integration_name = integration_name
        self._records: dict[str, dict[str, ExternalRecord]] = {}

        # Seed initial records if provided
        if records:
            for entity_type, record_list in records.items():
                self._records[entity_type] = {r.id: r for r in record_list}

        # Track API calls for assertions
        self.authenticate_calls: list[tuple[str, str]] = []
        self.refresh_token_calls: list[str] = []
        self.fetch_records_calls: list[tuple[str, datetime | None, str | None, list[str] | None]] = []
        self.get_record_calls: list[tuple[str, str]] = []
        self.create_record_calls: list[tuple[str, dict]] = []
        self.update_record_calls: list[tuple[str, str, dict]] = []
        self.delete_record_calls: list[tuple[str, str]] = []

        # Configurable behavior
        self.should_fail_auth = False
        self.should_fail_refresh = False
        self.should_fail_fetch = False
        self.auth_error_message = "Authentication failed"
        self.refresh_error_message = "Token refresh failed"
        self.fetch_error_message = "Fetch failed"

    def seed_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
        version: str | None = None,
    ) -> ExternalRecord:
        """Seed a record for testing."""
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data=data,
            version=version or "1",
            updated_at=datetime.now(timezone.utc),
        )
        if entity_type not in self._records:
            self._records[entity_type] = {}
        self._records[entity_type][external_id] = record
        return record

    async def authenticate(self, auth_code: str, redirect_uri: str, oauth_config=None) -> OAuthTokens:
        """Mock OAuth authentication."""
        self.authenticate_calls.append((auth_code, redirect_uri))

        if self.should_fail_auth:
            raise Exception(self.auth_error_message)

        return OAuthTokens(
            access_token=f"mock_access_token_{uuid4().hex[:8]}",
            refresh_token=f"mock_refresh_token_{uuid4().hex[:8]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=3600),
        )

    async def refresh_token(self, refresh_token: str, oauth_config=None) -> OAuthTokens:
        """Mock token refresh."""
        self.refresh_token_calls.append(refresh_token)

        if self.should_fail_refresh:
            raise Exception(self.refresh_error_message)

        return OAuthTokens(
            access_token=f"mock_access_token_{uuid4().hex[:8]}",
            refresh_token=f"mock_refresh_token_{uuid4().hex[:8]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=3600),
        )

    async def fetch_records(
        self,
        entity_type: str,
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """Mock fetching records."""
        self.fetch_records_calls.append((entity_type, since, page_token, record_ids))

        if self.should_fail_fetch:
            raise Exception(self.fetch_error_message)

        entity_records = self._records.get(entity_type, {})
        records = list(entity_records.values())

        # Filter by specific record IDs if provided
        if record_ids:
            records = [r for r in records if r.id in record_ids]

        # Filter by since if provided
        if since:
            records = [r for r in records if r.updated_at and r.updated_at > since]

        # Simple pagination simulation
        page_size = 10
        if page_token:
            start_idx = int(page_token)
        else:
            start_idx = 0

        end_idx = start_idx + page_size
        page_records = records[start_idx:end_idx]

        next_token = None
        if end_idx < len(records):
            next_token = str(end_idx)

        return page_records, next_token

    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Mock getting a single record."""
        self.get_record_calls.append((entity_type, external_id))

        entity_records = self._records.get(entity_type, {})
        return entity_records.get(external_id)

    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Mock creating a record."""
        self.create_record_calls.append((entity_type, data))

        external_id = str(uuid4())
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data=data,
            version="1",
            updated_at=datetime.now(timezone.utc),
        )

        if entity_type not in self._records:
            self._records[entity_type] = {}
        self._records[entity_type][external_id] = record

        return record

    async def update_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Mock updating a record."""
        self.update_record_calls.append((entity_type, external_id, data))

        entity_records = self._records.get(entity_type, {})
        existing = entity_records.get(external_id)

        if not existing:
            raise Exception(f"Record not found: {entity_type}/{external_id}")

        new_version = str(int(existing.version or "0") + 1)
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data={**existing.data, **data},
            version=new_version,
            updated_at=datetime.now(timezone.utc),
        )
        entity_records[external_id] = record

        return record

    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Mock deleting a record."""
        self.delete_record_calls.append((entity_type, external_id))

        entity_records = self._records.get(entity_type, {})
        if external_id in entity_records:
            del entity_records[external_id]
            return True
        return False

    def reset(self) -> None:
        """Reset all tracked calls and state (for test isolation)."""
        self._records.clear()
        self.authenticate_calls.clear()
        self.refresh_token_calls.clear()
        self.fetch_records_calls.clear()
        self.get_record_calls.clear()
        self.create_record_calls.clear()
        self.update_record_calls.clear()
        self.delete_record_calls.clear()
        self.should_fail_auth = False
        self.should_fail_refresh = False
        self.should_fail_fetch = False


class MockAdapterFactory(AdapterFactoryInterface):
    """Mock adapter factory for testing."""

    def __init__(self) -> None:
        self._adapters: dict[str, MockIntegrationAdapter] = {}

    def register_adapter(
        self, integration_name: str, adapter: MockIntegrationAdapter
    ) -> None:
        """Register a mock adapter for an integration."""
        self._adapters[integration_name] = adapter

    def get_adapter(
        self,
        integration: AvailableIntegration,
        access_token: str,
        external_account_id: str | None = None,
    ) -> IntegrationAdapterInterface:
        """Get mock adapter for integration."""
        if integration.name in self._adapters:
            return self._adapters[integration.name]

        # Create a new mock adapter if not registered
        adapter = MockIntegrationAdapter(integration_name=integration.name)
        self._adapters[integration.name] = adapter
        return adapter

    def get_mock_adapter(self, integration_name: str) -> MockIntegrationAdapter | None:
        """Get the mock adapter for assertions in tests."""
        return self._adapters.get(integration_name)

    def clear(self) -> None:
        """Clear all registered adapters."""
        self._adapters.clear()
