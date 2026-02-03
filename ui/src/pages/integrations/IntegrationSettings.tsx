import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { ToggleSwitch } from '@/components/ui/toggle-switch'
import type { UserIntegrationSettings, SyncRule, ConflictResolution } from '@/types'

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
  // Check if it's a known cron that maps to a preset
  const preset = CRON_TO_PRESET[syncFrequency]
  if (preset) return { mode: preset, custom: '' }
  // Otherwise treat as custom cron
  return { mode: 'custom', custom: syncFrequency }
}

function resolveSyncFrequency(mode: string, custom: string): string | null {
  if (mode === 'custom') return custom || null
  return PRESET_TO_CRON[mode] ?? null
}

// ─── Sub-components ──────────────────────────────────────────────

interface FrequencySelectorProps {
  mode: string
  customValue: string
  onModeChange: (mode: string) => void
  onCustomChange: (value: string) => void
}

function FrequencySelector({ mode, customValue, onModeChange, onCustomChange }: FrequencySelectorProps) {
  return (
    <div className="space-y-2">
      <label htmlFor="sync-frequency" className="font-medium block">
        Sync Frequency
      </label>
      <select
        id="sync-frequency"
        value={mode}
        onChange={(e) => onModeChange(e.target.value)}
        className="flex h-10 w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {FREQUENCY_PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </select>
      {mode === 'custom' && (
        <Input
          placeholder="e.g. 0 */2 * * *"
          value={customValue}
          onChange={(e) => onCustomChange(e.target.value)}
          className="max-w-xs mt-2"
          aria-label="Custom sync frequency"
        />
      )}
    </div>
  )
}

interface SyncRulesTableProps {
  rules: SyncRule[]
  onUpdateRule: (entityType: string, patch: Partial<SyncRule>) => void
}

function SyncRulesTable({ rules, onUpdateRule }: SyncRulesTableProps) {
  if (rules.length === 0) {
    return (
      <p className="text-muted-foreground">
        No supported entities for this integration.
      </p>
    )
  }

  return (
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
          {rules.map((rule) => (
            <tr key={rule.entity_type} className="border-b last:border-0">
              <td className="py-3 pr-4 font-medium capitalize">
                {rule.entity_type}
              </td>
              <td className="py-3 pr-4">
                <ToggleSwitch
                  checked={rule.enabled}
                  onChange={(enabled) => onUpdateRule(rule.entity_type, { enabled })}
                  label={`Toggle ${rule.entity_type} sync`}
                />
              </td>
              <td className="py-3 pr-4">
                <label className="sr-only" htmlFor={`direction-${rule.entity_type}`}>
                  {rule.entity_type} sync direction
                </label>
                <select
                  id={`direction-${rule.entity_type}`}
                  value={rule.direction}
                  onChange={(e) =>
                    onUpdateRule(rule.entity_type, {
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
                <label className="sr-only" htmlFor={`conflict-${rule.entity_type}`}>
                  {rule.entity_type} conflict resolution
                </label>
                <select
                  id={`conflict-${rule.entity_type}`}
                  value={rule.master_if_conflict ?? 'external'}
                  onChange={(e) =>
                    onUpdateRule(rule.entity_type, {
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
  )
}

// ─── Main component ──────────────────────────────────────────────

export function IntegrationSettings() {
  const { integrationId } = useParams<{ integrationId: string }>()
  const navigate = useNavigate()
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  // Remote data
  const { data: settings, isLoading: loadingSettings } = useQuery({
    queryKey: ['integration-settings', integrationId],
    queryFn: () => api.getIntegrationSettings(integrationId!),
    enabled: !!integrationId,
  })

  const { data: availableIntegration, isLoading: loadingAvailable } = useQuery({
    queryKey: ['available-integration', integrationId],
    queryFn: () => api.getAvailableIntegration(integrationId!),
    enabled: !!integrationId,
  })

  // Local editable state
  const [localSettings, setLocalSettings] = useState<UserIntegrationSettings | null>(null)
  const [frequencyMode, setFrequencyMode] = useState('24h')
  const [customFrequency, setCustomFrequency] = useState('')

  // Seed local state from fetched settings
  useEffect(() => {
    if (settings) {
      setLocalSettings(structuredClone(settings))
      const freq = deriveFrequencyState(settings.sync_frequency)
      setFrequencyMode(freq.mode)
      setCustomFrequency(freq.custom)
    }
  }, [settings])

  // Dirty tracking
  const isDirty = settings && localSettings
    ? JSON.stringify(settings) !== JSON.stringify(localSettings)
    : false

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: (updated: UserIntegrationSettings) =>
      api.updateIntegrationSettings(integrationId!, updated),
    onSuccess: () => {
      toast.success('Settings saved')
      queryClient.invalidateQueries({ queryKey: ['integration-settings', integrationId] })
    },
    onError: (error: Error) => {
      toast.error('Failed to save settings', error.message)
    },
  })

  // Helpers to update local state
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
    const entities = availableIntegration?.supported_entities ?? []
    const existing = new Map(localSettings.sync_rules.map((r) => [r.entity_type, r]))
    return entities.map(
      (e) =>
        existing.get(e) ?? {
          entity_type: e,
          direction: 'inbound' as const,
          enabled: false,
        }
    )
  }, [localSettings, availableIntegration])

  const handleSave = () => {
    if (!localSettings) return
    const cronFrequency = resolveSyncFrequency(frequencyMode, customFrequency)
    saveMutation.mutate({ ...localSettings, sync_rules: displayRules, sync_frequency: cronFrequency })
  }

  const handleDiscard = () => {
    if (settings) {
      setLocalSettings(structuredClone(settings))
      const freq = deriveFrequencyState(settings.sync_frequency)
      setFrequencyMode(freq.mode)
      setCustomFrequency(freq.custom)
    }
  }

  const isLoading = loadingSettings || loadingAvailable

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!localSettings) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold mb-2">Settings not found</h2>
        <p className="text-muted-foreground mb-4">
          Could not load settings for this integration.
        </p>
        <Button onClick={() => navigate('..')}>Back</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('..')}>
            ← Back
          </Button>
          <h1 className="text-2xl font-bold">
            {availableIntegration?.name ?? 'Integration'} Settings
          </h1>
        </div>
        <div className="flex gap-2">
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
            Save
          </Button>
        </div>
      </div>

      {/* General Settings */}
      <Card>
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>Auto-sync and frequency settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Auto-sync</p>
              <p className="text-sm text-muted-foreground">
                Automatically sync data on the configured schedule
              </p>
            </div>
            <ToggleSwitch
              checked={localSettings.auto_sync_enabled}
              onChange={updateAutoSync}
              label="Toggle auto-sync"
            />
          </div>
          <FrequencySelector
            mode={frequencyMode}
            customValue={customFrequency}
            onModeChange={updateFrequency}
            onCustomChange={updateCustomFrequency}
          />
        </CardContent>
      </Card>

      {/* Sync Rules */}
      <Card>
        <CardHeader>
          <CardTitle>Sync Rules</CardTitle>
          <CardDescription>
            Configure sync behavior for each entity type
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SyncRulesTable rules={displayRules} onUpdateRule={updateRule} />
        </CardContent>
      </Card>
    </div>
  )
}
