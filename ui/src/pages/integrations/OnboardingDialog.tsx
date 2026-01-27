import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import type { AvailableIntegration } from '@/types'

interface OnboardingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  integration: AvailableIntegration
  onComplete: () => void
}

type OnboardingStep = 'intro' | 'credentials' | 'settings' | 'complete'

export function OnboardingDialog({
  open,
  onOpenChange,
  integration,
  onComplete,
}: OnboardingDialogProps) {
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [step, setStep] = useState<OnboardingStep>('intro')
  const [accountId, setAccountId] = useState('')
  const [companyName, setCompanyName] = useState('')

  // Connect integration mutation
  const connectMutation = useMutation({
    mutationFn: () =>
      api.connectIntegration(integration.id, {
        external_account_id: accountId || `mock-${integration.name.toLowerCase().replace(/\s+/g, '-')}-${Date.now()}`,
        mock_credentials: {
          access_token: `mock_access_token_${Date.now()}`,
          refresh_token: `mock_refresh_token_${Date.now()}`,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-integrations'] })
      setStep('complete')
    },
    onError: (error: Error) => {
      toast.error('Connection failed', error.message)
    },
  })

  // Update settings mutation
  const settingsMutation = useMutation({
    mutationFn: () =>
      api.updateIntegrationSettings(integration.id, {
        sync_rules: integration.supported_entities.map((entity) => ({
          entity_type: entity,
          direction: 'inbound' as const,
          enabled: true,
        })),
        auto_sync_enabled: false,
      }),
    onSuccess: () => {
      onComplete()
    },
    onError: (error: Error) => {
      toast.error('Failed to save settings', error.message)
      // Still complete since connection worked
      onComplete()
    },
  })

  const handleClose = () => {
    setStep('intro')
    setAccountId('')
    setCompanyName('')
    onOpenChange(false)
  }

  const handleConnect = () => {
    connectMutation.mutate()
  }

  const handleFinish = () => {
    settingsMutation.mutate()
  }

  const renderStep = () => {
    switch (step) {
      case 'intro':
        return (
          <>
            <DialogHeader>
              <DialogTitle>Connect to {integration.name}</DialogTitle>
              <DialogDescription>
                Connect your {integration.name} account to sync your data automatically.
              </DialogDescription>
            </DialogHeader>

            <div className="py-6 space-y-4">
              <div className="text-center text-6xl mb-4">
                {integration.name === 'QuickBooks Online' ? '📗' : '🔗'}
              </div>

              <div className="bg-muted rounded-lg p-4">
                <h4 className="font-medium mb-2">What you'll be able to sync:</h4>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {integration.supported_entities.map((entity) => (
                    <li key={entity} className="flex items-center gap-2">
                      <span className="text-primary">✓</span>
                      {entity.charAt(0).toUpperCase() + entity.slice(1)}s
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-sm text-muted-foreground">
                In a real integration, you would be redirected to {integration.name} to authorize access.
                For this demo, we'll simulate the connection.
              </p>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={() => setStep('credentials')}>
                Continue
              </Button>
            </DialogFooter>
          </>
        )

      case 'credentials':
        return (
          <>
            <DialogHeader>
              <DialogTitle>Enter Account Details</DialogTitle>
              <DialogDescription>
                Enter your {integration.name} account information (mock data for demo).
              </DialogDescription>
            </DialogHeader>

            <div className="py-6 space-y-4">
              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Company Name
                </label>
                <Input
                  placeholder="Acme Corporation"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                />
              </div>

              <div>
                <label className="text-sm font-medium mb-1.5 block">
                  Account ID / Realm ID
                </label>
                <Input
                  placeholder="123456789"
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Leave blank to generate a mock ID
                </p>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm text-blue-800">
                  <strong>Demo Mode:</strong> In production, this would be an OAuth flow.
                  For testing, mock credentials will be stored.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setStep('intro')}>
                Back
              </Button>
              <Button
                onClick={handleConnect}
                disabled={connectMutation.isPending}
              >
                {connectMutation.isPending ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Connecting...
                  </>
                ) : (
                  'Connect Account'
                )}
              </Button>
            </DialogFooter>
          </>
        )

      case 'complete':
        return (
          <>
            <DialogHeader>
              <DialogTitle>Connection Successful!</DialogTitle>
              <DialogDescription>
                Your {integration.name} account has been connected.
              </DialogDescription>
            </DialogHeader>

            <div className="py-6 text-center">
              <div className="text-6xl mb-4">🎉</div>
              <p className="text-lg font-medium text-green-600 mb-2">
                Account Connected
              </p>
              <p className="text-sm text-muted-foreground">
                You can now sync your {integration.name} data.
                Click "Finish" to configure sync settings or start syncing right away.
              </p>
            </div>

            <DialogFooter>
              <Button
                onClick={handleFinish}
                disabled={settingsMutation.isPending}
              >
                {settingsMutation.isPending ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Saving...
                  </>
                ) : (
                  'Finish Setup'
                )}
              </Button>
            </DialogFooter>
          </>
        )

      default:
        return null
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent onClose={handleClose}>
        {renderStep()}
      </DialogContent>
    </Dialog>
  )
}
