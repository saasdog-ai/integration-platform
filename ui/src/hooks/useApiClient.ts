import { useMemo } from 'react'
import { useConfig } from '@/providers/ConfigProvider'
import { createApiClient, type ApiClient } from '@/api/apiClient'

/**
 * Hook to get a configured API client
 */
export function useApiClient(): ApiClient {
  const config = useConfig()
  const apiClient = useMemo(() => createApiClient(config), [config])
  return apiClient
}
