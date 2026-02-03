import { useEffect, useState } from 'react'
import { useApiClient } from '@/hooks/useApiClient'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'

type CallbackStatus = 'processing' | 'success' | 'error'

// Module-level guard: tracks which auth codes have been submitted.
// Survives React Strict Mode remounts and host-app redirects.
const submittedCodes = new Set<string>()

export function OAuthCallback() {
  const api = useApiClient()
  const [status, setStatus] = useState<CallbackStatus>('processing')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    const realmId = params.get('realmId')

    if (code && submittedCodes.has(code)) return
    if (code) submittedCodes.add(code)

    if (!code || !state) {
      setStatus('error')
      setErrorMessage('Missing required OAuth parameters (code or state).')
      return
    }

    // Parse state as {integrationId}:{csrfToken}
    const colonIndex = state.indexOf(':')
    if (colonIndex === -1) {
      setStatus('error')
      setErrorMessage('Invalid state parameter format.')
      return
    }

    const integrationId = state.substring(0, colonIndex)
    const csrfToken = state.substring(colonIndex + 1)

    if (!integrationId || !csrfToken) {
      setStatus('error')
      setErrorMessage('Invalid state parameter: missing integration ID or CSRF token.')
      return
    }

    const redirectUri = window.location.origin + '/integrations/oauth/callback'

    api
      .completeOAuthCallback(integrationId, {
        code,
        redirect_uri: redirectUri,
        state: csrfToken,
        realm_id: realmId ?? undefined,
      })
      .then(() => {
        setStatus('success')
        if (window.opener) {
          window.opener.postMessage(
            { type: 'oauth-complete', success: true },
            window.location.origin
          )
          window.close()
        }
      })
      .catch((err: unknown) => {
        setStatus('error')
        const message =
          err instanceof Error ? err.message : 'OAuth callback failed.'
        setErrorMessage(message)
        if (window.opener) {
          window.opener.postMessage(
            { type: 'oauth-complete', success: false, error: message },
            window.location.origin
          )
        }
      })
  }, [api])

  const handleClose = () => {
    window.close()
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="max-w-md w-full p-8 text-center space-y-4">
        {status === 'processing' && (
          <>
            <Spinner size="lg" />
            <p className="text-muted-foreground">
              Completing authorization...
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <p className="text-lg font-medium text-green-600">
              Authorization successful!
            </p>
            <p className="text-sm text-muted-foreground">
              This window should close automatically. If it doesn't, you can
              close it manually.
            </p>
            <Button variant="outline" onClick={handleClose}>
              Close Window
            </Button>
          </>
        )}

        {status === 'error' && (
          <>
            <p className="text-lg font-medium text-destructive">
              Authorization Failed
            </p>
            <p className="text-sm text-muted-foreground">{errorMessage}</p>
            <Button variant="outline" onClick={handleClose}>
              Close Window
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
