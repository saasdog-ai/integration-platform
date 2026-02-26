"""Xero constants — entity ordering, API endpoints, field mappings."""

# Entity sync order. Dependencies must sync before dependents:
# - Vendors and Chart of Accounts before Bills (bills reference vendors and accounts)
# - Customers before Invoices (invoices reference customers)
INBOUND_ENTITY_ORDER = [
    "vendor",
    "customer",
    "chart_of_accounts",
    "item",
    "bill",
    "invoice",
    "payment",
]

OUTBOUND_ENTITY_ORDER = [
    "vendor",
    "customer",
    "chart_of_accounts",
    "item",
    "bill",
    "invoice",
    "payment",
]

# Our entity_type string → Xero API endpoint name
# Note: Xero uses shared endpoints (Contacts for both vendor/customer,
# Invoices for both bill/invoice), filtered via query parameters.
XERO_ENTITY_ENDPOINTS: dict[str, str] = {
    "vendor": "Contacts",
    "customer": "Contacts",
    "chart_of_accounts": "Accounts",
    "item": "Items",
    "bill": "Invoices",  # Type=ACCPAY
    "invoice": "Invoices",  # Type=ACCREC
    "payment": "Payments",
}

# Our entity_type → Xero's primary ID field in response objects
XERO_ENTITY_ID_FIELDS: dict[str, str] = {
    "vendor": "ContactID",
    "customer": "ContactID",
    "chart_of_accounts": "AccountID",
    "item": "ItemID",
    "bill": "InvoiceID",
    "invoice": "InvoiceID",
    "payment": "PaymentID",
}

# Display names for logging
ENTITY_DISPLAY_NAMES: dict[str, str] = {
    "vendor": "Vendor",
    "customer": "Customer",
    "chart_of_accounts": "Chart of Accounts",
    "item": "Item",
    "bill": "Bill",
    "invoice": "Invoice",
    "payment": "Payment",
}

# Xero API pagination page size
XERO_PAGE_SIZE = 100

# Xero OAuth endpoints
XERO_AUTHORIZATION_URL = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"

# Xero API base URL
XERO_API_BASE_URL = "https://api.xero.com/api.xro/2.0"
