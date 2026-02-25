"""Schema mappers between Xero API format and internal system format.

Each entity has an inbound mapper (Xero → internal) and an outbound mapper
(internal → Xero). Xero uses shared endpoints — Contacts for vendor/customer,
Invoices for bill/invoice — distinguished by flags and Type fields.
"""

import json
from datetime import UTC, datetime
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _map_address_inbound(xero_addresses: list[dict] | None, addr_type: str = "STREET") -> dict | None:
    """Map a Xero address object to our internal address format.

    Xero stores addresses as a list; we pick the one matching addr_type.
    """
    if not xero_addresses:
        return None
    for addr in xero_addresses:
        if addr.get("AddressType") == addr_type:
            return {
                "street_1": addr.get("AddressLine1"),
                "street_2": addr.get("AddressLine2"),
                "city": addr.get("City"),
                "state": addr.get("Region"),
                "zip_code": addr.get("PostalCode"),
                "country": addr.get("Country", ""),
            }
    return None


def _map_address_outbound(addr: dict | None, addr_type: str = "STREET") -> dict | None:
    """Map our internal address to Xero address format."""
    if not addr:
        return None
    result: dict[str, Any] = {"AddressType": addr_type}
    if addr.get("street_1"):
        result["AddressLine1"] = addr["street_1"]
    if addr.get("street_2"):
        result["AddressLine2"] = addr["street_2"]
    if addr.get("city"):
        result["City"] = addr["city"]
    if addr.get("state"):
        result["Region"] = addr["state"]
    if addr.get("zip_code"):
        result["PostalCode"] = addr["zip_code"]
    if addr.get("country"):
        result["Country"] = addr["country"]
    return result if len(result) > 1 else None


def _parse_xero_timestamp(ts: str | None) -> datetime | None:
    """Parse a Xero timestamp string to datetime.

    Xero returns dates in formats like:
    - /Date(1686816000000+0000)/   (JSON .NET format)
    - 2024-06-15T10:30:00          (ISO 8601)
    """
    if not ts:
        return None
    try:
        # Handle Xero's /Date(...)/ format
        if ts.startswith("/Date("):
            ms_str = ts.split("(")[1].split("+")[0].split("-")[0].split(")")[0]
            return datetime.fromtimestamp(int(ms_str) / 1000, tz=UTC)
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError, IndexError):
        return None


