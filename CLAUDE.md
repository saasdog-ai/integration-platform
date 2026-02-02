# CLAUDE.md — Project Context for Claude Code

## What Is This Project?

A production-ready integration platform for syncing data between a SaaS application and external providers (ERPs like QuickBooks Online, CRMs, HRIS systems). Built as an alternative to expensive integration vendors (Workato, MuleSoft, Tray.io). The included QuickBooks integration is a fully working reference implementation.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic
- **Database**: PostgreSQL 15+ on port 5433 (shared with sister project `import-export-orchestrator`)
- **Queue**: AWS SQS (production) / in-memory (development)
- **Encryption**: AWS KMS / Azure Key Vault / Fernet (development)
- **UI**: React micro-frontend (Vite, TypeScript, module federation)
- **Infrastructure**: Docker, Docker Compose, Terraform (AWS ECS/Fargate)
- **Testing**: pytest (async), 318 tests (unit + integration)

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
    quickbooks/  QBO-specific: strategy, mappers, constants, internal repo, client
  services/      Business logic: sync_orchestrator, sync_job_runner, integration_service, settings_service
```

### Key Patterns

- **Strategy pattern**: `QuickBooksSyncStrategy` handles QBO-specific sync logic; registered in `sync_orchestrator._SYNC_STRATEGIES`
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
| `sample_vendors` | Internal vendor records |
| `sample_bills` | Internal bill records |
| `sample_invoices` | Internal invoice records |
| `sample_chart_of_accounts` | Internal chart of accounts |

### Migrations (`alembic/versions/`)

001 Initial schema, 002 job_params column, 004 disconnected_at, 005 last_job_id, 006 unique constraints, 007 integration_history, 008 sample data tables, 009 split sync cursors, 010 equalize version vectors.

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

### QuickBooks Integration (`app/integrations/quickbooks/`)

| File | Purpose |
|------|---------|
| `client.py` | `QuickBooksAdapter` — OAuth, API calls to QBO |
| `strategy.py` | `QuickBooksSyncStrategy` — entity ordering, inbound/outbound/bidirectional sync |
| `mappers.py` | Data mapping QBO <-> internal schema (INBOUND_MAPPERS, OUTBOUND_MAPPERS) |
| `constants.py` | Entity names, ordering, QBO API endpoints |
| `internal_repo.py` | `InternalDataRepository` — reads/writes to sample_vendors, sample_bills, etc. |

Entity dependency order: vendor, customer, chart_of_accounts, item, bill, invoice, payment.

The strategy's `__init__` accepts an optional `internal_repo` parameter for test injection.

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

All endpoints require `X-Client-ID` header (dev mode) or JWT (production).

## Test Structure

```
tests/
  conftest.py              Shared fixtures
  unit/                    Unit tests (285 tests)
    test_adapters.py       Adapter factory, mock adapter
    test_api.py            API endpoints
    test_auth.py           Authentication
    test_config.py         Configuration
    test_domain.py         Entities, enums
    test_encryption.py     Encryption services
    test_exceptions.py     Exception handling
    test_health.py         Health endpoints
    test_integration_service.py  Integration lifecycle
    test_middleware.py     Middleware
    test_queue.py          Queue implementations
    test_quickbooks.py     QBO adapter & strategy
    test_services.py       Service layer
    test_sync_job_runner.py  Job runner
    test_sync_orchestrator.py  Orchestration
    test_version_vectors.py  Version vectors & bidirectional sync (30 tests)
  integration/             Integration tests (3 tests)
    test_sync_e2e.py       E2E: outbound -> inbound -> bidirectional lifecycle
  mocks/
    adapters.py            MockIntegrationAdapter, MockAdapterFactory
    encryption.py          MockEncryptionService
    repositories.py        MockIntegrationRepository, MockSyncJobRepository, MockIntegrationStateRepository
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
- `QUEUE_URL` — SQS queue (production)
- `JOB_RUNNER_ENABLED`, `JOB_RUNNER_MAX_WORKERS` — background processing
- `SYNC_GLOBALLY_DISABLED` — kill switch
- `DISABLED_INTEGRATIONS` — per-integration disable list

## Feature Flags

- `sync_globally_disabled` — stops all sync jobs system-wide
- `disabled_integrations` — list of integration names to disable
- `job_termination_enabled` — auto-terminate stuck jobs
- `auth_enabled` — JWT validation (off in dev)
- `rate_limit_enabled` — request rate limiting

## Sister Projects

- **import-export-orchestrator**: Shares PostgreSQL (port 5433, container `job_runner_db`)
- **admin-host-app**: React host app that embeds this platform's micro-frontend UI (`/ui`)

## Conventions

- Async everywhere (SQLAlchemy, FastAPI, adapters, queue)
- Entity types are strings, not enums (stored in DB, user-configurable)
- `sync_direction` on records = last actual direction (INBOUND/OUTBOUND), never BIDIRECTIONAL
- Version vectors equalized after every sync: `iv = ev = lsv = max(iv, ev)`
- Composite PK on `integration_state` for partition-ready scaling
- History is append-only; cleanup via retention policy
