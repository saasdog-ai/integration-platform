import { Badge } from '@/components/ui/badge'
import type { IntegrationStatus, SyncJobStatus, RecordSyncStatus } from '@/types'

interface IntegrationStatusBadgeProps {
  status: IntegrationStatus
}

export function IntegrationStatusBadge({ status }: IntegrationStatusBadgeProps) {
  const variants: Record<IntegrationStatus, { variant: 'success' | 'warning' | 'error' | 'pending', label: string }> = {
    connected: { variant: 'success', label: 'Connected' },
    pending: { variant: 'pending', label: 'Pending' },
    error: { variant: 'error', label: 'Error' },
    revoked: { variant: 'warning', label: 'Disconnected' },
  }

  const { variant, label } = variants[status] || { variant: 'pending', label: status }

  return <Badge variant={variant}>{label}</Badge>
}

interface SyncJobStatusBadgeProps {
  status: SyncJobStatus
}

export function SyncJobStatusBadge({ status }: SyncJobStatusBadgeProps) {
  const variants: Record<SyncJobStatus, { variant: 'success' | 'warning' | 'error' | 'pending' | 'info', label: string }> = {
    pending: { variant: 'pending', label: 'Pending' },
    running: { variant: 'info', label: 'Running' },
    succeeded: { variant: 'success', label: 'Succeeded' },
    failed: { variant: 'error', label: 'Failed' },
    cancelled: { variant: 'warning', label: 'Cancelled' },
  }

  const { variant, label } = variants[status] || { variant: 'pending', label: status }

  return <Badge variant={variant}>{label}</Badge>
}

interface RecordSyncStatusBadgeProps {
  status: RecordSyncStatus
  forceSyncedAt?: string | null
  doNotSync?: boolean
}

export function RecordSyncStatusBadge({ status, forceSyncedAt, doNotSync }: RecordSyncStatusBadgeProps) {
  if (doNotSync) return <Badge variant="secondary">Excluded</Badge>

  const variants: Record<RecordSyncStatus, { variant: 'success' | 'warning' | 'error' | 'pending', label: string }> = {
    synced: { variant: 'success', label: 'Synced' },
    failed: { variant: 'error', label: 'Failed' },
    pending: { variant: 'pending', label: 'Pending' },
    conflict: { variant: 'warning', label: 'Conflict' },
  }

  const { variant, label } = variants[status] || { variant: 'pending', label: status }

  return (
    <span className="flex items-center gap-1">
      <Badge variant={variant}>{label}</Badge>
      {forceSyncedAt && status === 'synced' && (
        <span className="text-xs text-muted-foreground">(forced)</span>
      )}
    </span>
  )
}
