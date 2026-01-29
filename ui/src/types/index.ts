/**
 * Type definitions for Integrations UI
 */

// Integration status enum
export type IntegrationStatus = 'pending' | 'connected' | 'error' | 'revoked'

// Sync job status enum
export type SyncJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'

// Sync job type enum
export type SyncJobType = 'full_sync' | 'incremental' | 'entity_sync'

// Sync job trigger enum
export type SyncJobTrigger = 'user' | 'scheduler' | 'webhook'

/**
 * Available Integration - a supported integration type
 */
export interface AvailableIntegration {
  id: string
  name: string
  type: string // 'erp', 'hris', 'crm', etc.
  description: string | null
  supported_entities: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

/**
 * User Integration - a user's connection to an integration
 */
export interface UserIntegration {
  id: string
  client_id: string
  integration_id: string
  integration_name?: string | null
  integration_type?: string | null
  status: IntegrationStatus
  external_account_id: string | null
  last_connected_at: string | null
  disconnected_at: string | null
  created_at: string
  updated_at: string
  // Optional embedded integration for convenience (populated by some queries)
  integration?: AvailableIntegration
}

/**
 * Conflict resolution strategy
 */
export type ConflictResolution = 'external' | 'our_system' | 'most_recent'

/**
 * Sync Rule - configuration for syncing an entity type
 */
export interface SyncRule {
  entity_type: string
  direction: 'inbound' | 'outbound' | 'bidirectional'
  enabled: boolean
  master_if_conflict?: ConflictResolution
  field_mappings?: Record<string, string> | null
}

/**
 * User Integration Settings
 */
export interface UserIntegrationSettings {
  sync_rules: SyncRule[]
  sync_frequency: string | null
  auto_sync_enabled: boolean
}

/**
 * Sync Job - a sync job execution
 */
export interface SyncJob {
  id: string
  client_id: string
  integration_id: string
  integration_name: string // From backend join
  job_type: SyncJobType
  status: SyncJobStatus
  started_at: string | null
  completed_at: string | null
  entities_processed: Record<string, EntityProcessedSummary> | null
  error_code: string | null
  error_message: string | null
  error_details: Record<string, unknown> | null
  triggered_by: SyncJobTrigger
  created_at: string
  updated_at: string
}

/**
 * Entity processed summary in a sync job
 */
export interface EntityProcessedSummary {
  direction: string
  records_fetched: number
  records_created: number
  records_updated: number
  records_failed: number
}

/**
 * Request to trigger a sync job
 */
export interface TriggerSyncRequest {
  job_type?: SyncJobType
  entity_types?: string[]
}

/**
 * OAuth callback request
 */
export interface OAuthCallbackRequest {
  code: string
  state: string
  realm_id?: string // QuickBooks specific
}

/**
 * Connect integration request (mock)
 */
export interface ConnectIntegrationRequest {
  external_account_id: string
  // Mock credentials - in real implementation, OAuth would handle this
  mock_credentials?: {
    access_token: string
    refresh_token: string
  }
}

/**
 * API Error response
 */
export interface ApiError {
  error: string
  code: string
  details?: Record<string, unknown>
}

/**
 * Paginated response wrapper
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * Sync record status
 */
export type RecordSyncStatus = 'pending' | 'synced' | 'failed' | 'conflict'

/**
 * Sync direction for a record
 */
export type SyncDirection = 'inbound' | 'outbound' | 'bidirectional'

/**
 * Individual sync record details
 */
export interface SyncRecord {
  id: string
  entity_type: string
  internal_record_id: string | null
  external_record_id: string | null
  sync_direction: SyncDirection | null
  sync_status: RecordSyncStatus
  is_success: boolean
  updated_at: string
  error_code: string | null
  error_message: string | null
  error_details: Record<string, unknown> | null
}

/**
 * Paginated sync records response
 */
export interface SyncRecordsResponse {
  records: SyncRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
