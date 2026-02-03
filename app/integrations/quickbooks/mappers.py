"""Schema mappers between QBO API format and internal system format.

Each entity has an inbound mapper (QBO → internal) and an outbound mapper
(internal → QBO). These are the functions users would customize or ask
Claude Code to generate for their specific integration.
"""

import json
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_address_inbound(qbo_addr: dict | None) -> dict | None:
    """Map a QBO address object to our internal address format."""
    if not qbo_addr:
        return None
    return {
        "street_1": qbo_addr.get("Line1"),
        "street_2": qbo_addr.get("Line2"),
        "city": qbo_addr.get("City"),
        "state": qbo_addr.get("CountrySubDivisionCode"),
        "zip_code": qbo_addr.get("PostalCode"),
        "country": qbo_addr.get("Country", "US"),
    }


def _map_address_outbound(addr: dict | None) -> dict | None:
    """Map our internal address to QBO address format."""
    if not addr:
        return None
    result: dict[str, Any] = {}
    if addr.get("street_1"):
        result["Line1"] = addr["street_1"]
    if addr.get("street_2"):
        result["Line2"] = addr["street_2"]
    if addr.get("city"):
        result["City"] = addr["city"]
    if addr.get("state"):
        result["CountrySubDivisionCode"] = addr["state"]
    if addr.get("zip_code"):
        result["PostalCode"] = addr["zip_code"]
    if addr.get("country"):
        result["Country"] = addr["country"]
    return result or None


def _parse_qbo_timestamp(ts: str | None) -> datetime | None:
    """Parse a QBO ISO-8601 timestamp string to datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _safe_json(val: Any) -> Any:
    """Ensure a value is JSON-serializable (handle nested dicts from QBO)."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


# ---------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------

def map_vendor_inbound(qbo_data: dict) -> dict:
    """Map QBO Vendor response to sample_vendors fields."""
    email_obj = qbo_data.get("PrimaryEmailAddr") or {}
    phone_obj = qbo_data.get("PrimaryPhone") or {}

    return {
        "name": qbo_data.get("DisplayName", ""),
        "email_address": email_obj.get("Address"),
        "phone": phone_obj.get("FreeFormNumber"),
        "tax_number": qbo_data.get("TaxIdentifier"),
        "is_supplier": True,
        "is_customer": False,
        "status": "ACTIVE" if qbo_data.get("Active", True) else "ARCHIVED",
        "currency": (qbo_data.get("CurrencyRef") or {}).get("value", "USD"),
        "address": _map_address_inbound(qbo_data.get("BillAddr")),
    }


def map_vendor_outbound(internal_data: dict) -> dict:
    """Map sample_vendors fields to QBO Vendor create/update payload."""
    result: dict[str, Any] = {
        "DisplayName": internal_data["name"],
    }

    if internal_data.get("email_address"):
        result["PrimaryEmailAddr"] = {"Address": internal_data["email_address"]}

    if internal_data.get("phone"):
        result["PrimaryPhone"] = {"FreeFormNumber": internal_data["phone"]}

    if internal_data.get("tax_number"):
        result["TaxIdentifier"] = internal_data["tax_number"]

    if internal_data.get("currency"):
        result["CurrencyRef"] = {"value": internal_data["currency"]}

    addr = _map_address_outbound(
        internal_data.get("address") if isinstance(internal_data.get("address"), dict) else None
    )
    if addr:
        result["BillAddr"] = addr

    return result


# ---------------------------------------------------------------------------
# Bill
# ---------------------------------------------------------------------------

