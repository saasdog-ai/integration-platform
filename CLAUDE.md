# CLAUDE.md — Project Context for Claude Code

## What Is This Project?

A production-ready integration platform for syncing data between a SaaS application and external providers (ERPs like QuickBooks Online, CRMs, HRIS systems). Built as an alternative to expensive integration vendors (Workato, MuleSoft, Tray.io). Includes fully working QuickBooks Online and Xero integrations as reference implementations.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic
- **Database**: PostgreSQL 15+ on port 5433 (shared with sister project `import-export-orchestrator`)
- **Queue**: AWS SQS (production) / in-memory (development)
- **Encryption**: AWS KMS / Azure Key Vault / Fernet (development)
- **UI**: React micro-frontend (Vite, TypeScript, module federation)
- **Infrastructure**: Docker, Docker Compose, Terraform (AWS ECS/Fargate)
- **Testing**: pytest (async), 519 tests (unit + integration)

## Architecture

Hexagonal (clean) architecture with strict layer separation:

```
app/
  api/           HTTP endpoints, DTOs (request/response models)
  auth/          JWT auth (pluggable, dev mode uses X-Client-ID header)
  core/          Config, DI container, logging, middleware, exceptions
  domain/        Entities, enums, interfaces (pure, no dependencies)
  infrastructure/
    adapters/    Integration adapters (QuickBooks, mock)
    db/          SQLAlchemy models, repositories
    encryption/  KMS/KeyVault/Fernet
    queue/       SQS/in-memory
  integrations/
    shared/      Shared components: InternalDataRepository (sample DB access)
    quickbooks/  QBO-specific: strategy, mappers, constants, client
    xero/        Xero-specific: strategy, mappers, constants, client
  services/      Business logic: sync_orchestrator, sync_job_runner, integration_service, settings_service
```

### Key Patterns

- **Strategy pattern**: `QuickBooksSyncStrategy` and `XeroSyncStrategy` handle integration-specific sync logic; registered in `sync_orchestrator._SYNC_STRATEGIES`
- **Adapter pattern**: `IntegrationAdapterInterface` with factory-based creation
- **Repository pattern**: All DB access behind interfaces (`domain/interfaces.py`), implementations in `infrastructure/db/repositories.py`
- **DI container**: `core/dependency_injection.py`
- **Multi-tenancy**: `client_id` isolation throughout; composite PKs for partitioning

## Database Schema (key tables)

| Table | Purpose |
|-------|---------|
| `available_integrations` | Master catalog (QuickBooks, Xero, etc.) |
| `user_integrations` | User connections with encrypted credentials |
| `user_integration_settings` | Per-user sync rules (JSONB) |
| `system_integration_settings` | Default settings per integration |
| `sync_jobs` | Job execution history |
| `entity_sync_status` | Last sync time per entity type |
| `integration_state` | Record-level sync state (composite PK: `client_id + id`) |
| `integration_history` | Append-only sync audit log |
| `audit_log` | User/admin action audit trail (overrides, settings, connect/disconnect) |
| `sample_vendors` | Internal vendor records |
| `sample_bills` | Internal bill records |
| `sample_invoices` | Internal invoice records |
| `sample_chart_of_accounts` | Internal chart of accounts |

### Migrations (`alembic/versions/`)

001 Initial schema, 002 job_params column, 004 disconnected_at, 005 last_job_id, 006 unique constraints, 007 integration_history, 008 sample data tables, 009 split sync cursors, 010 equalize version vectors, 011-016 various, 017 audit_log table + sync override columns.

## Sync System

### Version Vectors

Every `IntegrationStateRecord` has three version fields:
- `internal_version_id` (iv) — bumped when our system changes the record
- `external_version_id` (ev) — bumped when external system changes the record
- `last_sync_version_id` (lsv) — set to `max(iv, ev)` after successful sync

