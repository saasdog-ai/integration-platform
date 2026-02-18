# Integration Platform

A production-ready framework for building integrations between your SaaS application and external providers (ERPs like QuickBooks, Xero, CRMs, HRIS systems, etc.).

## Why This Project?

Instead of paying expensive third-party integration vendors like Workato, MuleSoft, or Tray.io thousands of dollars per month, use this framework as a starting point to build your own integrations. The codebase is designed to be extended with AI coding tools like Claude Code — describe the integration you need, and let AI generate the adapter implementation.

**This is a chassis, not a finished product.** The included QuickBooks Online integration is a fully working reference implementation with inbound, outbound, and bidirectional sync. You'll extend it with additional integrations for your specific use case.

## Features

### Sync Engine
- **Inbound Sync**: Pull records from external systems (e.g., QBO) into your internal database with schema mapping
- **Outbound Sync**: Push internal records to external systems, discover changes via version vectors
- **Bidirectional Sync**: Version-vector-based conflict detection with configurable resolution (external wins or our system wins)
- **Version Vectors**: Three-component tracking (internal, external, last_sync) — all equalized after every successful sync
- **Entity Dependency Ordering**: Vendors sync before bills, customers before invoices
- **Incremental Sync**: Cursor-based with separate inbound (external clock) and outbound (internal clock) cursors
- **Batch Operations**: Batch upsert, batch mark-synced with advisory locks

### Integration Framework
- **Extensible Adapter Pattern**: Add new integrations by implementing `IntegrationAdapterInterface`
- **Strategy Pattern**: Integration-specific sync logic via `QuickBooksSyncStrategy` (entity ordering, schema mapping, version equalization)
- **Schema Mappers**: Bidirectional data mapping between external and internal formats

### Infrastructure
- **OAuth 2.0 Flow**: Complete infrastructure for connecting external systems (authorization, callback, token refresh)
- **Encrypted Credentials**: Pluggable encryption (AWS KMS, Azure Key Vault, Fernet for dev)
- **Async Job Processing**: Background job runner with pluggable message queues (AWS SQS, in-memory)
- **Stuck Job Detection**: Auto-terminate jobs exceeding runtime threshold
- **Pending Job Recovery**: Recover jobs lost due to queue failure
- **History & Audit**: Append-only sync history per job with configurable retention

### Platform
- **Multi-Tenant Ready**: Full `client_id` isolation with partition-ready composite primary keys
- **Micro-Frontend UI**: React-based UI embeddable in host applications via module federation
- **OpenAPI 3.1 Spec**: Auto-generated API docs with client SDK generation support
- **Clean Architecture**: Hexagonal architecture with strict layer separation
- **Cloud-Agnostic**: Runs on AWS, Azure, GCP, or local development
- **Feature Flags**: Global sync kill switch, per-integration disable, rate limiting
- **Admin API**: Cross-client visibility, sync cursor reset

## Technology Stack

- **Python 3.12** / **FastAPI** - Async web framework
- **Pydantic v2** - Data validation and settings
- **SQLAlchemy 2** - Async ORM
- **Alembic** - Database migrations
- **PostgreSQL 15+** - Primary database (port 5433)
- **React / TypeScript / Vite** - Micro-frontend UI
- **pytest** - 381 tests (unit + integration)
- **mypy, Ruff, Black** - Code quality
- **Docker & Docker Compose** - Containerization
- **Terraform** - AWS infrastructure (ECS/Fargate)

## Project Structure

