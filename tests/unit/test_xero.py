"""Tests for Xero integration — mappers, strategy ordering, adapter helpers."""

from datetime import UTC, datetime

from app.domain.entities import SyncRule
from app.domain.enums import SyncDirection
from app.integrations.xero.constants import INBOUND_ENTITY_ORDER, OUTBOUND_ENTITY_ORDER
from app.integrations.xero.mappers import (
    _get_where_filter,
    _map_address_inbound,
    _map_address_outbound,
    _parse_xero_timestamp,
    _safe_json,
    map_bill_inbound,
    map_bill_outbound,
    map_chart_of_accounts_inbound,
    map_customer_inbound,
    map_customer_outbound,
    map_invoice_inbound,
    map_invoice_outbound,
    map_item_inbound,
    map_payment_inbound,
    map_vendor_inbound,
    map_vendor_outbound,
)
from app.integrations.xero.strategy import XeroSyncStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestMapAddressInbound:
    def test_none_input(self):
        assert _map_address_inbound(None) is None

    def test_empty_list(self):
        assert _map_address_inbound([]) is None

    def test_full_address(self):
        addresses = [
            {
                "AddressType": "STREET",
                "AddressLine1": "123 Main St",
                "AddressLine2": "Suite 100",
                "City": "Auckland",
                "Region": "AKL",
                "PostalCode": "1010",
                "Country": "NZ",
            }
        ]
        result = _map_address_inbound(addresses)
        assert result["street_1"] == "123 Main St"
        assert result["street_2"] == "Suite 100"
        assert result["city"] == "Auckland"
        assert result["state"] == "AKL"
        assert result["zip_code"] == "1010"
        assert result["country"] == "NZ"

    def test_picks_correct_address_type(self):
        addresses = [
            {"AddressType": "POBOX", "AddressLine1": "PO Box 123"},
            {"AddressType": "STREET", "AddressLine1": "456 Oak Ave"},
        ]
        result = _map_address_inbound(addresses, "STREET")
        assert result["street_1"] == "456 Oak Ave"

    def test_no_matching_type(self):
        addresses = [{"AddressType": "POBOX", "AddressLine1": "PO Box 123"}]
        result = _map_address_inbound(addresses, "STREET")
        assert result is None


class TestMapAddressOutbound:
    def test_none_input(self):
        assert _map_address_outbound(None) is None

    def test_empty_dict(self):
        assert _map_address_outbound({}) is None

    def test_full_address(self):
        addr = {
            "street_1": "789 Elm Blvd",
            "city": "Wellington",
            "state": "WLG",
            "zip_code": "6011",
            "country": "NZ",
        }
        result = _map_address_outbound(addr)
        assert result["AddressType"] == "STREET"
        assert result["AddressLine1"] == "789 Elm Blvd"
        assert result["City"] == "Wellington"
        assert result["Region"] == "WLG"


class TestParseXeroTimestamp:
    def test_none(self):
        assert _parse_xero_timestamp(None) is None

    def test_valid_iso(self):
        result = _parse_xero_timestamp("2024-06-15T10:30:00+00:00")
        assert isinstance(result, datetime)

    def test_dotnet_date_format(self):
        # /Date(1686816000000+0000)/ = 2023-06-15T12:00:00Z
        result = _parse_xero_timestamp("/Date(1686816000000+0000)/")
        assert isinstance(result, datetime)
        assert result.year == 2023

    def test_invalid_string(self):
        assert _parse_xero_timestamp("not-a-date") is None


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


class TestGetWhereFilter:
    def test_vendor(self):
        assert _get_where_filter("vendor") == "IsSupplier==true"

    def test_customer(self):
        assert _get_where_filter("customer") == "IsCustomer==true"

    def test_bill(self):
        assert _get_where_filter("bill") == 'Type=="ACCPAY"'

    def test_invoice(self):
        assert _get_where_filter("invoice") == 'Type=="ACCREC"'

    def test_chart_of_accounts(self):
        assert _get_where_filter("chart_of_accounts") is None

    def test_item(self):
        assert _get_where_filter("item") is None

    def test_payment(self):
        assert _get_where_filter("payment") is None