Properties (defined in `domain/entities.py`):
- `is_in_sync`: `iv == ev == lsv`
- `needs_outbound_sync`: `iv > lsv`
- `needs_inbound_sync`: `ev > lsv`

After every successful sync, all three fields are equalized: `iv = ev = lsv = max(iv, ev)`.

### Sync Directions

Configured per entity type in `SyncRule`:
- **INBOUND**: external -> internal (fetch from QBO, write to our DB)
- **OUTBOUND**: internal -> external (read from our state records, push to QBO)
- **BIDIRECTIONAL**: both directions with conflict detection

### Conflict Resolution

When both sides changed (`needs_outbound_sync AND needs_inbound_sync`):
- `master_if_conflict = ConflictResolution.EXTERNAL` — QBO data wins (synced as INBOUND)
- `master_if_conflict = ConflictResolution.OUR_SYSTEM` — our data wins (synced as OUTBOUND)

The `sync_direction` field on `IntegrationStateRecord` always reflects the *actual direction of the last sync* (INBOUND or OUTBOUND) — never BIDIRECTIONAL.

### Sync Flow

1. User triggers sync via `POST /sync-jobs` or scheduler
2. Job queued to SQS (or in-memory queue in dev)
3. `SyncJobRunner` consumes message, calls `SyncOrchestrator.execute_sync_job()`
4. Orchestrator loads settings, resolves adapter, selects strategy
5. `_execute_with_strategy()` routes to:
   - `strategy.sync_entity_inbound()` for INBOUND rules
   - `strategy.sync_entity_outbound()` for OUTBOUND rules
   - `strategy.sync_entity_bidirectional()` for BIDIRECTIONAL rules
6. Strategy handles entity ordering, schema mapping, version equalization
7. History entries written for audit

### Integration Files

Both integrations live under `app/integrations/{name}/` and share the same structure:

| File | QBO (`quickbooks/`) | Xero (`xero/`) |
|------|---------------------|-----------------|
| `client.py` | `QuickBooksAdapter` — OAuth, QBO REST API | `XeroAdapter` — OAuth, Xero API v2.0 |
| `strategy.py` | `QuickBooksSyncStrategy` | `XeroSyncStrategy` |
| `mappers.py` | QBO ↔ internal schema | Xero ↔ internal schema (7 entities incl. item, payment) |
| `constants.py` | Entity ordering, QBO endpoints | Entity ordering, Xero endpoints, OAuth URLs |

Shared: `app/integrations/shared/internal_repo.py` — `InternalDataRepository` (reads/writes sample_* tables). Both strategies import from here. In a real deployment, replace this with an API client to the customer's internal system.

Entity dependency order (both): vendor, customer, chart_of_accounts, item, bill, invoice, payment.

Each strategy's `__init__` accepts an optional `internal_repo` parameter for test injection.

**Intentional API-driven differences:**
- Xero maps "customer" → vendor table (shared Contacts endpoint); QBO keeps them separate
- Xero handles `/Date(ms)/` timestamp format; QBO uses ISO format
- Xero uses `where` clause for `since` filtering; QBO uses API-native params
- Xero has item/payment inbound mappers; QBO doesn't (different API scopes)

## API Endpoints

### Health
- `GET /health` — health check

### Integrations (`/integrations`)
- `GET /integrations/available` — list catalog
- `GET /integrations/available/{id}` — get integration
- `GET /integrations` — list user connections
- `GET /integrations/{id}` — get user connection
- `POST /integrations/{id}/connect` — start OAuth
- `POST /integrations/{id}/callback` — complete OAuth
- `DELETE /integrations/{id}` — disconnect
- `GET /integrations/{id}/sync-status` — entity sync statuses
- `POST /integrations/{id}/sync-status/{entity}/reset` — reset cursor
- `GET /integrations/{id}/records` — browse records (paginated, filterable by entity_type, sync_status, do_not_sync)
- `POST /integrations/{id}/records/force-sync` — bulk force-sync failing records (clear errors, equalize version vectors)
- `POST /integrations/{id}/records/do-not-sync` — bulk toggle do-not-sync flag on records

