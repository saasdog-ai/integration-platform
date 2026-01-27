/**
 * Configuration Provider for Integrations UI
 *
 * This provider allows host applications to inject configuration when using
 * this UI as a micro-frontend via Module Federation.
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

/**
 * Configuration interface for the Integrations UI
 */
export interface IntegrationsConfig {
  /**
   * Base URL for the API (e.g., 'https://api.example.com' or '/api/integrations')
   * @default '/api/integrations'
   */
  apiBaseUrl: string

  /**
   * Function to retrieve the current auth token
   * Return empty string if no token (for unauthenticated requests)
   */
  getAuthToken: () => string

  /**
   * Optional route prefix for all routes (e.g., '/integrations')
   * @default ''
   */
  routePrefix?: string

  /**
   * Optional callback when user session expires (401 response)
   */
  onUnauthorized?: () => void

  /**
   * Client ID for multi-tenant scenarios
   */
  clientId?: string
}

const ConfigContext = createContext<IntegrationsConfig | null>(null)

// Default configuration for standalone mode
const defaultConfig: IntegrationsConfig = {
  apiBaseUrl: import.meta.env.VITE_API_URL || '/int-api',
  getAuthToken: () => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('auth_token') || ''
    }
    return ''
  },
  routePrefix: '',
  onUnauthorized: () => {
    console.warn('[Integrations] Unauthorized - please implement onUnauthorized handler')
  },
}

/**
 * Hook to access the Integrations configuration
 */
export function useConfig(): IntegrationsConfig {
  const context = useContext(ConfigContext)
  if (!context) {
    return defaultConfig
  }
  return context
}

interface IntegrationsProviderProps {
  config?: Partial<IntegrationsConfig>
  queryClient?: QueryClient
  children: ReactNode
}

// Default QueryClient for standalone use
const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
    },
  },
})

/**
 * Provider component for Integrations UI configuration
 */
export function IntegrationsProvider({
  config,
  queryClient,
  children,
}: IntegrationsProviderProps) {
  const mergedConfig = useMemo<IntegrationsConfig>(
    () => ({
      ...defaultConfig,
      ...config,
    }),
    [config]
  )

  const client = queryClient || defaultQueryClient

  return (
    <ConfigContext.Provider value={mergedConfig}>
      <QueryClientProvider client={client}>
        {children}
      </QueryClientProvider>
    </ConfigContext.Provider>
  )
}

export { ConfigContext }
