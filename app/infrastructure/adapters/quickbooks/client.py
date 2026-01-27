"""QuickBooks Online mock adapter for development and testing."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.logging import get_logger
from app.domain.entities import ExternalRecord, OAuthTokens
from app.domain.interfaces import IntegrationAdapterInterface

# NOTE: For real QuickBooks API implementation, use the http_client module:
# from app.infrastructure.adapters.http_client import get_http_client, make_request
#
# Example usage:
#   async with get_http_client(base_url="https://quickbooks.api.intuit.com") as client:
#       response = await client.get(f"/v3/company/{realm_id}/vendor/{vendor_id}")
#       response.raise_for_status()
#       return response.json()

logger = get_logger(__name__)


class QuickBooksAdapter(IntegrationAdapterInterface):
    """
    QuickBooks Online integration adapter.

    This is a mock implementation that simulates QuickBooks API calls
    and prints detailed sync activity for demonstration purposes.
    """

    # QuickBooks entity type mappings
    ENTITY_DISPLAY_NAMES = {
        "vendor": "Vendor",
        "bill": "Bill",
        "invoice": "Invoice",
        "customer": "Customer",
        "chart_of_accounts": "Chart of Accounts",
        "payment": "Payment",
        "item": "Item",
        "employee": "Employee",
    }

    def __init__(
        self,
        integration_name: str = "QuickBooks Online",
        access_token: str = "",
        external_account_id: str | None = None,
    ) -> None:
        """
        Initialize QuickBooks adapter.

        Args:
            integration_name: Name of the integration.
            access_token: OAuth access token for QuickBooks API.
            external_account_id: QuickBooks realm/company ID.
        """
        self._integration_name = integration_name
        self._access_token = access_token
        self._realm_id = external_account_id

        # Mock data storage
        self._records: dict[str, dict[str, ExternalRecord]] = {}
        self._seed_sample_data()

        print(f"\n{'='*60}")
        print(f"  QuickBooks Adapter Initialized")
        print(f"  Realm ID: {self._realm_id or 'Not set'}")
        print(f"{'='*60}\n")

    def _seed_sample_data(self) -> None:
        """Seed sample QuickBooks data for demonstration."""
        now = datetime.now(timezone.utc)

        # Sample vendors
        vendors = [
            {"id": "QBO-V-1001", "name": "Acme Supplies Inc.", "email": "accounts@acme.com", "balance": 15000.00},
            {"id": "QBO-V-1002", "name": "Office Depot", "email": "billing@officedepot.com", "balance": 2500.00},
            {"id": "QBO-V-1003", "name": "Tech Solutions LLC", "email": "ap@techsolutions.com", "balance": 8750.00},
            {"id": "QBO-V-1004", "name": "Global Logistics", "email": "invoices@globallogistics.com", "balance": 45000.00},
            {"id": "QBO-V-1005", "name": "Cloud Services Pro", "email": "billing@cloudservices.pro", "balance": 1200.00},
        ]

        # Sample bills
        bills = [
            {"id": "QBO-B-2001", "vendor_id": "QBO-V-1001", "amount": 5000.00, "due_date": "2026-02-15", "status": "Open"},
            {"id": "QBO-B-2002", "vendor_id": "QBO-V-1002", "amount": 750.00, "due_date": "2026-02-01", "status": "Paid"},
            {"id": "QBO-B-2003", "vendor_id": "QBO-V-1003", "amount": 3500.00, "due_date": "2026-02-20", "status": "Open"},
            {"id": "QBO-B-2004", "vendor_id": "QBO-V-1004", "amount": 12000.00, "due_date": "2026-03-01", "status": "Open"},
            {"id": "QBO-B-2005", "vendor_id": "QBO-V-1001", "amount": 2500.00, "due_date": "2026-01-30", "status": "Overdue"},
        ]

        # Sample invoices
        invoices = [
            {"id": "QBO-I-3001", "customer": "ABC Corp", "amount": 10000.00, "due_date": "2026-02-10", "status": "Sent"},
            {"id": "QBO-I-3002", "customer": "XYZ Industries", "amount": 25000.00, "due_date": "2026-02-28", "status": "Draft"},
            {"id": "QBO-I-3003", "customer": "StartupCo", "amount": 5500.00, "due_date": "2026-01-25", "status": "Paid"},
        ]

        # Store records
        self._records["vendor"] = {
            v["id"]: ExternalRecord(id=v["id"], entity_type="vendor", data=v, version="1", updated_at=now)
            for v in vendors
        }
        self._records["bill"] = {
            b["id"]: ExternalRecord(id=b["id"], entity_type="bill", data=b, version="1", updated_at=now)
            for b in bills
        }
        self._records["invoice"] = {
            i["id"]: ExternalRecord(id=i["id"], entity_type="invoice", data=i, version="1", updated_at=now)
            for i in invoices
        }

    async def authenticate(self, auth_code: str, redirect_uri: str) -> OAuthTokens:
        """Mock QuickBooks OAuth authentication."""
        print(f"\n[QuickBooks] Authenticating with OAuth...")
        print(f"[QuickBooks] Exchanging authorization code for tokens...")

        tokens = OAuthTokens(
            access_token=f"qbo_access_{uuid4().hex[:16]}",
            refresh_token=f"qbo_refresh_{uuid4().hex[:16]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(timezone.utc),
        )

        print(f"[QuickBooks] Authentication successful!")
        return tokens

    async def refresh_token(self, refresh_token: str) -> OAuthTokens:
        """Mock QuickBooks token refresh."""
        print(f"\n[QuickBooks] Refreshing access token...")

        tokens = OAuthTokens(
            access_token=f"qbo_access_{uuid4().hex[:16]}",
            refresh_token=f"qbo_refresh_{uuid4().hex[:16]}",
            token_type="Bearer",
            expires_in=3600,
            expires_at=datetime.now(timezone.utc),
        )

        print(f"[QuickBooks] Token refreshed successfully!")
        return tokens

    async def fetch_records(
        self,
        entity_type: str,
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """
        Mock fetching records from QuickBooks.

        Args:
            entity_type: The entity type to fetch (vendor, bill, invoice, etc.)
            since: Only fetch records modified after this time
            page_token: Pagination token
            record_ids: Optional list of specific record IDs to fetch
        """
        display_name = self.ENTITY_DISPLAY_NAMES.get(entity_type, entity_type.title())

        print(f"\n{'─'*50}")
        print(f"[QuickBooks] Fetching {display_name} records...")
        if since:
            print(f"[QuickBooks]   Modified since: {since.isoformat()}")
        if record_ids:
            print(f"[QuickBooks]   Specific IDs: {record_ids}")

        entity_records = self._records.get(entity_type, {})
        records = list(entity_records.values())

        # Filter by specific record IDs if provided
        if record_ids:
            records = [r for r in records if r.id in record_ids]

        # Filter by since if provided
        if since:
            records = [r for r in records if r.updated_at and r.updated_at > since]

        # Pagination
        page_size = 100
        start_idx = int(page_token) if page_token else 0
        end_idx = start_idx + page_size
        page_records = records[start_idx:end_idx]
        next_token = str(end_idx) if end_idx < len(records) else None

        # Print sync activity
        print(f"[QuickBooks]   Found {len(page_records)} {display_name} record(s)")
        for record in page_records:
            data = record.data
            if entity_type == "vendor":
                print(f"[QuickBooks]     → {record.id}: {data.get('name')} (Balance: ${data.get('balance', 0):,.2f})")
            elif entity_type == "bill":
                print(f"[QuickBooks]     → {record.id}: ${data.get('amount', 0):,.2f} - {data.get('status')} (Due: {data.get('due_date')})")
            elif entity_type == "invoice":
                print(f"[QuickBooks]     → {record.id}: {data.get('customer')} - ${data.get('amount', 0):,.2f} ({data.get('status')})")
            else:
                print(f"[QuickBooks]     → {record.id}")

        print(f"{'─'*50}")

        return page_records, next_token

    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Mock getting a single record from QuickBooks."""
        display_name = self.ENTITY_DISPLAY_NAMES.get(entity_type, entity_type.title())
        print(f"[QuickBooks] Getting {display_name} record: {external_id}")

        entity_records = self._records.get(entity_type, {})
        record = entity_records.get(external_id)

        if record:
            print(f"[QuickBooks]   Found: {record.data}")
        else:
            print(f"[QuickBooks]   Not found")

        return record

    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Mock creating a record in QuickBooks."""
        display_name = self.ENTITY_DISPLAY_NAMES.get(entity_type, entity_type.title())

        external_id = f"QBO-{entity_type[0].upper()}-{uuid4().hex[:6]}"
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data={**data, "id": external_id},
            version="1",
            updated_at=datetime.now(timezone.utc),
        )

        if entity_type not in self._records:
            self._records[entity_type] = {}
        self._records[entity_type][external_id] = record

        print(f"\n[QuickBooks] Created {display_name} record:")
        print(f"[QuickBooks]   ID: {external_id}")
        print(f"[QuickBooks]   Data: {data}")

        return record

    async def update_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Mock updating a record in QuickBooks."""
        display_name = self.ENTITY_DISPLAY_NAMES.get(entity_type, entity_type.title())

        entity_records = self._records.get(entity_type, {})
        existing = entity_records.get(external_id)

        if not existing:
            raise Exception(f"QuickBooks {display_name} not found: {external_id}")

        new_version = str(int(existing.version or "0") + 1)
        updated_data = {**existing.data, **data}
        record = ExternalRecord(
            id=external_id,
            entity_type=entity_type,
            data=updated_data,
            version=new_version,
            updated_at=datetime.now(timezone.utc),
        )
        entity_records[external_id] = record

        print(f"\n[QuickBooks] Updated {display_name} record:")
        print(f"[QuickBooks]   ID: {external_id}")
        print(f"[QuickBooks]   Version: {existing.version} → {new_version}")
        print(f"[QuickBooks]   Changes: {data}")

        return record

    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Mock deleting a record from QuickBooks."""
        display_name = self.ENTITY_DISPLAY_NAMES.get(entity_type, entity_type.title())

        entity_records = self._records.get(entity_type, {})
        if external_id in entity_records:
            del entity_records[external_id]
            print(f"\n[QuickBooks] Deleted {display_name} record: {external_id}")
            return True

        print(f"\n[QuickBooks] {display_name} record not found for deletion: {external_id}")
        return False
