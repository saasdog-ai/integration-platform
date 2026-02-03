"""QuickBooks Online constants — entity ordering, API names, field lists."""

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

# Our entity_type string → QBO API entity name (used in queries and URLs)
QBO_ENTITY_NAMES: dict[str, str] = {
    "vendor": "Vendor",
    "customer": "Customer",
    "chart_of_accounts": "Account",
    "item": "Item",
    "bill": "Bill",
    "invoice": "Invoice",
    "payment": "Payment",
    "employee": "Employee",
}

# QBO API entity name → our entity_type string (reverse lookup)
QBO_ENTITY_TYPES: dict[str, str] = {v: k for k, v in QBO_ENTITY_NAMES.items()}

# Display names for logging
ENTITY_DISPLAY_NAMES: dict[str, str] = {
    "vendor": "Vendor",
    "customer": "Customer",
    "chart_of_accounts": "Chart of Accounts",
    "item": "Item",
    "bill": "Bill",
    "invoice": "Invoice",
    "payment": "Payment",
    "employee": "Employee",
}

# QBO API pagination limit
QBO_MAX_RESULTS = 1000

# QBO OAuth endpoints
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
