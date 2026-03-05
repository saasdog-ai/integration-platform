"""QuickBooks Online adapter — real HTTP calls to the QBO API."""

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import ConnectionConfig, ExternalRecord, OAuthTokens
from app.domain.interfaces import IntegrationAdapterInterface
from app.infrastructure.adapters.http_client import get_http_client
from app.integrations.quickbooks.constants import (
    QBO_ENTITY_NAMES,
    QBO_MAX_RESULTS,
    QBO_TOKEN_URL,
)

logger = get_logger(__name__)


class QuickBooksAdapter(IntegrationAdapterInterface):
    """QuickBooks Online integration adapter.

    Makes real HTTP calls to the QBO v3 REST API.

    API reference:
    - Sandbox: https://sandbox-quickbooks.api.intuit.com/v3/company/{realmId}/...
    - Production: https://quickbooks.api.intuit.com/v3/company/{realmId}/...
    - Query: GET .../query?query=select * from Vendor STARTPOSITION 1 MAXRESULTS 1000
    - Read:  GET .../{entity}/{id}
    - Create/Update: POST .../{entity} (update requires Id + SyncToken in body)
    - Auth header: Authorization: Bearer {access_token}
    - Response envelope: {"QueryResponse": {"Vendor": [...]}} or {"Vendor": {...}}
    """

    def __init__(
        self,
        integration_name: str = "QuickBooks Online",
        access_token: str = "",
        external_account_id: str | None = None,
    ) -> None:
        self._integration_name = integration_name
        self._access_token = access_token
        self._realm_id = external_account_id

        settings = get_settings()
        self._base_url = settings.qbo_base_url
        self._company_url = f"{self._base_url}/v3/company/{self._realm_id}"

        logger.info(
            "QuickBooks adapter initialized",
            extra={
                "realm_id": self._realm_id,
                "base_url": self._base_url,
            },
        )

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _qbo_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the QBO API.

        Raises on non-2xx status or QBO Fault responses.
        """
        url = f"{self._company_url}{path}"

        async with get_http_client() as client:
            response = await client.request(
                method,
                url,
                headers=self._auth_headers(),
                params=params,
                json=json_body,
            )

        data = response.json()

        # Check for QBO Fault envelope
        if "Fault" in data:
            fault = data["Fault"]
            errors = fault.get("Error", [{}])
            msg = errors[0].get("Message", "Unknown QBO error") if errors else "Unknown QBO error"
            detail = errors[0].get("Detail", "") if errors else ""
            code = errors[0].get("code", "") if errors else ""
            logger.error(
                "QBO API error",
                extra={
                    "fault_type": fault.get("type"),
                    "code": code,
                    "error_message": msg,
                    "detail": detail,
                    "url": url,
                },
            )
            raise Exception(f"QBO API error [{code}]: {msg} — {detail}")

        # Raise on HTTP errors not caught by Fault
        response.raise_for_status()

        return data

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    async def authenticate(
        self, auth_code: str, redirect_uri: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
        """Exchange authorization code for access/refresh tokens."""
        client_id = connection_config.client_id if connection_config else None
        client_secret = connection_config.client_secret if connection_config else None

        if not client_id or not client_secret:
            raise Exception(
                "QBO client_id and client_secret must be configured in the integration's OAuth config"
            )

        # QBO uses HTTP Basic auth for the token endpoint
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        async with get_http_client() as client:
            response = await client.post(
                QBO_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": redirect_uri,
                },
            )

        if not response.is_success:
            logger.error(
                "QBO token exchange failed",
                extra={
                    "status_code": response.status_code,
                    "redirect_uri": redirect_uri,
                },
            )
            raise Exception(f"QBO token exchange failed ({response.status_code})")

        token_data = response.json()

        expires_in = token_data.get("expires_in", 3600)
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scope=token_data.get("scope"),
        )

    async def refresh_token(
        self, refresh_token: str, connection_config: ConnectionConfig | None = None
    ) -> OAuthTokens:
        """Refresh an expired access token."""
        client_id = connection_config.client_id if connection_config else None
        client_secret = connection_config.client_secret if connection_config else None

        if not client_id or not client_secret:
            raise Exception(
                "QBO client_id and client_secret must be configured in the integration's OAuth config"
            )

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        async with get_http_client() as client:
            response = await client.post(
                QBO_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        response.raise_for_status()
        token_data = response.json()

        expires_in = token_data.get("expires_in", 3600)
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", refresh_token),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scope=token_data.get("scope"),
        )

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def fetch_records(
        self,
        entity_type: str,
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """Fetch records from QBO using the query API with pagination.

        Uses QBO's SQL-like query syntax:
            SELECT * FROM Vendor STARTPOSITION 1 MAXRESULTS 1000
            SELECT * FROM Vendor WHERE MetaData.LastUpdatedTime > '2024-01-01'
        """
        qbo_entity = QBO_ENTITY_NAMES.get(entity_type)
        if not qbo_entity:
            logger.warning(
                f"Unknown entity type for QBO query: {entity_type}",
                extra={"entity_type": entity_type},
            )
            return [], None

        # Build query
        start_position = int(page_token) if page_token else 1
        query = f"SELECT * FROM {qbo_entity}"

        conditions: list[str] = []
        if since:
            conditions.append(f"MetaData.LastUpdatedTime > '{since.isoformat()}'")
        if record_ids:
            id_list = ",".join(f"'{rid}'" for rid in record_ids)
            conditions.append(f"Id IN ({id_list})")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" STARTPOSITION {start_position} MAXRESULTS {QBO_MAX_RESULTS}"

        logger.debug(
            "QBO query",
            extra={"entity_type": entity_type, "query": query},
        )

        data = await self._qbo_request(
            "GET",
            "/query",
            params={"query": query},
        )

        # Parse QueryResponse envelope
        query_response = data.get("QueryResponse", {})
        raw_records = query_response.get(qbo_entity, [])
        total_count = query_response.get("totalCount", len(raw_records))

        records = [self._to_external_record(entity_type, r) for r in raw_records]

        # Determine next page token
        next_position = start_position + len(raw_records)
        next_token = str(next_position) if next_position <= total_count else None

        logger.info(
            f"Fetched {len(records)} {qbo_entity} records from QBO",
            extra={
                "entity_type": entity_type,
                "start_position": start_position,
                "fetched": len(records),
                "total_count": total_count,
            },
        )

        return records, next_token

    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Get a single record by ID from QBO."""
        qbo_entity = QBO_ENTITY_NAMES.get(entity_type)
        if not qbo_entity:
            return None

        try:
            data = await self._qbo_request(
                "GET",
                f"/{qbo_entity.lower()}/{external_id}",
            )

            raw = data.get(qbo_entity)
            if not raw:
                return None

            return self._to_external_record(entity_type, raw)

        except Exception as e:
            logger.warning(
                f"Failed to get {qbo_entity} {external_id} from QBO",
                extra={"error": str(e)},
            )
            return None

    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Create a record in QBO."""
        qbo_entity = QBO_ENTITY_NAMES.get(entity_type)
        if not qbo_entity:
            raise Exception(f"Unknown entity type: {entity_type}")

        response_data = await self._qbo_request(
            "POST",
            f"/{qbo_entity.lower()}",
            json_body=data,
        )

        raw = response_data.get(qbo_entity)
        if not raw:
            raise Exception(f"QBO create response missing {qbo_entity} key")

        record = self._to_external_record(entity_type, raw)

        logger.info(
            f"Created {qbo_entity} in QBO",
            extra={
                "entity_type": entity_type,
                "external_id": record.id,
            },
        )

        return record

    async def update_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Update a record in QBO.

        QBO updates require the current SyncToken for optimistic concurrency.
        If the caller doesn't supply Id/SyncToken, we fetch the current record first.
        """
        qbo_entity = QBO_ENTITY_NAMES.get(entity_type)
        if not qbo_entity:
            raise Exception(f"Unknown entity type: {entity_type}")

        # Ensure Id is in the payload
        if "Id" not in data:
            data["Id"] = external_id

        # Ensure SyncToken is in the payload (QBO requires it for updates)
        if "SyncToken" not in data:
            current = await self.get_record(entity_type, external_id)
            if not current:
                raise Exception(f"QBO {qbo_entity} not found: {external_id}")
            data["SyncToken"] = current.data.get("SyncToken", "0")

        response_data = await self._qbo_request(
            "POST",
            f"/{qbo_entity.lower()}",
            json_body=data,
        )

        raw = response_data.get(qbo_entity)
        if not raw:
            raise Exception(f"QBO update response missing {qbo_entity} key")

        record = self._to_external_record(entity_type, raw)

        logger.info(
            f"Updated {qbo_entity} in QBO",
            extra={
                "entity_type": entity_type,
                "external_id": record.id,
            },
        )

        return record

    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Delete (deactivate) a record in QBO.

        QBO uses soft deletes for most entities — set Active=false.
        Some entities (Bill, Invoice) support void operations instead.
        """
        qbo_entity = QBO_ENTITY_NAMES.get(entity_type)
        if not qbo_entity:
            return False

        try:
            # Fetch current record to get SyncToken
            current = await self.get_record(entity_type, external_id)
            if not current:
                return False

            # For most entities, set Active=false (soft delete)
            payload = {
                "Id": external_id,
                "SyncToken": current.data.get("SyncToken", "0"),
                "Active": False,
            }

            await self._qbo_request(
                "POST",
                f"/{qbo_entity.lower()}",
                json_body=payload,
            )

            logger.info(
                f"Deactivated {qbo_entity} in QBO",
                extra={"external_id": external_id},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to delete {qbo_entity} {external_id}",
                extra={"error": str(e)},
            )
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_external_record(entity_type: str, raw: dict[str, Any]) -> ExternalRecord:
        """Convert a raw QBO API response dict to an ExternalRecord."""
        meta = raw.get("MetaData") or {}
        updated_at = None
        if meta.get("LastUpdatedTime"):
            try:
                updated_at = datetime.fromisoformat(meta["LastUpdatedTime"])
            except (ValueError, TypeError):
                pass

        return ExternalRecord(
            id=str(raw.get("Id", "")),
            entity_type=entity_type,
            data=raw,
            version=raw.get("SyncToken"),
            updated_at=updated_at,
        )
