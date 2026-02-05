"""Mock adapter for development and testing."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.logging import get_logger
from app.domain.entities import ConnectionConfig, ExternalRecord, OAuthTokens
from app.domain.interfaces import IntegrationAdapterInterface

logger = get_logger(__name__)


class MockAdapter(IntegrationAdapterInterface):
    """
    Mock integration adapter for development and testing.

    This adapter simulates an external integration without making real API calls.
    """

    def __init__(
        self,
        integration_name: str = "Mock Integration",
        access_token: str = "",
        external_account_id: str | None = None,
    ) -> None:
        """
        Initialize mock adapter.

        Args:
            integration_name: Name of the integration being mocked.
            access_token: OAuth access token (unused in mock).
            external_account_id: External account ID (unused in mock).
        """
        self._integration_name = integration_name
        self._access_token = access_token
        self._external_account_id = external_account_id

        # In-memory storage for mock records
        self._records: dict[str, dict[str, ExternalRecord]] = {}

        logger.debug(
            f"Initialized mock adapter for {integration_name}",
            extra={"external_account_id": external_account_id},
        )

    async def authenticate(
        self, auth_code: str, redirect_uri: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
        """Mock OAuth authentication."""
        logger.info(
            "Mock authentication",
            extra={
                "integration": self._integration_name,
                "auth_code_length": len(auth_code),
            },
        )

        return OAuthTokens(
            access_token=f"mock_access_{uuid4().hex[:16]}",
            refresh_token=f"mock_refresh_{uuid4().hex[:16]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(UTC),
        )

    async def refresh_token(
        self, refresh_token: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
        """Mock token refresh."""
        logger.info(
            "Mock token refresh",
            extra={"integration": self._integration_name},
        )

        return OAuthTokens(
            access_token=f"mock_access_{uuid4().hex[:16]}",
            refresh_token=f"mock_refresh_{uuid4().hex[:16]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(UTC),
        )

    async def fetch_records(
        self,
        entity_type: str,
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """Mock fetching records."""
        logger.info(
            "Mock fetch records",
            extra={
                "integration": self._integration_name,
                "entity_type": entity_type,
                "since": since.isoformat() if since else None,
                "record_ids": record_ids,
            },
        )

        entity_records = self._records.get(entity_type, {})
        records = list(entity_records.values())

        # Filter by specific record IDs if provided
        if record_ids:
            records = [r for r in records if r.id in record_ids]

        # Filter by since if provided
        if since:
            records = [r for r in records if r.updated_at and r.updated_at > since]

        # Simple pagination
        page_size = 10
        start_idx = int(page_token) if page_token else 0
        end_idx = start_idx + page_size
        page_records = records[start_idx:end_idx]

        next_token = str(end_idx) if end_idx < len(records) else None

        return page_records, next_token

    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Mock getting a single record."""
        logger.debug(
            "Mock get record",
            extra={
                "integration": self._integration_name,
                "entity_type": entity_type,
                "external_id": external_id,
            },
        )

        entity_records = self._records.get(entity_type, {})
        return entity_records.get(external_id)

    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Mock creating a record."""
        logger.info(
            "Mock create record",
            extra={
                "integration": self._integration_name,
                "entity_type": entity_type,
            },
        )

        external_id = f"mock_{uuid4().hex[:8]}"
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data=data,
            version="1",
            updated_at=datetime.now(UTC),
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
        logger.info(
            "Mock update record",
            extra={
                "integration": self._integration_name,
                "entity_type": entity_type,
                "external_id": external_id,
            },
        )

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
            updated_at=datetime.now(UTC),
        )
        entity_records[external_id] = record

        return record

    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Mock deleting a record."""
        logger.info(
            "Mock delete record",
            extra={
                "integration": self._integration_name,
                "entity_type": entity_type,
                "external_id": external_id,
            },
        )

        entity_records = self._records.get(entity_type, {})
        if external_id in entity_records:
            del entity_records[external_id]
            return True
        return False

    def seed_records(self, entity_type: str, count: int = 10) -> list[ExternalRecord]:
        """Seed mock records for testing."""
        records = []
        now = datetime.now(UTC)

        if entity_type not in self._records:
            self._records[entity_type] = {}

        for i in range(count):
            external_id = f"mock_{entity_type}_{i + 1}"
            record = ExternalRecord(
                id=external_id,
                entity_type=entity_type,
                data={
                    "name": f"Mock {entity_type} {i + 1}",
                    "created": now.isoformat(),
                },
                version="1",
                updated_at=now,
            )
            self._records[entity_type][external_id] = record
            records.append(record)

        return records
