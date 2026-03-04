/**
 * API Client for Integrations UI
 */

import type {
  AvailableIntegration,
  UserIntegration,
  UserIntegrationSettings,
  SyncJob,
  TriggerSyncRequest,
  ConnectIntegrationRequest,
  PaginatedResponse,
  SyncJobStatus,
  SyncRecordsResponse,
  RecordSyncStatus,
  EntitySyncStatusListResponse,
  ResetLastSyncTimeRequest,
  EntitySyncStatusResetResponse,
  ForceSyncRequest,
  DoNotSyncRequest,
  OverrideResultResponse,
} from '@/types'
import type { IntegrationsConfig } from '@/providers/ConfigProvider'

/** Default request timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 30_000

export class AuthenticationError extends Error {
  constructor(message: string = 'Authentication required') {
    super(message)
    this.name = 'AuthenticationError'
  }
}

/**
 * Create an API client with the given configuration
 */
export function createApiClient(config: IntegrationsConfig) {
  const { apiBaseUrl, getAuthToken, onUnauthorized } = config

  function getAuthHeaders(): HeadersInit {
    const token = getAuthToken()
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    if (config.clientId) {
      headers['X-Client-ID'] = config.clientId
    }
    return headers
  }

  async function handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 401) {
      onUnauthorized?.()
      throw new AuthenticationError('Session expired. Please log in again.')
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Unknown error' }))
      throw new Error(error.error || error.detail || error.message || `HTTP ${response.status}`)
    }
    return response.json()
  }

  /**
   * Wrapper around fetch that adds an AbortController with a timeout.
   * Throws a descriptive error on timeout or network failure.
   */
  async function fetchWithTimeout(
    url: string,
    options: RequestInit = {},
    timeoutMs: number = DEFAULT_TIMEOUT_MS
  ): Promise<Response> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      return await fetch(url, { ...options, signal: controller.signal })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error(`Request timed out after ${timeoutMs}ms`)
      }
      throw new Error(
        err instanceof Error ? err.message : 'Network request failed'
      )
    } finally {
      clearTimeout(timer)
    }
  }

  return {
    // ========================
    // Available Integrations
    // ========================

    async getAvailableIntegrations(): Promise<AvailableIntegration[]> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/available`, {
        headers: getAuthHeaders(),
      })
      const data = await handleResponse<{ integrations: AvailableIntegration[] }>(response)
      return data.integrations
    },

    async getAvailableIntegration(integrationId: string): Promise<AvailableIntegration> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/available/${integrationId}`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<AvailableIntegration>(response)
    },

    // ========================
    // User Integrations
    // ========================

    async getUserIntegrations(): Promise<UserIntegration[]> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations`, {
        headers: getAuthHeaders(),
      })
      const data = await handleResponse<{ integrations: UserIntegration[] }>(response)
      return data.integrations
    },

    async getUserIntegration(integrationId: string): Promise<UserIntegration> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<UserIntegration>(response)
    },

    async connectIntegration(
      integrationId: string,
      request: ConnectIntegrationRequest
    ): Promise<{ authorization_url: string }> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/connect`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(request),
      })
      return handleResponse<{ authorization_url: string }>(response)
    },

    async completeOAuthCallback(
      integrationId: string,
      request: { code: string; redirect_uri: string; state?: string; realm_id?: string }
    ): Promise<UserIntegration> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/callback`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(request),
      })
      return handleResponse<UserIntegration>(response)
    },

    async disconnectIntegration(integrationId: string): Promise<void> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      })
      if (response.status === 204) return
      await handleResponse<void>(response)
    },

    // ========================
    // Integration Settings
    // ========================

    async getIntegrationSettings(integrationId: string): Promise<UserIntegrationSettings> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/settings`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<UserIntegrationSettings>(response)
    },

    async updateIntegrationSettings(
      integrationId: string,
      settings: UserIntegrationSettings
    ): Promise<UserIntegrationSettings> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/settings`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(settings),
      })
      return handleResponse<UserIntegrationSettings>(response)
    },

    // ========================
    // Sync Jobs
    // ========================

    async triggerSync(
      integrationId: string,
      request?: TriggerSyncRequest
    ): Promise<SyncJob> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/sync-jobs`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          integration_id: integrationId,
          ...request,
        }),
      })
      return handleResponse<SyncJob>(response)
    },

    async getSyncJobs(params?: {
      integration_id?: string
      status?: SyncJobStatus
      page?: number
      page_size?: number
    }): Promise<PaginatedResponse<SyncJob>> {
      const searchParams = new URLSearchParams()
      if (params?.integration_id) searchParams.set('integration_id', params.integration_id)
      if (params?.status) searchParams.set('status', params.status)
      if (params?.page) searchParams.set('page', params.page.toString())
      if (params?.page_size) searchParams.set('page_size', params.page_size.toString())

      const queryString = searchParams.toString()
      const url = `${apiBaseUrl}/sync-jobs${queryString ? `?${queryString}` : ''}`

      const response = await fetchWithTimeout(url, {
        headers: getAuthHeaders(),
      })
      // Backend returns { jobs: [...], total: N }, transform to PaginatedResponse
      const data = await handleResponse<{ jobs: SyncJob[]; total: number }>(response)
      const page = params?.page ?? 1
      const page_size = params?.page_size ?? 20
      return {
        items: data.jobs,
        total: data.total,
        page,
        page_size,
        total_pages: Math.ceil(data.total / page_size),
      }
    },

    async getSyncJob(jobId: string): Promise<SyncJob> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/sync-jobs/${jobId}`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<SyncJob>(response)
    },

    async cancelSyncJob(jobId: string): Promise<SyncJob> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/sync-jobs/${jobId}/cancel`, {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      return handleResponse<SyncJob>(response)
    },

    async getSyncJobRecords(
      jobId: string,
      params?: {
        entity_type?: string
        status?: RecordSyncStatus
        page?: number
        page_size?: number
      }
    ): Promise<SyncRecordsResponse> {
      const searchParams = new URLSearchParams()
      if (params?.entity_type) searchParams.set('entity_type', params.entity_type)
      if (params?.status) searchParams.set('status', params.status)
      if (params?.page) searchParams.set('page', params.page.toString())
      if (params?.page_size) searchParams.set('page_size', params.page_size.toString())

      const queryString = searchParams.toString()
      const url = `${apiBaseUrl}/sync-jobs/${jobId}/records${queryString ? `?${queryString}` : ''}`

      const response = await fetchWithTimeout(url, {
        headers: getAuthHeaders(),
      })
      return handleResponse<SyncRecordsResponse>(response)
    },

    // ========================
    // System Default Settings
    // ========================

    async getSystemDefaultSettings(integrationId: string): Promise<UserIntegrationSettings> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/settings/defaults`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<UserIntegrationSettings>(response)
    },

    async updateSystemDefaultSettings(
      integrationId: string,
      settings: UserIntegrationSettings
    ): Promise<UserIntegrationSettings> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/settings/defaults`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(settings),
      })
      return handleResponse<UserIntegrationSettings>(response)
    },

    // ========================
    // Entity Sync Statuses
    // ========================

    async listEntitySyncStatuses(integrationId: string): Promise<EntitySyncStatusListResponse> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/sync-status`, {
        headers: getAuthHeaders(),
      })
      return handleResponse<EntitySyncStatusListResponse>(response)
    },

    async resetLastSyncTime(
      integrationId: string,
      entityType: string,
      request: ResetLastSyncTimeRequest
    ): Promise<EntitySyncStatusResetResponse> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/sync-status/${entityType}/reset`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(request),
      })
      return handleResponse<EntitySyncStatusResetResponse>(response)
    },

    // ========================
    // Manual Overrides & Records Browser
    // ========================

    async getIntegrationRecords(
      integrationId: string,
      params?: {
        entity_type?: string
        sync_status?: RecordSyncStatus
        do_not_sync?: boolean
        page?: number
        page_size?: number
      }
    ): Promise<SyncRecordsResponse> {
      const searchParams = new URLSearchParams()
      if (params?.entity_type) searchParams.set('entity_type', params.entity_type)
      if (params?.sync_status) searchParams.set('sync_status', params.sync_status)
      if (params?.do_not_sync !== undefined) searchParams.set('do_not_sync', String(params.do_not_sync))
      if (params?.page) searchParams.set('page', params.page.toString())
      if (params?.page_size) searchParams.set('page_size', params.page_size.toString())

      const queryString = searchParams.toString()
      const url = `${apiBaseUrl}/integrations/${integrationId}/records${queryString ? `?${queryString}` : ''}`

      const response = await fetchWithTimeout(url, {
        headers: getAuthHeaders(),
      })
      return handleResponse<SyncRecordsResponse>(response)
    },

    async forceSyncRecords(
      integrationId: string,
      request: ForceSyncRequest
    ): Promise<OverrideResultResponse> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/records/force-sync`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(request),
      })
      return handleResponse<OverrideResultResponse>(response)
    },

    async setDoNotSync(
      integrationId: string,
      request: DoNotSyncRequest
    ): Promise<OverrideResultResponse> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/integrations/${integrationId}/records/do-not-sync`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(request),
      })
      return handleResponse<OverrideResultResponse>(response)
    },

    // ========================
    // Admin - Cross-Client
    // ========================

    async adminGetAllIntegrations(): Promise<UserIntegration[]> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/admin/integrations`, {
        headers: getAuthHeaders(),
      })
      const data = await handleResponse<{ integrations: UserIntegration[] }>(response)
      return data.integrations
    },

    async adminListEntitySyncStatuses(
      clientId: string,
      integrationId: string
    ): Promise<EntitySyncStatusListResponse> {
      const response = await fetchWithTimeout(
        `${apiBaseUrl}/admin/clients/${clientId}/integrations/${integrationId}/sync-status`,
        { headers: getAuthHeaders() }
      )
      return handleResponse<EntitySyncStatusListResponse>(response)
    },

    async adminResetLastSyncTime(
      clientId: string,
      integrationId: string,
      entityType: string,
      request: ResetLastSyncTimeRequest
    ): Promise<EntitySyncStatusResetResponse> {
      const response = await fetchWithTimeout(
        `${apiBaseUrl}/admin/clients/${clientId}/integrations/${integrationId}/sync-status/${entityType}/reset`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify(request),
        }
      )
      return handleResponse<EntitySyncStatusResetResponse>(response)
    },

    // ========================
    // Health Check
    // ========================

    async checkHealth(): Promise<{ status: string }> {
      const response = await fetchWithTimeout(`${apiBaseUrl}/health`)
      return handleResponse<{ status: string }>(response)
    },
  }
}

export type ApiClient = ReturnType<typeof createApiClient>