# ---------------------------------------------------------------------------
# Vendor mappers
# ---------------------------------------------------------------------------


class TestVendorMappers:
    def test_inbound_full(self):
        xero = {
            "Name": "Acme Inc",
            "EmailAddress": "billing@acme.com",
            "Phones": [
                {"PhoneType": "DEFAULT", "PhoneNumber": "555-1234"},
                {"PhoneType": "FAX", "PhoneNumber": "555-5678"},
            ],
            "TaxNumber": "12-3456789",
            "ContactStatus": "ACTIVE",
            "IsSupplier": True,
            "IsCustomer": False,
            "DefaultCurrency": "NZD",
            "Addresses": [
                {
                    "AddressType": "STREET",
                    "AddressLine1": "100 Main",
                    "City": "Auckland",
                },
            ],
        }
        result = map_vendor_inbound(xero)
        assert result["name"] == "Acme Inc"
        assert result["email_address"] == "billing@acme.com"
        assert result["phone"] == "555-1234"
        assert result["tax_number"] == "12-3456789"
        assert result["is_supplier"] is True
        assert result["is_customer"] is False
        assert result["status"] == "ACTIVE"
        assert result["currency"] == "NZD"
        assert result["address"]["street_1"] == "100 Main"

    def test_inbound_archived(self):
        xero = {"Name": "Old Vendor", "ContactStatus": "ARCHIVED"}
        result = map_vendor_inbound(xero)
        assert result["status"] == "ARCHIVED"

    def test_inbound_minimal(self):
        result = map_vendor_inbound({})
        assert result["name"] == ""
        assert result["email_address"] is None
        assert result["phone"] is None

    def test_outbound(self):
        internal = {
            "name": "Acme Inc",
            "email_address": "billing@acme.com",
            "phone": "555-1234",
            "tax_number": "12-345",
            "currency": "NZD",
        }
        result = map_vendor_outbound(internal)
        assert result["Name"] == "Acme Inc"
        assert result["IsSupplier"] is True
        assert result["EmailAddress"] == "billing@acme.com"
        assert result["Phones"][0]["PhoneNumber"] == "555-1234"

    def test_outbound_minimal(self):
        result = map_vendor_outbound({"name": "Test"})
        assert result == {"Name": "Test", "IsSupplier": True}


# ---------------------------------------------------------------------------
# Customer mappers
# ---------------------------------------------------------------------------


class TestCustomerMappers:
    def test_inbound_full(self):
        xero = {
            "Name": "Client Corp",
            "EmailAddress": "client@corp.com",
            "Phones": [{"PhoneType": "DEFAULT", "PhoneNumber": "555-9999"}],
            "ContactStatus": "ACTIVE",
            "IsCustomer": True,
            "IsSupplier": False,
            "DefaultCurrency": "USD",
        }
        result = map_customer_inbound(xero)
        assert result["name"] == "Client Corp"
        assert result["is_customer"] is True
        assert result["is_supplier"] is False

    def test_outbound(self):
        internal = {"name": "Client Corp", "email_address": "client@corp.com"}
        result = map_customer_outbound(internal)
        assert result["Name"] == "Client Corp"
        assert result["IsCustomer"] is True
        assert result["EmailAddress"] == "client@corp.com"


# ---------------------------------------------------------------------------
# Bill mappers
# ---------------------------------------------------------------------------


