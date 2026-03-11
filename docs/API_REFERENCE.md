# API Reference

Complete API documentation for the Integration Platform. All endpoints require an `X-Client-ID` header (dev mode) or Bearer JWT token (production) for multi-tenant isolation.

Interactive documentation is also available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

```bash
# Set base URL and client ID for examples
BASE_URL="http://localhost:8001"
CLIENT_ID="550e8400-e29b-41d4-a716-446655440000"
```

---

## Health Check

```bash
curl $BASE_URL/health
```

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Integrations

### List Available Integrations

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

### List User's Connected Integrations

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

### Start OAuth Connection

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/connect" \
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

### Complete OAuth Callback

After the user authorizes, the external system redirects back with a code:

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/callback" \
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
  "last_connected_at": "2024-01-15T10:00:00Z"
}
```

### Disconnect Integration

```bash
curl -X DELETE "$BASE_URL/integrations/{integration_id}" \
  -H "X-Client-ID: $CLIENT_ID"
```

Response: `204 No Content`

### Get Sync Status

```bash
curl "$BASE_URL/integrations/{integration_id}/sync-status" \
  -H "X-Client-ID: $CLIENT_ID"
```

### Reset Sync Cursor

Reset the sync cursor for an entity type to trigger a full re-sync:

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/sync-status/{entity_type}/reset" \
  -H "X-Client-ID: $CLIENT_ID"
```

### Push Change Notification

Notify the platform that internal records have changed. Bumps `internal_version_id` on matching state records:

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/notify" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_type": "vendor",
    "record_ids": ["vendor-uuid-1", "vendor-uuid-2"]
  }'
```

If the sync rule has `sync_trigger: immediate`, an incremental sync job is queued automatically.

---

## Sync Jobs

### Trigger a Sync Job

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

### List Sync Jobs

```bash
# List all jobs
curl "$BASE_URL/sync-jobs" \
  -H "X-Client-ID: $CLIENT_ID"

# Filter by status and integration
curl "$BASE_URL/sync-jobs?status=succeeded&integration_id={uuid}&page=1&page_size=10" \
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
      "completed_at": "2024-01-15T10:31:22Z"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 10,
  "total_pages": 5
}
```

### Get Job Details

```bash
curl "$BASE_URL/sync-jobs/{job_id}" \
  -H "X-Client-ID: $CLIENT_ID"
```

### Cancel a Job

```bash
curl -X POST "$BASE_URL/sync-jobs/{job_id}/cancel" \
  -H "X-Client-ID: $CLIENT_ID"
```

### Get Job Record Details

Paginated record-level sync details for a specific job — see which records were synced, failed, or had errors:

```bash
# All records for a job
curl "$BASE_URL/sync-jobs/{job_id}/records" \
  -H "X-Client-ID: $CLIENT_ID"

# Filter by entity type and status
curl "$BASE_URL/sync-jobs/{job_id}/records?entity_type=invoice&status=failed&page=1&page_size=20" \
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

## Records & Manual Overrides

### Browse Integration State Records

```bash
curl "$BASE_URL/integrations/{integration_id}/records?entity_type=vendor&sync_status=failed&page=1&page_size=20" \
  -H "X-Client-ID: $CLIENT_ID"
```

Filters: `entity_type`, `sync_status` (`synced`, `failed`, `pending`, `conflict`), `do_not_sync`.

### Force-Sync Records

Force-sync failing records — clears errors, equalizes version vectors (`iv=ev=lsv=max`), marks as SYNCED. Only eligible for records in `failed` or `conflict` status:

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/records/force-sync" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "state_ids": ["state-uuid-1", "state-uuid-2"]
  }'
```

Writes an audit log entry with `force_synced_at` timestamp. If a record is later modified, the normal sync loop detects the change and re-syncs.

### Toggle Do-Not-Sync

Exclude records from all future sync operations:

```bash
curl -X POST "$BASE_URL/integrations/{integration_id}/records/do-not-sync" \
  -H "X-Client-ID: $CLIENT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "state_ids": ["state-uuid-1"],
    "do_not_sync": true
  }'
