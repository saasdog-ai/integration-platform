/**
 * MicroFrontend - Content-only component for embedding in host applications
 *
 * This component renders ONLY the integrations functionality without any
 * layout, navigation, or chrome. The host application provides:
 * - Header/navbar
 * - Sidebar navigation
 * - Overall layout
 *
 * This component provides:
 * - Integration tiles and management
 * - Sync job monitoring
 * - Internal routing between views
 * - Toast notifications (scoped to this component)
 *
 * Usage in host app:
 * ```tsx
 * <Route path="/integrations/*" element={<IntegrationsMicroFrontend />} />
 * ```
 */

// Import styles for micro-frontend (Tailwind + component styles)
import "./index.css"

import { Routes, Route, Navigate } from "react-router-dom"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ToastProvider } from "@/contexts/ToastContext"
import { QueryClient } from "@tanstack/react-query"
import { IntegrationsProvider } from "@/providers/ConfigProvider"
import {
  IntegrationList,
  IntegrationDetail,
  OAuthCallback,
  SyncJobs,
  JobDetail,
  AdminPage,
} from "@/pages"

// Default QueryClient for standalone use
const defaultQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
})

interface MicroFrontendProps {
  /**
   * Optional QueryClient from host app for shared caching
   */
  queryClient?: QueryClient
  /**
   * Client ID for multi-tenant isolation
   */
  clientId?: string
}

/**
 * Integrations micro-frontend content component.
 * Renders only the page content - no layout, no sidebar.
 *
 * Routes (relative to where this is mounted):
 * - /          → Integration list (tiles)
 * - /:id       → Integration detail/settings
 * - /jobs      → Sync jobs list
 * - /jobs/:id  → Job detail
 */
export function IntegrationsMicroFrontend({ queryClient, clientId }: MicroFrontendProps) {
  const client = queryClient || defaultQueryClient

  return (
    <ErrorBoundary>
      <IntegrationsProvider config={{ clientId }} queryClient={client}>
        <ToastProvider>
          <div className="integrations-content" style={{ fontFamily: 'inherit' }}>
            <Routes>
              {/* Default route - integration list */}
              <Route index element={<IntegrationList />} />

              {/* OAuth callback route - must be before :integrationId catch-all */}
              <Route path="oauth/callback" element={<OAuthCallback />} />

              {/* Admin route - must be before :integrationId catch-all */}
              <Route path="admin" element={<AdminPage />} />

              {/* Sync jobs routes */}
              <Route path="jobs" element={<SyncJobs />} />
              <Route path="jobs/:jobId" element={<JobDetail />} />

              {/* Integration detail route (tabbed: overview, records, settings) */}
              <Route path=":integrationId" element={<IntegrationDetail />} />

              {/* Catch-all - redirect to list */}
              <Route path="*" element={<Navigate to="" replace />} />
            </Routes>
          </div>
        </ToastProvider>
      </IntegrationsProvider>
    </ErrorBoundary>
  )
}

export default IntegrationsMicroFrontend
