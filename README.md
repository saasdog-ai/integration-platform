# Integration Platform

A production-ready framework for building integrations between your SaaS application and external providers (ERPs like QuickBooks, Xero, CRMs, HRIS systems, etc.).

## Why This Project?

Instead of paying expensive third-party integration vendors like Workato, MuleSoft, or Tray.io thousands of dollars per month, use this framework as a starting point to build your own integrations. The codebase is designed to be extended with AI coding tools like Claude Code — describe the integration you need, and let AI generate the adapter implementation.

**This is a chassis, not a finished product.** The included integrations (QuickBooks, etc.) are stubbed out for demonstration. You'll implement the actual API calls and data mappings for your specific use case.

## Features

- **Framework for Integrations**: Extensible adapter pattern — add new integrations by implementing a simple interface
- **OAuth Flow Built-In**: Complete OAuth 2.0 infrastructure for connecting external systems
- **Encrypted Credentials**: Secure credential storage with pluggable encryption (AWS KMS, Azure Key Vault, local)
- **Async Job Processing**: Background job runner with pluggable message queues (AWS SQS, in-memory)
- **Multi-Tenant Ready**: Full client isolation with partition-ready database design
- **Micro-Frontend UI**: React-based UI that can be embedded in your host application
- **Clean Architecture**: Hexagonal architecture makes it easy for AI tools to understand and extend
- **Cloud-Agnostic**: Designed to run on AWS, Azure, or GCP

## Technology Stack

- **Python 3.11+**
- **FastAPI** - Modern, fast async web framework
- **Pydantic v2** - Data validation and settings management
- **SQLAlchemy 2** - ORM with async support
- **Alembic** - Database migrations
- **APScheduler** - Cron job scheduling (ready for integration)
- **pytest** - Testing with coverage reporting
- **mypy, Ruff, Black** - Code quality tools
- **Docker & Docker Compose** - Containerization
- **Terraform** - Infrastructure as Code

## Project Structure

```
integration-platform/
├── app/
│   ├── api/                  # FastAPI routers and DTOs
│   ├── auth/                 # JWT authentication (pluggable)
│   ├── core/                 # Configuration, DI, logging, middleware
│   ├── domain/               # Domain entities, enums, interfaces
│   ├── infrastructure/
│   │   ├── adapters/         # Integration adapters (QuickBooks, Mock, etc.)
│   │   ├── db/               # Database models, repositories
│   │   ├── encryption/       # Encryption services (KMS, KeyVault, local)
│   │   ├── queue/            # Message queues (SQS, in-memory)
│   │   └── storage/          # Storage abstractions
│   ├── services/             # Business logic (sync orchestration, job runner)
│   └── main.py               # FastAPI application entry point
├── ui/                       # React micro-frontend
├── infra/
│   └── aws/terraform/        # AWS infrastructure (ECS/Fargate)
├── tests/                    # Test suite
├── alembic/                  # Database migrations
├── scripts/                  # Utility scripts
└── docker-compose.yml        # Local development setup
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

## API Endpoints

### Health Checks

- `GET /health` - Basic health check with version info

### Integrations

- `GET /integrations/available` - List available integrations
- `GET /integrations/available/{id}` - Get integration details
- `GET /integrations` - List user's connected integrations
- `GET /integrations/{id}` - Get connected integration details
- `POST /integrations/{id}/connect` - Start OAuth connection flow
- `POST /integrations/{id}/callback` - Complete OAuth with auth code
- `DELETE /integrations/{id}` - Disconnect an integration

### Sync Jobs

- `POST /sync-jobs` - Trigger a new sync job
- `GET /sync-jobs` - List sync jobs (with filters and pagination)
- `GET /sync-jobs/{id}` - Get sync job details
- `POST /sync-jobs/{id}/cancel` - Cancel a pending/running job
- `POST /sync-jobs/{id}/execute` - Execute job immediately (dev/demo)

### Settings

- `GET /settings/{integration_id}` - Get user's integration settings
- `PUT /settings/{integration_id}` - Update integration settings

See the interactive API documentation at `/docs` for detailed request/response schemas.

## Development

### Running Tests

```bash
# Run all tests with coverage
make test

# Run specific test file
pytest tests/unit/test_domain.py

# Run with verbose output
pytest -v
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
> "Create a Xero integration adapter that implements OAuth token exchange and fetches invoices. Follow the pattern in `app/infrastructure/adapters/quickbooks/`."

### Manual Steps

1. **Create adapter** in `app/infrastructure/adapters/<integration_name>/`:
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
