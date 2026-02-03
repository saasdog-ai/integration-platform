"""Tests for QuickBooks integration — mappers, strategy ordering, adapter helpers."""

from datetime import UTC, datetime

from app.domain.entities import SyncRule
from app.domain.enums import SyncDirection
from app.integrations.quickbooks.constants import INBOUND_ENTITY_ORDER, OUTBOUND_ENTITY_ORDER
from app.integrations.quickbooks.mappers import (
    _map_address_inbound,
    _map_address_outbound,
    _parse_qbo_timestamp,
    _safe_json,
    map_bill_inbound,
    map_bill_outbound,
    map_invoice_inbound,
    map_invoice_outbound,
    map_vendor_inbound,
    map_vendor_outbound,
)
from app.integrations.quickbooks.strategy import QuickBooksSyncStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestMapAddressInbound:
    def test_none_input(self):
        assert _map_address_inbound(None) is None

    def test_empty_input(self):
        assert _map_address_inbound({}) is None

    def test_full_address(self):
        qbo = {
            "Line1": "123 Main St",
            "Line2": "Suite 100",
            "City": "Austin",
            "CountrySubDivisionCode": "TX",
            "PostalCode": "78701",
            "Country": "US",
        }
        result = _map_address_inbound(qbo)
        assert result["street_1"] == "123 Main St"
        assert result["street_2"] == "Suite 100"
        assert result["city"] == "Austin"
        assert result["state"] == "TX"
        assert result["zip_code"] == "78701"
        assert result["country"] == "US"

    def test_default_country(self):
        result = _map_address_inbound({"Line1": "456 Oak Ave"})
        assert result["country"] == "US"


class TestMapAddressOutbound:
    def test_none_input(self):
        assert _map_address_outbound(None) is None

    def test_empty_dict(self):
        assert _map_address_outbound({}) is None

    def test_full_address(self):
        addr = {
            "street_1": "789 Elm Blvd",
            "city": "Denver",
            "state": "CO",
            "zip_code": "80202",
            "country": "US",
        }
        result = _map_address_outbound(addr)
        assert result["Line1"] == "789 Elm Blvd"
        assert result["City"] == "Denver"
        assert result["CountrySubDivisionCode"] == "CO"


class TestParseTimestamp:
    def test_none(self):
        assert _parse_qbo_timestamp(None) is None

    def test_valid_iso(self):
        result = _parse_qbo_timestamp("2024-06-15T10:30:00-05:00")
        assert isinstance(result, datetime)

    def test_invalid_string(self):
        assert _parse_qbo_timestamp("not-a-date") is None


class TestSafeJson:
    def test_string_json(self):
        assert _safe_json('[{"a": 1}]') == [{"a": 1}]

    def test_invalid_string(self):
        assert _safe_json("hello") == "hello"

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert _safe_json(d) is d

    def test_none_passthrough(self):
        assert _safe_json(None) is None


# ---------------------------------------------------------------------------
# Vendor mappers
# ---------------------------------------------------------------------------


class TestVendorMappers:
    def test_inbound_full(self):
        qbo = {
            "DisplayName": "Acme Inc",
            "PrimaryEmailAddr": {"Address": "billing@acme.com"},
            "PrimaryPhone": {"FreeFormNumber": "555-1234"},
            "TaxIdentifier": "12-3456789",
            "Active": True,
            "CurrencyRef": {"value": "USD"},
            "BillAddr": {"Line1": "100 Main", "City": "NY"},
        }
        result = map_vendor_inbound(qbo)
        assert result["name"] == "Acme Inc"
        assert result["email_address"] == "billing@acme.com"
        assert result["phone"] == "555-1234"
        assert result["tax_number"] == "12-3456789"
        assert result["is_supplier"] is True
        assert result["is_customer"] is False
        assert result["status"] == "ACTIVE"
        assert result["currency"] == "USD"
        assert result["address"]["street_1"] == "100 Main"

    def test_inbound_inactive(self):
        qbo = {"DisplayName": "Old Vendor", "Active": False}
        result = map_vendor_inbound(qbo)
        assert result["status"] == "ARCHIVED"

    def test_inbound_minimal(self):
        result = map_vendor_inbound({})
        assert result["name"] == ""
        assert result["email_address"] is None
        assert result["currency"] == "USD"

    def test_outbound(self):
        internal = {
            "name": "Acme Inc",
            "email_address": "billing@acme.com",
            "phone": "555-1234",
            "tax_number": "12-345",
            "currency": "USD",
        }
        result = map_vendor_outbound(internal)
        assert result["DisplayName"] == "Acme Inc"
        assert result["PrimaryEmailAddr"] == {"Address": "billing@acme.com"}
        assert result["PrimaryPhone"] == {"FreeFormNumber": "555-1234"}

    def test_outbound_minimal(self):
        result = map_vendor_outbound({"name": "Test"})
        assert result == {"DisplayName": "Test"}


