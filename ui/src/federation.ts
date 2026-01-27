/**
 * Federation Export - All-in-one export for module federation consumers
 *
 * This file exports everything a host application might need:
 * - Components (MicroFrontend, individual pages)
 * - Providers (ConfigProvider)
 * - API client
 * - Types
 */

// Main micro-frontend component
export { IntegrationsMicroFrontend, default as MicroFrontend } from './MicroFrontend'

// Provider for configuration injection
export { IntegrationsProvider, useConfig, type IntegrationsConfig } from './providers/ConfigProvider'

// Individual page components
export { IntegrationList } from './pages/integrations/IntegrationList'
export { IntegrationDetail } from './pages/integrations/IntegrationDetail'
export { SyncJobs } from './pages/jobs/SyncJobs'
export { JobDetail } from './pages/jobs/JobDetail'

// API client
export { createApiClient, type ApiClient, AuthenticationError } from './api/apiClient'

// Hook for API access
export { useApiClient } from './hooks/useApiClient'

// Types
export type {
  AvailableIntegration,
  UserIntegration,
  UserIntegrationSettings,
  SyncJob,
  SyncRule,
  IntegrationStatus,
  SyncJobStatus,
  SyncJobType,
  SyncJobTrigger,
  TriggerSyncRequest,
  ConnectIntegrationRequest,
  PaginatedResponse,
} from './types'
