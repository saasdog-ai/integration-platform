# Sync Architecture

Deep dive into the integration platform's sync engine — version vectors, conflict resolution, change detection, and sync directions.

For a high-level overview, see the main [README](../README.md#architecture-overview).

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Your Application                                                   │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐   │
│  │  Host App     │    │  Integration Platform                    │   │
│  │  (React)      │    │                                          │   │
│  │              ├────►│  REST API (FastAPI)                      │   │
│  │  saas-host   │    │    │                                      │   │
│  │  admin-host  │    │    ├── /integrations   (OAuth, connect)   │   │
│  └──────────────┘    │    ├── /sync-jobs      (trigger, status)  │   │
│                      │    ├── /settings        (sync rules)      │   │
│                      │    └── /admin           (cross-tenant)    │   │
│                      │                                          │   │
│                      │  ┌─────────────────────────────────────┐  │   │
│                      │  │  Sync Orchestrator                  │  │   │
│                      │  │                                     │  │   │
│                      │  │  ┌─────────┐  ┌────────┐           │  │   │
│                      │  │  │  QBO    │  │  Xero  │  + more   │  │   │
│                      │  │  │Strategy │  │Strategy│           │  │   │
│                      │  │  └────┬────┘  └───┬────┘           │  │   │
│                      │  │       │            │                │  │   │
│                      │  │  ┌────▼────────────▼────┐          │  │   │
│                      │  │  │  Version Vectors     │          │  │   │
│                      │  │  │  iv / ev / lsv       │          │  │   │
│                      │  │  │  Conflict Resolution │          │  │   │
│                      │  │  └──────────┬───────────┘          │  │   │
│                      │  └─────────────┼───────────────────────┘  │   │
│                      └────────────────┼──────────────────────────┘   │
│                                       │                             │
│                      ┌────────────────▼──────────────────────────┐   │
│                      │  PostgreSQL                                │   │
│                      │                                            │   │
│                      │  integration_state   (record-level sync)   │   │
│                      │  sync_jobs           (job history)         │   │
│                      │  user_integrations   (OAuth credentials)   │   │
│                      │  sample_* tables     (your business data)  │   │
│                      └────────────────────────────────────────────┘   │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐ ┌─────▼──────┐ ┌──────▼─────┐
           │  QuickBooks   │ │   Xero     │ │  Sage, etc │
           │  Online API   │ │   API      │ │  (add new) │
           │               │ │            │ │            │
           │  OAuth 2.0    │ │  OAuth 2.0 │ │  OAuth 2.0 │
           │  REST API     │ │  REST API  │ │  REST API  │
           └───────────────┘ └────────────┘ └────────────┘
```

### Data Flow

**Inbound sync** (external → internal):
```
External API  ──fetch──►  Strategy  ──map──►  internal_repo.upsert_*()  ──►  Your DB
                              │
                     update integration_state (ev++, equalize)
```

**Outbound sync** (internal → external):
```
Your DB  ──get_*()──►  Strategy  ──map──►  Adapter.create/update()  ──►  External API
                           │
                  update integration_state (iv++, equalize)
```

**Bidirectional sync**:
```
1. Fetch external records ──► classify each as inbound/outbound/conflict
2. Conflicts resolved by master_if_conflict setting
3. Process inbound records (external wins)
4. Process outbound records (our system wins)
5. Equalize version vectors: iv = ev = lsv = max(iv, ev)
```

## Version Vectors

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

## Sync Directions

Configured per entity type in user settings:

| Direction | Behavior |
|-----------|----------|
| `inbound` | Fetch from external, write to internal DB |
| `outbound` | Discover outbound-needing records via version vectors, push to external |
| `bidirectional` | Classify each record as inbound/outbound/conflict using version vectors |

## Conflict Resolution

When both sides changed (`needs_outbound_sync AND needs_inbound_sync`):

| Setting | Behavior |
|---------|----------|
| `master_if_conflict = external` | External system wins (synced as inbound) |
| `master_if_conflict = our_system` | Our system wins (synced as outbound) |

The `sync_direction` field on each record always reflects the actual direction of the most recent sync (INBOUND or OUTBOUND), never BIDIRECTIONAL.

## Change Detection Methods

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

### Push Notification Flow

Your internal system calls the notify endpoint with a list of changed record IDs. The platform bumps `internal_version_id` on matching state records (creating new ones if needed). If the sync rule has `sync_trigger: immediate`, an incremental sync job is queued automatically.

### Webhook Flow

An external system (e.g., QuickBooks) calls the webhook endpoint. The platform bumps `external_version_id` on matching state records. Same trigger logic applies. The webhook endpoint currently returns `501` — implement provider-specific payload parsing in `app/api/integrations.py` to activate it.

### Example Sync Rule

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

## Sync Flow (Detailed)

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

## Entity Dependency Ordering

Entities sync in dependency order to ensure FK references resolve correctly:

**Inbound order**: vendor → customer → chart_of_accounts → item → bill → invoice → payment

**Outbound order**: Same ordering ensures parent records exist in the external system before child records reference them.

## QuickBooks Online Integration

Supported entities: vendor, customer, chart_of_accounts, item, bill, invoice, payment.

Entity sync order respects dependencies (vendors before bills, customers before invoices). The strategy handles schema mapping via dedicated mapper functions.

## Xero Integration

Supported entities: vendor, customer, chart_of_accounts, item, bill, invoice, payment.

Key differences from QBO:
- Xero uses a shared Contacts endpoint for vendors and customers (filtered by `IsSupplier`/`IsCustomer`)
- Xero uses `/Date(ms)/` timestamp format instead of ISO
- Xero uses `where` clause for `since` filtering instead of API-native params
