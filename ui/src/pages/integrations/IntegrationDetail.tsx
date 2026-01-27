import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { IntegrationStatusBadge, SyncJobStatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/utils'

export function IntegrationDetail() {
  const { integrationId } = useParams<{ integrationId: string }>()
  const navigate = useNavigate()
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  // Fetch user integration
  const { data: userIntegration, isLoading: loadingIntegration } = useQuery({
    queryKey: ['user-integration', integrationId],
    queryFn: () => api.getUserIntegration(integrationId!),
    enabled: !!integrationId,
  })

  // Fetch integration settings
  const { data: settings, isLoading: loadingSettings } = useQuery({
    queryKey: ['integration-settings', integrationId],
    queryFn: () => api.getIntegrationSettings(integrationId!),
    enabled: !!integrationId,
  })

  // Fetch recent sync jobs
  const { data: jobsData } = useQuery({
    queryKey: ['sync-jobs', { integration_id: integrationId, page_size: 5 }],
    queryFn: () => api.getSyncJobs({ integration_id: integrationId, page_size: 5 }),
    enabled: !!integrationId,
  })

  // Trigger sync mutation
  const syncMutation = useMutation({
    mutationFn: () => api.triggerSync(integrationId!),
    onSuccess: (job) => {
      toast.success('Sync started', `Job ID: ${job.id.slice(0, 8)}...`)
      queryClient.invalidateQueries({ queryKey: ['sync-jobs'] })
      navigate('../jobs')
    },
    onError: (error: Error) => {
      toast.error('Failed to start sync', error.message)
    },
  })

  // Disconnect mutation
  const disconnectMutation = useMutation({
    mutationFn: () => api.disconnectIntegration(integrationId!),
    onSuccess: () => {
      toast.success('Integration disconnected')
      queryClient.invalidateQueries({ queryKey: ['user-integrations'] })
      navigate('..')
    },
    onError: (error: Error) => {
      toast.error('Failed to disconnect', error.message)
    },
  })

  const isLoading = loadingIntegration || loadingSettings

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!userIntegration) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold mb-2">Integration not found</h2>
        <p className="text-muted-foreground mb-4">
          This integration may not be connected or doesn't exist.
        </p>
        <Button onClick={() => navigate('..')}>Back to Integrations</Button>
      </div>
    )
  }

  const integration = userIntegration.integration

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('..')}>
            ← Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{integration?.name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <IntegrationStatusBadge status={userIntegration.status} />
              {userIntegration.external_account_id && (
                <span className="text-sm text-muted-foreground">
                  Account: {userIntegration.external_account_id}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending || userIntegration.status !== 'connected'}
          >
            {syncMutation.isPending ? <Spinner size="sm" className="mr-2" /> : null}
            🔄 Sync Now
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              if (confirm('Are you sure you want to disconnect this integration?')) {
                disconnectMutation.mutate()
              }
            }}
            disabled={disconnectMutation.isPending}
          >
            Disconnect
          </Button>
        </div>
      </div>

      {/* Sync Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Sync Settings</CardTitle>
          <CardDescription>Configure which entities to sync and their direction</CardDescription>
        </CardHeader>
        <CardContent>
          {settings?.sync_rules && settings.sync_rules.length > 0 ? (
            <div className="space-y-3">
              {settings.sync_rules.map((rule) => (
                <div
                  key={rule.entity_type}
                  className="flex items-center justify-between p-3 bg-muted rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-medium capitalize">{rule.entity_type}</span>
                    <Badge variant="outline">{rule.direction}</Badge>
                  </div>
                  <Badge variant={rule.enabled ? 'success' : 'secondary'}>
                    {rule.enabled ? 'Enabled' : 'Disabled'}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground">No sync rules configured.</p>
          )}
        </CardContent>
      </Card>

      {/* Recent Jobs */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Sync Jobs</CardTitle>
            <CardDescription>Latest sync activity for this integration</CardDescription>
          </div>
          <Button variant="outline" onClick={() => navigate('../jobs')}>
            View All Jobs
          </Button>
        </CardHeader>
        <CardContent>
          {jobsData?.items && jobsData.items.length > 0 ? (
            <div className="space-y-2">
              {jobsData.items.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between p-3 bg-muted rounded-lg cursor-pointer hover:bg-muted/80"
                  onClick={() => navigate(`../jobs/${job.id}`)}
                >
                  <div className="flex items-center gap-3">
                    <SyncJobStatusBadge status={job.status} />
                    <span className="text-sm">
                      {job.job_type.replace('_', ' ')}
                    </span>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {formatDate(job.created_at)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground">No sync jobs yet.</p>
          )}
        </CardContent>
      </Card>

      {/* Connection Info */}
      <Card>
        <CardHeader>
          <CardTitle>Connection Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Connected at:</span>
            <span>{userIntegration.last_connected_at ? formatDate(userIntegration.last_connected_at) : 'N/A'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Integration ID:</span>
            <span className="font-mono text-sm">{userIntegration.integration_id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">External Account:</span>
            <span>{userIntegration.external_account_id || 'N/A'}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
