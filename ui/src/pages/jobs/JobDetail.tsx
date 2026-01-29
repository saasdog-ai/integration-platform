import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { SyncJobStatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/utils'
import { DEFAULT_PAGE_SIZE, JOB_DETAIL_REFETCH_INTERVAL_MS } from '@/lib/constants'
import type { SyncJob, SyncRecord, RecordSyncStatus, EntityProcessedSummary } from '@/types'

// ─── Sub-components ──────────────────────────────────────────────

function JobStatusCard({ job }: { job: SyncJob }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Job Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Status</p>
            <div className="mt-1">
              <SyncJobStatusBadge status={job.status} />
            </div>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Type</p>
            <p className="font-medium capitalize">{job.job_type.replace('_', ' ')}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Triggered By</p>
            <p className="font-medium capitalize">{job.triggered_by}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Created</p>
            <p className="font-medium">{formatDate(job.created_at)}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t">
          <div>
            <p className="text-sm text-muted-foreground">Started At</p>
            <p className="font-medium">
              {job.started_at ? formatDate(job.started_at) : 'Not started'}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Completed At</p>
            <p className="font-medium">
              {job.completed_at ? formatDate(job.completed_at) : 'Not completed'}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function EntitiesProcessedCard({
  entities,
}: {
  entities: Record<string, EntityProcessedSummary>
}) {
  const filtered = Object.entries(entities).filter(([key]) => !key.startsWith('_'))
  if (filtered.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Entities Processed</CardTitle>
        <CardDescription>Summary of synced data by entity type</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {filtered.map(([entityType, summary]) => (
            <div
              key={entityType}
              className="flex items-center justify-between p-3 bg-muted rounded-lg"
            >
              <div className="flex items-center gap-3">
                <Badge variant="outline" className="capitalize">
                  {entityType}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {summary.direction}
                </span>
              </div>
              <div className="flex gap-4 text-sm">
                <span>
                  <strong>{summary.records_fetched}</strong> fetched
                </span>
                <span className="text-green-600">
                  <strong>{summary.records_created}</strong> created
                </span>
                <span className="text-blue-600">
                  <strong>{summary.records_updated}</strong> updated
                </span>
                {summary.records_failed > 0 && (
                  <span className="text-red-600">
                    <strong>{summary.records_failed}</strong> failed
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ErrorDetailsPanel({
  record,
  onClose,
}: {
  record: SyncRecord
  onClose: () => void
}) {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
      <div className="space-y-2">
        <div className="flex justify-between items-start">
          <div>
            <p className="font-medium text-red-700">
              Error: {record.error_code}
            </p>
            <p className="text-sm text-red-600">{record.error_message}</p>
          </div>
          <button
            className="text-red-500 hover:text-red-700"
            onClick={onClose}
            aria-label="Close error details"
          >
            ✕
          </button>
        </div>
        {record.error_details && (
          <pre className="mt-2 p-3 bg-white rounded text-xs overflow-auto border">
            {JSON.stringify(record.error_details, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

interface RecordsTableProps {
  records: SyncRecord[]
  expandedError: string | null
  onToggleError: (id: string | null) => void
  page: number
  totalPages: number
  total: number
  onPageChange: (page: number) => void
}

function RecordsTable({
  records,
  expandedError,
  onToggleError,
  page,
  totalPages,
  total,
  onPageChange,
}: RecordsTableProps) {
  const expandedRecord = useMemo(
    () => (expandedError ? records.find((r) => r.id === expandedError) : null),
    [expandedError, records]
  )

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th scope="col" className="text-left py-2 px-3 font-medium">Timestamp</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Entity Type</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Internal ID</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Direction</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Status</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">External ID</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Error</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id} className="border-b hover:bg-muted/50">
                <td className="py-2 px-3 text-muted-foreground">
                  {formatDate(record.updated_at)}
                </td>
                <td className="py-2 px-3">
                  <Badge variant="outline" className="capitalize">
                    {record.entity_type}
                  </Badge>
                </td>
                <td className="py-2 px-3 font-mono text-xs">
                  {record.internal_record_id || '-'}
                </td>
                <td className="py-2 px-3 capitalize">
                  {record.sync_direction || '-'}
                </td>
                <td className="py-2 px-3">
                  {record.is_success ? (
                    <Badge variant="success">Synced</Badge>
                  ) : (
                    <Badge variant="error">Failed</Badge>
                  )}
                </td>
                <td className="py-2 px-3 font-mono text-xs">
                  {record.external_record_id || '-'}
                </td>
                <td className="py-2 px-3">
                  {record.error_code ? (
                    <button
                      className="text-red-600 hover:underline text-left"
                      onClick={() =>
                        onToggleError(expandedError === record.id ? null : record.id)
                      }
                      aria-expanded={expandedError === record.id}
                    >
                      {record.error_code}
                      {expandedError === record.id ? ' ▼' : ' ▶'}
                    </button>
                  ) : (
                    '-'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {expandedRecord && (
        <ErrorDetailsPanel
          record={expandedRecord}
          onClose={() => onToggleError(null)}
        />
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} ({total} records)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page === 1}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [recordsPage, setRecordsPage] = useState(1)
  const [recordsFilter, setRecordsFilter] = useState<{
    entity_type?: string
    status?: RecordSyncStatus
  }>({})
  const [expandedError, setExpandedError] = useState<string | null>(null)

  // Fetch job details with auto-refresh for active jobs
  const { data: job, isLoading } = useQuery({
    queryKey: ['sync-job', jobId],
    queryFn: () => api.getSyncJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.status === 'pending' || data?.status === 'running') {
        return JOB_DETAIL_REFETCH_INTERVAL_MS
      }
      return false
    },
  })

  // Cancel job mutation
  const cancelMutation = useMutation({
    mutationFn: () => api.cancelSyncJob(jobId!),
    onSuccess: () => {
      toast.success('Job cancelled')
      queryClient.invalidateQueries({ queryKey: ['sync-job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['sync-jobs'] })
    },
    onError: (error: Error) => {
      toast.error('Failed to cancel job', error.message)
    },
  })

  // Fetch job records (only when job is completed)
  const { data: recordsData, isLoading: recordsLoading } = useQuery({
    queryKey: ['sync-job-records', jobId, recordsPage, recordsFilter],
    queryFn: () =>
      api.getSyncJobRecords(jobId!, {
        page: recordsPage,
        page_size: DEFAULT_PAGE_SIZE,
        ...recordsFilter,
      }),
    enabled: !!jobId && !!job && (job.status === 'succeeded' || job.status === 'failed'),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!job) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold mb-2">Job not found</h2>
        <Button onClick={() => navigate('..')}>Back to Jobs</Button>
      </div>
    )
  }

  const isActive = job.status === 'pending' || job.status === 'running'
  const entityKeys = job.entities_processed
    ? Object.keys(job.entities_processed).filter((k) => !k.startsWith('_'))
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('..')}>
            ← Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-3">
              Sync Job
              <SyncJobStatusBadge status={job.status} />
              {isActive && <Spinner size="sm" />}
            </h1>
            <p className="text-muted-foreground mt-1">
              {job.integration_name || 'Unknown Integration'} • {job.job_type.replace('_', ' ')}
            </p>
          </div>
        </div>
        {isActive && (
          <Button
            variant="destructive"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
          >
            {cancelMutation.isPending ? <Spinner size="sm" className="mr-2" /> : null}
            Cancel Job
          </Button>
        )}
      </div>

      <JobStatusCard job={job} />

      {job.entities_processed && Object.keys(job.entities_processed).length > 0 && (
        <EntitiesProcessedCard entities={job.entities_processed} />
      )}

      {/* Record Details Table */}
      {(job.status === 'succeeded' || job.status === 'failed') && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Record Details</CardTitle>
                <CardDescription>
                  Individual records synced in this job
                  {recordsData && ` (${recordsData.total} total)`}
                </CardDescription>
              </div>
              <div className="flex gap-2">
                <div>
                  <label htmlFor="records-status-filter" className="sr-only">
                    Filter by status
                  </label>
                  <select
                    id="records-status-filter"
                    className="text-sm border rounded px-2 py-1"
                    value={recordsFilter.status || ''}
                    onChange={(e) => {
                      setRecordsFilter((f) => ({
                        ...f,
                        status: (e.target.value as RecordSyncStatus) || undefined,
                      }))
                      setRecordsPage(1)
                    }}
                  >
                    <option value="">All Statuses</option>
                    <option value="synced">Synced</option>
                    <option value="failed">Failed</option>
                    <option value="pending">Pending</option>
                  </select>
                </div>
                {entityKeys.length > 0 && (
                  <div>
                    <label htmlFor="records-entity-filter" className="sr-only">
                      Filter by entity type
                    </label>
                    <select
                      id="records-entity-filter"
                      className="text-sm border rounded px-2 py-1"
                      value={recordsFilter.entity_type || ''}
                      onChange={(e) => {
                        setRecordsFilter((f) => ({
                          ...f,
                          entity_type: e.target.value || undefined,
                        }))
                        setRecordsPage(1)
                      }}
                    >
                      <option value="">All Entity Types</option>
                      {entityKeys.map((entityType) => (
                        <option key={entityType} value={entityType}>
                          {entityType}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {recordsLoading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : recordsData && recordsData.records.length > 0 ? (
              <RecordsTable
                records={recordsData.records}
                expandedError={expandedError}
                onToggleError={setExpandedError}
                page={recordsData.page}
                totalPages={recordsData.total_pages}
                total={recordsData.total}
                onPageChange={setRecordsPage}
              />
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                No records found for this job
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Job Error Details */}
      {job.error_message && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="text-red-600">Error Details</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {job.error_code && (
                <div>
                  <p className="text-sm text-muted-foreground">Error Code</p>
                  <Badge variant="error">{job.error_code}</Badge>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Error Message</p>
                <p className="font-medium text-red-600">{job.error_message}</p>
              </div>
              {job.error_details && (
                <div>
                  <p className="text-sm text-muted-foreground">Details</p>
                  <pre className="mt-1 p-3 bg-muted rounded-md text-xs overflow-auto">
                    {JSON.stringify(job.error_details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