def map_bill_inbound(qbo_data: dict) -> dict:
    """Map QBO Bill response to sample_bills fields."""
    vendor_ref = qbo_data.get("VendorRef") or {}
    meta = qbo_data.get("MetaData") or {}

    # Map QBO line items to our format
    line_items = []
    for line in qbo_data.get("Line", []):
        # Skip subtotal lines
        if line.get("DetailType") == "SubTotalLineDetail":
            continue
        mapped_line: dict[str, Any] = {
            "description": line.get("Description", ""),
            "quantity": 1,
            "unit_price": float(line.get("Amount", 0)),
            "total": float(line.get("Amount", 0)),
        }
        # Extract quantity/unit_price from detail if available
        detail = (
            line.get("ItemBasedExpenseLineDetail")
            or line.get("AccountBasedExpenseLineDetail")
            or {}
        )
        if detail.get("Qty"):
            mapped_line["quantity"] = float(detail["Qty"])
            mapped_line["unit_price"] = float(detail.get("UnitPrice", 0))
        line_items.append(mapped_line)

    # Map status: QBO doesn't have a status field on Bill directly;
    # determine from Balance vs TotalAmt
    total = float(qbo_data.get("TotalAmt", 0))
    balance = float(qbo_data.get("Balance", 0))
    if balance == 0 and total > 0:
        status = "paid"
    elif qbo_data.get("DueDate"):
        due = _parse_qbo_timestamp(qbo_data["DueDate"])
        if due:
            # Ensure timezone-aware comparison (QBO dates may be naive)
            now = datetime.now(timezone.utc)
            due_aware = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
            if due_aware < now:
                status = "overdue"
            else:
                status = "pending"
        else:
            status = "pending"
    else:
        status = "pending"

    return {
        "bill_number": qbo_data.get("DocNumber"),
        "vendor_external_id": vendor_ref.get("value"),
        "vendor_name": vendor_ref.get("name"),
        "amount": total,
        "date": _parse_qbo_timestamp(qbo_data.get("TxnDate")),
        "due_date": _parse_qbo_timestamp(qbo_data.get("DueDate")),
        "paid_on_date": _parse_qbo_timestamp(meta.get("LastUpdatedTime")) if status == "paid" else None,
        "description": (line_items[0]["description"] if line_items else None),
        "currency": (qbo_data.get("CurrencyRef") or {}).get("value", "USD"),
        "status": status,
        "line_items": line_items,
    }


def map_bill_outbound(internal_data: dict) -> dict:
    """Map sample_bills fields to QBO Bill create/update payload."""
    result: dict[str, Any] = {}

    if internal_data.get("bill_number"):
        result["DocNumber"] = internal_data["bill_number"]

    if internal_data.get("date"):
        date_val = internal_data["date"]
        if isinstance(date_val, datetime):
            result["TxnDate"] = date_val.strftime("%Y-%m-%d")
        else:
            result["TxnDate"] = str(date_val)[:10]

    if internal_data.get("due_date"):
        due_val = internal_data["due_date"]
        if isinstance(due_val, datetime):
            result["DueDate"] = due_val.strftime("%Y-%m-%d")
        else:
            result["DueDate"] = str(due_val)[:10]

    if internal_data.get("currency"):
        result["CurrencyRef"] = {"value": internal_data["currency"]}

    # VendorRef — requires the QBO vendor ID (external_id), not our internal UUID
    if internal_data.get("vendor_external_id"):
        result["VendorRef"] = {"value": internal_data["vendor_external_id"]}

    # Line items
    line_items = _safe_json(internal_data.get("line_items")) or []
    qbo_lines = []
    for item in line_items:
        if isinstance(item, dict):
            qbo_lines.append({
                "Amount": float(item.get("total", item.get("unit_price", 0))),
                "Description": item.get("description", ""),
                "DetailType": "AccountBasedExpenseLineDetail",
                "AccountBasedExpenseLineDetail": {
                    "AccountRef": {"value": "1"},  # Default expense account
                },
            })

    if not qbo_lines:
        # QBO requires at least one line item
        qbo_lines.append({
            "Amount": float(internal_data.get("amount", 0)),
            "Description": internal_data.get("description", "Expense"),
            "DetailType": "AccountBasedExpenseLineDetail",
            "AccountBasedExpenseLineDetail": {
                "AccountRef": {"value": "1"},
            },
        })

    result["Line"] = qbo_lines
    return result


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

def map_invoice_inbound(qbo_data: dict) -> dict:
    """Map QBO Invoice response to sample_invoices fields."""
    customer_ref = qbo_data.get("CustomerRef") or {}
    meta = qbo_data.get("MetaData") or {}

    # Map line items
    line_items = []
    sub_total = 0.0
    for line in qbo_data.get("Line", []):
        if line.get("DetailType") == "SubTotalLineDetail":
            sub_total = float(line.get("Amount", 0))
            continue
        if line.get("DetailType") == "DiscountLineDetail":
            continue
        mapped_line: dict[str, Any] = {
            "description": line.get("Description", ""),
            "quantity": 1,
            "unit_price": float(line.get("Amount", 0)),
            "total": float(line.get("Amount", 0)),
        }
        detail = line.get("SalesItemLineDetail") or {}
        if detail.get("Qty"):
            mapped_line["quantity"] = float(detail["Qty"])
            mapped_line["unit_price"] = float(detail.get("UnitPrice", 0))
        line_items.append(mapped_line)

    total_amount = float(qbo_data.get("TotalAmt", 0))
    balance = float(qbo_data.get("Balance", 0))
    if sub_total == 0:
        sub_total = total_amount

    total_tax = total_amount - sub_total if total_amount > sub_total else 0

    # Status mapping
    if balance == 0 and total_amount > 0:
        status = "PAID"
    elif qbo_data.get("EmailStatus") == "EmailSent":
        status = "SUBMITTED"
    else:
        status = "DRAFT"

    bill_email = qbo_data.get("BillEmail") or {}

    return {
        "invoice_number": qbo_data.get("DocNumber"),
        "contact_external_id": customer_ref.get("value"),
        "contact_name": customer_ref.get("name"),
        "issue_date": _parse_qbo_timestamp(qbo_data.get("TxnDate")),
        "due_date": _parse_qbo_timestamp(qbo_data.get("DueDate")),
        "paid_on_date": _parse_qbo_timestamp(meta.get("LastUpdatedTime")) if status == "PAID" else None,
        "memo": qbo_data.get("PrivateNote"),
        "currency": (qbo_data.get("CurrencyRef") or {}).get("value", "USD"),
        "exchange_rate": None,
        "sub_total": sub_total,
        "total_tax_amount": total_tax,
        "total_amount": total_amount,
        "balance": balance,
        "status": status,
        "line_items": line_items,
        "tracking_categories": None,
        "bill_email": bill_email.get("Address"),
    }