# ---------------------------------------------------------------------------
# Bill mappers
# ---------------------------------------------------------------------------


class TestBillMappers:
    def test_inbound_basic(self):
        qbo = {
            "DocNumber": "B-001",
            "VendorRef": {"value": "42", "name": "Acme"},
            "TotalAmt": 1500.00,
            "Balance": 1500.00,
            "TxnDate": "2024-06-01",
            "DueDate": "2099-07-01",
            "CurrencyRef": {"value": "USD"},
            "Line": [
                {
                    "Amount": 1500.00,
                    "Description": "Consulting",
                    "DetailType": "AccountBasedExpenseLineDetail",
                },
            ],
            "MetaData": {"LastUpdatedTime": "2024-06-01T12:00:00"},
        }
        result = map_bill_inbound(qbo)
        assert result["bill_number"] == "B-001"
        assert result["vendor_external_id"] == "42"
        assert result["amount"] == 1500.00
        assert result["status"] == "pending"
        assert len(result["line_items"]) == 1

    def test_inbound_paid_status(self):
        qbo = {"TotalAmt": 500, "Balance": 0, "Line": []}
        result = map_bill_inbound(qbo)
        assert result["status"] == "paid"

    def test_inbound_skips_subtotal_lines(self):
        qbo = {
            "TotalAmt": 100,
            "Balance": 100,
            "Line": [
                {
                    "Amount": 100,
                    "Description": "Work",
                    "DetailType": "AccountBasedExpenseLineDetail",
                },
                {"Amount": 100, "DetailType": "SubTotalLineDetail"},
            ],
        }
        result = map_bill_inbound(qbo)
        assert len(result["line_items"]) == 1

    def test_outbound(self):
        internal = {
            "bill_number": "B-002",
            "date": datetime(2024, 6, 1, tzinfo=UTC),
            "due_date": "2024-07-01",
            "currency": "USD",
            "vendor_external_id": "42",
            "line_items": [
                {"description": "Work", "unit_price": 200, "total": 200},
            ],
        }
        result = map_bill_outbound(internal)
        assert result["DocNumber"] == "B-002"
        assert result["TxnDate"] == "2024-06-01"
        assert result["DueDate"] == "2024-07-01"
        assert result["VendorRef"] == {"value": "42"}
        assert len(result["Line"]) == 1
        assert result["Line"][0]["Amount"] == 200.0

    def test_outbound_default_line(self):
        internal = {"amount": 999, "description": "Misc"}
        result = map_bill_outbound(internal)
        assert len(result["Line"]) == 1
        assert result["Line"][0]["Amount"] == 999.0


# ---------------------------------------------------------------------------
# Invoice mappers
# ---------------------------------------------------------------------------


