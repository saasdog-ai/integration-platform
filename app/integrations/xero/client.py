"""Xero adapter — real HTTP calls to the Xero API."""

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import ConnectionConfig, ExternalRecord, OAuthTokens
from app.domain.interfaces import IntegrationAdapterInterface
from app.infrastructure.adapters.http_client import get_http_client
from app.integrations.xero.constants import (
    XERO_API_BASE_URL,
    XERO_CONNECTIONS_URL,
    XERO_ENTITY_ENDPOINTS,
    XERO_ENTITY_ID_FIELDS,
    XERO_PAGE_SIZE,
    XERO_TOKEN_URL,
)
from app.integrations.xero.mappers import _get_where_filter

logger = get_logger(__name__)


class XeroAdapter(IntegrationAdapterInterface):
    """Xero integration adapter.

    Makes real HTTP calls to the Xero API v2.0.

    API reference:
    - Base: https://api.xero.com/api.xro/2.0
    - Contacts: GET /Contacts?where=IsSupplier==true&page=1
    - Invoices: GET /Invoices?where=Type=="ACCPAY"&page=1
    - Auth header: Authorization: Bearer {access_token}
    - Tenant header: Xero-Tenant-Id: {tenant_id}
    - Response envelope: {"Contacts": [...]} or {"Invoices": [...]}
    """

    def __init__(
        self,
        integration_name: str = "Xero",
        access_token: str = "",
        external_account_id: str | None = None,
    ) -> None:
        self._integration_name = integration_name
        self._access_token = access_token
        self._tenant_id = external_account_id

        logger.info(
            "Xero adapter initialized",
            extra={
                "tenant_id": self._tenant_id,
            },
        )

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._tenant_id:
            headers["Xero-Tenant-Id"] = self._tenant_id
        return headers

    async def _xero_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Xero API.

        Raises on non-2xx status or Xero error responses.
        """
        url = f"{XERO_API_BASE_URL}{path}"
        request_headers = headers or self._auth_headers()

        async with get_http_client() as client:
            response = await client.request(
                method,
                url,
                headers=request_headers,
                params=params,
                json=json_body,
            )

        # Xero returns 2xx for success
        if not response.is_success:
            error_body = response.text
            logger.error(
                "Xero API error",
                extra={
                    "status_code": response.status_code,
                    "response_body": error_body[:500],
                    "url": url,
                },
            )
            raise Exception(
                f"Xero API error ({response.status_code}): {error_body[:200]}"
            )

        return response.json()

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
            settings = get_settings()
            client_id = client_id or settings.xero_client_id
            client_secret = client_secret or settings.xero_client_secret

        if not client_id or not client_secret:
            raise Exception(
                "Xero client_id and client_secret must be configured"
            )

        # Xero uses HTTP Basic auth for the token endpoint
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        async with get_http_client() as client:
            response = await client.post(
                XERO_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": redirect_uri,
                },
            )

        if not response.is_success:
            error_body = response.text
            logger.error(
                "Xero token exchange failed",
                extra={
                    "status_code": response.status_code,
                    "response_body": error_body,
                    "redirect_uri": redirect_uri,
                },
            )
            raise Exception(f"Xero token exchange failed ({response.status_code}): {error_body}")

        token_data = response.json()

        expires_in = token_data.get("expires_in", 1800)  # Xero default 30 min
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
            settings = get_settings()
            client_id = client_id or settings.xero_client_id
            client_secret = client_secret or settings.xero_client_secret

        if not client_id or not client_secret:
            raise Exception(
                "Xero client_id and client_secret must be configured"
            )

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        async with get_http_client() as client:
            response = await client.post(
                XERO_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

        response.raise_for_status()
        token_data = response.json()

        expires_in = token_data.get("expires_in", 1800)
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", refresh_token),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=expires_in,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scope=token_data.get("scope"),
        )

    # ------------------------------------------------------------------
    # Tenant resolution (generic hook override)
    # ------------------------------------------------------------------

    async def resolve_external_account_id(self, access_token: str) -> str | None:
        """Resolve Xero tenant ID by calling the connections API.

        Xero doesn't provide the tenant ID in the OAuth callback URL like QBO
        provides realm_id. Instead, we call GET /connections to get the list
        of authorized tenants and use the first one.
        """
        async with get_http_client() as client:
            response = await client.get(
                XERO_CONNECTIONS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )

        if not response.is_success:
            logger.error(
                "Failed to fetch Xero connections",
                extra={"status_code": response.status_code},
            )
            return None

        connections = response.json()
        if connections and isinstance(connections, list) and len(connections) > 0:
            tenant_id = connections[0].get("tenantId")
            logger.info(
                "Resolved Xero tenant ID",
                extra={
                    "tenant_id": tenant_id,
                    "org_name": connections[0].get("tenantName"),
                    "connections_count": len(connections),
                },
            )
            return tenant_id

        logger.warning("No Xero connections found")
        return None

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
        """Fetch records from Xero with page-based pagination.

        Xero paginates with ?page=N (1-indexed) and returns up to 100 records.
        Uses If-Modified-Since header for incremental sync.
        Uses 'where' parameter to filter shared endpoints.
        """
        endpoint = XERO_ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            logger.warning(
                f"Unknown entity type for Xero: {entity_type}",
                extra={"entity_type": entity_type},
            )
            return [], None

        page = int(page_token) if page_token else 1
        params: dict[str, Any] = {"page": page}

        # Apply entity-specific filters for shared endpoints
        where_filter = _get_where_filter(entity_type)
        if where_filter:
            params["where"] = where_filter

        # Specific record IDs
        if record_ids:
            id_field = XERO_ENTITY_ID_FIELDS.get(entity_type, "")
            ids_clause = " OR ".join(f'{id_field}==Guid("{rid}")' for rid in record_ids)
            if where_filter:
                params["where"] = f"({where_filter}) AND ({ids_clause})"
            else:
                params["where"] = ids_clause

        # Build headers with optional If-Modified-Since
        headers = self._auth_headers()
        if since:
            headers["If-Modified-Since"] = since.strftime("%Y-%m-%dT%H:%M:%S")

        logger.debug(
            "Xero fetch",
            extra={"entity_type": entity_type, "endpoint": endpoint, "page": page},
        )

        data = await self._xero_request(
            "GET",
            f"/{endpoint}",
            params=params,
            headers=headers,
        )

        # Parse response envelope — Xero wraps results in {"Contacts": [...]}
        raw_records = data.get(endpoint, [])

        records = [self._to_external_record(entity_type, r) for r in raw_records]

        # Determine next page — Xero returns fewer than page_size when done
        next_token = str(page + 1) if len(raw_records) >= XERO_PAGE_SIZE else None

        logger.info(
            f"Fetched {len(records)} {endpoint} records from Xero",
            extra={
                "entity_type": entity_type,
                "page": page,
                "fetched": len(records),
                "has_next": next_token is not None,
            },
        )

        return records, next_token

    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Get a single record by ID from Xero."""
        endpoint = XERO_ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return None

        try:
            data = await self._xero_request(
                "GET",
                f"/{endpoint}/{external_id}",
            )

            raw_records = data.get(endpoint, [])
            if not raw_records:
                return None

            return self._to_external_record(entity_type, raw_records[0])

        except Exception as e:
            logger.warning(
                f"Failed to get {endpoint} {external_id} from Xero",
                extra={"error": str(e)},
            )
            return None

    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Create a record in Xero.

        Xero uses POST for both create and update.
        """
        endpoint = XERO_ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            raise Exception(f"Unknown entity type: {entity_type}")

        response_data = await self._xero_request(
            "POST",
            f"/{endpoint}",
            json_body=data,
        )

        raw_records = response_data.get(endpoint, [])
        if not raw_records:
            raise Exception(f"Xero create response missing {endpoint} key")

        record = self._to_external_record(entity_type, raw_records[0])

        logger.info(
            f"Created {endpoint} in Xero",
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
        """Update a record in Xero.

        Xero uses POST for updates — include the ID in the body.
        No SyncToken needed (unlike QBO).
        """
        endpoint = XERO_ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            raise Exception(f"Unknown entity type: {entity_type}")

        # Ensure ID is in the payload
        id_field = XERO_ENTITY_ID_FIELDS.get(entity_type, "")
        if id_field and id_field not in data:
            data[id_field] = external_id

        response_data = await self._xero_request(
            "POST",
            f"/{endpoint}/{external_id}",
            json_body=data,
        )

        raw_records = response_data.get(endpoint, [])
        if not raw_records:
            raise Exception(f"Xero update response missing {endpoint} key")

        record = self._to_external_record(entity_type, raw_records[0])

        logger.info(
            f"Updated {endpoint} in Xero",
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
        """Delete (archive) a record in Xero.

        Xero uses status-based soft deletes: set Status to ARCHIVED.
        """
        endpoint = XERO_ENTITY_ENDPOINTS.get(entity_type)
        if not endpoint:
            return False

        try:
            id_field = XERO_ENTITY_ID_FIELDS.get(entity_type, "")
            payload: dict[str, Any] = {
                id_field: external_id,
            }

            # Contacts use ContactStatus, Invoices use Status
            if endpoint == "Contacts":
                payload["ContactStatus"] = "ARCHIVED"
            else:
                payload["Status"] = "ARCHIVED"

            await self._xero_request(
                "POST",
                f"/{endpoint}/{external_id}",
                json_body=payload,
            )

            logger.info(
                f"Archived {endpoint} in Xero",
                extra={"external_id": external_id},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to archive {endpoint} {external_id}",
                extra={"error": str(e)},
            )
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_external_record(entity_type: str, raw: dict[str, Any]) -> ExternalRecord:
        """Convert a raw Xero API response dict to an ExternalRecord."""
        id_field = XERO_ENTITY_ID_FIELDS.get(entity_type, "")
        record_id = str(raw.get(id_field, ""))

        # Parse UpdatedDateUTC
        updated_at = None
        updated_str = raw.get("UpdatedDateUTC")
        if updated_str:
            try:
                if updated_str.startswith("/Date("):
                    ms_str = updated_str.split("(")[1].split("+")[0].split("-")[0].split(")")[0]
                    updated_at = datetime.fromtimestamp(int(ms_str) / 1000, tz=UTC)
                else:
                    updated_at = datetime.fromisoformat(updated_str)
            except (ValueError, TypeError, IndexError):
                pass

        return ExternalRecord(
            id=record_id,
            entity_type=entity_type,
            data=raw,
            version=None,  # Xero doesn't use SyncToken
            updated_at=updated_at,
        )
