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

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  // Fetch job details with auto-refresh for active jobs
  const { data: job, isLoading } = useQuery({
    queryKey: ['sync-job', jobId],
    queryFn: () => api.getSyncJob(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.status === 'pending' || data?.status === 'running') {
        return 2000 // Refresh every 2 seconds
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
  const canCancel = job.status === 'pending' || job.status === 'running'

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
        {canCancel && (
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

      {/* Status Card */}
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

          {/* Timing */}
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

      {/* Entities Processed */}
      {job.entities_processed && Object.keys(job.entities_processed).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Entities Processed</CardTitle>
            <CardDescription>Summary of synced data by entity type</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(job.entities_processed)
                .filter(([key]) => !key.startsWith('_'))
                .map(([entityType, summary]) => (
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
      )}

      {/* Error Details */}
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