class TestBillMappers:
    def test_inbound_basic(self):
        xero = {
            "InvoiceNumber": "B-001",
            "Type": "ACCPAY",
            "Contact": {"ContactID": "abc-123", "Name": "Acme"},
            "Total": 1500.00,
            "AmountDue": 1500.00,
            "DateString": "2024-06-01",
            "DueDateString": "2024-07-01",
            "CurrencyCode": "NZD",
            "Status": "AUTHORISED",
            "LineItems": [
                {
                    "Description": "Consulting",
                    "Quantity": 1,
                    "UnitAmount": 1500.00,
                    "LineAmount": 1500.00,
                },
            ],
        }
        result = map_bill_inbound(xero)
        assert result["bill_number"] == "B-001"
        assert result["vendor_external_id"] == "abc-123"
        assert result["vendor_name"] == "Acme"
        assert result["amount"] == 1500.00
        assert result["status"] == "pending"
        assert result["currency"] == "NZD"
        assert len(result["line_items"]) == 1

    def test_inbound_paid_status(self):
        xero = {
            "Total": 500,
            "AmountDue": 0,
            "Status": "PAID",
            "FullyPaidOnDate": "2024-06-15",
        }
        result = map_bill_inbound(xero)
        assert result["status"] == "paid"
        assert result["paid_on_date"] is not None

    def test_inbound_voided(self):
        xero = {"Total": 100, "AmountDue": 100, "Status": "VOIDED"}
        result = map_bill_inbound(xero)
        assert result["status"] == "voided"

    def test_outbound(self):
        internal = {
            "bill_number": "B-002",
            "date": datetime(2024, 6, 1, tzinfo=UTC),
            "due_date": "2024-07-01",
            "currency": "NZD",
            "vendor_external_id": "abc-123",
            "line_items": [
                {"description": "Work", "quantity": 2, "unit_price": 200, "total": 400},
            ],
        }
        result = map_bill_outbound(internal)
        assert result["Type"] == "ACCPAY"
        assert result["InvoiceNumber"] == "B-002"
        assert result["DateString"] == "2024-06-01"
        assert result["DueDateString"] == "2024-07-01"
        assert result["Contact"] == {"ContactID": "abc-123"}
        assert len(result["LineItems"]) == 1
        assert result["LineItems"][0]["Quantity"] == 2.0

    def test_outbound_default_line(self):
        internal = {"amount": 999, "description": "Misc"}
        result = map_bill_outbound(internal)
        assert len(result["LineItems"]) == 1
        assert result["LineItems"][0]["UnitAmount"] == 999.0


# ---------------------------------------------------------------------------
# Invoice mappers
# ---------------------------------------------------------------------------


class TestInvoiceMappers:
    def test_inbound_basic(self):
        xero = {
            "InvoiceNumber": "INV-001",
            "Type": "ACCREC",
            "Contact": {"ContactID": "def-456", "Name": "Client Co"},
            "Total": 2000,
            "TotalTax": 200,
            "SubTotal": 1800,
            "AmountDue": 2000,
            "DateString": "2024-06-01",
            "DueDateString": "2024-07-01",
            "CurrencyCode": "USD",
            "Reference": "Q2 work",
            "Status": "DRAFT",
            "LineItems": [
                {
                    "Description": "Services",
                    "Quantity": 10,
                    "UnitAmount": 180,
                    "LineAmount": 1800,
                },
            ],
        }
        result = map_invoice_inbound(xero)
        assert result["invoice_number"] == "INV-001"
        assert result["contact_external_id"] == "def-456"
        assert result["total_amount"] == 2000
        assert result["total_tax_amount"] == 200
        assert result["sub_total"] == 1800
        assert result["status"] == "DRAFT"
        assert result["memo"] == "Q2 work"
        assert len(result["line_items"]) == 1
        assert result["line_items"][0]["quantity"] == 10

    def test_inbound_paid_status(self):
        xero = {
            "Total": 1000,
            "AmountDue": 0,
            "TotalTax": 0,
            "Status": "PAID",
            "FullyPaidOnDate": "2024-07-01",
        }
        result = map_invoice_inbound(xero)
        assert result["status"] == "PAID"
        assert result["paid_on_date"] is not None

    def test_inbound_authorised_status(self):
        xero = {"Total": 1000, "AmountDue": 1000, "TotalTax": 0, "Status": "AUTHORISED"}
        result = map_invoice_inbound(xero)
        assert result["status"] == "SUBMITTED"

    def test_outbound(self):
        internal = {
            "invoice_number": "INV-002",
            "issue_date": datetime(2024, 6, 1, tzinfo=UTC),
            "due_date": "2024-07-01",
            "currency": "NZD",
            "memo": "Test memo",
            "contact_external_id": "def-456",
            "line_items": [
                {"description": "Dev", "quantity": 5, "unit_price": 150, "total": 750},
            ],
        }
        result = map_invoice_outbound(internal)
        assert result["Type"] == "ACCREC"
        assert result["InvoiceNumber"] == "INV-002"
        assert result["Contact"] == {"ContactID": "def-456"}
        assert result["Reference"] == "Test memo"
        assert len(result["LineItems"]) == 1
        assert result["LineItems"][0]["Quantity"] == 5.0