def _safe_json(val: Any) -> Any:
    """Ensure a value is JSON-serializable (handle nested dicts)."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def _get_where_filter(entity_type: str) -> str | None:
    """Return the Xero 'where' filter clause for shared endpoints.

    Contacts endpoint serves both vendors and customers.
    Invoices endpoint serves both bills (ACCPAY) and invoices (ACCREC).
    """
    filters: dict[str, str] = {
        "vendor": "IsSupplier==true",
        "customer": "IsCustomer==true",
        "bill": 'Type=="ACCPAY"',
        "invoice": 'Type=="ACCREC"',
    }
    return filters.get(entity_type)


# ---------------------------------------------------------------------------
# Vendor (Xero Contact with IsSupplier=true)
# ---------------------------------------------------------------------------


def map_vendor_inbound(xero_data: dict) -> dict:
    """Map Xero Contact response to sample_vendors fields."""
    phones = xero_data.get("Phones") or []
    phone_number = None
    for p in phones:
        if p.get("PhoneType") == "DEFAULT" and p.get("PhoneNumber"):
            phone_number = p["PhoneNumber"]
            break

    return {
        "name": xero_data.get("Name", ""),
        "email_address": xero_data.get("EmailAddress"),
        "phone": phone_number,
        "tax_number": xero_data.get("TaxNumber"),
        "is_supplier": True,
        "is_customer": bool(xero_data.get("IsCustomer", False)),
        "status": "ACTIVE" if xero_data.get("ContactStatus") == "ACTIVE" else "ARCHIVED",
        "currency": xero_data.get("DefaultCurrency", ""),
        "address": _map_address_inbound(xero_data.get("Addresses")),
    }


def map_vendor_outbound(internal_data: dict) -> dict:
    """Map sample_vendors fields to Xero Contact create/update payload."""
    result: dict[str, Any] = {
        "Name": internal_data["name"],
        "IsSupplier": True,
    }

    if internal_data.get("email_address"):
        result["EmailAddress"] = internal_data["email_address"]

    if internal_data.get("phone"):
        result["Phones"] = [
            {"PhoneType": "DEFAULT", "PhoneNumber": internal_data["phone"]}
        ]

    if internal_data.get("tax_number"):
        result["TaxNumber"] = internal_data["tax_number"]

    if internal_data.get("currency"):
        result["DefaultCurrency"] = internal_data["currency"]

    addr = _map_address_outbound(
        internal_data.get("address") if isinstance(internal_data.get("address"), dict) else None
    )
    if addr:
        result["Addresses"] = [addr]

    return result


# ---------------------------------------------------------------------------
# Customer (Xero Contact with IsCustomer=true)
# ---------------------------------------------------------------------------


def map_customer_inbound(xero_data: dict) -> dict:
    """Map Xero Contact response to sample_vendors fields (customer variant)."""
    phones = xero_data.get("Phones") or []
    phone_number = None
    for p in phones:
        if p.get("PhoneType") == "DEFAULT" and p.get("PhoneNumber"):
            phone_number = p["PhoneNumber"]
            break

    return {
        "name": xero_data.get("Name", ""),
        "email_address": xero_data.get("EmailAddress"),
        "phone": phone_number,
        "tax_number": xero_data.get("TaxNumber"),
        "is_supplier": bool(xero_data.get("IsSupplier", False)),
        "is_customer": True,
        "status": "ACTIVE" if xero_data.get("ContactStatus") == "ACTIVE" else "ARCHIVED",
        "currency": xero_data.get("DefaultCurrency", ""),
        "address": _map_address_inbound(xero_data.get("Addresses")),
    }


def map_customer_outbound(internal_data: dict) -> dict:
    """Map sample_vendors fields to Xero Contact payload (customer variant)."""
    result: dict[str, Any] = {
        "Name": internal_data["name"],
        "IsCustomer": True,
    }

    if internal_data.get("email_address"):
        result["EmailAddress"] = internal_data["email_address"]

    if internal_data.get("phone"):
        result["Phones"] = [
            {"PhoneType": "DEFAULT", "PhoneNumber": internal_data["phone"]}
        ]

    if internal_data.get("tax_number"):
        result["TaxNumber"] = internal_data["tax_number"]

    if internal_data.get("currency"):
        result["DefaultCurrency"] = internal_data["currency"]

    addr = _map_address_outbound(
        internal_data.get("address") if isinstance(internal_data.get("address"), dict) else None
    )
    if addr:
        result["Addresses"] = [addr]

    return result


# ---------------------------------------------------------------------------
# Bill (Xero Invoice with Type=ACCPAY)
# ---------------------------------------------------------------------------


def map_bill_inbound(xero_data: dict) -> dict:
    """Map Xero Invoice (ACCPAY) response to sample_bills fields."""
    contact = xero_data.get("Contact") or {}

    line_items = []
    for line in xero_data.get("LineItems") or []:
        mapped_line: dict[str, Any] = {
            "description": line.get("Description", ""),
            "quantity": float(line.get("Quantity", 1)),
            "unit_price": float(line.get("UnitAmount", 0)),
            "total": float(line.get("LineAmount", 0)),
        }
        line_items.append(mapped_line)

    total = float(xero_data.get("Total", 0))
    amount_due = float(xero_data.get("AmountDue", 0))

    # Map Xero status → internal status
    xero_status = xero_data.get("Status", "")
    if xero_status == "PAID" or (amount_due == 0 and total > 0):
        status = "paid"
    elif xero_status == "AUTHORISED":
        status = "pending"
    elif xero_status == "DRAFT":
        status = "pending"
    elif xero_status == "VOIDED":
        status = "voided"
    else:
        status = "pending"

    return {
        "bill_number": xero_data.get("InvoiceNumber"),
        "vendor_external_id": contact.get("ContactID"),
        "vendor_name": contact.get("Name"),
        "amount": total,
        "date": _parse_xero_timestamp(xero_data.get("DateString") or xero_data.get("Date")),
        "due_date": _parse_xero_timestamp(xero_data.get("DueDateString") or xero_data.get("DueDate")),
        "paid_on_date": (
            _parse_xero_timestamp(xero_data.get("FullyPaidOnDate")) if status == "paid" else None
        ),
        "description": (line_items[0]["description"] if line_items else None),
        "currency": xero_data.get("CurrencyCode", ""),
        "status": status,
        "line_items": line_items,
    }


def map_bill_outbound(internal_data: dict) -> dict:
    """Map sample_bills fields to Xero Invoice (ACCPAY) payload."""
    result: dict[str, Any] = {
        "Type": "ACCPAY",
        "Status": "DRAFT",
    }

    if internal_data.get("bill_number"):
        result["InvoiceNumber"] = internal_data["bill_number"]

    if internal_data.get("date"):
        date_val = internal_data["date"]
        if isinstance(date_val, datetime):
            result["DateString"] = date_val.strftime("%Y-%m-%d")
        else:
            result["DateString"] = str(date_val)[:10]

    if internal_data.get("due_date"):
        due_val = internal_data["due_date"]
        if isinstance(due_val, datetime):
            result["DueDateString"] = due_val.strftime("%Y-%m-%d")
        else:
            result["DueDateString"] = str(due_val)[:10]

    if internal_data.get("currency"):
        result["CurrencyCode"] = internal_data["currency"]

    # Contact reference
    if internal_data.get("vendor_external_id"):
        result["Contact"] = {"ContactID": internal_data["vendor_external_id"]}

    # Line items
    line_items = _safe_json(internal_data.get("line_items")) or []
    xero_lines = []
    for item in line_items:
        if isinstance(item, dict):
            xero_lines.append({
                "Description": item.get("description", ""),
                "Quantity": float(item.get("quantity", 1)),
                "UnitAmount": float(item.get("unit_price", 0)),
                "AccountCode": "400",  # Default expense account
            })

    if not xero_lines:
        xero_lines.append({
            "Description": internal_data.get("description", "Expense"),
            "Quantity": 1,
            "UnitAmount": float(internal_data.get("amount", 0)),
            "AccountCode": "400",
        })

    result["LineItems"] = xero_lines
    return result


# ---------------------------------------------------------------------------
# Invoice (Xero Invoice with Type=ACCREC)
# ---------------------------------------------------------------------------


def map_invoice_inbound(xero_data: dict) -> dict:
    """Map Xero Invoice (ACCREC) response to sample_invoices fields."""
    contact = xero_data.get("Contact") or {}

    line_items = []
    sub_total = float(xero_data.get("SubTotal", 0))
    for line in xero_data.get("LineItems") or []:
        mapped_line: dict[str, Any] = {
            "description": line.get("Description", ""),
            "quantity": float(line.get("Quantity", 1)),
            "unit_price": float(line.get("UnitAmount", 0)),
            "total": float(line.get("LineAmount", 0)),
        }
        line_items.append(mapped_line)

    total_amount = float(xero_data.get("Total", 0))
    total_tax = float(xero_data.get("TotalTax", 0))
    amount_due = float(xero_data.get("AmountDue", 0))

    if sub_total == 0:
        sub_total = total_amount - total_tax

    # Status mapping
    xero_status = xero_data.get("Status", "")
    if xero_status == "PAID" or (amount_due == 0 and total_amount > 0):
        status = "PAID"
    elif xero_status == "SUBMITTED":
        status = "SUBMITTED"
    elif xero_status == "AUTHORISED":
        status = "SUBMITTED"
    elif xero_status == "VOIDED":
        status = "VOIDED"
    else:
        status = "DRAFT"

    return {
        "invoice_number": xero_data.get("InvoiceNumber"),
        "contact_external_id": contact.get("ContactID"),
        "contact_name": contact.get("Name"),
        "issue_date": _parse_xero_timestamp(xero_data.get("DateString") or xero_data.get("Date")),
        "due_date": _parse_xero_timestamp(xero_data.get("DueDateString") or xero_data.get("DueDate")),
        "paid_on_date": (
            _parse_xero_timestamp(xero_data.get("FullyPaidOnDate")) if status == "PAID" else None
        ),
        "memo": xero_data.get("Reference"),
        "currency": xero_data.get("CurrencyCode", ""),
        "exchange_rate": xero_data.get("CurrencyRate"),
        "sub_total": sub_total,
        "total_tax_amount": total_tax,
        "total_amount": total_amount,
        "balance": amount_due,
        "status": status,
        "line_items": line_items,
        "tracking_categories": None,
        "bill_email": None,
    }


def map_invoice_outbound(internal_data: dict) -> dict:
    """Map sample_invoices fields to Xero Invoice (ACCREC) payload."""
    result: dict[str, Any] = {
        "Type": "ACCREC",
        "Status": "DRAFT",
    }

    if internal_data.get("invoice_number"):
        result["InvoiceNumber"] = internal_data["invoice_number"]

    if internal_data.get("issue_date"):
        date_val = internal_data["issue_date"]
        if isinstance(date_val, datetime):
            result["DateString"] = date_val.strftime("%Y-%m-%d")
        else:
            result["DateString"] = str(date_val)[:10]

    if internal_data.get("due_date"):
        due_val = internal_data["due_date"]
        if isinstance(due_val, datetime):
            result["DueDateString"] = due_val.strftime("%Y-%m-%d")
        else:
            result["DueDateString"] = str(due_val)[:10]

    if internal_data.get("currency"):
        result["CurrencyCode"] = internal_data["currency"]

    if internal_data.get("memo"):
        result["Reference"] = internal_data["memo"]

    # Contact reference
    if internal_data.get("contact_external_id"):
        result["Contact"] = {"ContactID": internal_data["contact_external_id"]}

    # Line items
    line_items = _safe_json(internal_data.get("line_items")) or []
    xero_lines = []
    for item in line_items:
        if isinstance(item, dict):
            xero_lines.append({
                "Description": item.get("description", ""),
                "Quantity": float(item.get("quantity", 1)),
                "UnitAmount": float(item.get("unit_price", 0)),
                "AccountCode": "200",  # Default revenue account
            })

    if not xero_lines:
        xero_lines.append({
            "Description": internal_data.get("memo", "Service"),
            "Quantity": 1,
            "UnitAmount": float(internal_data.get("total_amount", 0)),
            "AccountCode": "200",
        })

    result["LineItems"] = xero_lines
    return result


# ---------------------------------------------------------------------------
# Chart of Accounts
# ---------------------------------------------------------------------------


def map_chart_of_accounts_inbound(xero_data: dict) -> dict:
    """Map Xero Account response to sample_chart_of_accounts fields."""
    return {
        "name": xero_data.get("Name", ""),
        "account_number": xero_data.get("Code"),
        "account_type": xero_data.get("Type", ""),
        "account_sub_type": xero_data.get("SystemAccount"),
        "classification": xero_data.get("Class"),
        "current_balance": None,  # Xero doesn't include balance in account list
        "currency": xero_data.get("CurrencyCode", ""),
        "description": xero_data.get("Description"),
        "active": xero_data.get("Status") == "ACTIVE",
        "parent_account_external_id": None,  # Xero accounts are flat
    }


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


def map_item_inbound(xero_data: dict) -> dict:
    """Map Xero Item response to internal item format."""
    purchase = xero_data.get("PurchaseDetails") or {}
    sales = xero_data.get("SalesDetails") or {}

    return {
        "name": xero_data.get("Name", ""),
        "code": xero_data.get("Code"),
        "description": xero_data.get("Description"),
        "purchase_description": purchase.get("UnitPrice"),
        "sale_description": sales.get("UnitPrice"),
        "is_sold": xero_data.get("IsSold", False),
        "is_purchased": xero_data.get("IsPurchased", False),
        "active": True,  # Xero items don't have a status field; assume active
    }


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


def map_payment_inbound(xero_data: dict) -> dict:
    """Map Xero Payment response to internal payment format."""
    invoice = xero_data.get("Invoice") or {}
    account = xero_data.get("Account") or {}

    return {
        "amount": float(xero_data.get("Amount", 0)),
        "date": _parse_xero_timestamp(xero_data.get("DateString") or xero_data.get("Date")),
        "reference": xero_data.get("Reference"),
        "currency": xero_data.get("CurrencyCode", ""),
        "status": xero_data.get("Status", ""),
        "invoice_external_id": invoice.get("InvoiceID"),
        "invoice_number": invoice.get("InvoiceNumber"),
        "account_external_id": account.get("AccountID"),
        "is_reconciled": xero_data.get("IsReconciled", False),
    }


# ---------------------------------------------------------------------------
# Registry — maps entity_type to mapper functions
# ---------------------------------------------------------------------------

INBOUND_MAPPERS: dict[str, Any] = {
    "vendor": map_vendor_inbound,
    "customer": map_customer_inbound,
    "bill": map_bill_inbound,
    "invoice": map_invoice_inbound,
    "chart_of_accounts": map_chart_of_accounts_inbound,
    "item": map_item_inbound,
    "payment": map_payment_inbound,
}

OUTBOUND_MAPPERS: dict[str, Any] = {
    "vendor": map_vendor_outbound,
    "customer": map_customer_outbound,
    "bill": map_bill_outbound,
    "invoice": map_invoice_outbound,
}
