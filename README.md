# Integration Platform

A production-ready framework for building integrations between your Enterprise application and external providers (ERPs like QuickBooks, Xero, CRMs, HRIS systems, etc.).

## Why This Project?

Third-party integration vendors like Workato, MuleSoft, and Tray.io charge thousands of dollars per month. This framework gives you a production-ready starting point to build your own integrations instead -- and it's designed to be extended with AI coding tools like Claude Code.

**This may be the last integration framework you'll ever need.** This project handles API-based integrations (ERPs, CRMs, HRIS) -- real-time sync via REST/OAuth APIs. Its sister project, [import-export-orchestrator](https://github.com/saasdog-ai/import-export-orchestrator), handles file-based integrations (CSV, SFTP, bulk imports/exports). Together, they cover the two fundamental integration patterns. The sync engine, conflict resolution, and multi-tenant infrastructure are the hard parts -- once those are solved, adding a new integration is just describing API mappings. With AI coding tools, that takes minutes, not months.

### What's Included

- **Sync engine** -- long-running sync jobs with job status tracking, per-record sync history, and incremental cursors
- **Version vectors** -- three-component conflict detection with configurable resolution (external wins vs. our system wins)
- **Bidirectional sync** -- inbound, outbound, and bidirectional with entity dependency ordering
- **Multi-tenant isolation** -- full `client_id` partitioning across all tables
- **OAuth credential management** -- connect/disconnect flow with encrypted token storage (KMS, Key Vault, Fernet)
- **Retry & DLQ handling** -- pluggable message queues (SQS, Pub/Sub, Azure Queue) with dead-letter support
- **Audit logging** -- append-only history for every sync operation and manual override
- **REST API** -- all features exposed as API endpoints, plus admin APIs for defaults and overrides
- **Embeddable UI** -- React micro-frontend you can drop into your host app via module federation
- **Multi-cloud Terraform** -- deploy to AWS (ECS/Fargate), GCP (Cloud Run), or Azure (Container Apps)

### How to Use It

The included QuickBooks Online and Xero integrations are fully working reference implementations with inbound, outbound, and bidirectional sync across 7 entity types.

1. **Clone and deploy** -- download the source and spin up infrastructure with the included Terraform configs (`CLOUD=aws|gcp|azure ./scripts/infra.sh up`)
2. **Point your AI tool at the codebase** -- the project includes detailed `CLAUDE.md` files that give AI tools full context
3. **Describe what you need** -- tell your AI tool to *"add a Sage integration following the same patterns as QuickBooks and Xero"*
4. **Test and ship** -- run the 500+ included tests as a baseline, add integration-specific tests, and deploy

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│  API Layer  (FastAPI routers, DTOs, OpenAPI docs)     │
├──────────────────────────────────────────────────────┤
│  Auth       (JWT / X-Client-ID, admin API key)        │
├──────────────────────────────────────────────────────┤
│  Services   (SyncOrchestrator, JobRunner, Settings)   │
├──────────────────────────────────────────────────────┤
│  Domain     (Entities, enums, interfaces — no deps)   │
├──────────────────────────────────────────────────────┤
│  Infrastructure                                       │
│    Adapters  (QBO, Xero, mock)                        │
│    DB        (SQLAlchemy repos, Alembic migrations)   │
│    Queue     (SQS / in-memory)                        │
│    Encryption (KMS / Key Vault / Fernet)              │
├──────────────────────────────────────────────────────┤
│  Integrations                                         │
│    quickbooks/  strategy, mappers, client, constants  │
│    xero/        strategy, mappers, client, constants  │
│    shared/      InternalDataRepository (your data)    │
└──────────────────────────────────────────────────────┘
```

**Key tables**: `integration_state` (record-level sync tracking with version vectors), `sync_jobs` (job execution history), `user_integrations` (OAuth connections per tenant), `user_integration_settings` (sync rules per tenant).

**Sync flow**: User triggers sync → job queued → orchestrator selects strategy → strategy fetches/pushes records per entity in dependency order → version vectors equalized → history written.

For detailed sync architecture (version vectors, conflict resolution, change detection modes), see [docs/SYNC_ARCHITECTURE.md](docs/SYNC_ARCHITECTURE.md).

## Deployment Guide

### Prerequisites

- Cloud CLI configured: AWS CLI, `gcloud`, or `az` (depending on your cloud)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- [Docker](https://docs.docker.com/get-docker/)
- PostgreSQL 15+ (provisioned automatically by shared-infrastructure)

### Step 1: Deploy shared-infrastructure

The [shared-infrastructure](https://github.com/saasdog-ai/shared-infrastructure) project creates the foundational resources (VPC, ECS cluster, RDS PostgreSQL) that this platform runs on.

```bash
git clone https://github.com/saasdog-ai/shared-infrastructure.git
cd shared-infrastructure
```

**Bootstrap the Terraform state backend** (one-time):

```bash
cd infra/aws/terraform/bootstrap
terraform init
terraform apply -var="company_prefix=mycompany"
```

**Deploy the infrastructure**:

```bash
cd ../  # back to infra/aws/terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set company_prefix, environment, region, RDS settings
```

```bash
terraform init \
  -backend-config="bucket=mycompany-shared-infra-tfstate-dev" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=mycompany-shared-infra-tflock-dev" \
  -backend-config="encrypt=true"

