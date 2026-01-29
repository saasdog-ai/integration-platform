import { type ReactNode } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/contexts/ToastContext'
import type { ApiClient } from '@/api/apiClient'
import { vi } from 'vitest'

/** Create a mock API client with all methods stubbed */
export function createMockApiClient(overrides?: Partial<ApiClient>): ApiClient {
  return {
    getAvailableIntegrations: vi.fn().mockResolvedValue([]),
    getAvailableIntegration: vi.fn().mockResolvedValue({
      id: 'int1',
      name: 'QuickBooks Online',
      type: 'accounting',
      description: null,
      supported_entities: ['invoice', 'customer', 'payment'],
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }),
    getUserIntegrations: vi.fn().mockResolvedValue([]),
    getUserIntegration: vi.fn().mockResolvedValue({
      id: 'ui1',
      client_id: 'c1',
      integration_id: 'int1',
      integration_name: 'QuickBooks Online',
      integration_type: 'accounting',
      status: 'connected',
      external_account_id: 'acct-123',
      last_connected_at: '2024-01-01T00:00:00Z',
      disconnected_at: null,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    }),
    connectIntegration: vi.fn().mockResolvedValue({}),
    completeOAuthCallback: vi.fn().mockResolvedValue({}),
    disconnectIntegration: vi.fn().mockResolvedValue(undefined),
    getIntegrationSettings: vi.fn().mockResolvedValue({
      sync_rules: [
        { entity_type: 'invoice', direction: 'inbound', enabled: true },
        { entity_type: 'customer', direction: 'bidirectional', enabled: false },
      ],
      sync_frequency: '6h',
      auto_sync_enabled: true,
    }),
    updateIntegrationSettings: vi.fn().mockResolvedValue({}),
    triggerSync: vi.fn().mockResolvedValue({ id: 'job1', status: 'pending' }),
    getSyncJobs: vi.fn().mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 0,
    }),
    getSyncJob: vi.fn().mockResolvedValue({
      id: 'job1',
      status: 'succeeded',
      job_type: 'full_sync',
      triggered_by: 'user',
      integration_name: 'QuickBooks Online',
      created_at: '2024-01-01T00:00:00Z',
      started_at: '2024-01-01T00:00:01Z',
      completed_at: '2024-01-01T00:00:05Z',
      entities_processed: null,
      error_code: null,
      error_message: null,
      error_details: null,
    }),
    cancelSyncJob: vi.fn().mockResolvedValue({}),
    getSyncJobRecords: vi.fn().mockResolvedValue({
      records: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 0,
    }),
    checkHealth: vi.fn().mockResolvedValue({ status: 'ok' }),
    ...overrides,
  } as ApiClient
}

// Module-level mock reference so tests can swap implementations
export let mockApi: ApiClient = createMockApiClient()

/** Replace the mock API client for the current test */
export function setMockApiClient(api: ApiClient) {
  mockApi = api
}

/** Get the current mock API client */
export function getMockApiClient(): ApiClient {
  return mockApi
}

interface WrapperOptions {
  initialRoute?: string
}

function createWrapper({ initialRoute = '/' }: WrapperOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={[initialRoute]}>
            {children}
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    )
  }
}

export function renderWithProviders(
  ui: ReactNode,
  options?: WrapperOptions & Omit<RenderOptions, 'wrapper'>
) {
  const { initialRoute, ...renderOptions } = options ?? {}
  return render(ui, {
    wrapper: createWrapper({ initialRoute }),
    ...renderOptions,
  })
}