### Settings (`/integrations/{id}/settings`)
- `GET` / `PUT` — user settings
- `GET` / `PUT` with `/defaults` — system defaults

### Sync Jobs (`/sync-jobs`)
- `POST /sync-jobs` — trigger sync
- `GET /sync-jobs` — list (paginated)
- `GET /sync-jobs/{id}` — details
- `POST /sync-jobs/{id}/cancel` — cancel
- `POST /sync-jobs/{id}/execute` — execute immediately (dev)
- `GET /sync-jobs/{id}/records` — record-level details (paginated)

### Admin (`/admin`)
- `GET /admin/integrations` — all user integrations (cross-client)
- `GET /admin/clients/{cid}/integrations/{iid}/sync-status`
- `POST /admin/clients/{cid}/integrations/{iid}/sync-status/{entity}/reset`

**Authentication:**
- Regular endpoints require `X-Client-ID` header (dev mode) or JWT (production)
- Admin endpoints (`/admin/*`) require `X-Admin-API-Key` header in production
  - In development mode with no key configured, admin access is allowed
  - In production, set `ADMIN_API_KEY` environment variable (see Configuration section)

## Test Structure

```
tests/
  conftest.py              Shared fixtures
  unit/                    Unit tests
    test_adapters.py       Adapter factory, mock adapter
    test_api.py            API endpoints
    test_auth.py           Authentication
    test_admin_auth.py     Admin authentication
    test_admin_crud.py     Admin CRUD operations
    test_change_detection.py  Change detection modes
    test_config.py         Configuration
    test_domain.py         Entities, enums
    test_encryption.py     Encryption services
    test_exceptions.py     Exception handling
    test_feature_flags.py  Feature flags
    test_health.py         Health endpoints
    test_integration_service.py  Integration lifecycle
    test_middleware.py     Middleware
    test_oauth_state.py    OAuth state handling
    test_queue.py          Queue implementations
    test_quickbooks.py     QBO adapter & strategy
    test_xero.py           Xero adapter & strategy
    test_sync_overrides.py Force-sync, do-not-sync, audit log, record browser
    test_scheduler.py      Scheduler
    test_services.py       Service layer
    test_sync_job_runner.py  Job runner
    test_sync_orchestrator.py  Orchestration
    test_version_vectors.py  Version vectors & bidirectional sync
  integration/             Integration tests
    test_sync_e2e.py       E2E: outbound -> inbound -> bidirectional lifecycle
    test_scheduler_e2e.py  Scheduler E2E
  mocks/
    adapters.py            MockIntegrationAdapter, MockAdapterFactory
    encryption.py          MockEncryptionService
    feature_flags.py       MockFeatureFlagService
    repositories.py        MockIntegrationRepository, MockSyncJobRepository, MockIntegrationStateRepository
    scheduler.py           MockScheduler
```

Run tests:
```bash
pytest tests/ -v --no-cov          # All tests
pytest tests/unit/ -v --no-cov     # Unit only
pytest tests/integration/ -v -s    # Integration with output
```

## Development Commands

```bash
make run                # Start dev server (uvicorn, port 8000)
make test               # Run tests
make test-cov           # Tests with coverage
make lint               # Ruff + black check
make format             # Auto-format
make mypy               # Type checking
make migrate-upgrade    # Apply DB migrations
make migrate-downgrade  # Rollback last migration
make docker-up          # Start Docker services
make docker-down        # Stop Docker services
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/demo_sync_job.py` | Demo full sync flow with mock infrastructure |
| `scripts/generate_test_data.py` | Seed vendors/bills/invoices in internal DB |
| `scripts/seed_sample_data.sql` | SQL seed for integration catalog |
| `scripts/start.sh` | Container startup script |

## Configuration (`app/core/config.py`)