terraform apply
```

**Note the outputs** — you'll need them for the next step:

```bash
terraform output
# vpc_id, ecs_cluster_arn, rds_endpoint, rds_master_password_secret_arn, etc.
```

> **Multi-cloud**: GCP and Azure Terraform configs are included under `infra/gcp/` and `infra/azure/`. Use `CLOUD=gcp` or `CLOUD=azure` with the orchestration script (Step 2 alternative).

### Step 2: Deploy integration-platform

```bash
git clone https://github.com/saasdog-ai/integration-platform.git
cd integration-platform
```

**Bootstrap the state backend** (one-time):

```bash
cd infra/aws/terraform/bootstrap
terraform init && terraform apply
```

**Configure and deploy**:

```bash
cd ../  # back to infra/aws/terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: paste shared-infrastructure outputs
#   shared_vpc_id, shared_ecs_cluster_arn, shared_rds_endpoint, etc.
```

```bash
terraform init \
  -backend-config="bucket=integration-platform-terraform-state-dev-ACCOUNT_ID" \
  -backend-config="key=terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="encrypt=true" \
  -backend-config="dynamodb_table=integration-platform-terraform-state-lock-dev"

terraform apply
```

**Alternative — one-command deployment** (handles both projects):

```bash
# From the parent directory containing both repos
CLOUD=aws COMPANY_PREFIX=mycompany ./scripts/infra.sh up
```

This bootstraps state backends, applies shared-infrastructure, reads its outputs, applies integration-platform, builds the Docker image, pushes to ECR, and deploys to ECS. Use `CLOUD=gcp` or `CLOUD=azure` for other clouds.

### Step 3: Set up secrets

The container's `start.sh` script auto-creates the database and runs Alembic migrations on first boot. `DATABASE_URL` is auto-constructed by Terraform from the shared-infrastructure RDS outputs. The remaining secrets need manual setup:

| Secret | Purpose | How to Create |
|--------|---------|---------------|
| `ADMIN_API_KEY` | Authenticates `/admin/*` endpoints | `openssl rand -base64 32 \| tr -d '/+=' \| head -c 32` |
| `JWT_SECRET_KEY` | Signs JWT tokens (HS256) | `openssl rand -base64 48` |
| `QBO_CLIENT_ID` / `QBO_CLIENT_SECRET` | QuickBooks OAuth | [Intuit Developer Portal](https://developer.intuit.com) |
| `XERO_CLIENT_ID` / `XERO_CLIENT_SECRET` | Xero OAuth | [Xero Developer Portal](https://developer.xero.com) |

**Where to store them**:
- **AWS**: Secrets Manager (Terraform creates the secret shells in `infra/aws/terraform/secrets.tf` — you populate the values)
- **GCP**: Secret Manager
- **Azure**: Key Vault
- **Local dev**: `.env` file (gitignored)

```bash
# Example: create the admin API key in AWS Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id "mycompany-integration-platform-admin-api-key-dev" \
  --secret-string "$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
```

### Step 4: Seed the database

After the first deploy (migrations have run), seed the integration catalog:

```bash
psql $DATABASE_URL -f scripts/seed_sample_data.sql
```

This populates:
- `available_integrations` — the catalog of supported integrations (QBO, Xero, NetSuite, Sage, HubSpot)
- `system_integration_settings` — default sync rules for QBO and Xero (entity types, directions, conflict resolution)

For custom integrations, add rows to these tables (see [Adding New Integrations](#adding-new-integrations)).

### Step 5: Verify deployment

```bash
curl https://your-app-url/health
# {"status": "healthy", "version": "0.1.0", ...}

curl https://your-app-url/docs
# Swagger UI — interactive API documentation
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `INTERNAL_DATABASE_URL` | Internal business data DB | `postgresql+asyncpg://postgres:postgres@localhost:5433/job_runner` |
| `APP_ENV` | Environment (`development` / `staging` / `production`) | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `AUTH_ENABLED` | Enable JWT authentication | `false` |
| `JWT_SECRET_KEY` | Token signing key (HS256) | `CHANGE_THIS_IN_PRODUCTION` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_JWKS_URL` | JWKS endpoint (for RS256) | - |
| `JWT_ISSUER` | Expected token issuer | - |
| `JWT_AUDIENCE` | Expected token audience | - |
| `CLOUD_PROVIDER` | Cloud provider (`local` / `aws` / `azure` / `gcp`) | `local` |
| `QUEUE_URL` | SQS queue URL (if using AWS) | - |
| `AWS_ENDPOINT_URL` | LocalStack endpoint (for local dev) | - |
| `JOB_RUNNER_ENABLED` | Enable background job runner | `true` |
| `JOB_RUNNER_MAX_WORKERS` | Max concurrent job workers | `5` |
| `ADMIN_API_KEY` | API key for admin endpoints (required in prod) | - |
| `SYNC_GLOBALLY_DISABLED` | Kill switch for all sync jobs | `false` |
| `DISABLED_INTEGRATIONS` | Comma-separated list of integrations to disable | - |

> **Production validation**: When `APP_ENV=production`, the app enforces that `AUTH_ENABLED=true`, `JWT_SECRET_KEY` is changed, and `ADMIN_API_KEY` is set. It will refuse to start otherwise.

### Tear down

```bash
CLOUD=aws ./scripts/infra.sh down
```

Or manually: `terraform destroy` in integration-platform first, then shared-infrastructure. State backends (S3 bucket, DynamoDB table) are preserved for the next spin-up.

### Cost Estimate (AWS, dev environment)

| Resource | Monthly |
|----------|---------|
| NAT Gateway | ~$32 |
| ALB | ~$16 |
| ECS Fargate (0.25 vCPU) | ~$9 |
| RDS (db.t3.micro) | ~$13 |
| Secrets Manager + KMS | ~$2 |
| **Total** | **~$73** |

## Customization Guide

### Connect to Your Own Data (Replace `internal_repo.py`)

This is the most important customization. The included `InternalDataRepository` (`app/integrations/shared/internal_repo.py`) reads and writes demo `sample_*` tables. In production, you replace it with access to your actual business data.

**What it does**: The sync strategies (QBO, Xero) call methods like `get_vendors()`, `upsert_vendor()`, `get_bills()`, `upsert_bill()` to read from and write to your internal system.

**Method contract** (per entity):

```python
async def get_{entity}s(
    self, client_id: UUID, since: datetime | None, record_ids: list[str] | None
) -> list[dict]

async def upsert_{entity}(
    self, client_id: UUID, data: dict, record_id: str | None
) -> str  # returns record ID
```

**Two approaches**:

1. **Direct DB access** (current pattern): Replace the SQL queries in `internal_repo.py` to point at your own tables instead of `sample_*`. Simplest if your data lives in the same PostgreSQL instance. Update `INTERNAL_DATABASE_URL` if it's in a different database.

2. **API client**: Replace `InternalDataRepository` with an HTTP client that calls your system's REST API. The sync strategies only depend on the method signatures above — the implementation can be anything.

**Entities currently supported**: vendor, customer, bill, invoice, chart_of_accounts, item, payment. Each has `get_*` and `upsert_*` methods. Add new entity methods following the same pattern.

### Enable JWT Authentication

By default, auth is disabled (`AUTH_ENABLED=false`). The API accepts an `X-Client-ID` header for tenant isolation during development.

**To enable in production**:

1. Set `AUTH_ENABLED=true`
2. Choose an approach:
   - **HS256 (shared secret)**: Set `JWT_SECRET_KEY` to a strong random value. Your auth server signs tokens with the same secret.
   - **RS256/ES256 (JWKS)**: Set `JWT_ALGORITHM=RS256`, `JWT_JWKS_URL=https://your-auth-server/.well-known/jwks.json`, and optionally `JWT_ISSUER` and `JWT_AUDIENCE`.
3. The platform extracts `client_id` from the JWT payload for multi-tenant isolation.

**Required token claims** (minimum):

```json
{
  "client_id": "uuid-string",
  "exp": 1234567890,
  "iat": 1234567890
}
```

The JWT verification code is in `app/auth/jwt.py` (uses `python-jose`). The auth dependency is in `app/auth/dependencies.py`.

### Adding New Integrations

The adapter pattern makes it easy to add new integrations — either manually or with AI assistance. Use Claude Code or similar tools to generate implementations:

**Example prompt for Claude Code:**
> "Create a Sage integration adapter that implements OAuth token exchange and fetches invoices. Follow the pattern in `app/integrations/quickbooks/`."

**Manual steps:**

1. **Create adapter** in `app/integrations/<name>/`:
   - `constants.py` — entity ordering, API endpoints, OAuth URLs
   - `mappers.py` — bidirectional data mapping (`INBOUND_MAPPERS`, `OUTBOUND_MAPPERS`)
   - `client.py` — API adapter implementing `IntegrationAdapterInterface`
   - `strategy.py` — sync strategy with inbound/outbound/bidirectional methods

2. **Register adapter** in `app/infrastructure/adapters/factory.py`

3. **Register strategy** in `app/services/sync_orchestrator.py` → `_init_strategies()`

4. **Seed the database** — add rows to `available_integrations` and `system_integration_settings` via `scripts/seed_sample_data.sql` or an Alembic migration

See the project's `CLAUDE.md` for the full adapter, strategy, and mapper contracts with detailed method signatures.

### Credential Encryption

OAuth tokens are encrypted at rest using pluggable encryption:

| Provider | Backend | Config |
|----------|---------|--------|
| AWS | KMS | Set `KMS_KEY_ID` |
| Azure | Key Vault | Set `AZURE_KEYVAULT_URL` |
| Local | Fernet | Default for development |

### Admin API

The `/admin/*` endpoints provide cross-tenant visibility and management. In production, they require an `X-Admin-API-Key` header. In development mode with no key configured, they're accessible without authentication.

Generate a key: `openssl rand -base64 32 | tr -d '/+=' | head -c 32`

## Quick Start (Local Dev)

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL 15+ (shared with import-export-orchestrator)

### With Docker

```bash
git clone <repository-url>
cd integration-platform
cp .env.example .env

# Start shared PostgreSQL (from sister project)
cd ../import-export-orchestrator
docker-compose up -d postgres

# Create the database
docker exec -it job_runner_db psql -U postgres -c "CREATE DATABASE integration_platform;"

# Start integration-platform
cd ../integration-platform
docker-compose up -d
```

This starts LocalStack (AWS emulation), the app, and runs migrations automatically.

**Access**:
- API: http://localhost:8001
- Swagger UI: http://localhost:8001/docs
- Health: http://localhost:8001/health

### Without Docker

```bash
python -m venv .venv
source .venv/bin/activate
make install-dev
cp .env.example .env
# Edit .env with your database connection
make migrate-upgrade
make run
```

### Micro-Frontend UI

```bash
cd ui
npm install
npm run build && npm run preview  # Runs on :3001
```

The micro-frontend **must** run in `preview` mode (not `dev`) — `vite-plugin-federation` requires built assets for `remoteEntry.js`.

Host apps ([saas-host-app](https://github.com/saasdog-ai/saas-host-app), [admin-host-app](https://github.com/saasdog-ai/admin-host-app)) load the micro-frontend and proxy API calls to the backend.

## API Reference

All endpoints require an `X-Client-ID` header (dev mode) or Bearer JWT token (production) for multi-tenant isolation.

Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

### Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| **Integrations** | | |
| `GET` | `/integrations/available` | List integration catalog |
| `GET` | `/integrations` | List user's connected integrations |
| `POST` | `/integrations/{id}/connect` | Start OAuth connection |
| `POST` | `/integrations/{id}/callback` | Complete OAuth callback |
| `DELETE` | `/integrations/{id}` | Disconnect integration |
| `GET` | `/integrations/{id}/sync-status` | Entity sync statuses |
| `POST` | `/integrations/{id}/notify` | Push change notification |
| **Records & Overrides** | | |
| `GET` | `/integrations/{id}/records` | Browse integration state records |
| `POST` | `/integrations/{id}/records/force-sync` | Force-sync failing records |
| `POST` | `/integrations/{id}/records/do-not-sync` | Toggle do-not-sync flag |
| **Settings** | | |
| `GET` / `PUT` | `/integrations/{id}/settings` | User sync settings |
| **Sync Jobs** | | |
| `POST` | `/sync-jobs` | Trigger sync job |
| `GET` | `/sync-jobs` | List jobs (paginated, filterable) |
| `GET` | `/sync-jobs/{id}` | Job details |
| `POST` | `/sync-jobs/{id}/cancel` | Cancel a job |
| `GET` | `/sync-jobs/{id}/records` | Record-level sync details |
| **Admin** (requires `X-Admin-API-Key`) | | |
| `GET` | `/admin/integrations` | All integrations across clients |
| `POST` | `/admin/integrations/available` | Create catalog entry |
| `PUT` | `/admin/integrations/available/{id}` | Update catalog entry |
| `GET` / `PUT` | `/integrations/{id}/settings/defaults` | System default settings |

### Settings Example

The settings endpoint controls sync behavior per integration per tenant:

```json
{
  "sync_rules": [
    {
      "entity_type": "vendor",
      "direction": "bidirectional",
      "enabled": true,
      "master_if_conflict": "external",
      "change_source": "polling",
      "sync_trigger": "deferred"
    },
    {
      "entity_type": "bill",
      "direction": "inbound",
      "enabled": true,
      "master_if_conflict": "external",
      "change_source": "push",
      "sync_trigger": "immediate"
    }
  ],
  "sync_frequency": "0 */6 * * *",
  "auto_sync_enabled": true
}
```

Options: direction (`inbound` / `outbound` / `bidirectional`), conflict resolution (`external` / `our_system`), change source (`polling` / `push` / `webhook` / `hybrid`), trigger (`deferred` / `immediate`).

### OpenAPI / Client SDK Generation

Download the spec and generate type-safe client libraries:

```bash
curl http://localhost:8001/openapi.json -o openapi.json