```
integration-platform/
├── app/
│   ├── api/                  # FastAPI routers and DTOs
│   ├── auth/                 # JWT authentication (pluggable)
│   ├── core/                 # Configuration, DI, logging, middleware, exceptions
│   ├── domain/               # Entities, enums, interfaces (pure, no deps)
│   ├── infrastructure/
│   │   ├── adapters/         # Adapter factory, HTTP client, mock adapter
│   │   ├── db/               # SQLAlchemy models, repositories
│   │   ├── encryption/       # KMS, Key Vault, Fernet
│   │   └── queue/            # SQS, in-memory
│   ├── integrations/
│   │   └── quickbooks/       # QBO strategy, mappers, constants, client, internal repo
│   ├── services/             # Orchestrator, job runner, integration service, settings
│   └── main.py               # FastAPI app entry point
├── ui/                       # React micro-frontend (Vite, TypeScript)
├── infra/aws/terraform/      # AWS ECS/Fargate infrastructure
├── tests/
│   ├── unit/                 # 285 unit tests
│   ├── integration/          # 3 E2E integration tests
│   └── mocks/                # Mock adapters, repos, encryption
├── alembic/                  # Database migrations (001–011)
├── scripts/                  # Demo, data generation, seed SQL
└── docker-compose.yml        # Local development (LocalStack, app)
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 15+ (shared with import-export-orchestrator)

### Local Development with Docker

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd integration-platform
   ```

2. **Copy environment file**:
   ```bash
   cp .env.example .env
   ```

3. **Start the shared PostgreSQL** (from import-export-orchestrator):
   ```bash
   cd ../import-export-orchestrator
   docker-compose up -d postgres
   ```

4. **Create the database**:
   ```bash
   docker exec -it job_runner_db psql -U postgres -c "CREATE DATABASE integration_platform;"
   ```

5. **Start integration-platform services**:
   ```bash
   cd ../integration-platform
   docker-compose up -d
   ```

   This will:
   - Start LocalStack (for AWS services emulation)
   - Build and start the application
   - Run database migrations automatically

6. **Start the micro-frontend UI** (optional, for embedded UI testing):
   ```bash
   cd ui
   npm install
   npm run build && npm run preview
   ```

7. **Access the API**:
   - API: http://localhost:8001
   - API Docs (Swagger UI): http://localhost:8001/docs
   - API Docs (ReDoc): http://localhost:8001/redoc
   - Health Check: http://localhost:8001/health
   - Micro-Frontend: http://localhost:3001

8. **Stop services**:
   ```bash
   docker-compose down
   ```

### Local Development without Docker

1. **Create virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   make install-dev
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your database connection
   ```

4. **Run database migrations**:
   ```bash
   make migrate-upgrade
   ```

5. **Run the application**:
   ```bash
   make run
   ```

## Sync Architecture

### Version Vectors

Every record tracked in `integration_state` has three version fields:

| Field | Meaning |
|-------|---------|
| `internal_version_id` (iv) | Bumped when our system modifies the record |
| `external_version_id` (ev) | Bumped when the external system modifies the record |
| `last_sync_version_id` (lsv) | Set to `max(iv, ev)` after successful sync |

**Change detection**:
- `iv > lsv` = needs outbound sync (our change not yet pushed)
- `ev > lsv` = needs inbound sync (external change not yet pulled)
- Both true = conflict (resolved by `master_if_conflict` setting)
- `iv == ev == lsv` = fully in sync

After every successful sync, all three are equalized: `iv = ev = lsv`.

### Change Detection Methods

Each sync rule specifies how changes are detected (`change_source`) and when to act on them (`sync_trigger`):

| Change Source | Description |
|---------------|-------------|
| `polling` | Default. Changes discovered during scheduled sync jobs |
| `push` | Internal system proactively notifies via `POST /integrations/{id}/notify` |
| `webhook` | External system pushes changes via `POST /integrations/{id}/webhooks/{provider}` |
| `hybrid` | Combination of polling and webhook/push |

| Sync Trigger | Description |
|--------------|-------------|
| `deferred` | Default. Bump version vectors only; changes picked up at next scheduled sync |
| `immediate` | Queue an incremental sync job as soon as the change notification arrives |

**Push notification flow**: Your internal system calls the notify endpoint with a list of changed record IDs. The platform bumps `internal_version_id` on matching state records (creating new ones if needed). If the sync rule has `sync_trigger: immediate`, an incremental sync job is queued automatically.

**Webhook flow**: An external system (e.g., QuickBooks) calls the webhook endpoint. The platform bumps `external_version_id` on matching state records. Same trigger logic applies. The webhook endpoint currently returns `501` — implement provider-specific payload parsing in `app/api/integrations.py` to activate it.

**Example sync rule with push + immediate trigger**:
```json
{
  "entity_type": "vendor",
  "direction": "bidirectional",
  "enabled": true,
  "master_if_conflict": "external",
  "change_source": "push",
  "sync_trigger": "immediate"
}
```

### Sync Directions

Configured per entity type in user settings:

| Direction | Behavior |
|-----------|----------|
| `inbound` | Fetch from external, write to internal DB |
| `outbound` | Discover outbound-needing records via version vectors, push to external |
| `bidirectional` | Classify each record as inbound/outbound/conflict using version vectors |

### Conflict Resolution

When `master_if_conflict = external`: external system wins (synced as inbound).
When `master_if_conflict = our_system`: our system wins (synced as outbound).

The `sync_direction` field on each record always reflects the actual direction of the most recent sync (INBOUND or OUTBOUND), never BIDIRECTIONAL.

### QuickBooks Online Integration

Supported entities: vendor, customer, chart_of_accounts, item, bill, invoice, payment.

Entity sync order respects dependencies (vendors before bills, customers before invoices). The strategy handles schema mapping via dedicated mapper functions.

## API Reference

All endpoints require a `X-Client-ID` header for multi-tenant isolation. In production, this would be extracted from a JWT token.

```bash
# Set base URL and client ID for examples
BASE_URL="http://localhost:8001"
CLIENT_ID="550e8400-e29b-41d4-a716-446655440000"
```

### Health Check

```bash
# Check API health
curl $BASE_URL/health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