Key environment variables:
- `DATABASE_URL` — PostgreSQL connection (port 5433)
- `INTERNAL_DATABASE_URL` — internal business DB (sister project)
- `APP_ENV` — development / production
- `CLOUD_PROVIDER` — local / aws / azure / gcp
- `QBO_CLIENT_ID`, `QBO_CLIENT_SECRET`, `QBO_ENVIRONMENT` — QuickBooks OAuth
- `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET` — Xero OAuth
- `QUEUE_URL` — SQS queue (production)
- `JOB_RUNNER_ENABLED`, `JOB_RUNNER_MAX_WORKERS` — background processing
- `SYNC_GLOBALLY_DISABLED` — kill switch
- `DISABLED_INTEGRATIONS` — per-integration disable list
- `ADMIN_API_KEY` — API key for `/admin/*` endpoints (required in production)

### Admin API Key Setup

The admin API (`/admin/*` endpoints) requires authentication in production:

1. **Generate a key**: `openssl rand -base64 32 | tr -d '/+=' | head -c 32`
2. **Set in environment**: Add `ADMIN_API_KEY=<your-key>` to your deployment config
3. **Store securely**: Use AWS Secrets Manager, Azure Key Vault, or similar
4. **Client usage**: Include `X-Admin-API-Key: <your-key>` header in admin API requests

In development mode (`APP_ENV=development`) with no key configured, admin endpoints are accessible without authentication.

## Feature Flags

- `sync_globally_disabled` — stops all sync jobs system-wide
- `disabled_integrations` — list of integration names to disable
- `job_termination_enabled` — auto-terminate stuck jobs
- `auth_enabled` — JWT validation (off in dev)
- `rate_limit_enabled` — request rate limiting

## Sister Projects

- **import-export-orchestrator**: Shares PostgreSQL (port 5433, container `job_runner_db`)
- **saas-host-app**: User-facing React host app that embeds this platform's micro-frontend
- **admin-host-app**: Admin React host app that embeds this platform's micro-frontend with admin features

## Frontend Architecture (Micro-Frontend)

The UI (`/ui`) is a React micro-frontend using **Vite Module Federation**. Host apps load it dynamically.

### Ports & Processes

| App | Port | Purpose |
|-----|------|---------|
| **integration-platform UI** | 3001 | Micro-frontend, serves `remoteEntry.js` |
| **saas-host-app** | 4000 | User-facing host, loads micro-FE |
| **admin-host-app** | 4001 | Admin host, loads micro-FE with admin API key |

### How It Works

1. **Module Federation**: Host apps import from `http://localhost:3001/assets/remoteEntry.js`
2. **API Proxying**: Host apps proxy `/int-api/*` → AWS ALB → ECS backend
3. **Admin API Key**: admin-host-app injects `X-Admin-API-Key` header for `/int-api/admin/*`

### Starting the Frontend (Development)

```bash
# 1. Build and serve the micro-frontend (MUST use preview mode for Module Federation)
npm run build && npm run preview      # in /ui directory, runs on :3001

# 2. Start host apps (in separate terminals)
npm run dev                              # in /saas-host-app, runs on :4000
npm run dev                              # in /admin-host-app, runs on :4001
```

**Important**: The micro-frontend MUST run in `preview` mode (not `dev` mode) because `vite-plugin-federation` requires built assets to serve `remoteEntry.js` correctly.

### Host App Configuration

Both host apps use vite proxy to route API calls:
- `saas-host-app/vite.config.ts` — proxies to AWS ALB
- `admin-host-app/vite.config.ts` — proxies to AWS ALB + injects `X-Admin-API-Key` for admin routes

The ALB URL is configured in these files. Update when ALB changes.

## Conventions

- Async everywhere (SQLAlchemy, FastAPI, adapters, queue)
- Entity types are strings, not enums (stored in DB, user-configurable)
- `sync_direction` on records = last actual direction (INBOUND/OUTBOUND), never BIDIRECTIONAL
- Version vectors equalized after every sync: `iv = ev = lsv = max(iv, ev)`
- Composite PK on `integration_state` for partition-ready scaling
- History is append-only; cleanup via retention policy

