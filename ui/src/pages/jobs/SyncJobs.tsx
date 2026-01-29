import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useApiClient } from '@/hooks/useApiClient'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { SyncJobStatusBadge } from '@/components/StatusBadge'
import { formatRelativeTime } from '@/lib/utils'
import {
  DEFAULT_PAGE_SIZE,
  SYNC_JOBS_REFETCH_INTERVAL_MS,
  REFRESH_GRACE_PERIOD_MS,
} from '@/lib/constants'
import type { SyncJobStatus } from '@/types'

const STATUS_FILTERS: { value: SyncJobStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'cancelled', label: 'Cancelled' },
]

export function SyncJobs() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [statusFilter, setStatusFilter] = useState<SyncJobStatus | 'all'>(
    (searchParams.get('status') as SyncJobStatus) || 'all'
  )
  const [page, setPage] = useState(1)

  // Auto-refresh for pending/running jobs
  const [autoRefresh, setAutoRefresh] = useState(true)

  // Fetch sync jobs
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['sync-jobs', { status: statusFilter === 'all' ? undefined : statusFilter, page }],
    queryFn: () =>
      api.getSyncJobs({
        status: statusFilter === 'all' ? undefined : statusFilter,
        page,
        page_size: DEFAULT_PAGE_SIZE,
      }),
    refetchInterval: autoRefresh ? SYNC_JOBS_REFETCH_INTERVAL_MS : false,
  })

  // Auto-disable refresh when no pending/running jobs
  useEffect(() => {
    if (data?.items) {
      const hasActiveJobs = data.items.some(
        (job) => job.status === 'pending' || job.status === 'running'
      )
      if (!hasActiveJobs && autoRefresh) {
        const timer = setTimeout(() => setAutoRefresh(false), REFRESH_GRACE_PERIOD_MS)
        return () => clearTimeout(timer)
      }
    }
  }, [data?.items, autoRefresh])

  // Re-enable refresh when filter changes
  useEffect(() => {
    setAutoRefresh(true)
  }, [statusFilter])

  const handleStatusChange = (status: SyncJobStatus | 'all') => {
    setStatusFilter(status)
    setPage(1)
    if (status === 'all') {
      searchParams.delete('status')
    } else {
      searchParams.set('status', status)
    }
    setSearchParams(searchParams)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('..')}>
            ← Back
          </Button>
          <div>
            <h1 className="text-xl font-bold">Sync Jobs</h1>
            <p className="text-sm text-muted-foreground">
              {data?.total || 0} total
              {isFetching && !isLoading && ' • Refreshing...'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {STATUS_FILTERS.map(({ value, label }) => (
            <Button
              key={value}
              variant={statusFilter === value ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleStatusChange(value)}
              aria-pressed={statusFilter === value}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {/* Jobs Table */}
      <div className="border rounded-lg">
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner size="lg" />
          </div>
        ) : data?.items && data.items.length > 0 ? (
          <div className="divide-y">
            {data.items.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between px-4 py-2 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => navigate(job.id)}
              >
                <div className="flex items-center gap-3">
                  <SyncJobStatusBadge status={job.status} />
                  <span className="font-medium">
                    {job.integration_name || 'Unknown'}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {job.job_type.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  <span>{job.triggered_by}</span>
                  <span className="w-24 text-right">{formatRelativeTime(job.created_at)}</span>
                  <svg
                    className="w-4 h-4 text-muted-foreground/50"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-muted-foreground">
              {statusFilter !== 'all'
                ? `No ${statusFilter} jobs`
                : 'No jobs yet'}
            </p>
          </div>
        )}

        {/* Pagination */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between px-4 py-2 border-t bg-muted/30">
            <span className="text-sm text-muted-foreground">
              Page {page} of {data.total_pages}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
