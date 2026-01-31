import { useState, useEffect, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { ToggleSwitch } from '@/components/ui/toggle-switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import type {
  UserIntegrationSettings,
  SyncRule,
  ConflictResolution,
  EntitySyncStatus,
} from '@/types'

// ─── Constants ──────────────────────────────────────────────────

const FREQUENCY_PRESETS = [
  { label: 'Every hour', value: '1h' },
  { label: 'Every 6 hours', value: '6h' },
  { label: 'Every 12 hours', value: '12h' },
  { label: 'Daily', value: '24h' },
  { label: 'Custom', value: 'custom' },
] as const

const DIRECTION_OPTIONS = [
  { label: 'Inbound', value: 'inbound' },
  { label: 'Outbound', value: 'outbound' },
  { label: 'Bidirectional', value: 'bidirectional' },
] as const

const CONFLICT_OPTIONS: { label: string; value: ConflictResolution }[] = [
  { label: 'External wins', value: 'external' },
  { label: 'Our system wins', value: 'our_system' },
]

const PRESET_TO_CRON: Record<string, string> = {
  '1h': '0 * * * *',
  '6h': '0 */6 * * *',
  '12h': '0 */12 * * *',
  '24h': '0 0 * * *',
}

const CRON_TO_PRESET: Record<string, string> = Object.fromEntries(
  Object.entries(PRESET_TO_CRON).map(([k, v]) => [v, k])
)

function deriveFrequencyState(syncFrequency: string | null) {
  if (!syncFrequency) return { mode: '24h', custom: '' }
  const preset = CRON_TO_PRESET[syncFrequency]
  if (preset) return { mode: preset, custom: '' }
  return { mode: 'custom', custom: syncFrequency }
}

