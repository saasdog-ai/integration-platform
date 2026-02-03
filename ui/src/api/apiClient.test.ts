import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createApiClient, AuthenticationError } from './apiClient'
import type { IntegrationsConfig } from '@/providers/ConfigProvider'

function createTestConfig(overrides?: Partial<IntegrationsConfig>): IntegrationsConfig {
  return {
    apiBaseUrl: 'https://api.test',
    getAuthToken: () => 'test-token',
    onUnauthorized: vi.fn(),
    ...overrides,
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('createApiClient', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── Auth headers ────────────────────────────────────────────

  describe('authentication', () => {
    it('includes Bearer token when token is present', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ integrations: [] }))
      const api = createApiClient(createTestConfig())
      await api.getAvailableIntegrations()

      const headers = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Record<string, string>
      expect(headers['Authorization']).toBe('Bearer test-token')
    })

    it('omits Authorization header when token is empty', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ integrations: [] }))
      const api = createApiClient(createTestConfig({ getAuthToken: () => '' }))
      await api.getAvailableIntegrations()

      const headers = (fetchSpy.mock.calls[0][1] as RequestInit).headers as Record<string, string>
      expect(headers['Authorization']).toBeUndefined()
    })

    it('throws AuthenticationError and calls onUnauthorized on 401', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ error: 'Unauthorized' }, 401))
      const onUnauthorized = vi.fn()
      const api = createApiClient(createTestConfig({ onUnauthorized }))

      await expect(api.getUserIntegrations()).rejects.toThrow(AuthenticationError)
      expect(onUnauthorized).toHaveBeenCalledOnce()
    })
  })

  // ── Error handling ──────────────────────────────────────────

  describe('error handling', () => {
    it('throws Error with message from response body on non-ok status', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ error: 'Bad request data' }, 400))
      const api = createApiClient(createTestConfig())

      await expect(api.getAvailableIntegration('id1')).rejects.toThrow('Bad request data')
    })

    it('falls back to HTTP status when body is not JSON', async () => {
      fetchSpy.mockResolvedValue(
        new Response('not json', { status: 500, headers: { 'Content-Type': 'text/plain' } })
      )
      const api = createApiClient(createTestConfig())

      await expect(api.getAvailableIntegration('id1')).rejects.toThrow('Unknown error')
    })

    it('wraps network failures in descriptive Error', async () => {
      fetchSpy.mockRejectedValue(new TypeError('Failed to fetch'))
      const api = createApiClient(createTestConfig())

      await expect(api.getAvailableIntegrations()).rejects.toThrow('Failed to fetch')
    })

    it('throws timeout error when request exceeds timeout', async () => {
      vi.useFakeTimers()
      try {
        fetchSpy.mockImplementation((_url: string, options: RequestInit) => {
          return new Promise((_resolve, reject) => {
            const signal = (options as RequestInit)?.signal
            signal?.addEventListener('abort', () => {
              reject(new DOMException('The operation was aborted.', 'AbortError'))
            })
          })
        })
        const api = createApiClient(createTestConfig())

        const promise = api.getAvailableIntegrations()
        vi.advanceTimersByTime(31_000)

        await expect(promise).rejects.toThrow(/timed out/)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  // ── Available integrations ──────────────────────────────────

  describe('getAvailableIntegrations', () => {
    it('returns the integrations array from response', async () => {
      const integrations = [{ id: '1', name: 'Test' }]
      fetchSpy.mockResolvedValue(jsonResponse({ integrations }))
      const api = createApiClient(createTestConfig())

      const result = await api.getAvailableIntegrations()
      expect(result).toEqual(integrations)
    })
  })

  describe('getAvailableIntegration', () => {
    it('calls correct endpoint', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ id: '123', name: 'QB' }))
      const api = createApiClient(createTestConfig())

      await api.getAvailableIntegration('123')
      expect(fetchSpy.mock.calls[0][0]).toBe('https://api.test/integrations/available/123')
    })
  })

  // ── User integrations ───────────────────────────────────────

  describe('getUserIntegrations', () => {
    it('returns the integrations array from response', async () => {
      const integrations = [{ id: 'u1', status: 'connected' }]
      fetchSpy.mockResolvedValue(jsonResponse({ integrations }))
      const api = createApiClient(createTestConfig())

      const result = await api.getUserIntegrations()
      expect(result).toEqual(integrations)
    })
  })

  describe('connectIntegration', () => {
    it('sends POST with request body', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ authorization_url: 'https://intuit.com/oauth' }))
      const api = createApiClient(createTestConfig())

      await api.connectIntegration('int1', { redirect_uri: 'http://localhost/callback', state: 'test-state' })

      expect(fetchSpy.mock.calls[0][0]).toBe('https://api.test/integrations/int1/connect')
      const options = fetchSpy.mock.calls[0][1] as RequestInit
      expect(options.method).toBe('POST')
      expect(JSON.parse(options.body as string)).toEqual({ redirect_uri: 'http://localhost/callback', state: 'test-state' })
    })
  })

  describe('disconnectIntegration', () => {
    it('succeeds on 204 No Content', async () => {
      fetchSpy.mockResolvedValue(new Response(null, { status: 204 }))
      const api = createApiClient(createTestConfig())

      await expect(api.disconnectIntegration('int1')).resolves.toBeUndefined()
    })

    it('throws on non-204 error', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ error: 'Not found' }, 404))
      const api = createApiClient(createTestConfig())

      await expect(api.disconnectIntegration('int1')).rejects.toThrow('Not found')
    })
  })

  // ── Settings ────────────────────────────────────────────────

  describe('getIntegrationSettings', () => {
    it('fetches settings from correct endpoint', async () => {
      const settings = { sync_rules: [], sync_frequency: '1h', auto_sync_enabled: true }
      fetchSpy.mockResolvedValue(jsonResponse(settings))
      const api = createApiClient(createTestConfig())

      const result = await api.getIntegrationSettings('int1')
      expect(result).toEqual(settings)
      expect(fetchSpy.mock.calls[0][0]).toBe('https://api.test/integrations/int1/settings')
    })
  })

  describe('updateIntegrationSettings', () => {
    it('sends PUT with full settings body', async () => {
      const settings = { sync_rules: [], sync_frequency: '6h', auto_sync_enabled: false }
      fetchSpy.mockResolvedValue(jsonResponse(settings))
      const api = createApiClient(createTestConfig())

      await api.updateIntegrationSettings('int1', settings)

      const options = fetchSpy.mock.calls[0][1] as RequestInit
      expect(options.method).toBe('PUT')
      expect(JSON.parse(options.body as string)).toEqual(settings)
    })
  })

  // ── Sync jobs ───────────────────────────────────────────────

  describe('getSyncJobs', () => {
    it('builds query string from params', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ jobs: [], total: 0 }))
      const api = createApiClient(createTestConfig())

      await api.getSyncJobs({ status: 'failed', page: 2, page_size: 10 })

      const url = fetchSpy.mock.calls[0][0] as string
      expect(url).toContain('status=failed')
      expect(url).toContain('page=2')
      expect(url).toContain('page_size=10')
    })

    it('transforms response into PaginatedResponse', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ jobs: [{ id: 'j1' }], total: 25 }))
      const api = createApiClient(createTestConfig())

      const result = await api.getSyncJobs({ page: 2, page_size: 10 })
      expect(result.items).toEqual([{ id: 'j1' }])
      expect(result.total).toBe(25)
      expect(result.page).toBe(2)
      expect(result.page_size).toBe(10)
      expect(result.total_pages).toBe(3)
    })
  })

  describe('triggerSync', () => {
    it('sends POST with integration_id and request params', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ id: 'j1', status: 'pending' }))
      const api = createApiClient(createTestConfig())

      await api.triggerSync('int1', { job_type: 'full_sync' })

      const options = fetchSpy.mock.calls[0][1] as RequestInit
      expect(options.method).toBe('POST')
      expect(JSON.parse(options.body as string)).toEqual({
        integration_id: 'int1',
        job_type: 'full_sync',
      })
    })
  })

  describe('cancelSyncJob', () => {
    it('sends POST to cancel endpoint', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ id: 'j1', status: 'cancelled' }))
      const api = createApiClient(createTestConfig())

      await api.cancelSyncJob('j1')
      expect(fetchSpy.mock.calls[0][0]).toBe('https://api.test/sync-jobs/j1/cancel')
    })
  })

  describe('getSyncJobRecords', () => {
    it('builds query string from filter params', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({ records: [], total: 0, page: 1, page_size: 20, total_pages: 0 })
      )
      const api = createApiClient(createTestConfig())

      await api.getSyncJobRecords('j1', { entity_type: 'invoice', status: 'failed' })

      const url = fetchSpy.mock.calls[0][0] as string
      expect(url).toContain('entity_type=invoice')
      expect(url).toContain('status=failed')
    })
  })

  // ── Health check ────────────────────────────────────────────

  describe('checkHealth', () => {
    it('calls health endpoint without auth headers', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ status: 'ok' }))
      const api = createApiClient(createTestConfig())

      const result = await api.checkHealth()
      expect(result).toEqual({ status: 'ok' })
    })
  })
})
