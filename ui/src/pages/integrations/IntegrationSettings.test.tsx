import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Routes, Route } from 'react-router-dom'
import { IntegrationSettings } from './IntegrationSettings'
import {
  renderWithProviders,
  createMockApiClient,
  setMockApiClient,
  getMockApiClient,
} from '@/test/test-utils'

vi.mock('@/hooks/useApiClient')

function renderSettings() {
  return renderWithProviders(
    <Routes>
      <Route path=":integrationId/settings" element={<IntegrationSettings />} />
    </Routes>,
    { initialRoute: '/int1/settings' }
  )
}

describe('IntegrationSettings', () => {
  beforeEach(() => {
    setMockApiClient(createMockApiClient())
  })

  it('renders settings page with integration name', async () => {
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })
  })

  it('displays auto-sync toggle with correct initial state', async () => {
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })
    const toggle = screen.getByRole('switch', { name: /toggle auto-sync/i })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('displays sync frequency from settings', async () => {
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })
    const select = screen.getByLabelText('Sync Frequency') as HTMLSelectElement
    expect(select.value).toBe('6h')
  })

  it('displays sync rules for each supported entity', async () => {
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('invoice')).toBeInTheDocument()
    })
    expect(screen.getByText('customer')).toBeInTheDocument()
    expect(screen.getByText('payment')).toBeInTheDocument()
  })

  it('enables Save/Discard buttons after making a change', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })

    const saveBtn = screen.getByRole('button', { name: /save/i })
    const discardBtn = screen.getByRole('button', { name: /discard/i })
    expect(saveBtn).toBeDisabled()
    expect(discardBtn).toBeDisabled()

    // Toggle auto-sync off
    const toggle = screen.getByRole('switch', { name: /toggle auto-sync/i })
    await user.click(toggle)

    expect(saveBtn).toBeEnabled()
    expect(discardBtn).toBeEnabled()
  })

  it('reverts changes on Discard', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })

    const toggle = screen.getByRole('switch', { name: /toggle auto-sync/i })
    expect(toggle).toHaveAttribute('aria-checked', 'true')

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')

    await user.click(screen.getByRole('button', { name: /discard/i }))
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('calls updateIntegrationSettings on Save', async () => {
    const user = userEvent.setup()
    const api = getMockApiClient()
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })

    // Make a change
    const toggle = screen.getByRole('switch', { name: /toggle auto-sync/i })
    await user.click(toggle)

    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(api.updateIntegrationSettings).toHaveBeenCalledOnce()
    })
    const callArgs = (api.updateIntegrationSettings as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(callArgs[0]).toBe('int1')
    expect(callArgs[1].auto_sync_enabled).toBe(false)
  })

  it('shows custom frequency input when Custom is selected', async () => {
    const user = userEvent.setup()
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('QuickBooks Online Settings')).toBeInTheDocument()
    })

    const select = screen.getByLabelText('Sync Frequency')
    await user.selectOptions(select, 'custom')

    expect(screen.getByPlaceholderText('e.g. 30m, 2h, 3d')).toBeInTheDocument()
  })

  it('shows error state when settings fail to load', async () => {
    setMockApiClient(
      createMockApiClient({
        getIntegrationSettings: vi.fn().mockRejectedValue(new Error('Network error')),
      })
    )
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('Settings not found')).toBeInTheDocument()
    })
  })
})