```

Set `do_not_sync: false` to re-include — records with version mismatches are set to PENDING.

**Record selector** (used by both override endpoints): provide exactly one of:
1. `state_ids` — direct integration_state UUIDs
2. `internal_record_ids` + `entity_type` — look up by internal IDs
3. `external_record_ids` + `entity_type` — look up by external provider IDs

---

## Settings

### Get Integration Settings

```bash
curl "$BASE_URL/integrations/{integration_id}/settings" \
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

**Options**:
- Direction: `inbound`, `outbound`, `bidirectional`
- Conflict resolution: `external` (external system wins), `our_system` (our system wins)
- Change source: `polling`, `push`, `webhook`, `hybrid`
- Sync trigger: `deferred` (next scheduled sync), `immediate` (queue job now)

### Update Settings

```bash
curl -X PUT "$BASE_URL/integrations/{integration_id}/settings" \
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

## Admin Endpoints

All admin endpoints require an `X-Admin-API-Key` header. In development mode with no key configured, they're accessible without authentication.

### List All Integrations (Cross-Tenant)

```bash
curl "$BASE_URL/admin/integrations" \
  -H "X-Admin-API-Key: $ADMIN_KEY"
```

### Create Integration Catalog Entry

```bash
curl -X POST "$BASE_URL/admin/integrations/available" \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sage Intacct",
    "type": "erp",
    "description": "Cloud financial management",
    "supported_entities": ["vendor", "bill", "invoice"],
    "connection_config": {
      "auth_type": "oauth2",
      "authorization_url": "https://...",
      "token_url": "https://...",
      "scopes": ["..."]
    },
    "is_active": true
  }'
```

### Update Integration Catalog Entry

```bash
curl -X PUT "$BASE_URL/admin/integrations/available/{integration_id}" \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

Set `is_active: false` to soft-delete.

### Get/Set System Default Settings

```bash
# Get defaults for an integration
curl "$BASE_URL/integrations/{integration_id}/settings/defaults" \
  -H "X-Admin-API-Key: $ADMIN_KEY"

# Update defaults
curl -X PUT "$BASE_URL/integrations/{integration_id}/settings/defaults" \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "sync_rules": [...], "sync_frequency": "0 */6 * * *" }'
```

### Admin Sync Status & Cursor Reset

```bash
# View entity sync status for a specific client
curl "$BASE_URL/admin/clients/{client_id}/integrations/{integration_id}/sync-status" \
  -H "X-Admin-API-Key: $ADMIN_KEY"

# Reset sync cursor for a client's entity
curl -X POST "$BASE_URL/admin/clients/{client_id}/integrations/{integration_id}/sync-status/{entity_type}/reset" \
  -H "X-Admin-API-Key: $ADMIN_KEY"
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Integration not found",
  "code": "NOT_FOUND",
  "details": null
}
```

| Status | Meaning |
|--------|---------|
| `400` | Validation error |
| `401` | Authentication required |
| `403` | Forbidden |
| `404` | Resource not found |
| `409` | Conflict (e.g., integration already connected) |
| `500` | Internal server error |

---

## OpenAPI / Client SDK Generation

The API is fully documented using **OpenAPI 3.1**. FastAPI auto-generates the spec.

**Documentation URLs** (when running locally):
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc
- OpenAPI JSON: http://localhost:8001/openapi.json

**Generate client SDKs:**

```bash
curl http://localhost:8001/openapi.json -o openapi.json

# TypeScript
npx @openapitools/openapi-generator-cli generate -i openapi.json -g typescript-fetch -o ./clients/typescript

# Python
npx @openapitools/openapi-generator-cli generate -i openapi.json -g python -o ./clients/python
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