# ---------------------------------------------------------------------------
# Chart of Accounts mapper
# ---------------------------------------------------------------------------


class TestChartOfAccountsMapper:
    def test_inbound_full(self):
        xero = {
            "Name": "Sales Revenue",
            "Code": "200",
            "Type": "REVENUE",
            "SystemAccount": None,
            "Class": "REVENUE",
            "CurrencyCode": "NZD",
            "Description": "Revenue from sales",
            "Status": "ACTIVE",
        }
        result = map_chart_of_accounts_inbound(xero)
        assert result["name"] == "Sales Revenue"
        assert result["account_number"] == "200"
        assert result["account_type"] == "REVENUE"
        assert result["classification"] == "REVENUE"
        assert result["active"] is True
        assert result["description"] == "Revenue from sales"

    def test_inbound_archived(self):
        xero = {"Name": "Old Account", "Status": "ARCHIVED"}
        result = map_chart_of_accounts_inbound(xero)
        assert result["active"] is False

    def test_inbound_minimal(self):
        result = map_chart_of_accounts_inbound({})
        assert result["name"] == ""
        assert result["account_type"] == ""


# ---------------------------------------------------------------------------
# Item mapper
# ---------------------------------------------------------------------------


class TestItemMapper:
    def test_inbound_full(self):
        xero = {
            "Name": "Widget",
            "Code": "W-001",
            "Description": "A fine widget",
            "IsSold": True,
            "IsPurchased": True,
            "PurchaseDetails": {"UnitPrice": 10.00},
            "SalesDetails": {"UnitPrice": 25.00},
        }
        result = map_item_inbound(xero)
        assert result["name"] == "Widget"
        assert result["code"] == "W-001"
        assert result["description"] == "A fine widget"
        assert result["is_sold"] is True
        assert result["is_purchased"] is True

    def test_inbound_minimal(self):
        result = map_item_inbound({})
        assert result["name"] == ""
        assert result["code"] is None


# ---------------------------------------------------------------------------
# Payment mapper
# ---------------------------------------------------------------------------


class TestPaymentMapper:
    def test_inbound_full(self):
        xero = {
            "Amount": 500.00,
            "DateString": "2024-06-15",
            "Reference": "Payment for INV-001",
            "CurrencyCode": "NZD",
            "Status": "AUTHORISED",
            "IsReconciled": True,
            "Invoice": {"InvoiceID": "inv-abc", "InvoiceNumber": "INV-001"},
            "Account": {"AccountID": "acc-123"},
        }
        result = map_payment_inbound(xero)
        assert result["amount"] == 500.00
        assert result["reference"] == "Payment for INV-001"
        assert result["currency"] == "NZD"
        assert result["invoice_external_id"] == "inv-abc"
        assert result["invoice_number"] == "INV-001"
        assert result["account_external_id"] == "acc-123"
        assert result["is_reconciled"] is True

    def test_inbound_minimal(self):
        result = map_payment_inbound({})
        assert result["amount"] == 0
        assert result["invoice_external_id"] is None


# ---------------------------------------------------------------------------
# Strategy — entity ordering
# ---------------------------------------------------------------------------