def map_invoice_outbound(internal_data: dict) -> dict:
    """Map sample_invoices fields to QBO Invoice create/update payload."""
    result: dict[str, Any] = {}

    if internal_data.get("invoice_number"):
        result["DocNumber"] = internal_data["invoice_number"]

    if internal_data.get("issue_date"):
        date_val = internal_data["issue_date"]
        if isinstance(date_val, datetime):
            result["TxnDate"] = date_val.strftime("%Y-%m-%d")
        else:
            result["TxnDate"] = str(date_val)[:10]

    if internal_data.get("due_date"):
        due_val = internal_data["due_date"]
        if isinstance(due_val, datetime):
            result["DueDate"] = due_val.strftime("%Y-%m-%d")
        else:
            result["DueDate"] = str(due_val)[:10]

    if internal_data.get("currency"):
        result["CurrencyRef"] = {"value": internal_data["currency"]}

    if internal_data.get("memo"):
        result["PrivateNote"] = internal_data["memo"]

    # CustomerRef — requires QBO customer ID
    if internal_data.get("contact_external_id"):
        result["CustomerRef"] = {"value": internal_data["contact_external_id"]}

    if internal_data.get("bill_email"):
        result["BillEmail"] = {"Address": internal_data["bill_email"]}

    # Line items
    line_items = _safe_json(internal_data.get("line_items")) or []
    qbo_lines = []
    for item in line_items:
        if isinstance(item, dict):
            qbo_lines.append({
                "Amount": float(item.get("total", item.get("unit_price", 0))),
                "Description": item.get("description", ""),
                "DetailType": "SalesItemLineDetail",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": "1", "name": "Services"},
                    "Qty": float(item.get("quantity", 1)),
                    "UnitPrice": float(item.get("unit_price", 0)),
                },
            })

    if not qbo_lines:
        qbo_lines.append({
            "Amount": float(internal_data.get("total_amount", 0)),
            "Description": internal_data.get("memo", "Service"),
            "DetailType": "SalesItemLineDetail",
            "SalesItemLineDetail": {
                "ItemRef": {"value": "1", "name": "Services"},
                "Qty": 1,
                "UnitPrice": float(internal_data.get("total_amount", 0)),
            },
        })

    result["Line"] = qbo_lines
    return result


# ---------------------------------------------------------------------------
# Chart of Accounts
# ---------------------------------------------------------------------------

def map_chart_of_accounts_inbound(qbo_data: dict) -> dict:
    """Map QBO Account response to sample_chart_of_accounts fields."""
    return {
        "name": qbo_data.get("Name", ""),
        "account_number": qbo_data.get("AcctNum"),
        "account_type": qbo_data.get("AccountType", ""),
        "account_sub_type": qbo_data.get("AccountSubType"),
        "classification": qbo_data.get("Classification"),
        "current_balance": float(qbo_data.get("CurrentBalance", 0)),
        "currency": (qbo_data.get("CurrencyRef") or {}).get("value", "USD"),
        "description": qbo_data.get("Description"),
        "active": qbo_data.get("Active", True),
        "parent_account_external_id": (qbo_data.get("ParentRef") or {}).get("value"),
    }


# ---------------------------------------------------------------------------
# Registry — maps entity_type to mapper functions
# ---------------------------------------------------------------------------

INBOUND_MAPPERS: dict[str, Any] = {
    "vendor": map_vendor_inbound,
    "bill": map_bill_inbound,
    "invoice": map_invoice_inbound,
    "chart_of_accounts": map_chart_of_accounts_inbound,
}

OUTBOUND_MAPPERS: dict[str, Any] = {
    "vendor": map_vendor_outbound,
    "bill": map_bill_outbound,
    "invoice": map_invoice_outbound,
}