# TypeScript
npx @openapitools/openapi-generator-cli generate -i openapi.json -g typescript-fetch -o ./clients/typescript

# Python
npx @openapitools/openapi-generator-cli generate -i openapi.json -g python -o ./clients/python
```

See [OpenAPI Generator docs](https://openapi-generator.tech/docs/generators) for all supported languages.

### Error Responses

All errors follow this format:

```json
{
  "error": "Integration not found",
  "code": "NOT_FOUND",
  "details": null
}
```

Common HTTP status codes: `400` (validation), `401` (auth required), `403` (forbidden), `404` (not found), `409` (conflict), `500` (internal error).

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
- **Terraform** - Multi-cloud infrastructure (AWS, GCP, Azure)

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
│   │   ├── shared/           # InternalDataRepository (replace with your data)
│   │   ├── quickbooks/       # QBO strategy, mappers, constants, client
│   │   └── xero/             # Xero strategy, mappers, constants, client
│   ├── services/             # Orchestrator, job runner, integration service, settings
│   └── main.py               # FastAPI app entry point
├── ui/                       # React micro-frontend (Vite, TypeScript)
├── infra/
│   ├── aws/terraform/        # AWS ECS/Fargate infrastructure
│   ├── gcp/terraform/        # GCP Cloud Run infrastructure
│   ├── azure/terraform/      # Azure Container Apps infrastructure
│   └── shared/               # Shared infra module (alternative to standalone project)
├── docs/                     # Architecture documentation
├── tests/
│   ├── unit/                 # 285 unit tests
│   ├── integration/          # 3 E2E integration tests
│   └── mocks/                # Mock adapters, repos, encryption
├── alembic/                  # Database migrations (001-017)
├── scripts/                  # Demo, data generation, seed SQL
└── docker-compose.yml        # Local development (LocalStack, app)
```

## Related Projects

- **[shared-infrastructure](https://github.com/saasdog-ai/shared-infrastructure)** — Shared AWS/GCP/Azure infra (VPC, compute, database) — deploy this first
- **[import-export-orchestrator](https://github.com/saasdog-ai/import-export-orchestrator)** — Sister project for async import/export jobs (shares PostgreSQL)
- **[saas-host-app](https://github.com/saasdog-ai/saas-host-app)** — User-facing host app that embeds this platform's micro-frontend
- **[admin-host-app](https://github.com/saasdog-ai/admin-host-app)** — Admin host app that embeds the micro-frontend with admin API key