### Integrations

#### List Available Integrations

```bash
curl "$BASE_URL/integrations/available" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response:
```json
{
  "integrations": [
    {
      "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "name": "QuickBooks Online",
      "type": "erp",
      "description": "Accounting software for small businesses",
      "supported_entities": ["invoice", "bill", "vendor", "customer"],
      "connection_config": {
        "auth_type": "oauth2",
        "authorization_url": "https://appcenter.intuit.com/connect/oauth2",
        "token_url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        "scopes": ["com.intuit.quickbooks.accounting"]
      },
      "is_active": true
    }
  ]
}
```

#### List User's Connected Integrations

```bash
curl "$BASE_URL/integrations" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response:
```json
{
  "integrations": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "client_id": "550e8400-e29b-41d4-a716-446655440000",
      "integration_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "integration_name": "QuickBooks Online",
      "integration_type": "erp",
      "status": "connected",
      "external_account_id": "1234567890",
      "last_connected_at": "2024-01-15T10:00:00Z",
      "disconnected_at": null,
      "created_at": "2024-01-10T08:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

#### Start OAuth Connection

```bash
curl -X POST "$BASE_URL/integrations/f47ac10b-58cc-4372-a567-0e02b2c3d479/connect" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "redirect_uri": "https://myapp.com/integrations/callback",
    "state": "random-state-string"
  }'
```

Response:
```json
{
  "authorization_url": "https://appcenter.intuit.com/connect/oauth2?client_id=...&redirect_uri=...&state=..."
}
```

#### Complete OAuth Callback

After the user authorizes, the external system redirects back with a code:

```bash
curl -X POST "$BASE_URL/integrations/f47ac10b-58cc-4372-a567-0e02b2c3d479/callback" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "authorization-code-from-oauth",
    "redirect_uri": "https://myapp.com/integrations/callback"
  }'
```

Response:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "client_id": "550e8400-e29b-41d4-a716-446655440000",
  "integration_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "status": "connected",
  "external_account_id": "1234567890",
  "last_connected_at": "2024-01-15T10:00:00Z",
  ...
}
```

#### Disconnect Integration