class TestStrategyOrdering:
    def setup_method(self):
        self.strategy = XeroSyncStrategy()

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
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "ContactID": "abc-123",
            "Name": "Test Vendor",
            "UpdatedDateUTC": "2024-06-15T10:30:00+00:00",
        }
        record = XeroAdapter._to_external_record("vendor", raw)
        assert record.id == "abc-123"
        assert record.entity_type == "vendor"
        assert record.version is None  # Xero doesn't use SyncToken
        assert record.data == raw
        assert isinstance(record.updated_at, datetime)

    def test_to_external_record_dotnet_date(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "ContactID": "def-456",
            "Name": "Test",
            "UpdatedDateUTC": "/Date(1686816000000+0000)/",
        }
        record = XeroAdapter._to_external_record("vendor", raw)
        assert record.id == "def-456"
        assert isinstance(record.updated_at, datetime)

    def test_to_external_record_no_updated_at(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {"ContactID": "xyz", "Name": "X"}
        record = XeroAdapter._to_external_record("vendor", raw)
        assert record.id == "xyz"
        assert record.updated_at is None

    def test_to_external_record_bill(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "InvoiceID": "inv-789",
            "Type": "ACCPAY",
            "InvoiceNumber": "B-001",
        }
        record = XeroAdapter._to_external_record("bill", raw)
        assert record.id == "inv-789"
        assert record.entity_type == "bill"

    def test_to_external_record_invoice(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "InvoiceID": "inv-999",
            "Type": "ACCREC",
            "InvoiceNumber": "INV-001",
        }
        record = XeroAdapter._to_external_record("invoice", raw)
        assert record.id == "inv-999"
        assert record.entity_type == "invoice"

    def test_to_external_record_chart_of_accounts(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "AccountID": "acc-001",
            "Name": "Sales",
            "Code": "200",
        }
        record = XeroAdapter._to_external_record("chart_of_accounts", raw)
        assert record.id == "acc-001"

    def test_to_external_record_item(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "ItemID": "item-001",
            "Name": "Widget",
        }
        record = XeroAdapter._to_external_record("item", raw)
        assert record.id == "item-001"

    def test_to_external_record_payment(self):
        from app.integrations.xero.client import XeroAdapter

        raw = {
            "PaymentID": "pay-001",
            "Amount": 500,
        }
        record = XeroAdapter._to_external_record("payment", raw)
        assert record.id == "pay-001"


# ---------------------------------------------------------------------------
# Mapper registries
# ---------------------------------------------------------------------------


class TestMapperRegistries:
    def test_inbound_mappers_has_all_entities(self):
        from app.integrations.xero.mappers import INBOUND_MAPPERS

        expected = {"vendor", "customer", "bill", "invoice", "chart_of_accounts", "item", "payment"}
        assert set(INBOUND_MAPPERS.keys()) == expected

    def test_outbound_mappers(self):
        from app.integrations.xero.mappers import OUTBOUND_MAPPERS

        expected = {"vendor", "customer", "bill", "invoice"}
        assert set(OUTBOUND_MAPPERS.keys()) == expected


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_entity_endpoints(self):
        from app.integrations.xero.constants import XERO_ENTITY_ENDPOINTS

        assert XERO_ENTITY_ENDPOINTS["vendor"] == "Contacts"
        assert XERO_ENTITY_ENDPOINTS["customer"] == "Contacts"
        assert XERO_ENTITY_ENDPOINTS["bill"] == "Invoices"
        assert XERO_ENTITY_ENDPOINTS["invoice"] == "Invoices"
        assert XERO_ENTITY_ENDPOINTS["chart_of_accounts"] == "Accounts"
        assert XERO_ENTITY_ENDPOINTS["item"] == "Items"
        assert XERO_ENTITY_ENDPOINTS["payment"] == "Payments"

    def test_entity_id_fields(self):
        from app.integrations.xero.constants import XERO_ENTITY_ID_FIELDS

        assert XERO_ENTITY_ID_FIELDS["vendor"] == "ContactID"
        assert XERO_ENTITY_ID_FIELDS["bill"] == "InvoiceID"
        assert XERO_ENTITY_ID_FIELDS["chart_of_accounts"] == "AccountID"
        assert XERO_ENTITY_ID_FIELDS["item"] == "ItemID"
        assert XERO_ENTITY_ID_FIELDS["payment"] == "PaymentID"

    def test_entity_order_has_all_seven(self):
        assert len(INBOUND_ENTITY_ORDER) == 7
        assert len(OUTBOUND_ENTITY_ORDER) == 7
