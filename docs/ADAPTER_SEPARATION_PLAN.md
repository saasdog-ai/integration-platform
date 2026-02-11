# Adapter Separation Plan: Hosted Integration Platform

This document outlines the architecture for separating the integration-platform into:
1. **Platform** (hosted by SaaSDog, closed source)
2. **Adapter SDK** (published to PyPI, open source)
3. **Customer Integrations** (customer's repo, Claude Code accessible)

---

## Table of Contents

1. [Overview](#overview)
2. [Target Architecture](#target-architecture)
3. [SDK Package Contents](#sdk-package-contents)
4. [Customer Integrations Repo Structure](#customer-integrations-repo-structure)
5. [Interface Definitions](#interface-definitions)
6. [Entity Definitions](#entity-definitions)
7. [Enum Definitions](#enum-definitions)
8. [Settings and OAuth Token Management](#settings-and-oauth-token-management)
9. [Change Detection and Sync Triggers](#change-detection-and-sync-triggers)
10. [Platform Adapter Loading](#platform-adapter-loading)
11. [Customer CI/CD Pipeline](#customer-cicd-pipeline)
12. [Deployment Model](#deployment-model)
13. [Migration Steps](#migration-steps)

---

## Overview

### Current State

```
integration-platform/
├── app/
│   ├── domain/
│   │   ├── interfaces.py      # IntegrationAdapterInterface, etc.
│   │   ├── entities.py        # ExternalRecord, OAuthTokens, SyncJob, etc.
│   │   └── enums.py           # SyncDirection, RecordSyncStatus, etc.
│   │
│   └── integrations/
│       └── quickbooks/
│           ├── client.py      # QuickBooksAdapter
│           ├── strategy.py    # QuickBooksSyncStrategy
│           ├── mappers.py     # Inbound/outbound mappers
│           ├── constants.py   # Entity names, ordering
│           └── internal_repo.py  # Writes to sample_* tables
```

### Problems with Current State

1. Adapters are tightly coupled to platform code
2. Customers can't add new integrations without modifying platform
3. No clear separation for hosted deployment model
4. Customers can't use Claude Code on adapters without platform source access

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ integration-platform (your core, closed source for hosted)         │
├─────────────────────────────────────────────────────────────────────┤
│ app/                                                                │
│   ├── domain/              # Stays here, also published as SDK     │
│   ├── services/            # Sync orchestrator, job runner         │
│   ├── api/                 # REST endpoints                        │
│   └── infrastructure/      # DB, queue, encryption                 │
│                                                                     │
│ NO adapters here anymore                                            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ saasdog-adapter-sdk (published to PyPI, MIT license)               │
├─────────────────────────────────────────────────────────────────────┤
│ saasdog_sdk/                                                        │
│   ├── __init__.py                                                   │
│   ├── interfaces.py        # IntegrationAdapterInterface           │
│   │                        # SyncStrategyInterface                 │
│   │                        # InternalDataRepositoryInterface       │
│   │                        # WebhookHandlerInterface               │
│   ├── entities.py          # ExternalRecord, OAuthTokens, etc.     │
│   ├── enums.py             # SyncDirection, RecordSyncStatus, etc. │
│   └── http.py              # HTTP client utilities                 │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ customer-integrations (customer's repo, Claude Code accessible)    │
├─────────────────────────────────────────────────────────────────────┤
│ Dockerfile                 # FROM saasdog/platform:x.x.x           │
│ adapters/                                                           │
│   ├── saasdog.yaml         # Adapter manifest                      │
│   ├── internal_repo.py     # Customer implements for their DB      │
│   ├── quickbooks/                                                   │
│   │   ├── adapter.py       # QuickBooksAdapter                     │
│   │   ├── strategy.py      # QuickBooksSyncStrategy                │
│   │   ├── mappers.py       # Schema mappings                       │
│   │   ├── constants.py     # Entity config                         │
│   │   └── webhook.py       # QuickBooksWebhookHandler              │
│   └── xero/                # Future adapters...                    │
│       └── ...                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Deployment Model

**Key principle:** You (SaaSDog) provision all infrastructure. Customer only writes adapters.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: You provision infrastructure into customer's AWS account           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Your Control Plane                    Customer's AWS Account               │
│  ┌───────────────────┐                 ┌─────────────────────────────────┐  │
│  │                   │  Terraform/     │                                 │  │
│  │ Provisioning      │  Cross-account  │  ┌─────────────┐                │  │
│  │ System            │────────────────►│  │ RDS Postgres│                │  │
│  │                   │  IAM role       │  └─────────────┘                │  │
│  └───────────────────┘                 │  ┌─────────────┐                │  │
│                                        │  │ SQS Queues  │                │  │
│                                        │  └─────────────┘                │  │
│                                        │  ┌─────────────┐                │  │
│                                        │  │ S3 Bucket   │                │  │
│                                        │  └─────────────┘                │  │
│                                        │  ┌─────────────┐                │  │
│                                        │  │ ECS Cluster │                │  │
│                                        │  └─────────────┘                │  │
│                                        │  ┌─────────────┐                │  │
│                                        │  │ ECR Repo    │ (for their     │  │
│                                        │  └─────────────┘  built images) │  │
│                                        └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Customer extends your base image with their adapters                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Your Private ECR              Customer's Repo            Customer's ECR    │
│  ┌───────────────┐             ┌─────────────────┐        ┌─────────────┐  │
│  │               │             │ Dockerfile:     │        │             │  │
│  │ platform:1.2.3│◄────────────│ FROM saasdog/   │───────►│ acme:latest │  │
│  │               │   extends   │   platform:1.2.3│ builds │             │  │
│  │ (your code,   │             │                 │        │ (platform + │  │
│  │  no source)   │             │ COPY adapters/  │        │  adapters)  │  │
│  │               │             │   /app/adapters/│        │             │  │
│  └───────────────┘             │                 │        └─────────────┘  │
│                                │ # Their adapters│              │          │
│                                │ # baked in      │              │          │
│                                └─────────────────┘              │          │
│                                        │                        │          │
│                                Claude Code ✓                    │          │
│                                        │                        ▼          │
│                                        │               ┌─────────────────┐ │
│                                        └──────────────►│ ECS Service     │ │
│                                          CI/CD deploys │ (runs combined  │ │
│                                                        │  image)         │ │
│                                                        └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

**What each party does:**

| You (SaaSDog) | Customer |
|---------------|----------|
| Publish platform base image to your ECR | Write adapters in their repo |
| Provision RDS, SQS, S3, ECS into their AWS | Extend base image with Dockerfile |
| Manage infrastructure lifecycle | Run CI/CD to build & deploy |
| Push platform updates/patches | Pull new base version when ready |
| Monitor, alerting | Configure OAuth for external systems |

**Customer's Dockerfile:**

```dockerfile
# They extend your base image - no platform source code visible
FROM <your-ecr>/saasdog/platform:1.2.3

# Copy their adapters (this is all they write)
COPY adapters/ /app/adapters/
COPY requirements.txt /app/adapter-requirements.txt
RUN pip install -r /app/adapter-requirements.txt
```

**Adapters are baked in at build time**, not loaded dynamically at runtime. This is simpler and more secure.

---

## SDK Package Contents

```
saasdog-adapter-sdk/
├── pyproject.toml
├── README.md
├── saasdog_sdk/
│   ├── __init__.py
│   ├── interfaces.py      # Abstract base classes
│   ├── entities.py        # Data models
│   ├── enums.py           # Enumerations
│   └── http.py            # HTTP client utilities
```

### pyproject.toml

```toml
[project]
name = "saasdog-adapter-sdk"
version = "0.1.0"
description = "SDK for building SaaSDog integration adapters"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
dependencies = [
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Customer Integrations Repo Structure

```
acme-integrations/                    # Claude Code works here
├── Dockerfile                        # FROM saasdog/platform:x.x.x
├── adapters/
│   ├── __init__.py
│   ├── saasdog.yaml                  # Adapter manifest
│   ├── internal_repo.py              # Customer's internal data access
│   ├── quickbooks/
│   │   ├── __init__.py
│   │   ├── adapter.py
│   │   ├── strategy.py
│   │   ├── mappers.py
│   │   ├── constants.py
│   │   └── webhook.py
│   └── xero/
│       └── ...
├── requirements.txt                  # Adapter dependencies
├── CLAUDE.md                         # How to build adapters
├── .github/
│   └── workflows/
│       └── deploy.yml
└── tests/
    └── test_quickbooks.py
```

### Dockerfile

```dockerfile
# Customer's repo: acme-integrations/Dockerfile
FROM <your-account>.dkr.ecr.us-east-1.amazonaws.com/saasdog/platform:1.2.3

# Copy their adapters into the image
COPY adapters/ /app/adapters/
COPY requirements.txt /app/adapter-requirements.txt
RUN pip install -r /app/adapter-requirements.txt
```

### Adapter Manifest (saasdog.yaml)

```yaml
# adapters/saasdog.yaml

internal_repo:
  module: adapters.internal_repo
  class: AcmeInternalRepo

adapters:
  - name: quickbooks
    module: adapters.quickbooks.adapter
    adapter_class: QuickBooksAdapter
    strategy_class: QuickBooksSyncStrategy
    webhook_handler_class: QuickBooksWebhookHandler

  - name: xero
    module: adapters.xero.adapter
    adapter_class: XeroAdapter
    strategy_class: XeroSyncStrategy
    webhook_handler_class: XeroWebhookHandler
```

---

## Interface Definitions

### interfaces.py

```python
"""Abstract interfaces that adapters implement."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from saasdog_sdk.entities import (
    AuthenticatedContext,
    ConnectionConfig,
    ExternalRecord,
    IntegrationHistoryRecord,
    IntegrationStateRecord,
    OAuthTokens,
    SyncContext,
    SyncJob,
    SyncRule,
    WebhookEvent,
)
from saasdog_sdk.enums import RecordSyncStatus, SyncDirection


# =============================================================================
# External System Adapter Interface
# =============================================================================

class IntegrationAdapterInterface(ABC):
    """Interface for external system adapters (QuickBooks, Xero, etc.).

    Handles all communication with the external system's API.
    """

    @abstractmethod
    def with_auth(self, auth_context: AuthenticatedContext) -> "IntegrationAdapterInterface":
        """Return adapter instance configured with auth credentials.

        Platform calls this before any API operations.
        """

    # -------------------------------------------------------------------------
    # OAuth
    # -------------------------------------------------------------------------

    @abstractmethod
    async def authenticate(
        self,
        auth_code: str,
        redirect_uri: str,
        connection_config: ConnectionConfig,
    ) -> OAuthTokens:
        """Exchange authorization code for tokens."""

    @abstractmethod
    async def refresh_token(
        self,
        refresh_token: str,
        connection_config: ConnectionConfig,
    ) -> OAuthTokens:
        """Refresh expired access token.

        Platform calls this when access_token is expired.
        Adapter makes HTTP call to OAuth provider.
        Platform stores the returned tokens.
        """

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def fetch_records(
        self,
        entity_type: str,
        since: datetime | None = None,
        page_token: str | None = None,
        record_ids: list[str] | None = None,
    ) -> tuple[list[ExternalRecord], str | None]:
        """Fetch records from external system.

        Args:
            entity_type: The entity type to fetch (e.g., "vendor", "bill").
            since: Only fetch records modified after this time.
            page_token: Pagination token for fetching next page.
            record_ids: Optional list of specific record IDs to fetch.

        Returns:
            Tuple of (records, next_page_token)
        """

    @abstractmethod
    async def get_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> ExternalRecord | None:
        """Get a single record by ID from external system."""

    @abstractmethod
    async def create_record(
        self,
        entity_type: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Create record in external system."""

    @abstractmethod
    async def update_record(
        self,
        entity_type: str,
        external_id: str,
        data: dict[str, Any],
    ) -> ExternalRecord:
        """Update record in external system."""

    @abstractmethod
    async def delete_record(
        self,
        entity_type: str,
        external_id: str,
    ) -> bool:
        """Delete record in external system."""


# =============================================================================
# Sync Strategy Interface
# =============================================================================

class SyncStrategyInterface(ABC):
    """Interface for provider-specific sync logic.

    Handles entity ordering, schema mapping, and orchestrates the
    sync operations between external and internal systems.
    """

    @abstractmethod
    def get_entity_order(self, direction: SyncDirection) -> list[str]:
        """Return entity types in dependency order for the given direction."""

    @abstractmethod
    def get_ordered_rules(
        self,
        rules: list[SyncRule],
        direction: SyncDirection,
    ) -> list[SyncRule]:
        """Sort enabled rules according to entity dependency order."""

    @abstractmethod
    async def sync_entity_inbound(
        self,
        context: SyncContext,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: "IntegrationStateRepositoryInterface",
        internal_repo: "InternalDataRepositoryInterface",
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pull records from external system, write to internal database.

        Returns a summary dict with counts of fetched/created/updated/failed records.
        """

    @abstractmethod
    async def sync_entity_outbound(
        self,
        context: SyncContext,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: "IntegrationStateRepositoryInterface",
        internal_repo: "InternalDataRepositoryInterface",
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Push records from internal database to external system.

        Discovers records via version vectors in state_repo, pushes to
        the external system, and equalizes all three version fields.

        Returns a summary dict with counts.
        """

    @abstractmethod
    async def sync_entity_bidirectional(
        self,
        context: SyncContext,
        entity_type: str,
        adapter: IntegrationAdapterInterface,
        state_repo: "IntegrationStateRepositoryInterface",
        internal_repo: "InternalDataRepositoryInterface",
        rule: SyncRule,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Bidirectional sync using version vectors for conflict detection.

        Classifies each record as inbound, outbound, conflict, or in-sync
        based on version vectors, then delegates to the appropriate handler.

        Returns a summary dict with counts.
        """


# =============================================================================
# Internal Data Repository Interface
# =============================================================================

class InternalDataRepositoryInterface(ABC):
    """Interface for CRUD operations on customer's internal data.

    Customer implements this to connect to their business database.
    The sync strategy uses this to read/write during sync operations.
    """

    # -------------------------------------------------------------------------
    # Read operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_records(
        self,
        client_id: UUID,
        entity_type: str,
        since: datetime | None = None,
        record_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get records from internal system.

        Used during outbound sync to find records to push to external system.

        Args:
            client_id: Tenant ID for multi-tenant isolation
            entity_type: e.g., "vendor", "bill", "invoice"
            since: Only return records modified after this time
            record_ids: If provided, only return these specific records

        Returns:
            List of record dicts. Must include "id" field.
        """

    @abstractmethod
    async def get_record_by_id(
        self,
        client_id: UUID,
        entity_type: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        """Get a single record by internal ID."""

    @abstractmethod
    async def get_record_by_external_id(
        self,
        client_id: UUID,
        entity_type: str,
        external_id: str,
    ) -> dict[str, Any] | None:
        """Get a record by its external system ID.

        Used during inbound sync to check if record already exists.
        """

    # -------------------------------------------------------------------------
    # Write operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def create_record(
        self,
        client_id: UUID,
        entity_type: str,
        data: dict[str, Any],
    ) -> str:
        """Create a new record. Returns internal record ID."""

    @abstractmethod
    async def update_record(
        self,
        client_id: UUID,
        entity_type: str,
        record_id: str,
        data: dict[str, Any],
    ) -> None:
        """Update an existing record."""

    @abstractmethod
    async def upsert_record(
        self,
        client_id: UUID,
        entity_type: str,
        data: dict[str, Any],
        external_id: str | None = None,
    ) -> str:
        """Create or update a record.

        If external_id is provided and a record with that external_id exists,
        update it. Otherwise create a new record.

        Returns internal record ID.
        """

    @abstractmethod
    async def delete_record(
        self,
        client_id: UUID,
        entity_type: str,
        record_id: str,
    ) -> bool:
        """Delete a record. Returns True if deleted."""

    # -------------------------------------------------------------------------
    # External ID management
    # -------------------------------------------------------------------------

    @abstractmethod
    async def set_external_id(
        self,
        client_id: UUID,
        entity_type: str,
        record_id: str,
        external_id: str,
    ) -> None:
        """Set the external system ID on an internal record.

        Called after successful outbound sync to link internal record
        to its external counterpart.
        """


# =============================================================================
# Integration State Repository Interface (Platform-provided)
# =============================================================================

class IntegrationStateRepositoryInterface(ABC):
    """Interface for sync state access.

    Provided by platform, not implemented by customer.
    Tracks version vectors and sync status for each record.
    """

    @abstractmethod
    async def get_record(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        internal_record_id: str | None = None,
    ) -> IntegrationStateRecord | None:
        """Get a specific record's sync state by internal record ID."""

    @abstractmethod
    async def get_record_by_external_id(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        external_record_id: str,
    ) -> IntegrationStateRecord | None:
        """Get a specific record's sync state by external record ID."""

    @abstractmethod
    async def get_records_by_status(
        self,
        client_id: UUID,
        integration_id: UUID,
        entity_type: str,
        status: RecordSyncStatus,
        limit: int = 1000,
    ) -> list[IntegrationStateRecord]:
        """Get records by sync status."""

    @abstractmethod
    async def upsert_record(
        self,
        record: IntegrationStateRecord,
    ) -> IntegrationStateRecord:
        """Create or update a record's sync state."""

    @abstractmethod
    async def batch_upsert_records(
        self,
        records: list[IntegrationStateRecord],
    ) -> list[IntegrationStateRecord]:
        """Upsert multiple records in a single transaction."""

    @abstractmethod
    async def batch_create_history(
        self,
        entries: list[IntegrationHistoryRecord],
    ) -> None:
        """Create multiple history entries in a single transaction."""


# =============================================================================
# Webhook Handler Interface
# =============================================================================

class WebhookHandlerInterface(ABC):
    """Interface for provider-specific webhook handling.

    Each external system has different webhook formats and signature
    verification methods. Adapter implements this for webhook support.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'quickbooks', 'xero')."""

    @abstractmethod
    def verify_signature(
        self,
        headers: dict[str, str],
        body: bytes,
        secret: str,
    ) -> bool:
        """Verify webhook signature from the provider."""

    @abstractmethod
    def parse_payload(self, body: bytes) -> list[WebhookEvent]:
        """Parse webhook payload into normalized events."""
```

---

## Entity Definitions

### entities.py

```python
"""Domain entities used by adapters."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Any, Literal
from uuid import UUID

from saasdog_sdk.enums import ConflictResolution, RecordSyncStatus, SyncDirection


# =============================================================================
# External System Entities
# =============================================================================

@dataclass
class ExternalRecord:
    """A record fetched from an external system."""
    id: str
    entity_type: str
    data: dict[str, Any]
    version: str | None = None
    updated_at: datetime | None = None


@dataclass
class OAuthTokens:
    """OAuth tokens from external system."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    expires_at: datetime | None = None
    scope: str | None = None


@dataclass
class OAuthCredentials:
    """OAuth credentials passed to adapter."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        # Add 5 minute buffer
        return datetime.now(UTC) >= (self.expires_at - timedelta(minutes=5))


@dataclass
class ConnectionConfig:
    """OAuth app configuration (client credentials)."""
    client_id: str
    client_secret: str

    # Provider-specific
    realm_id: str | None = None      # QuickBooks company ID
    tenant_id: str | None = None     # Xero tenant ID

    # OAuth URLs (can be overridden per provider)
    auth_url: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None


@dataclass
class AuthenticatedContext:
    """Everything adapter needs to make authenticated API calls."""
    credentials: OAuthCredentials
    connection_config: ConnectionConfig

    def auth_header(self) -> dict[str, str]:
        """Get Authorization header."""
        return {
            "Authorization": f"{self.credentials.token_type} {self.credentials.access_token}"
        }


# =============================================================================
# Sync Entities
# =============================================================================

@dataclass
class SyncJob:
    """A sync job being executed."""
    id: UUID
    client_id: UUID
    integration_id: UUID
    status: str
    job_params: dict[str, Any] | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None


@dataclass
class SyncRule:
    """Configuration for syncing an entity type."""
    entity_type: str
    enabled: bool = True
    direction: SyncDirection = SyncDirection.INBOUND
    master_if_conflict: ConflictResolution = ConflictResolution.EXTERNAL
    custom_field_mappings: dict[str, str] | None = None  # internal_field → external_field


@dataclass
class IntegrationSettings:
    """Full settings for an integration."""
    sync_rules: list[SyncRule]
    auto_sync_enabled: bool = True
    sync_frequency: str = "*/15 * * * *"  # Cron expression
    sync_trigger: Literal["deferred", "immediate"] = "deferred"

    # Provider-specific settings (adapter can access these)
    provider_settings: dict[str, Any] | None = None


@dataclass
class SyncContext:
    """Context passed to strategy during sync operations."""
    job: SyncJob
    settings: IntegrationSettings
    rules: list[SyncRule]

    def get_rule(self, entity_type: str) -> SyncRule | None:
        """Get sync rule for an entity type."""
        return next((r for r in self.rules if r.entity_type == entity_type), None)


# =============================================================================
# State Tracking Entities
# =============================================================================

@dataclass
class IntegrationStateRecord:
    """Sync state for a single record."""
    id: UUID
    client_id: UUID
    integration_id: UUID
    entity_type: str
    internal_record_id: str | None = None
    external_record_id: str | None = None
    sync_status: RecordSyncStatus = RecordSyncStatus.PENDING
    sync_direction: SyncDirection | None = None
    internal_version_id: int = 1
    external_version_id: int = 1
    last_sync_version_id: int = 1
    last_synced_at: datetime | None = None
    last_job_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_in_sync(self) -> bool:
        """All version vectors are equal."""
        return (
            self.internal_version_id == self.external_version_id == self.last_sync_version_id
        )

    @property
    def needs_outbound_sync(self) -> bool:
        """Internal system has changes not yet synced."""
        return self.internal_version_id > self.last_sync_version_id

    @property
    def needs_inbound_sync(self) -> bool:
        """External system has changes not yet synced."""
        return self.external_version_id > self.last_sync_version_id


@dataclass
class IntegrationHistoryRecord:
    """Audit log entry for a sync operation."""
    id: UUID
    client_id: UUID
    state_record_id: UUID
    integration_id: UUID
    entity_type: str
    internal_record_id: str | None = None
    external_record_id: str | None = None
    sync_status: RecordSyncStatus = RecordSyncStatus.PENDING
    sync_direction: SyncDirection | None = None
    job_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    created_at: datetime | None = None


# =============================================================================
# Webhook Entities
# =============================================================================

@dataclass
class WebhookEvent:
    """Normalized webhook event."""
    entity_type: str
    record_ids: list[str]
    event_type: str  # "created", "updated", "deleted"
```

---

## Enum Definitions

### enums.py

```python
"""Enumerations used by adapters."""

from enum import Enum


class SyncDirection(str, Enum):
    INBOUND = "INBOUND"          # External → Internal
    OUTBOUND = "OUTBOUND"        # Internal → External
    BIDIRECTIONAL = "BIDIRECTIONAL"


class RecordSyncStatus(str, Enum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ConflictResolution(str, Enum):
    EXTERNAL = "EXTERNAL"        # External system wins
    OUR_SYSTEM = "OUR_SYSTEM"    # Internal system wins
```

---

## Settings and OAuth Token Management

### How Settings Flow to Adapters

Platform loads settings and passes them to the strategy via `SyncContext`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Platform (owns settings)                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────┐    ┌─────────────────────────┐                 │
│  │ user_integration_       │    │ system_integration_     │                 │
│  │ settings                │    │ settings                │                 │
│  │                         │    │                         │                 │
│  │ - sync_rules            │    │ - default_sync_rules    │                 │
│  │ - entity configs        │    │ - default configs       │                 │
│  │ - custom mappings       │    │                         │                 │
│  └───────────┬─────────────┘    └───────────┬─────────────┘                 │
│              │                              │                               │
│              └──────────┬───────────────────┘                               │
│                         ▼                                                   │
│              ┌─────────────────────────┐                                    │
│              │ SyncOrchestrator        │                                    │
│              │                         │                                    │
│              │ 1. Load settings        │                                    │
│              │ 2. Merge user + system  │                                    │
│              │ 3. Build SyncContext    │                                    │
│              └───────────┬─────────────┘                                    │
│                          │                                                  │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Adapter (receives settings via SyncContext)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  strategy.sync_entity_inbound(                                              │
│      context=SyncContext(         ◄─── Settings passed in                  │
│          rules=[SyncRule(...), ...],                                        │
│          settings=IntegrationSettings(...),                                 │
│      ),                                                                     │
│      ...                                                                    │
│  )                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How OAuth Token Management Works

Platform manages token storage/encryption. Adapter just implements refresh logic.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Platform (owns tokens)                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ user_integrations                                                   │    │
│  │                                                                     │    │
│  │ - encrypted_credentials (access_token, refresh_token, expires_at)  │    │
│  │ - connection_config (client_id, client_secret, realm_id)           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  TokenManager:                                                              │
│  1. Decrypt credentials                                                     │
│  2. Check if access_token expired                                           │
│  3. If expired → call adapter.refresh_token()                               │
│  4. Store new tokens (encrypted)                                            │
│  5. Pass valid access_token to adapter                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Platform TokenManager (Pseudocode)

```python
# Platform code (not in SDK)

class TokenManager:
    """Manages OAuth tokens - decryption, refresh, storage."""

    def __init__(
        self,
        encryption_service: EncryptionServiceInterface,
        integration_repo: IntegrationRepositoryInterface,
    ):
        self._encryption = encryption_service
        self._repo = integration_repo

    async def get_authenticated_context(
        self,
        user_integration: UserIntegration,
        adapter: IntegrationAdapterInterface,
    ) -> AuthenticatedContext:
        """Get valid credentials, refreshing if needed."""

        # 1. Decrypt stored credentials
        credentials = await self._decrypt_credentials(user_integration)
        connection_config = self._get_connection_config(user_integration)

        # 2. Check if token expired
        if credentials.is_expired:
            # 3. Call adapter to refresh
            new_tokens = await adapter.refresh_token(
                refresh_token=credentials.refresh_token,
                connection_config=connection_config,
            )

            # 4. Store new tokens (encrypted)
            await self._store_credentials(user_integration, new_tokens)

            credentials = OAuthCredentials(
                access_token=new_tokens.access_token,
                refresh_token=new_tokens.refresh_token,
                expires_at=new_tokens.expires_at,
            )

        return AuthenticatedContext(
            credentials=credentials,
            connection_config=connection_config,
        )
```

---

## Change Detection and Sync Triggers

### 1. Polling (Platform → External System)

No adapter changes needed. Platform handles scheduling.

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Platform        │         │ Customer's      │         │ External System │
│ (Scheduler)     │         │ Adapter         │         │ (QuickBooks)    │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
         │                           │                           │
         │ 1. Cron triggers job      │                           │
         ├──────────────────────────►│                           │
         │                           │ 2. fetch_records(since)   │
         │                           ├──────────────────────────►│
         │                           │                           │
         │                           │◄──────────────────────────┤
         │                           │ 3. Records returned       │
         │◄──────────────────────────┤                           │
         │ 4. Update state, write    │                           │
         │    to internal DB         │                           │
```

### 2. Push (Customer's System → Platform)

Customer calls platform API when their data changes.

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Customer's      │         │ Platform        │         │ Customer's      │
│ Backend App     │         │ API             │         │ Adapter         │
└────────┬────────┘         └────────┬────────┘         └────────┬────────┘
         │                           │                           │
         │ 1. Data changed           │                           │
         │    POST /notify/push      │                           │
         ├──────────────────────────►│                           │
         │    {entity: "vendor",     │                           │
         │     record_ids: [...]}    │                           │
         │                           │                           │
         │                           │ 2. Bump internal_version_id
         │                           │    on state records       │
         │                           │                           │
         │                           │ 3. If immediate trigger:  │
         │                           │    Queue sync job         │
         │                           ├──────────────────────────►│
```

Platform API endpoint:

```python
@router.post("/notify/push")
async def notify_internal_change(
    request: PushNotificationRequest,
    client_id: UUID = Depends(get_client_id),
):
    """Customer's backend calls this when internal data changes."""
    await state_repo.bump_version_vectors(
        client_id=client_id,
        integration_id=request.integration_id,
        entity_type=request.entity_type,
        record_ids=request.record_ids,
        bump_internal=True,
    )

    if settings.sync_trigger == "immediate":
        await queue_sync_job(client_id, request.integration_id)
```

### 3. Webhook (External System → Platform)

Requires adapter-specific logic for signature verification and payload parsing.

```python
# adapters/quickbooks/webhook.py

from saasdog_sdk.interfaces import WebhookHandlerInterface, WebhookEvent
import hmac
import hashlib
import base64
import json

class QuickBooksWebhookHandler(WebhookHandlerInterface):

    def provider_name(self) -> str:
        return "quickbooks"

    def verify_signature(
        self,
        headers: dict[str, str],
        body: bytes,
        secret: str,
    ) -> bool:
        """Verify Intuit webhook signature."""
        signature = headers.get("intuit-signature", "")
        expected = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).digest()
        return hmac.compare_digest(base64.b64decode(signature), expected)

    def parse_payload(self, body: bytes) -> list[WebhookEvent]:
        """Parse QuickBooks webhook payload."""
        data = json.loads(body)
        events = []

        for notification in data.get("eventNotifications", []):
            for entity in notification.get("dataChangeEvent", {}).get("entities", []):
                events.append(WebhookEvent(
                    entity_type=entity["name"].lower(),
                    record_ids=[entity["id"]],
                    event_type=entity["operation"].lower(),
                ))

        return events
```

Platform webhook endpoint:

```python
@router.post("/webhooks/{provider}")
async def handle_webhook(provider: str, request: Request):
    """Receive webhooks from external systems."""
    body = await request.body()
    headers = dict(request.headers)

    handler = get_webhook_handler(provider)
    if not handler:
        raise HTTPException(404, f"No webhook handler for {provider}")

    secret = await get_webhook_secret(provider)
    if not handler.verify_signature(headers, body, secret):
        raise HTTPException(401, "Invalid signature")

    events = handler.parse_payload(body)

    for event in events:
        await state_repo.bump_version_vectors(
            client_id=client_id,
            integration_id=integration_id,
            entity_type=event.entity_type,
            record_ids=event.record_ids,
            bump_external=True,
        )

    if settings.sync_trigger == "immediate":
        await queue_sync_job(client_id, integration_id)
```

### Sync Triggers

**Deferred (Batch on Schedule):**
```
10:01   Push notification → bump internal_version_id
10:05   Webhook received → bump external_version_id
10:12   Another push → bump internal_version_id

10:15   Scheduled sync job runs
        └─ Finds all records with needs_outbound_sync
        └─ Finds all records with needs_inbound_sync
        └─ Syncs everything in one batch
```

**Immediate (Real-time):**
```
10:01   Push notification
        └─ bump internal_version_id
        └─ Queue sync job immediately
10:01   Sync job runs (just that record)

10:05   Webhook received
        └─ bump external_version_id
        └─ Queue sync job immediately
10:05   Sync job runs (just that record)
```

---

## Platform Adapter Loading

Adapters are **baked into the Docker image** at build time (via customer's Dockerfile).
At container startup, platform loads them from `/app/adapters/`.

### Adapter Loader

```python
# Platform code - runs at container startup

import importlib
import yaml
from pathlib import Path

def load_customer_adapters(adapter_path: str = "/app/adapters"):
    """Load adapters baked into the container image.

    Customer's Dockerfile copies their adapters to /app/adapters/.
    This function reads the manifest and imports the adapter classes.
    """

    manifest_path = Path(adapter_path) / "saasdog.yaml"
    if not manifest_path.exists():
        raise RuntimeError("No saasdog.yaml manifest found at /app/adapters/")

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    # Load customer's internal repo implementation
    repo_config = manifest["internal_repo"]
    repo_mod = importlib.import_module(repo_config["module"])
    internal_repo_cls = getattr(repo_mod, repo_config["class"])
    internal_repo = internal_repo_cls()

    # Load each adapter defined in manifest
    adapters = {}
    for adapter_config in manifest["adapters"]:
        mod = importlib.import_module(adapter_config["module"])

        adapter_cls = getattr(mod, adapter_config["adapter_class"])
        strategy_cls = getattr(mod, adapter_config["strategy_class"])
        webhook_handler_cls = None

        if "webhook_handler_class" in adapter_config:
            webhook_handler_cls = getattr(mod, adapter_config["webhook_handler_class"])

        adapters[adapter_config["name"]] = {
            "adapter_class": adapter_cls,
            "strategy": strategy_cls(internal_repo=internal_repo),
            "webhook_handler": webhook_handler_cls() if webhook_handler_cls else None,
        }

    return adapters, internal_repo


# Called at FastAPI startup
@app.on_event("startup")
async def startup():
    global LOADED_ADAPTERS, INTERNAL_REPO
    LOADED_ADAPTERS, INTERNAL_REPO = load_customer_adapters()
```

### Full Sync Flow

```python
# Platform's SyncOrchestrator

class SyncOrchestrator:

    async def execute_sync_job(self, job: SyncJob):
        # 1. Load user integration
        user_integration = await self._repo.get_user_integration(
            job.client_id, job.integration_id
        )

        # 2. Load settings (merged user + system)
        settings = await self._load_settings(job.client_id, job.integration_id)

        # 3. Get adapter from customer's loaded adapters
        adapter_info = self._loaded_adapters[user_integration.integration_name]
        adapter_cls = adapter_info["adapter_class"]
        strategy = adapter_info["strategy"]

        # 4. Get authenticated context (handles token refresh)
        adapter_instance = adapter_cls()
        auth_context = await self._token_manager.get_authenticated_context(
            user_integration, adapter_instance
        )

        # 5. Create authed adapter
        authed_adapter = adapter_instance.with_auth(auth_context)

        # 6. Build sync context
        sync_context = SyncContext(
            job=job,
            settings=settings,
            rules=settings.sync_rules,
        )

        # 7. Execute sync with strategy
        for rule in strategy.get_ordered_rules(settings.sync_rules, SyncDirection.INBOUND):
            if rule.direction in (SyncDirection.INBOUND, SyncDirection.BIDIRECTIONAL):
                await strategy.sync_entity_inbound(
                    context=sync_context,
                    entity_type=rule.entity_type,
                    adapter=authed_adapter,
                    state_repo=self._state_repo,
                    internal_repo=self._internal_repo,
                )
```

---

## Customer CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Adapters

on:
  push:
    branches: [main]
  repository_dispatch:
    types: [platform-patch]
  workflow_dispatch:

env:
  AWS_REGION: us-east-1
  ECR_REPO: acme-integrations
  ECS_CLUSTER: saasdog
  ECS_SERVICE: platform

jobs:
  deploy:
    runs-on: ubuntu-latest

    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/github-deploy
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push
        run: |
          # Always pull fresh base image to get patches
          docker pull ${{ secrets.SAASDOG_ECR }}/platform:1.2 --quiet

          docker build \
            --pull \
            -t $ECR_REPO:${{ github.sha }} \
            -t $ECR_REPO:latest \
            .

          docker tag $ECR_REPO:${{ github.sha }} ${{ secrets.ECR_URL }}/$ECR_REPO:${{ github.sha }}
          docker tag $ECR_REPO:latest ${{ secrets.ECR_URL }}/$ECR_REPO:latest

          docker push ${{ secrets.ECR_URL }}/$ECR_REPO:${{ github.sha }}
          docker push ${{ secrets.ECR_URL }}/$ECR_REPO:latest

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster $ECS_CLUSTER \
            --service $ECS_SERVICE \
            --force-new-deployment
```

---

## Deployment Model

### Enterprise Deployment Reality

In most large companies:
- **Their infra/cloud team runs Terraform** - you provide the module, they execute it
- **They control their AWS environment** - you don't get cross-account access
- **They need to pull your Docker image** - from an accessible registry

**Solution:** You provide artifacts, they deploy.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ What You Provide (artifacts)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. DOCKER IMAGE (platform)                                                 │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ Docker Hub: saasdog/integration-platform:1.2.3                  │     │
│     │ - OR -                                                          │     │
│     │ Public ECR: public.ecr.aws/saasdog/integration-platform:1.2.3   │     │
│     │ - OR -                                                          │     │
│     │ Private ECR with pull-through credentials (for paying customers)│     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  2. TERRAFORM MODULE                                                        │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ Terraform Registry: saasdog/integration-platform/aws            │     │
│     │ - OR -                                                          │     │
│     │ GitHub: github.com/saasdog/terraform-aws-integration-platform   │     │
│     │ - OR -                                                          │     │
│     │ Provided directly to customer (zip, private repo access)        │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  3. ADAPTER SDK                                                             │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ PyPI: pip install saasdog-adapter-sdk                           │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  4. STARTER TEMPLATE                                                        │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │ GitHub Template: github.com/saasdog/integrations-starter        │     │
│     │ - Dockerfile                                                    │     │
│     │ - Sample QuickBooks adapter                                     │     │
│     │ - CI/CD workflow                                                │     │
│     │ - CLAUDE.md for AI-assisted development                         │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ What Customer Does                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INFRA TEAM                           DEV TEAM                              │
│  ┌─────────────────────────────┐      ┌─────────────────────────────┐       │
│  │                             │      │                             │       │
│  │ 1. Get Terraform module     │      │ 1. Clone starter template   │       │
│  │ 2. Configure variables      │      │ 2. Write adapters           │       │
│  │ 3. Run terraform apply      │      │ 3. Build Docker image       │       │
│  │ 4. Provide ECR URL, secrets │      │    (extends your base)      │       │
│  │    to dev team              │      │ 4. Push to ECR              │       │
│  │                             │      │ 5. Deploy to ECS            │       │
│  └─────────────────────────────┘      └─────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Docker Image Distribution Options

| Option | Pros | Cons | Best For |
|--------|------|------|----------|
| **Docker Hub** (public) | Easy to pull, familiar | No access control | Open source / freemium |
| **Public ECR** | No rate limits, AWS-native | Less familiar | AWS-focused customers |
| **Private ECR + credentials** | Access control, audit logs | Customer needs creds | Paying enterprise |
| **Customer pulls & mirrors** | They control everything | Extra step for them | High-security enterprises |

**Recommended:** Docker Hub or Public ECR for the base image. Customers extend it with their adapters.

```bash
# Customer's infra team can verify they can pull your image
docker pull saasdog/integration-platform:1.2.3
```

### Terraform Module (Customer Runs This)

You publish the module. Customer's infra team configures and applies it.

```hcl
# Customer's main.tf
module "saasdog" {
  source  = "saasdog/integration-platform/aws"  # From Terraform Registry
  version = "1.2.0"

  # Required
  platform_image = "saasdog/integration-platform:1.2.3"  # Your Docker Hub image

  # Customer configures these
  resource_prefix    = "acme"
  ecs_task_count     = 2
  rds_instance_class = "db.t4g.medium"

  # Their existing infrastructure
  vpc_id     = "vpc-abc123"
  subnet_ids = ["subnet-123", "subnet-456"]

  # Their GitHub org for CI/CD role
  github_org  = "acme-corp"
  github_repo = "acme-integrations"

  tags = {
    Environment = "production"
    CostCenter  = "engineering"
  }
}

output "ecr_repository_url" {
  value = module.saasdog.ecr_repository_url
}

output "ecs_cluster_name" {
  value = module.saasdog.ecs_cluster_name
}
```

```hcl
# Your published module: modules/integration-platform/variables.tf

variable "customer_id" {
  description = "Unique customer identifier"
  type        = string
}

variable "aws_account_id" {
  description = "Customer's AWS account ID"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "us-east-1"
}

variable "resource_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "saasdog"
}

variable "ecs_task_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 1
}

variable "ecs_cpu" {
  description = "CPU units for ECS task (256, 512, 1024, etc.)"
  type        = number
  default     = 256
}

variable "ecs_memory" {
  description = "Memory in MB for ECS task"
  type        = number
  default     = 512
}

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.small"
}

variable "rds_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 20
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "Existing VPC ID (optional, creates new if not provided)"
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Existing subnet IDs (optional)"
  type        = list(string)
  default     = []
}
```

### Per-Customer tfvars

```hcl
# customers/acme-corp.tfvars

customer_id        = "acme-corp"
aws_account_id     = "123456789012"
aws_region         = "us-west-2"
resource_prefix    = "acme"

ecs_task_count     = 2
ecs_cpu            = 512
ecs_memory         = 1024

rds_instance_class     = "db.t4g.medium"
rds_allocated_storage  = 50

tags = {
  Environment = "production"
  CostCenter  = "engineering"
  ManagedBy   = "saasdog"
}

# Customer wants to use existing VPC
vpc_id     = "vpc-abc123"
subnet_ids = ["subnet-123", "subnet-456"]
```

### Terraform Resources Using Variables

```hcl
# modules/customer-environment/main.tf

locals {
  name_prefix = var.resource_prefix
  common_tags = merge(var.tags, {
    Customer  = var.customer_id
    ManagedBy = "saasdog"
  })
}

resource "aws_db_instance" "platform" {
  identifier        = "${local.name_prefix}-platform-db"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage

  tags = local.common_tags
}

resource "aws_sqs_queue" "sync_jobs" {
  name = "${local.name_prefix}-sync-jobs"
  tags = local.common_tags
}

resource "aws_s3_bucket" "data" {
  bucket = "${local.name_prefix}-${var.customer_id}-data"
  tags   = local.common_tags
}

resource "aws_ecr_repository" "customer_adapters" {
  name = "${local.name_prefix}-integrations"
  tags = local.common_tags
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"
  tags = local.common_tags
}

resource "aws_ecs_service" "platform" {
  name            = "${local.name_prefix}-platform"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.platform.arn
  desired_count   = var.ecs_task_count  # Customer-configurable

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "platform" {
  family = "${local.name_prefix}-platform"

  cpu    = var.ecs_cpu     # Customer-configurable
  memory = var.ecs_memory  # Customer-configurable

  container_definitions = jsonencode([{
    name  = "platform"
    image = "${aws_ecr_repository.customer_adapters.repository_url}:latest"

    environment = [
      { name = "DATABASE_URL", value = "..." },
      { name = "SQS_QUEUE_URL", value = aws_sqs_queue.sync_jobs.url },
      { name = "S3_BUCKET", value = aws_s3_bucket.data.bucket },
    ]
  }])

  tags = local.common_tags
}

# IAM role for customer's GitHub Actions
resource "aws_iam_role" "github_deploy" {
  name = "${local.name_prefix}-github-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.customer_github_org}/*:*"
        }
      }
    }]
  })

  tags = local.common_tags
}
```

### Customer Onboarding Flow (Self-Service)

**You do NOT need access to their AWS account.** You provide artifacts, they deploy.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Customer's Infra Team                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Get Terraform module from you (registry, GitHub, or direct download)   │
│  2. Configure variables for their environment:                              │
│     - VPC, subnets                                                          │
│     - Sizing (ECS tasks, RDS instance class)                                │
│     - Naming conventions, tags                                              │
│     - GitHub org/repo for CI/CD                                             │
│  3. Run: terraform init && terraform apply                                  │
│  4. Outputs:                                                                │
│     - ECR repository URL (for dev team to push images)                      │
│     - ECS cluster/service names                                             │
│     - RDS endpoint                                                          │
│     - IAM role ARN for GitHub Actions                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Customer's Dev Team                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Clone integrations-starter template                                     │
│  2. Update GitHub Actions workflow with outputs from infra team:            │
│     - ECR_REPOSITORY_URL                                                    │
│     - ECS_CLUSTER_NAME                                                      │
│     - ECS_SERVICE_NAME                                                      │
│     - AWS_ROLE_ARN                                                          │
│  3. Write adapters (with Claude Code)                                       │
│  4. Push to main → CI/CD builds and deploys                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Your Role                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  - Publish Docker image to Docker Hub / Public ECR                          │
│  - Publish Terraform module                                                 │
│  - Publish SDK to PyPI                                                      │
│  - Maintain starter template                                                │
│  - Provide documentation                                                    │
│  - Support contract (if purchased)                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### What You Deliver to Customer

| Artifact | Location | Access |
|----------|----------|--------|
| Docker image | `docker.io/saasdog/integration-platform:1.2.3` | Public (or licensed) |
| Terraform module | Terraform Registry or GitHub | Public (or licensed) |
| Adapter SDK | `pip install saasdog-adapter-sdk` | Public (MIT) |
| Starter template | GitHub template repo | Public |
| Documentation | docs.saasdog.ai | Public |

### Versioning & Compatibility

```
Platform image:     saasdog/integration-platform:1.2.3
Terraform module:   saasdog/integration-platform/aws v1.2.0
Adapter SDK:        saasdog-adapter-sdk 1.2.0

All three should be compatible within the same minor version (1.2.x).
```

### Database Migrations

Migrations are baked into the Docker image. The platform handles them automatically or via explicit command.

**Option A: Auto-migrate on startup (simpler)**

```python
# Platform entrypoint.py

import subprocess
import sys

def run_migrations():
    """Run pending Alembic migrations before starting the app."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Migration failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"Migrations complete: {result.stdout}")

if __name__ == "__main__":
    run_migrations()
    # Start the actual application
    subprocess.run(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])
```

**Option B: Separate migration command (safer for production)**

```dockerfile
# Platform Dockerfile

# Default: run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Customer can override to run migrations
# docker run saasdog/integration-platform:1.2.3 alembic upgrade head
```

Customer's upgrade process:
```bash
# 1. Run migrations first (separate ECS task or one-off container)
docker run --env-file .env saasdog/integration-platform:1.2.3 alembic upgrade head

# 2. Then deploy the new version
aws ecs update-service --cluster ... --service ... --force-new-deployment
```

**Option C: Init container (Kubernetes) or ECS task definition with migration sidecar**

```hcl
# Terraform - ECS task with migration container

resource "aws_ecs_task_definition" "platform" {
  family = "${local.name_prefix}-platform"

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = var.platform_image
      essential = false
      command   = ["alembic", "upgrade", "head"]

      # This container runs first, then exits
    },
    {
      name      = "platform"
      image     = var.platform_image
      essential = true

      # Wait for migration container to complete
      dependsOn = [{
        containerName = "migrate"
        condition     = "SUCCESS"
      }]
    }
  ])
}
```

**Recommended approach:**

| Environment | Approach |
|-------------|----------|
| Development | Auto-migrate on startup |
| Production | Explicit migration step before deploy |

**Migration versioning in release notes:**

```markdown
## v1.3.0 Release Notes

### Breaking Changes
- None

### Database Migrations
- **012_add_webhook_events_table.py** - Adds `webhook_events` table
- **013_add_index_on_sync_jobs.py** - Adds index on `sync_jobs(client_id, status)`

### Upgrade Instructions
1. Backup your database
2. Run migrations: `docker run ... alembic upgrade head`
3. Deploy new image: update ECS service

### Rollback
If needed: `docker run ... alembic downgrade 011`
```

**Platform startup check:**

```python
# app/main.py

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

def check_migrations():
    """Verify database is at expected migration version."""
    engine = create_engine(settings.database_url)

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        head_rev = script.get_current_head()

        if current_rev != head_rev:
            raise RuntimeError(
                f"Database migration required. "
                f"Current: {current_rev}, Required: {head_rev}. "
                f"Run: docker run <image> alembic upgrade head"
            )

@app.on_event("startup")
async def startup():
    check_migrations()  # Fail fast if migrations pending
    # ... rest of startup
```

This way:
- Platform refuses to start if migrations are pending
- Customer gets a clear error message with instructions
- No silent data corruption from schema mismatch

### Cost per Customer

| Component | Monthly Cost (AWS) |
|-----------|--------------------|
| RDS db.t4g.small | ~$25 |
| Fargate 0.5 vCPU, 1GB | ~$18 |
| SQS | ~$2 |
| S3 | ~$5 |
| Data transfer | ~$10 |
| **Total** | **~$60/month** |

---

## Migration Steps

### Phase 1: Create SDK Package

1. Create new repo: `saasdog-adapter-sdk`
2. Extract from `app/domain/`:
   - `interfaces.py` → `saasdog_sdk/interfaces.py`
   - `entities.py` → `saasdog_sdk/entities.py`
   - `enums.py` → `saasdog_sdk/enums.py`
3. Add new interfaces:
   - `SyncStrategyInterface`
   - `InternalDataRepositoryInterface`
   - `WebhookHandlerInterface`
4. Add HTTP utilities: `saasdog_sdk/http.py`
5. Publish to PyPI (or private registry)

### Phase 2: Create Integrations Starter Template

1. Create template repo: `saasdog-integrations-starter`
2. Move QuickBooks adapter from platform:
   - `app/integrations/quickbooks/` → `adapters/quickbooks/`
3. Update imports to use SDK
4. Create `adapters/saasdog.yaml` manifest
5. Create sample `internal_repo.py`
6. Add Dockerfile, CI/CD, CLAUDE.md

### Phase 3: Update Integration Platform

1. Remove `app/integrations/` directory
2. Add adapter loading logic
3. Update `SyncOrchestrator` to use loaded adapters
4. Add webhook routing to loaded handlers
5. Ensure platform builds without adapters

### Phase 4: Test End-to-End

1. Build platform container (no adapters)
2. Build customer container (extends platform + adapters)
3. Run full sync test
4. Verify:
   - Inbound sync works
   - Outbound sync works
   - Bidirectional sync works
   - Token refresh works
   - Webhooks work
   - Settings are passed correctly

### Phase 5: Documentation

1. SDK README with interface documentation
2. Starter template CLAUDE.md for AI-assisted development
3. Customer onboarding guide
4. Terraform module documentation

---

## Summary: What Lives Where

| Component | Location | Who Implements |
|-----------|----------|----------------|
| Sync engine, job runner | Platform | SaaSDog |
| State management, version vectors | Platform | SaaSDog |
| Token storage, encryption | Platform | SaaSDog |
| API endpoints | Platform | SaaSDog |
| Adapter interfaces | SDK | SaaSDog (defines) |
| Domain entities, enums | SDK | SaaSDog (defines) |
| HTTP utilities | SDK | SaaSDog (provides) |
| IntegrationAdapterInterface | SDK / Customer repo | Customer (implements) |
| SyncStrategyInterface | SDK / Customer repo | Customer (implements) |
| InternalDataRepositoryInterface | SDK / Customer repo | Customer (implements) |
| WebhookHandlerInterface | SDK / Customer repo | Customer (implements) |
| Mappers | Customer repo | Customer |
| Entity constants | Customer repo | Customer |

The adapter is **stateless** — it receives everything it needs from the platform for each operation. Customer has full Claude Code access to their adapters repo. Platform source remains closed.
