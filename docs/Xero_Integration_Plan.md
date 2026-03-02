# Xero Integration Adapter — Implementation Plan

> **Also serves as a template for adding any new integration adapter** (e.g., HubSpot, NetSuite, Sage).
> Replace "Xero" with your integration name and follow the same structure.

## Context

The integration-platform has a working QuickBooks Online (QBO) adapter as the reference implementation. The Xero adapter follows the same pattern, supporting all 7 entities: vendor, customer, chart_of_accounts, item, bill, invoice, payment. Xero API credentials (Client ID + Secret) are registered as a Web App with redirect URI `http://localhost:4000/integrations/oauth/callback`.

Xero is already seeded in the DB (`id: 22222222-2222-2222-2222-222222222222`) but with incomplete entity support — needs updating.

**Key constraint**: No integration-specific logic in the framework. All framework changes must be generic hooks usable by any future adapter (proving the platform's extensibility).

---

## Architecture Overview

Each integration adapter consists of 5 files in `app/integrations/<name>/`:

| File | Purpose | Reference |
|------|---------|-----------|
| `constants.py` | Entity ordering, API endpoint mappings, OAuth URLs, pagination limits | `app/integrations/quickbooks/constants.py` |
| `mappers.py` | Inbound (external→internal) and outbound (internal→external) schema mappers per entity | `app/integrations/quickbooks/mappers.py` |
| `client.py` | `<Name>Adapter(IntegrationAdapterInterface)` — OAuth, HTTP CRUD | `app/integrations/quickbooks/client.py` |
| `strategy.py` | `<Name>SyncStrategy` — sync orchestration with version vectors | `app/integrations/quickbooks/strategy.py` |
| `__init__.py` | Package exports | `app/integrations/quickbooks/__init__.py` |

Plus 2 registration points and a DB migration.

### What you reuse (do NOT duplicate):
- **`InternalDataRepository`** (`app/integrations/quickbooks/internal_repo.py`) — accesses the same internal tables (sample_vendors, sample_bills, etc.). All adapters share it.
- **`IntegrationAdapterInterface`** (`app/domain/interfaces.py`) — 8 required methods + optional hooks
- **Sync orchestrator** (`app/services/sync_orchestrator.py`) — calls your strategy generically
- **Integration service** (`app/services/integration_service.py`) — OAuth flow, no adapter-specific code
- **Adapter factory** (`app/infrastructure/adapters/factory.py`) — registry pattern

---

## Files to Create (7 new files)

### 1. `app/integrations/xero/__init__.py`
Package init with public exports (XeroAdapter, XeroSyncStrategy, constants).

### 2. `app/integrations/xero/constants.py` (~70 lines)
- **Entity ordering** (same dependency chain: vendor → customer → chart_of_accounts → item → bill → invoice → payment)
- **`XERO_ENTITY_ENDPOINTS`**: maps internal entity types to Xero API paths
  - `vendor` → `Contacts`, `customer` → `Contacts` (shared endpoint)
  - `chart_of_accounts` → `Accounts`, `item` → `Items`
  - `bill` → `Invoices`, `invoice` → `Invoices` (shared endpoint)
  - `payment` → `Payments`
- **`XERO_ENTITY_ID_FIELDS`**: maps entity types to Xero's ID field names (`ContactID`, `InvoiceID`, etc.)
- **OAuth URLs**: authorization (`https://login.xero.com/identity/connect/authorize`), token (`https://identity.xero.com/connect/token`), connections (`https://api.xero.com/connections`)
- **API base URL**: `https://api.xero.com/api.xro/2.0`
- **Page size**: 100 (Xero default)

### 3. `app/integrations/xero/mappers.py` (~400 lines)
14 mapper functions (7 inbound + 7 outbound, though some entities are inbound-only):

**Key design — shared Xero endpoints map to separate internal entities:**
- `Contacts` endpoint → vendor (filter: `IsSupplier=true`) AND customer (filter: `IsCustomer=true`)
- `Invoices` endpoint → bill (filter: `Type=ACCPAY`) AND invoice (filter: `Type=ACCREC`)

**Mapper registries:**
- `INBOUND_MAPPERS`: all 7 entities
- `OUTBOUND_MAPPERS`: vendor, customer, bill, invoice (chart_of_accounts/item/payment are read-only initially)

**Entity field mappings:**

| Internal Entity | Xero API Entity | Key Xero Fields |
|----------------|-----------------|-----------------|
| vendor | Contact (IsSupplier=true) | ContactID, Name, EmailAddress, Phones, TaxNumber, ContactStatus, DefaultCurrency, Addresses |
| customer | Contact (IsCustomer=true) | Same as vendor |
| chart_of_accounts | Account | AccountID, Name, Code, Type, Status, Description, CurrencyCode |
| item | Item | ItemID, Code, Description, SalesDetails.UnitPrice, PurchaseDetails.UnitPrice |
| bill | Invoice (Type=ACCPAY) | InvoiceID, InvoiceNumber, Contact.ContactID, Date, DueDate, Total, LineItems, Status, CurrencyCode |
| invoice | Invoice (Type=ACCREC) | Same as bill |
| payment | Payment | PaymentID, Invoice.InvoiceID, Amount, Date, Status, Reference |

### 4. `app/integrations/xero/client.py` (~350 lines)
`XeroAdapter(IntegrationAdapterInterface)` with:

- **OAuth**: `authenticate()` exchanges code for tokens via `POST https://identity.xero.com/connect/token` with Basic auth header (base64-encoded `client_id:client_secret`).
- **`resolve_external_account_id()`**: Overrides the generic interface hook — calls `GET https://api.xero.com/connections` to get the Xero org tenant UUID. Called automatically by the framework after token exchange when `realm_id` is not provided by the frontend.
- **`refresh_token()`**: Standard OAuth2 refresh via same token endpoint with `grant_type=refresh_token`.
- **Headers**: Every API call includes `Xero-Tenant-Id: {tenant_id}` (stored as `external_account_id` on UserIntegration) plus `Authorization: Bearer {access_token}`.
- **`fetch_records()`**: Page-based pagination (`?page=N`), applies `where` filters for vendor/customer and bill/invoice splits, uses `If-Modified-Since` header for incremental sync.
- **`get_record()`**: `GET /{endpoint}/{id}`
- **`create_record()` / `update_record()`**: `POST /{endpoint}` (Xero uses POST for both; update includes the entity ID in the body).
- **`delete_record()`**: Archives by setting `ContactStatus=ARCHIVED` or equivalent.
- **Response parsing**: Xero wraps results in `{"Contacts": [...]}`, `{"Invoices": [...]}` etc.
- **Rate limits**: Xero allows 60 req/min per org, 5,000/day. Headers: `X-MinLimit-Remaining`, `X-DayLimit-Remaining`.

### 5. `app/integrations/xero/strategy.py` (~950 lines)
`XeroSyncStrategy` — near-copy of `QuickBooksSyncStrategy` with:
- Imports from `xero.constants` and `xero.mappers` instead of `quickbooks.*`
- Reuses `InternalDataRepository` from quickbooks (same internal tables)
- No SyncToken handling (Xero doesn't use optimistic locking tokens)
- Same inbound/outbound/bidirectional sync logic, version vector equalization, batch upsert, dependency resolution

**Strategy methods (same interface as QBO):**
- `get_entity_order(direction)` → ordered entity list
- `get_ordered_rules(rules, direction)` → sort enabled rules by dependency order
- `sync_entity_inbound(job, entity_type, adapter, state_repo, since, record_ids)` → external → internal
- `sync_entity_outbound(job, entity_type, adapter, state_repo, since, record_ids, rule)` → internal → external
- `sync_entity_bidirectional(job, entity_type, adapter, state_repo, rule, since, outbound_since, record_ids)` → both with conflict detection

---

## Change Detection & Sync Directions

### Inbound Change Detection (what changed in Xero?)

Xero supports the **`If-Modified-Since` HTTP header**. When included on a GET request, Xero returns only records with `UpdatedDateUTC` after that timestamp.

**Flow:**
1. **First sync**: No `since` cursor → fetch ALL records from Xero
2. **After sync**: Framework stores `max_external_updated_at` in `entity_sync_status` table
3. **Next sync**: Orchestrator passes that cursor as `since` to `adapter.fetch_records()` → adapter sets `If-Modified-Since` header → Xero returns only modified records
4. **Version vectors**: Each fetched record bumps `external_version_id` (ev) on its `IntegrationStateRecord`

This is analogous to QBO's `WHERE MetaData.LastUpdatedTime > '{since}'` — different mechanism, same framework interface.

### Outbound Change Detection (what changed internally?)

Uses **polling** (same as QBO):
1. Strategy queries internal DB for records where `updated_at > last_successful_sync_at`
2. Bumps `internal_version_id` (iv) on matching `IntegrationStateRecord`s
3. Records with `iv > last_sync_version_id` are pushed to Xero via `adapter.create_record()` or `adapter.update_record()`

### Bidirectional Sync

When a sync rule is configured as `BIDIRECTIONAL`, the strategy:
1. **Polls internal changes** → bumps iv for modified records
2. **Fetches external changes** from Xero (using `If-Modified-Since`) → bumps ev
3. **Classifies each record** using version vectors:
   - `ev > lsv` only → sync INBOUND (Xero → internal)
   - `iv > lsv` only → sync OUTBOUND (internal → Xero)
   - Both `iv > lsv` AND `ev > lsv` → **CONFLICT** → resolved by `master_if_conflict` setting:
     - `EXTERNAL` → Xero data wins (synced as inbound)
     - `OUR_SYSTEM` → internal data wins (synced as outbound)
   - `iv == ev == lsv` → in sync, skip
4. **Equalizes version vectors** after sync: `iv = ev = lsv = max(iv, ev)`

### Bidirectional Support per Entity

| Entity | Inbound (Xero→Internal) | Outbound (Internal→Xero) | Bidirectional | Notes |
|--------|------------------------|-------------------------|---------------|-------|
| vendor | Yes | Yes | Yes | POST to create/update Contact |
| customer | Yes | Yes | Yes | POST to create/update Contact |
| chart_of_accounts | Yes | No (initially) | No | Limited update support in Xero |
| item | Yes | No (initially) | No | POST to create, PUT to update |
| bill | Yes | Yes | Yes | POST to create/update Invoice (ACCPAY) |
| invoice | Yes | Yes | Yes | POST to create/update Invoice (ACCREC) |
| payment | Yes | No (initially) | No | Payments can only be created, not updated |

Outbound/bidirectional support for chart_of_accounts, item, and payment can be added later — the framework supports it, but the Xero API has limitations for these entities.

### 6. `alembic/versions/014_update_xero_integration.py` (~40 lines)
Updates the existing Xero row (`22222222-2222-2222-2222-222222222222`) to:
- `supported_entities`: `["vendor", "customer", "chart_of_accounts", "item", "bill", "invoice", "payment"]`
- `connection_config`: updated scopes (`accounting.contacts.read`, `accounting.transactions.read`, `accounting.settings.read`, `offline_access`)

### 7. `tests/unit/test_xero.py` (~400 lines)
- Mapper tests for all entities (full data, minimal data, edge cases like inactive/archived)
- Adapter helper tests (`_to_external_record`, `_get_where_filter`)
- Strategy ordering tests (entity order, ordered rules)
- Timestamp parsing tests
- ~50-60 test cases

---

## Files to Modify (6 existing files)

**Goal: No Xero-specific logic in the framework.** The only framework changes are generic hooks that any future adapter can use.

### 8. `app/core/config.py` (+3 lines)
Add after QBO config (line 100):
```python
# Xero
xero_client_id: str | None = Field(default=None)
xero_client_secret: str | None = Field(default=None)
```

### 9. `app/domain/interfaces.py` (+8 lines)
Add optional method to `IntegrationAdapterInterface`:
```python
async def resolve_external_account_id(self, access_token: str) -> str | None:
    """Resolve external account/tenant ID after OAuth token exchange.

    Override in adapters where the account ID is not provided in the
    OAuth callback URL (e.g., Xero requires a connections API call).
    Returns None by default (e.g., QBO gets realm_id from callback URL).
    """
    return None
```
This is the **generic hook** — no integration-specific code. Any adapter can override it.

### 10. `app/infrastructure/adapters/factory.py` (+3 lines)
Register in `get_adapter_factory()` after QBO registration (line 64):
```python
from app.integrations.xero.client import XeroAdapter
_factory_instance.register("Xero", XeroAdapter)
```

### 11. `app/services/sync_orchestrator.py` (+5 lines)
Register in `_init_strategies()` after QBO strategy (line 67):
```python
try:
    from app.integrations.xero.strategy import XeroSyncStrategy
    register_sync_strategy("Xero", XeroSyncStrategy)
except ImportError:
    pass
```

### 12. `app/services/integration_service.py` (~5 lines)
**Generic tenant/account ID resolution**: After `adapter.authenticate()` returns tokens (line 282), if `realm_id` is None, call the generic hook:
```python
if not realm_id:
    realm_id = await adapter.resolve_external_account_id(tokens.access_token)
```
This is **not integration-specific** — it calls the interface method. QBO's adapter returns `None` (default — QBO gets `realmId` from the callback URL). Xero's adapter calls its connections API. Any future adapter can override this hook without touching the framework.

### 13. `scripts/seed_sample_data.sql` (~3 lines changed)
Update Xero row: `supported_entities` → all 7, `connection_config` → updated scopes.

---

## Implementation Order

1. Config + constants (foundation)
2. Mappers (pure functions, easy to test in isolation)
3. Client/adapter (OAuth + HTTP)
4. Strategy (orchestration, uses mappers + adapter)
5. Registration (factory + orchestrator)
6. DB migration + seed update
7. Generic interface hook + integration service
8. Tests
9. Store Xero credentials as env vars (`XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`)

---

## Xero API Reference

### OAuth 2.0 (Authorization Code Flow)
- **Authorization URL**: `https://login.xero.com/identity/connect/authorize`
- **Token URL**: `https://identity.xero.com/connect/token`
- **Connections URL**: `https://api.xero.com/connections` (returns authorized tenant IDs)
- **Token auth**: HTTP Basic (`base64(client_id:client_secret)`)
- **Access token lifetime**: 30 minutes
- **Refresh token lifetime**: 60 days (single-use; each refresh returns a new one)
- **Scopes**: `accounting.contacts.read`, `accounting.transactions.read`, `accounting.settings.read`, `offline_access`

### API
- **Base URL**: `https://api.xero.com/api.xro/2.0`
- **Required header**: `Xero-Tenant-Id: {tenant_uuid}` on every API request
- **Pagination**: `?page=N` (default page size 100)
- **Incremental sync**: `If-Modified-Since` header (ISO 8601 UTC)
- **Filtering**: `?where=IsSupplier==true`, `?where=Type=="ACCPAY"`

### Rate Limits
- 60 requests/minute per organization
- 5,000 requests/day per organization
- 5 concurrent requests max
- Response headers: `X-MinLimit-Remaining`, `X-DayLimit-Remaining`
- 429 response with `Retry-After` header when exceeded

---

## Template: Adding a New Integration

To add a new integration (e.g., HubSpot), follow these steps:

### 1. Create adapter package
```
app/integrations/hubspot/
├── __init__.py
├── constants.py          # Entity ordering, API endpoints, OAuth URLs
├── mappers.py            # INBOUND_MAPPERS + OUTBOUND_MAPPERS dicts
├── client.py             # HubSpotAdapter(IntegrationAdapterInterface)
└── strategy.py           # HubSpotSyncStrategy (copy from QBO/Xero, change imports)
```

### 2. Register adapter + strategy
- `app/infrastructure/adapters/factory.py`: `_factory_instance.register("HubSpot", HubSpotAdapter)`
- `app/services/sync_orchestrator.py`: `register_sync_strategy("HubSpot", HubSpotSyncStrategy)`

### 3. Add config
- `app/core/config.py`: Add `hubspot_client_id`, `hubspot_client_secret` fields

### 4. Seed DB
- New migration: `INSERT INTO available_integrations` or `UPDATE` existing row
- Set `name`, `type`, `supported_entities`, `connection_config` (OAuth URLs + scopes)

### 5. Write tests
- `tests/unit/test_hubspot.py`: Mapper tests, adapter helper tests, strategy ordering

### 6. Implement required interface methods
Every adapter MUST implement (from `IntegrationAdapterInterface`):
- `authenticate(auth_code, redirect_uri, connection_config)` → `OAuthTokens`
- `refresh_token(refresh_token, connection_config)` → `OAuthTokens`
- `fetch_records(entity_type, since, page_token, record_ids)` → `(list[ExternalRecord], next_token)`
- `get_record(entity_type, external_id)` → `ExternalRecord | None`
- `create_record(entity_type, data)` → `ExternalRecord`
- `update_record(entity_type, external_id, data)` → `ExternalRecord`
- `delete_record(entity_type, external_id)` → `bool`

Optional hooks:
- `resolve_external_account_id(access_token)` → `str | None` (for tenant ID resolution post-OAuth)

### 7. Reuse InternalDataRepository
All adapters share the same internal tables. Import `InternalDataRepository` from `app/integrations/quickbooks/internal_repo.py` in your strategy. Do NOT create a new one.

---

## Verification

1. Run existing tests: `pytest tests/ -v --no-cov` — ensure no regressions
2. Run new tests: `pytest tests/unit/test_xero.py -v`
3. Run migration: `make migrate-upgrade`
4. Start backend, verify Xero appears in `GET /integrations/available`
5. Test OAuth flow end-to-end via saas-host-app UI (connect to Xero as Alice, verify tenant ID stored)
6. Trigger a sync job and verify entity fetch from Xero API
