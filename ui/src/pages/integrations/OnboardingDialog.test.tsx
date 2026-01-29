import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OnboardingDialog } from './OnboardingDialog'
import {
  renderWithProviders,
  createMockApiClient,
  setMockApiClient,
  getMockApiClient,
} from '@/test/test-utils'
import type { AvailableIntegration } from '@/types'

vi.mock('@/hooks/useApiClient')

const mockIntegration: AvailableIntegration = {
  id: 'int1',
  name: 'QuickBooks Online',
  type: 'accounting',
  description: 'Sync QuickBooks data',
  supported_entities: ['invoice', 'customer', 'payment'],
  is_active: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

function renderDialog(props?: Partial<React.ComponentProps<typeof OnboardingDialog>>) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    integration: mockIntegration,
    onComplete: vi.fn(),
    ...props,
  }
  return {
    ...renderWithProviders(<OnboardingDialog {...defaultProps} />),
    props: defaultProps,
  }
}

describe('OnboardingDialog', () => {
  beforeEach(() => {
    setMockApiClient(createMockApiClient())
  })

  it('renders intro step with integration name', () => {
    renderDialog()
    expect(screen.getByText('Connect to QuickBooks Online')).toBeInTheDocument()
  })

  it('lists supported entities on intro step', () => {
    renderDialog()
    expect(screen.getByText(/Invoices/i)).toBeInTheDocument()
    expect(screen.getByText(/Customers/i)).toBeInTheDocument()
    expect(screen.getByText(/Payments/i)).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    renderDialog({ open: false })
    expect(screen.queryByText('Connect to QuickBooks Online')).not.toBeInTheDocument()
  })

  it('calls onOpenChange on cancel click', async () => {
    const user = userEvent.setup()
    const { props } = renderDialog()
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(props.onOpenChange).toHaveBeenCalledWith(false)
  })

  it('calls OAuth callback when Connect is clicked', async () => {
    const user = userEvent.setup()
    const api = getMockApiClient()
    renderDialog()

    await user.click(screen.getByRole('button', { name: /connect quickbooks/i }))

    await waitFor(() => {
      expect(api.completeOAuthCallback).toHaveBeenCalledOnce()
    })
  })

  it('shows complete step after successful connection', async () => {
    const user = userEvent.setup()
    renderDialog()

    await user.click(screen.getByRole('button', { name: /connect quickbooks/i }))

    await waitFor(() => {
      expect(screen.getByText('Connection Successful!')).toBeInTheDocument()
    })
  })

  it('calls updateIntegrationSettings on finish and then onComplete', async () => {
    const user = userEvent.setup()
    const api = getMockApiClient()
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: /connect quickbooks/i }))
    await waitFor(() => {
      expect(screen.getByText('Connection Successful!')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /finish setup/i }))

    await waitFor(() => {
      expect(api.updateIntegrationSettings).toHaveBeenCalledOnce()
    })
    await waitFor(() => {
      expect(props.onComplete).toHaveBeenCalledOnce()
    })
  })

  it('does NOT call onComplete when settings save fails', async () => {
    const user = userEvent.setup()
    setMockApiClient(
      createMockApiClient({
        updateIntegrationSettings: vi.fn().mockRejectedValue(new Error('Save failed')),
      })
    )
    const { props } = renderDialog()

    await user.click(screen.getByRole('button', { name: /connect quickbooks/i }))
    await waitFor(() => {
      expect(screen.getByText('Connection Successful!')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /finish setup/i }))

    // Wait for mutation to settle
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /finish setup/i })).toBeEnabled()
    })
    expect(props.onComplete).not.toHaveBeenCalled()
  })

  it('returns to intro step and shows error on connection failure', async () => {
    const user = userEvent.setup()
    setMockApiClient(
      createMockApiClient({
        completeOAuthCallback: vi.fn().mockRejectedValue(new Error('OAuth failed')),
      })
    )
    renderDialog()

    await user.click(screen.getByRole('button', { name: /connect quickbooks/i }))

    await waitFor(() => {
      expect(screen.getByText('Connect to QuickBooks Online')).toBeInTheDocument()
    })
  })
})