function resolveSyncFrequency(mode: string, custom: string): string | null {
  if (mode === 'custom') return custom || null
  return PRESET_TO_CRON[mode] ?? null
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

// ─── System Default Settings Section ────────────────────────────

function SystemDefaultSettings() {
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string>('')

  // Fetch all available integrations
  const { data: availableIntegrations, isLoading: loadingAvailable } = useQuery({
    queryKey: ['available-integrations'],
    queryFn: () => api.getAvailableIntegrations(),
  })

  // Auto-select first integration
  useEffect(() => {
    if (availableIntegrations?.length && !selectedIntegrationId) {
      setSelectedIntegrationId(availableIntegrations[0].id)
    }
  }, [availableIntegrations, selectedIntegrationId])

  const selectedIntegration = availableIntegrations?.find(
    (i) => i.id === selectedIntegrationId
  )

  // Fetch system defaults for selected integration
  const { data: defaults, isLoading: loadingDefaults } = useQuery({
    queryKey: ['system-defaults', selectedIntegrationId],
    queryFn: () => api.getSystemDefaultSettings(selectedIntegrationId),
    enabled: !!selectedIntegrationId,
  })

  // Local editable state
  const [localSettings, setLocalSettings] = useState<UserIntegrationSettings | null>(null)
  const [frequencyMode, setFrequencyMode] = useState('24h')
  const [customFrequency, setCustomFrequency] = useState('')

  // Seed local state from fetched defaults
  useEffect(() => {
    if (defaults) {
      setLocalSettings(structuredClone(defaults))
      const freq = deriveFrequencyState(defaults.sync_frequency)
      setFrequencyMode(freq.mode)
      setCustomFrequency(freq.custom)
    } else if (selectedIntegration) {
      // No defaults yet - create empty form with all supported entities
      setLocalSettings({
        sync_rules: selectedIntegration.supported_entities.map((e) => ({
          entity_type: e,
          direction: 'inbound' as const,
          enabled: false,
        })),
        sync_frequency: null,
        auto_sync_enabled: false,
      })
      setFrequencyMode('24h')
      setCustomFrequency('')
    }
  }, [defaults, selectedIntegration])

  // Dirty tracking
  const isDirty = defaults && localSettings
    ? JSON.stringify(defaults) !== JSON.stringify(localSettings)
    : localSettings !== null && defaults === undefined

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (updated: UserIntegrationSettings) =>
      api.updateSystemDefaultSettings(selectedIntegrationId, updated),
    onSuccess: () => {
      toast.success('System defaults saved')
      queryClient.invalidateQueries({ queryKey: ['system-defaults', selectedIntegrationId] })
    },
    onError: (error: Error) => {
      toast.error('Failed to save defaults', error.message)
    },
  })

  // Helpers
  const updateAutoSync = useCallback((enabled: boolean) => {
    setLocalSettings((prev) => (prev ? { ...prev, auto_sync_enabled: enabled } : prev))
  }, [])

  const updateFrequency = useCallback((preset: string) => {
    setFrequencyMode(preset)
    if (preset !== 'custom') {
      setLocalSettings((prev) => (prev ? { ...prev, sync_frequency: preset } : prev))
      setCustomFrequency('')
    }
  }, [])

  const updateCustomFrequency = useCallback((value: string) => {
    setCustomFrequency(value)
    setLocalSettings((prev) => (prev ? { ...prev, sync_frequency: value } : prev))
  }, [])

  const updateRule = useCallback((entityType: string, patch: Partial<SyncRule>) => {
    setLocalSettings((prev) => {
      if (!prev) return prev
      const exists = prev.sync_rules.some((r) => r.entity_type === entityType)
      if (exists) {
        return {
          ...prev,
          sync_rules: prev.sync_rules.map((r) =>
            r.entity_type === entityType ? { ...r, ...patch } : r
          ),
        }
      }
      return {
        ...prev,
        sync_rules: [
          ...prev.sync_rules,
          { entity_type: entityType, direction: 'inbound' as const, enabled: false, ...patch },
        ],
      }
    })
  }, [])

  // Ensure every supported entity has a rule row
  const displayRules = useMemo((): SyncRule[] => {
    if (!localSettings) return []
    const entities = selectedIntegration?.supported_entities ?? []
    const existing = new Map(localSettings.sync_rules.map((r) => [r.entity_type, r]))
    return entities.map(
      (e) =>
        existing.get(e) ?? {
          entity_type: e,
          direction: 'inbound' as const,
          enabled: false,
        }
    )
  }, [localSettings, selectedIntegration])

  const handleSave = () => {
    if (!localSettings) return
    const cronFrequency = resolveSyncFrequency(frequencyMode, customFrequency)
    saveMutation.mutate({ ...localSettings, sync_rules: displayRules, sync_frequency: cronFrequency })
  }

  const handleDiscard = () => {
    if (defaults) {
      setLocalSettings(structuredClone(defaults))
      const freq = deriveFrequencyState(defaults.sync_frequency)
      setFrequencyMode(freq.mode)
      setCustomFrequency(freq.custom)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Default Settings</CardTitle>
        <CardDescription>
          Configure default sync settings per integration type. These apply to all new users.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Integration selector */}
        <div>
          <label htmlFor="defaults-integration" className="font-medium block mb-1">
            Integration
          </label>
          {loadingAvailable ? (
            <Spinner size="sm" />
          ) : (
            <select
              id="defaults-integration"
              value={selectedIntegrationId}
              onChange={(e) => setSelectedIntegrationId(e.target.value)}
              className="flex h-10 w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {availableIntegrations?.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {loadingDefaults ? (
          <div className="flex items-center justify-center py-8">
            <Spinner size="lg" />
          </div>
        ) : localSettings ? (
          <>
            {/* Auto-sync toggle */}
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Auto-sync default</p>
                <p className="text-sm text-muted-foreground">
                  Enable auto-sync by default for new connections
                </p>
              </div>
              <ToggleSwitch
                checked={localSettings.auto_sync_enabled}
                onChange={updateAutoSync}
                label="Toggle default auto-sync"
              />
            </div>

            {/* Frequency selector */}
            <div className="space-y-2">
              <label htmlFor="defaults-frequency" className="font-medium block">
                Default Sync Frequency
              </label>
              <select
                id="defaults-frequency"
                value={frequencyMode}
                onChange={(e) => updateFrequency(e.target.value)}
                className="flex h-10 w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {FREQUENCY_PRESETS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
              {frequencyMode === 'custom' && (
                <Input
                  placeholder="e.g. 0 */2 * * *"
                  value={customFrequency}
                  onChange={(e) => updateCustomFrequency(e.target.value)}
                  className="max-w-xs mt-2"
                  aria-label="Custom sync frequency"
                />
              )}
            </div>

            {/* Sync rules table */}
            <div>
              <h3 className="font-medium mb-2">Default Sync Rules</h3>
              {displayRules.length === 0 ? (
                <p className="text-muted-foreground">
                  No supported entities for this integration.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left">
                        <th scope="col" className="pb-2 pr-4 font-medium">Entity</th>
                        <th scope="col" className="pb-2 pr-4 font-medium">Enabled</th>
                        <th scope="col" className="pb-2 pr-4 font-medium">Direction</th>
                        <th scope="col" className="pb-2 font-medium">Conflict Resolution</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayRules.map((rule) => (
                        <tr key={rule.entity_type} className="border-b last:border-0">
                          <td className="py-3 pr-4 font-medium capitalize">
                            {rule.entity_type}
                          </td>
                          <td className="py-3 pr-4">
                            <ToggleSwitch
                              checked={rule.enabled}
                              onChange={(enabled) => updateRule(rule.entity_type, { enabled })}
                              label={`Toggle ${rule.entity_type} sync`}
                            />
                          </td>
                          <td className="py-3 pr-4">
                            <label className="sr-only" htmlFor={`defaults-direction-${rule.entity_type}`}>
                              {rule.entity_type} sync direction
                            </label>
                            <select
                              id={`defaults-direction-${rule.entity_type}`}
                              value={rule.direction}
                              onChange={(e) =>
                                updateRule(rule.entity_type, {
                                  direction: e.target.value as SyncRule['direction'],
                                })
                              }
                              className="flex h-9 rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {DIRECTION_OPTIONS.map((d) => (
                                <option key={d.value} value={d.value}>
                                  {d.label}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="py-3">
                            <label className="sr-only" htmlFor={`defaults-conflict-${rule.entity_type}`}>
                              {rule.entity_type} conflict resolution
                            </label>
                            <select
                              id={`defaults-conflict-${rule.entity_type}`}
                              value={rule.master_if_conflict ?? 'external'}
                              onChange={(e) =>
                                updateRule(rule.entity_type, {
                                  master_if_conflict: e.target.value as ConflictResolution,
                                })
                              }
                              className="flex h-9 rounded-md border border-input bg-background px-2 py-1 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {CONFLICT_OPTIONS.map((c) => (
                                <option key={c.value} value={c.value}>
                                  {c.label}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 justify-end">
              <Button
                variant="outline"
                onClick={handleDiscard}
                disabled={!isDirty || saveMutation.isPending}
              >
                Discard
              </Button>
              <Button
                onClick={handleSave}
                disabled={!isDirty || saveMutation.isPending}
              >
                {saveMutation.isPending ? <Spinner size="sm" className="mr-2" /> : null}
                Save Defaults
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

// ─── Last Sync Time Management Section ──────────────────────────

function LastSyncTimeManagement() {
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [selectedClientId, setSelectedClientId] = useState<string>('')
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string>('')
  const [resetTarget, setResetTarget] = useState<EntitySyncStatus | null>(null)
  const [resetInbound, setResetInbound] = useState(true)
  const [resetSync, setResetSync] = useState(true)

  // Fetch all integrations across all clients
  const { data: allIntegrations, isLoading: loadingIntegrations } = useQuery({
    queryKey: ['admin-all-integrations'],
    queryFn: () => api.adminGetAllIntegrations(),
  })

  // Derive unique client IDs
  const clientIds = useMemo(() => {
    if (!allIntegrations) return []
    const ids = new Set(allIntegrations.map((i) => i.client_id))
    return Array.from(ids)
  }, [allIntegrations])

  // Auto-select first client
  useEffect(() => {
    if (clientIds.length && !selectedClientId) {
      setSelectedClientId(clientIds[0])
    }
  }, [clientIds, selectedClientId])

  // Filter integrations for selected client
  const clientIntegrations = useMemo(() => {
    if (!allIntegrations || !selectedClientId) return []
    return allIntegrations.filter((i) => i.client_id === selectedClientId)
  }, [allIntegrations, selectedClientId])

  // Auto-select first integration when client changes
  useEffect(() => {
    if (clientIntegrations.length) {
      setSelectedIntegrationId(clientIntegrations[0].integration_id)
    } else {
      setSelectedIntegrationId('')
    }
  }, [clientIntegrations])

  // Fetch entity sync statuses for selected client+integration
  const { data: syncStatuses, isLoading: loadingStatuses } = useQuery({
    queryKey: ['admin-entity-sync-statuses', selectedClientId, selectedIntegrationId],
    queryFn: () => api.adminListEntitySyncStatuses(selectedClientId, selectedIntegrationId),
    enabled: !!selectedClientId && !!selectedIntegrationId,
  })

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: ({ entityType }: { entityType: string }) =>
      api.adminResetLastSyncTime(selectedClientId, selectedIntegrationId, entityType, {
        reset_inbound_sync_time: resetInbound,
        reset_last_sync_time: resetSync,
      }),
    onSuccess: (data) => {
      toast.success('Sync time reset', data.message)
      queryClient.invalidateQueries({
        queryKey: ['admin-entity-sync-statuses', selectedClientId, selectedIntegrationId],
      })
      setResetTarget(null)
    },
    onError: (error: Error) => {
      toast.error('Failed to reset sync time', error.message)
    },
  })

  const openResetDialog = (status: EntitySyncStatus) => {
    setResetTarget(status)
    setResetInbound(true)
    setResetSync(true)
  }

  const handleReset = () => {
    if (!resetTarget) return
    resetMutation.mutate({ entityType: resetTarget.entity_type })
  }

  const selectedIntegrationName = clientIntegrations.find(
    (i) => i.integration_id === selectedIntegrationId
  )?.integration_name

  const handleClientChange = (clientId: string) => {
    setSelectedClientId(clientId)
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Last Sync Time Management</CardTitle>
          <CardDescription>
            View entity sync statuses and reset last sync times for any client to trigger a full re-sync.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Client selector */}
          <div>
            <label htmlFor="cursor-client" className="font-medium block mb-1">
              Client
            </label>
            {loadingIntegrations ? (
              <Spinner size="sm" />
            ) : !clientIds.length ? (
              <p className="text-muted-foreground text-sm">No connected integrations found.</p>
            ) : (
              <select
                id="cursor-client"
                value={selectedClientId}
                onChange={(e) => handleClientChange(e.target.value)}
                className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring font-mono"
              >
                {clientIds.map((cid) => (
                  <option key={cid} value={cid}>
                    {cid}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Integration selector */}
          {selectedClientId && clientIntegrations.length > 0 && (
            <div>
              <label htmlFor="cursor-integration" className="font-medium block mb-1">
                Integration
              </label>
              <select
                id="cursor-integration"
                value={selectedIntegrationId}
                onChange={(e) => setSelectedIntegrationId(e.target.value)}
                className="flex h-10 w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {clientIntegrations.map((i) => (
                  <option key={i.integration_id} value={i.integration_id}>
                    {i.integration_name ?? i.integration_id}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Sync statuses table */}
          {loadingStatuses ? (
            <div className="flex items-center justify-center py-8">
              <Spinner size="lg" />
            </div>
          ) : !syncStatuses?.statuses?.length ? (
            selectedClientId && selectedIntegrationId ? (
              <p className="text-muted-foreground text-sm">
                No sync status records found for this integration.
              </p>
            ) : null
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th scope="col" className="pb-2 pr-4 font-medium">Entity Type</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Last Sync</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Last Inbound</th>
                    <th scope="col" className="pb-2 pr-4 font-medium">Records Synced</th>
                    <th scope="col" className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {syncStatuses.statuses.map((status) => (
                    <tr key={status.entity_type} className="border-b last:border-0">
                      <td className="py-3 pr-4 font-medium capitalize">
                        {status.entity_type}
                      </td>
                      <td className="py-3 pr-4 text-muted-foreground">
                        {formatDateTime(status.last_successful_sync_at)}
                      </td>
                      <td className="py-3 pr-4 text-muted-foreground">
                        {formatDateTime(status.last_inbound_sync_at)}
                      </td>
                      <td className="py-3 pr-4">
                        {status.records_synced_count}
                      </td>
                      <td className="py-3">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openResetDialog(status)}
                        >
                          Reset
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Reset confirmation dialog */}
      <Dialog open={!!resetTarget} onOpenChange={(open) => !open && setResetTarget(null)}>
        <DialogContent onClose={() => setResetTarget(null)}>
          <DialogHeader>
            <DialogTitle>Reset Last Sync Time</DialogTitle>
            <DialogDescription>
              Reset the last sync time for <strong className="capitalize">{resetTarget?.entity_type}</strong>
              {selectedIntegrationName ? ` on ${selectedIntegrationName}` : ''}.
              This will cause a full re-sync on the next run.
            </DialogDescription>
          </DialogHeader>
          <div className="px-6 space-y-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={resetInbound}
                onChange={(e) => setResetInbound(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <span className="text-sm">Reset inbound sync time</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={resetSync}
                onChange={(e) => setResetSync(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <span className="text-sm">Reset last sync time</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResetTarget(null)}>
              Cancel
            </Button>
            <Button
              onClick={handleReset}
              disabled={(!resetInbound && !resetSync) || resetMutation.isPending}
            >
              {resetMutation.isPending ? <Spinner size="sm" className="mr-2" /> : null}
              Confirm Reset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ─── Main Admin Page ────────────────────────────────────────────

export function AdminPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Integration Admin</h1>
      <SystemDefaultSettings />
      <LastSyncTimeManagement />
    </div>
  )
}
