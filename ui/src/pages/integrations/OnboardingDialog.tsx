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
import { Spinner } from '@/components/ui/spinner'
import type { AvailableIntegration } from '@/types'

interface OnboardingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  integration: AvailableIntegration
  onComplete: () => void
}

type OnboardingStep = 'intro' | 'connecting' | 'complete'

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

  // Connect integration mutation - uses OAuth callback for mock flow
  const connectMutation = useMutation({
    mutationFn: async () => {
      // For mock mode, we skip the OAuth redirect and directly call the callback
      // with a mock authorization code. The backend adapter handles this.
      const result = await api.completeOAuthCallback(integration.id, {
        code: `mock_auth_code_${Date.now()}`,
        redirect_uri: window.location.origin + '/integrations/callback',
      })
      return result
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-integrations'] })
      setStep('complete')
    },
    onError: (error: unknown) => {
      console.error('Connection error:', error)
      setStep('intro') // Go back to intro on error
      let message = 'Unknown error'
      if (error instanceof Error) {
        message = error.message
      } else if (typeof error === 'object' && error !== null && 'message' in error) {
        message = String((error as { message: unknown }).message)
      } else if (typeof error === 'object' && error !== null) {
        try {
          message = JSON.stringify(error)
        } catch {
          message = 'Connection failed'
        }
      } else if (typeof error === 'string') {
        message = error
      }
      toast.error('Connection failed', message)
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
    if (connectMutation.isPending) return // Don't close while connecting
    setStep('intro')
    onOpenChange(false)
  }

  const handleConnect = () => {
    setStep('connecting')
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

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm text-blue-800">
                  <strong>Demo Mode:</strong> In production, you would be redirected to {integration.name} to authorize.
                  For testing, mock credentials will be stored automatically.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleConnect}>
                Connect {integration.name}
              </Button>
            </DialogFooter>
          </>
        )

      case 'connecting':
        return (
          <>
            <DialogHeader>
              <DialogTitle>Connecting to {integration.name}</DialogTitle>
              <DialogDescription>
                Please wait while we establish the connection...
              </DialogDescription>
            </DialogHeader>

            <div className="py-12 flex flex-col items-center justify-center space-y-4">
              <Spinner size="lg" />
              <p className="text-sm text-muted-foreground">
                Setting up mock credentials...
              </p>
            </div>
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