```bash
curl -X DELETE "$BASE_URL/integrations/f47ac10b-58cc-4372-a567-0e02b2c3d479" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response: `204 No Content`

---

### Sync Jobs

#### Trigger a Sync Job

```bash
curl -X POST "$BASE_URL/sync-jobs" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "job_type": "incremental",
    "entity_types": ["invoice", "bill"]
  }'
```

Job types: `full_sync`, `incremental`, `entity_sync`

Response:
```json
{
  "id": "job-uuid-here",
  "client_id": "550e8400-e29b-41d4-a716-446655440000",
  "integration_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "integration_name": "QuickBooks Online",
  "job_type": "incremental",
  "status": "pending",
  "triggered_by": "user",
  "started_at": null,
  "completed_at": null,
  "entities_processed": null,
  "error_code": null,
  "error_message": null,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

#### List Sync Jobs

```bash
# List all jobs
curl "$BASE_URL/sync-jobs" \
  -H "X-Client-ID: $CLIENT_ID"

# Filter by status and integration
curl "$BASE_URL/sync-jobs?status=succeeded&integration_id=f47ac10b-58cc-4372-a567-0e02b2c3d479&page=1&page_size=10" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response:
```json
{
  "jobs": [
    {
      "id": "job-uuid-here",
      "status": "succeeded",
      "job_type": "incremental",
      "entities_processed": {
        "invoice": {"fetched": 15, "created": 3, "updated": 12},
        "bill": {"fetched": 8, "created": 2, "updated": 6}
      },
      "started_at": "2024-01-15T10:30:05Z",
      "completed_at": "2024-01-15T10:31:22Z",
      ...
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 10,
  "total_pages": 5
}
```

#### Get Job Details

```bash
curl "$BASE_URL/sync-jobs/job-uuid-here" \
  -H "X-Client-ID: $CLIENT_ID"
```

#### Cancel a Job

```bash
curl -X POST "$BASE_URL/sync-jobs/job-uuid-here/cancel" \
  -H "X-Client-ID: $CLIENT_ID"
```

#### Get Job Record Details

Get paginated record-level sync details for a specific job. Useful for seeing exactly which records were synced, failed, or encountered errors.

```bash
# Get all records for a job
curl "$BASE_URL/sync-jobs/job-uuid-here/records" \
  -H "X-Client-ID: $CLIENT_ID"

# Filter by entity type and status, with pagination
curl "$BASE_URL/sync-jobs/job-uuid-here/records?entity_type=invoice&status=failed&page=1&page_size=20" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response:
```json
{
  "records": [
    {
      "id": "record-uuid",
      "entity_type": "invoice",
      "internal_record_id": "INV-001",
      "external_record_id": "QB-12345",
      "sync_direction": "outbound",
      "sync_status": "synced",
      "is_success": true,
      "updated_at": "2024-01-15T10:31:00Z",
      "error_code": null,
      "error_message": null,
      "error_details": null
    },
    {
      "id": "record-uuid-2",
      "entity_type": "invoice",
      "internal_record_id": "INV-002",
      "external_record_id": null,
      "sync_direction": "outbound",
      "sync_status": "failed",
      "is_success": false,
      "updated_at": "2024-01-15T10:31:05Z",
      "error_code": "VALIDATION_ERROR",
      "error_message": "Missing required field: customer_id",
      "error_details": {
        "field": "customer_id",
        "validation": "required"
      }
    }
  ],
  "total": 25,
  "page": 1,
  "page_size": 20,
  "total_pages": 2
}
```

---

### Settings

#### Get Integration Settings

```bash
curl "$BASE_URL/integrations/f47ac10b-58cc-4372-a567-0e02b2c3d479/settings" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response:
```json
{
  "sync_rules": [
    {
      "entity_type": "vendor",
      "direction": "bidirectional",
      "enabled": true,
      "master_if_conflict": "external",
      "field_mappings": null,
      "change_source": "polling",
      "sync_trigger": "deferred"
    },
    {
      "entity_type": "bill",
      "direction": "inbound",
      "enabled": true,
      "master_if_conflict": "external",
      "field_mappings": null,
      "change_source": "push",
      "sync_trigger": "immediate"
    }
  ],
  "sync_frequency": "0 */6 * * *",
  "auto_sync_enabled": true
}
```

Sync direction options: `inbound`, `outbound`, `bidirectional`.
Conflict resolution options: `external` (external system wins), `our_system` (our system wins).
Change source options: `polling`, `push`, `webhook`, `hybrid`.
Sync trigger options: `deferred` (next scheduled sync), `immediate` (queue job now).

#### Update Settings

```bash
curl -X PUT "$BASE_URL/integrations/f47ac10b-58cc-4372-a567-0e02b2c3d479/settings" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "sync_rules": [
      {
        "entity_type": "vendor",
        "direction": "bidirectional",
        "enabled": true,
        "master_if_conflict": "external"
      },
      {
        "entity_type": "bill",
        "direction": "inbound",
        "enabled": true
      }
    ],
    "sync_frequency": "0 */4 * * *",
    "auto_sync_enabled": true
  }'
```

---

### Error Responses

All errors follow this format:

```json
{
  "error": "Integration not found",
  "code": "NOT_FOUND",
  "details": null
}
```

Common HTTP status codes:
- `400` - Validation error
- `401` - Authentication required
- `403` - Forbidden
- `404` - Resource not found
- `409` - Conflict (e.g., integration already connected)
- `500` - Internal server error

---

### OpenAPI Specification

The API is fully documented using **OpenAPI 3.1**. FastAPI automatically generates the spec from route definitions and Pydantic models.

**Documentation URLs** (when running locally):
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc
- OpenAPI JSON: http://localhost:8001/openapi.json

#### Generating Client SDKs

Use the OpenAPI spec to generate type-safe client libraries in any language:

**Download the spec:**
```bash
curl http://localhost:8001/openapi.json -o openapi.json
```

**Generate clients using OpenAPI Generator:**

```bash
# Install OpenAPI Generator
npm install -g @openapitools/openapi-generator-cli

# Generate TypeScript client
openapi-generator-cli generate -i openapi.json -g typescript-fetch -o ./clients/typescript

# Generate Python client
openapi-generator-cli generate -i openapi.json -g python -o ./clients/python

# Generate Go client
openapi-generator-cli generate -i openapi.json -g go -o ./clients/go

# Generate Java client
openapi-generator-cli generate -i openapi.json -g java -o ./clients/java
```

**Using the generated TypeScript client:**
```typescript
import { IntegrationsApi, SyncJobsApi, Configuration } from './clients/typescript';

const config = new Configuration({
  basePath: 'http://localhost:8001',
  headers: { 'X-Client-ID': 'your-client-uuid' }
});

const integrationsApi = new IntegrationsApi(config);
const syncJobsApi = new SyncJobsApi(config);

// List available integrations
const available = await integrationsApi.listAvailableIntegrationsIntegrationsAvailableGet();

// Trigger a sync job
const job = await syncJobsApi.triggerSyncSyncJobsPost({
  triggerSyncRequest: {
    integrationId: 'uuid-here',
    jobType: 'incremental',
    entityTypes: ['invoice', 'bill']
  }
});
```

See [OpenAPI Generator docs](https://openapi-generator.tech/docs/generators) for all supported languages.

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v --no-cov

# Run unit tests only (285 tests)
pytest tests/unit/ -v --no-cov

# Run integration tests with output (3 E2E tests)
pytest tests/integration/ -v -s --no-cov

# Run version vector / bidirectional sync tests (30 tests)
pytest tests/unit/test_version_vectors.py -v --no-cov

# Run with coverage
make test-cov
```

### Code Quality

```bash
# Run linter
make lint

# Format code
make format

# Type checking
make mypy
```

### Database Migrations

```bash
# Create a new migration
make migrate

# Apply migrations
make migrate-upgrade

# Rollback last migration
make migrate-downgrade
```

## Adding New Integrations

The adapter pattern makes it easy to add new integrations — either manually or with AI assistance. Use Claude Code or similar tools to generate implementations:

**Example prompt for Claude Code:**
> "Create a Xero integration adapter that implements OAuth token exchange and fetches invoices. Follow the pattern in `app/integrations/quickbooks/`."

### Manual Steps

1. **Create adapter** in `app/integrations/<integration_name>/`:
   ```python
   from app.domain.interfaces import IntegrationAdapterInterface

   class MyIntegrationAdapter(IntegrationAdapterInterface):
       async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> OAuthTokens:
           # Implement OAuth token exchange
           pass

       async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
           # Implement token refresh
           pass

       async def fetch_records(self, entity_type: str, ...) -> list[ExternalRecord]:
           # Implement data fetching
           pass
   ```

2. **Register adapter** in `app/infrastructure/adapters/factory.py`

3. **Add integration to database** via migration or seed script

## Architecture

### Clean Architecture

The project follows hexagonal (clean) architecture principles:

- **Domain Layer** (`app/domain/`): Pure business entities, enums, and interfaces
- **Services Layer** (`app/services/`): Business logic orchestration
- **Infrastructure Layer** (`app/infrastructure/`): External concerns (DB, queues, adapters)
- **API Layer** (`app/api/`): HTTP endpoints and DTOs
- **Core Layer** (`app/core/`): Configuration, DI, logging, middleware

### Database Partitioning

The `integration_state` table is designed for horizontal scaling with billions of rows:

- Composite primary key: `(client_id, id)`
- Partition-ready by `client_id`
- Optimized indexes for common query patterns

### Message Queue Abstraction

The platform supports multiple queue backends:

- **In-Memory** (default for local dev): Simple, no external dependencies
- **AWS SQS**: Production-ready with DLQ support

Configure via environment variables:
```bash
CLOUD_PROVIDER=local    # Uses in-memory queue
CLOUD_PROVIDER=aws      # Uses SQS (requires QUEUE_URL)
```

## Security

### Authentication

The project includes pluggable JWT authentication (`app/auth/`). Currently in development mode (allow-all). To enable:

1. Implement JWT validation in `app/auth/jwt.py`
2. Update `get_client_id()` dependency to extract from token

### Credential Encryption

User credentials are encrypted at rest using pluggable encryption:

- **AWS KMS**: Production encryption using AWS Key Management Service
- **Azure Key Vault**: Production encryption for Azure deployments
- **Local**: Development-only encryption using Fernet

### Admin API Authentication

The `/admin/*` endpoints require API key authentication in production:

1. **Generate a key**: `openssl rand -base64 32 | tr -d '/+=' | head -c 32`
2. **Set environment variable**: `ADMIN_API_KEY=<your-key>`
3. **Include header in requests**: `X-Admin-API-Key: <your-key>`

In development mode (`APP_ENV=development`) with no key configured, admin endpoints are accessible without authentication.

### Secrets Management

**Never commit secrets to the repository!**

- Use `.env` files locally (gitignored)
- Use AWS Secrets Manager / Azure Key Vault in production
- Use environment variables for Docker/Terraform

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `APP_ENV` | Environment (development/production) | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CLOUD_PROVIDER` | Cloud provider (local/aws/azure/gcp) | `local` |
| `QUEUE_URL` | SQS queue URL (if using AWS) | - |
| `AWS_ENDPOINT_URL` | LocalStack endpoint (for local dev) | - |
| `JOB_RUNNER_ENABLED` | Enable background job runner | `true` |
| `JOB_RUNNER_MAX_WORKERS` | Max concurrent job workers | `5` |
| `ADMIN_API_KEY` | API key for admin endpoints (required in prod) | - |

## Related Projects

- **import-export-orchestrator**: Sister project for async import/export jobs (shares PostgreSQL)
- **saas-host-app**: Host application that embeds this platform's micro-frontend

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests (maintain coverage)
5. Run linting and type checking
6. Submit a pull request

## License

MIT License - see LICENSE file for details.