## Adding a New Integration

Use this checklist to add a new integration (e.g., "Sage"). Copy the `quickbooks/` directory as a starting point and adapt each file.

### 1. Create integration files (`app/integrations/{name}/`)

| File | Purpose | Key requirements |
|------|---------|------------------|
| `__init__.py` | Package init | Empty file |
| `constants.py` | Entity ordering, API endpoints, display names | Define `INBOUND_ENTITY_ORDER`, `OUTBOUND_ENTITY_ORDER`, `ENTITY_DISPLAY_NAMES`, and API-specific constants (base URLs, OAuth endpoints, page sizes, endpoint mappings) |
| `mappers.py` | Inbound/outbound data mapping | Export `INBOUND_MAPPERS` and `OUTBOUND_MAPPERS` dicts (entity_type → mapper_fn), plus named `map_vendor_inbound` for FK resolution. Each mapper is a pure function: `dict → dict` |
| `client.py` | API adapter (HTTP calls) | Implement `IntegrationAdapterInterface` from `domain/interfaces.py`. Methods: `fetch_records`, `get_record`, `create_record`, `update_record`, `delete_record`, `check_connection`, `get_auth_url`, `exchange_code`, `refresh_token`, `revoke_token`. Handle pagination and `since` filtering per the external API |
| `strategy.py` | Sync strategy | Implement the 10 required methods (see Strategy Contract below). Import from your own `constants.py` and `mappers.py`, and import `InternalDataRepository` from `shared/internal_repo.py` for DB access |

### 2. Register in two places

**Adapter factory** (`app/infrastructure/adapters/factory.py`):
```python
from app.integrations.{name}.client import {Name}Adapter
_factory_instance.register("{Integration Display Name}", {Name}Adapter)
```

**Strategy registry** (`app/services/sync_orchestrator.py` → `_init_strategies()`):
```python
from app.integrations.{name}.strategy import {Name}SyncStrategy
register_sync_strategy("{Integration Display Name}", {Name}SyncStrategy)
```

The display name string (e.g., `"QuickBooks Online"`, `"Xero"`) must match the `name` column in `available_integrations`.

### 3. Database seeding

Add rows to the seed SQL (`scripts/seed_sample_data.sql`) and/or create an Alembic migration:

- **`available_integrations`**: One row with a fixed UUID, name, type, supported_entities JSON list, and connection_config JSON (OAuth URLs, scopes)
- **`system_integration_settings`**: One row with default sync rules (entity types, directions, change detection modes). Use the QBO or Xero seed as a template. Referenced by `integration_id` FK to `available_integrations`

### 4. Strategy contract (10 required methods)

```
get_entity_order(direction) → list[str]
get_ordered_rules(rules, direction) → list[SyncRule]
sync_entity_inbound(job, entity_type, adapter, state_repo, since?, record_ids?) → dict
sync_entity_outbound(job, entity_type, adapter, state_repo, since?, record_ids?, rule?) → dict
sync_entity_bidirectional(job, entity_type, adapter, state_repo, rule, since?, outbound_since?, record_ids?) → dict
_process_inbound_record(job, entity_type, record, mapper_fn, state_repo, adapter?) → IntegrationStateRecord
_flush_inbound_batch(records, state_repo, job) → (created, updated, failed)
_prepare_outbound_data(job, entity_type, state, state_repo) → dict
_write_history_entries(records, state_repo, job_id) → None
_write_failure_history(state, state_repo, job_id, direction, error) → None
```