class TestInvoiceMappers:
    def test_inbound_basic(self):
        qbo = {
            "DocNumber": "INV-001",
            "CustomerRef": {"value": "55", "name": "Client Co"},
            "TotalAmt": 2000,
            "Balance": 2000,
            "TxnDate": "2024-06-01",
            "DueDate": "2024-07-01",
            "CurrencyRef": {"value": "USD"},
            "PrivateNote": "Q2 work",
            "Line": [
                {
                    "Amount": 2000,
                    "Description": "Services",
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {"Qty": 10, "UnitPrice": 200},
                },
            ],
            "MetaData": {},
        }
        result = map_invoice_inbound(qbo)
        assert result["invoice_number"] == "INV-001"
        assert result["contact_external_id"] == "55"
        assert result["total_amount"] == 2000
        assert result["status"] == "DRAFT"
        assert len(result["line_items"]) == 1
        assert result["line_items"][0]["quantity"] == 10

    def test_inbound_paid_status(self):
        qbo = {"TotalAmt": 1000, "Balance": 0, "Line": [], "MetaData": {}}
        result = map_invoice_inbound(qbo)
        assert result["status"] == "PAID"

    def test_inbound_submitted_status(self):
        qbo = {
            "TotalAmt": 1000,
            "Balance": 1000,
            "EmailStatus": "EmailSent",
            "Line": [],
            "MetaData": {},
        }
        result = map_invoice_inbound(qbo)
        assert result["status"] == "SUBMITTED"

    def test_outbound(self):
        internal = {
            "invoice_number": "INV-002",
            "issue_date": datetime(2024, 6, 1, tzinfo=UTC),
            "due_date": "2024-07-01",
            "currency": "CAD",
            "memo": "Test memo",
            "contact_external_id": "55",
            "bill_email": "client@example.com",
            "line_items": [
                {"description": "Dev", "quantity": 5, "unit_price": 150, "total": 750},
            ],
        }
        result = map_invoice_outbound(internal)
        assert result["DocNumber"] == "INV-002"
        assert result["CustomerRef"] == {"value": "55"}
        assert result["BillEmail"] == {"Address": "client@example.com"}
        assert len(result["Line"]) == 1
        assert result["Line"][0]["SalesItemLineDetail"]["Qty"] == 5.0


# ---------------------------------------------------------------------------
# Strategy — entity ordering
# ---------------------------------------------------------------------------


class TestStrategyOrdering:
    def setup_method(self):
        self.strategy = QuickBooksSyncStrategy()

    def test_inbound_order(self):
        order = self.strategy.get_entity_order(SyncDirection.INBOUND)
        assert order == list(INBOUND_ENTITY_ORDER)
        # Vendors/customers before bills/invoices
        assert order.index("vendor") < order.index("bill")
        assert order.index("customer") < order.index("invoice")

    def test_outbound_order(self):
        order = self.strategy.get_entity_order(SyncDirection.OUTBOUND)
        assert order == list(OUTBOUND_ENTITY_ORDER)

    def test_get_ordered_rules(self):
        rules = [
            SyncRule(entity_type="invoice", direction=SyncDirection.INBOUND),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND),
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND),
        ]
        ordered = self.strategy.get_ordered_rules(rules, SyncDirection.INBOUND)
        types = [r.entity_type for r in ordered]
        assert types == ["vendor", "bill", "invoice"]

    def test_get_ordered_rules_filters_disabled(self):
        rules = [
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True),
            SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=False),
        ]
        ordered = self.strategy.get_ordered_rules(rules, SyncDirection.INBOUND)
        assert len(ordered) == 1
        assert ordered[0].entity_type == "vendor"

    def test_unknown_entity_sorted_last(self):
        rules = [
            SyncRule(entity_type="custom_entity", direction=SyncDirection.INBOUND),
            SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND),
        ]
        ordered = self.strategy.get_ordered_rules(rules, SyncDirection.INBOUND)
        assert ordered[0].entity_type == "vendor"
        assert ordered[1].entity_type == "custom_entity"


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------


class TestAdapterHelpers:
    def test_to_external_record(self):
        from app.integrations.quickbooks.client import QuickBooksAdapter

        raw = {
            "Id": "42",
            "DisplayName": "Test",
            "SyncToken": "3",
            "MetaData": {"LastUpdatedTime": "2024-06-15T10:30:00-05:00"},
        }
        record = QuickBooksAdapter._to_external_record("vendor", raw)
        assert record.id == "42"
        assert record.entity_type == "vendor"
        assert record.version == "3"
        assert record.data == raw
        assert isinstance(record.updated_at, datetime)

    def test_to_external_record_no_metadata(self):
        from app.integrations.quickbooks.client import QuickBooksAdapter

        raw = {"Id": "1", "DisplayName": "X"}
        record = QuickBooksAdapter._to_external_record("vendor", raw)
        assert record.id == "1"
        assert record.updated_at is None
