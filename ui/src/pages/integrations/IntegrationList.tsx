import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { IntegrationStatusBadge } from '@/components/StatusBadge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { OnboardingDialog } from './OnboardingDialog'
import type { AvailableIntegration, UserIntegration } from '@/types'

// Integration type icons
const TYPE_ICONS: Record<string, string> = {
  erp: '📊',
  hris: '👥',
  crm: '🤝',
  accounting: '💰',
  default: '🔗',
}

// Integration-specific logos (using emoji for now)
const INTEGRATION_LOGOS: Record<string, string> = {
  'QuickBooks Online': '📗',
  'Xero': '📘',
  'NetSuite': '📙',
  'Sage Intacct': '📕',
  default: '🔌',
}

export function IntegrationList() {
  const api = useApiClient()
  const toast = useToast()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [selectedIntegration, setSelectedIntegration] = useState<AvailableIntegration | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [disconnectTarget, setDisconnectTarget] = useState<{ integrationId: string; name: string; accountId?: string } | null>(null)

  // Fetch available integrations
  const { data: availableIntegrations, isLoading: loadingAvailable } = useQuery({
    queryKey: ['available-integrations'],
    queryFn: () => api.getAvailableIntegrations(),
  })

  // Fetch user's connected integrations
  const { data: userIntegrations, isLoading: loadingUser } = useQuery({
    queryKey: ['user-integrations'],
    queryFn: () => api.getUserIntegrations(),
  })

  // Trigger sync mutation
  const syncMutation = useMutation({
    mutationFn: (integrationId: string) => api.triggerSync(integrationId),
    onSuccess: (job) => {
      toast.success('Sync started', `Job ID: ${job.id.slice(0, 8)}...`)
      queryClient.invalidateQueries({ queryKey: ['sync-jobs'] })
      navigate('jobs')
    },
    onError: (error: Error) => {
      toast.error('Failed to start sync', error.message)
    },
  })

  // Disconnect mutation
  const disconnectMutation = useMutation({
    mutationFn: (integrationId: string) => api.disconnectIntegration(integrationId),
    onSuccess: () => {
      toast.success('Integration disconnected')
      queryClient.invalidateQueries({ queryKey: ['user-integrations'] })
      setDisconnectTarget(null)
    },
    onError: (error: Error) => {
      toast.error('Failed to disconnect', error.message)
    },
  })

  const isLoading = loadingAvailable || loadingUser

  // Map user integrations by integration_id for quick lookup
  const userIntegrationMap = new Map<string, UserIntegration>(
    userIntegrations?.map((ui) => [ui.integration_id, ui]) || []
  )

  const handleConnect = (integration: AvailableIntegration) => {
    setSelectedIntegration(integration)
    setShowOnboarding(true)
  }

  const handleSync = (integrationId: string) => {
    syncMutation.mutate(integrationId)
  }

  const handleOnboardingComplete = () => {
    setShowOnboarding(false)
    setSelectedIntegration(null)
    queryClient.invalidateQueries({ queryKey: ['user-integrations'] })
    toast.success('Integration connected', 'You can now sync your data.')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Integrations</h1>
          <p className="text-muted-foreground mt-1">
            Connect your accounts to sync data automatically
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate('jobs')}>
          View Sync Jobs
        </Button>
      </div>

      {/* Integration Tiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {availableIntegrations?.map((integration) => {
          const userIntegration = userIntegrationMap.get(integration.id)
          const isConnected = userIntegration?.status === 'connected'
          const logo = INTEGRATION_LOGOS[integration.name] || INTEGRATION_LOGOS.default
          const typeIcon = TYPE_ICONS[integration.type] || TYPE_ICONS.default

          return (
            <Card key={integration.id} className="relative overflow-hidden">
              {/* Type badge */}
              <div className="absolute top-3 right-3">
                <Badge variant="secondary" className="text-xs">
                  {typeIcon} {integration.type.toUpperCase()}
                </Badge>
              </div>

              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="text-4xl">{logo}</div>
                  <div>
                    <CardTitle className="text-lg">{integration.name}</CardTitle>
                    {userIntegration && (
                      <div className="mt-1">
                        <IntegrationStatusBadge status={userIntegration.status} />
                      </div>
                    )}
                  </div>
                </div>
              </CardHeader>

              <CardContent>
                <CardDescription className="min-h-[40px]">
                  {integration.description || `Sync your ${integration.name} data`}
                </CardDescription>

                {/* Supported entities */}
                <div className="mt-3">
                  <p className="text-xs text-muted-foreground mb-1">Supported entities:</p>
                  <div className="flex flex-wrap gap-1">
                    {integration.supported_entities.slice(0, 4).map((entity) => (
                      <Badge key={entity} variant="outline" className="text-xs">
                        {entity}
                      </Badge>
                    ))}
                    {integration.supported_entities.length > 4 && (
                      <Badge variant="outline" className="text-xs">
                        +{integration.supported_entities.length - 4} more
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Connected account info */}
                {userIntegration?.external_account_id && (
                  <div className="mt-3 p-2 bg-muted rounded-md">
                    <p className="text-xs text-muted-foreground">Connected account:</p>
                    <p className="text-sm font-medium">{userIntegration.external_account_id}</p>
                  </div>
                )}
              </CardContent>

              <CardFooter className="gap-2">
                {isConnected ? (
                  <>
                    <Button
                      className="flex-1"
                      size="sm"
                      onClick={() => handleSync(integration.id)}
                      disabled={syncMutation.isPending}
                    >
                      {syncMutation.isPending ? (
                        <>
                          <Spinner size="sm" className="mr-2" />
                          Syncing...
                        </>
                      ) : (
                        'Sync Now'
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate(`${integration.id}`)}
                    >
                      Manage
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setDisconnectTarget({
                        integrationId: integration.id,
                        name: integration.name,
                        accountId: userIntegration?.external_account_id ?? undefined,
                      })}
                    >
                      Disconnect
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      className="flex-1"
                      onClick={() => handleConnect(integration)}
                    >
                      {userIntegration ? 'Reconnect' : 'Connect'}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate(`${integration.id}`)}
                    >
                      Manage
                    </Button>
                  </>
                )}
              </CardFooter>
            </Card>
          )
        })}
      </div>

      {/* Empty state */}
      {availableIntegrations?.length === 0 && (
        <Card className="p-8 text-center">
          <div className="text-4xl mb-4">🔌</div>
          <h3 className="text-lg font-semibold mb-2">No integrations available</h3>
          <p className="text-muted-foreground">
            Contact your administrator to enable integrations.
          </p>
        </Card>
      )}

      {/* Disconnect Confirmation Dialog */}
      <Dialog open={!!disconnectTarget} onOpenChange={(open) => { if (!open) setDisconnectTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect {disconnectTarget?.name}?</DialogTitle>
            <DialogDescription>
              This will remove your credentials for this integration. Any data already synced will remain in the system.
            </DialogDescription>
          </DialogHeader>
          {disconnectTarget?.accountId && (
            <div className="px-6 text-sm text-muted-foreground">
              Account: <span className="font-medium text-foreground">{disconnectTarget.accountId}</span>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisconnectTarget(null)} autoFocus>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (disconnectTarget) {
                  disconnectMutation.mutate(disconnectTarget.integrationId)
                }
              }}
              disabled={disconnectMutation.isPending}
            >
              {disconnectMutation.isPending ? <Spinner size="sm" className="mr-2" /> : null}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Onboarding Dialog */}
      {selectedIntegration && (
        <OnboardingDialog
          open={showOnboarding}
          onOpenChange={setShowOnboarding}
          integration={selectedIntegration}
          onComplete={handleOnboardingComplete}
        />
      )}
    </div>
  )
}