**Error handling (CRITICAL)**: `_write_failure_history` must be called in ALL 4 failure paths:
1. **Inbound** `sync_entity_inbound`: inline `IntegrationHistoryRecord` in the per-record exception handler
2. **Standalone outbound** `sync_entity_outbound`: call `_write_failure_history()` in the per-record exception handler
3. **Bidirectional external records** `sync_entity_bidirectional`: inline `IntegrationHistoryRecord` in the per-record exception handler
4. **Bidirectional internal-only outbound** `sync_entity_bidirectional` (section 3): call `_write_failure_history()` in the per-record exception handler

Missing any of these paths means failed records are silently dropped from the audit log.

**Version vector equalization** — after every successful sync (all directions):
```python
max_v = max(state.internal_version_id, state.external_version_id)
state.internal_version_id = max_v
state.external_version_id = max_v
state.last_sync_version_id = max_v
```

### 5. Mapper contract

```python
INBOUND_MAPPERS: dict[str, Callable[[dict], dict]] = {
    "vendor": map_vendor_inbound,
    "bill": map_bill_inbound,
    # ... one entry per supported entity type
}

OUTBOUND_MAPPERS: dict[str, Callable[[dict], dict]] = {
    "vendor": map_vendor_outbound,
    "bill": map_bill_outbound,
    # ... outbound mappers only needed for entities that support outbound sync
}
```

**FK resolution pattern**: Inbound mappers for bills should include `vendor_external_id` in their output. The strategy's `_process_inbound_record` resolves this to `vendor_id` via `state_repo.get_record_by_external_id()`. Same pattern for invoices with `contact_external_id`.

### 6. Adapter contract (`IntegrationAdapterInterface`)

Key methods to implement:
- `fetch_records(entity_type, since?, page_token?, record_ids?)` → `(list[ExternalRecord], next_token)` — must handle pagination and return `ExternalRecord` objects with `id`, `data` (raw API response), and `updated_at`
- `get_record(entity_type, record_id)` → `ExternalRecord | None`
- `create_record(entity_type, data)` → `ExternalRecord`
- `update_record(entity_type, record_id, data)` → `ExternalRecord`
- OAuth methods: `get_auth_url`, `exchange_code`, `refresh_token`, `revoke_token`

Constructor signature: `__init__(self, integration_name, access_token, external_account_id)`

### 7. Critical patterns to get right

- **Outbound data via `_prepare_outbound_data`**: Always re-read the internal record fresh from the DB and map it. Never use stale metadata from the state record. Falls back to metadata only if the internal read fails.
- **FK resolution on outbound**: `_prepare_outbound_data` must resolve internal FKs (e.g., `vendor_id` → `vendor_external_id`) via `state_repo.get_record()` before calling the outbound mapper.
- **Cursor advancement for failing entities**: The orchestrator advances the `since` cursor based on `max_external_updated_at` from the strategy result. If an entity completely fails, return `max_external_updated_at = None` so the cursor stays put and retries next sync.
- **Customer → vendor table mapping**: If the external API uses a shared endpoint for vendors and customers (like Xero's Contacts), map `_get_internal_upsert_fn("customer")` to `self._internal_repo.upsert_vendor` and filter via API query params.
- **`internal_repo` reuse**: All integrations share `shared/internal_repo.py` for DB access. Import from `app.integrations.shared.internal_repo` — don't duplicate it. In production, customers replace this with their own data access layer.

### 8. Testing

Create `tests/unit/test_{name}.py` covering:
- Adapter unit tests (mocked HTTP): fetch_records pagination, create/update/delete, auth URL, token exchange/refresh
- Strategy unit tests (mocked adapter + state_repo): inbound sync, outbound sync, bidirectional with conflicts, error handling (verify failure history is written)
- Mapper unit tests: inbound and outbound mapping for each entity type

Reference files:
- `tests/unit/test_quickbooks.py` — QBO adapter + strategy tests
- `tests/unit/test_xero.py` — Xero adapter + strategy tests
- `tests/unit/test_version_vectors.py` — version vector and bidirectional sync tests (integration-agnostic)
- `tests/integration/test_sync_e2e.py` — E2E lifecycle test
