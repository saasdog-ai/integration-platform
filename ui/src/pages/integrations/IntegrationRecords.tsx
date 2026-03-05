import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useApiClient } from '@/hooks/useApiClient'
import { useToast } from '@/contexts/ToastContext'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { RecordSyncStatusBadge } from '@/components/StatusBadge'
import { formatDate } from '@/lib/utils'
import { DEFAULT_PAGE_SIZE } from '@/lib/constants'
import type { SyncRecord, RecordSyncStatus } from '@/types'

// ─── Filter Bar ──────────────────────────────────────────────────

interface Filters {
  entity_type?: string
  sync_status?: RecordSyncStatus
  do_not_sync?: boolean
}

function RecordsFilterBar({
  filters,
  onFiltersChange,
  entityTypes,
}: {
  filters: Filters
  onFiltersChange: (filters: Filters) => void
  entityTypes: string[]
}) {
  return (
    <div className="flex gap-2 flex-wrap">
      <div>
        <label htmlFor="records-entity-filter" className="sr-only">
          Filter by entity type
        </label>
        <select
          id="records-entity-filter"
          className="text-sm border rounded px-2 py-1"
          value={filters.entity_type || ''}
          onChange={(e) =>
            onFiltersChange({ ...filters, entity_type: e.target.value || undefined })
          }
        >
          <option value="">All Entity Types</option>
          {entityTypes.map((et) => (
            <option key={et} value={et}>
              {et}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="records-status-filter" className="sr-only">
          Filter by status
        </label>
        <select
          id="records-status-filter"
          className="text-sm border rounded px-2 py-1"
          value={filters.sync_status || ''}
          onChange={(e) =>
            onFiltersChange({
              ...filters,
              sync_status: (e.target.value as RecordSyncStatus) || undefined,
            })
          }
        >
          <option value="">All Statuses</option>
          <option value="synced">Synced</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
          <option value="conflict">Conflict</option>
        </select>
      </div>
      <div>
        <label htmlFor="records-dns-filter" className="sr-only">
          Filter by do-not-sync
        </label>
        <select
          id="records-dns-filter"
          className="text-sm border rounded px-2 py-1"
          value={filters.do_not_sync === undefined ? '' : String(filters.do_not_sync)}
          onChange={(e) =>
            onFiltersChange({
              ...filters,
              do_not_sync: e.target.value === '' ? undefined : e.target.value === 'true',
            })
          }
        >
          <option value="">All Records</option>
          <option value="true">Excluded Only</option>
          <option value="false">Active Only</option>
        </select>
      </div>
    </div>
  )
}

// ─── Error Details Panel ─────────────────────────────────────────

function ErrorDetailsPanel({
  record,
  onClose,
}: {
  record: SyncRecord
  onClose: () => void
}) {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
      <div className="space-y-2">
        <div className="flex justify-between items-start">
          <div>
            <p className="font-medium text-red-700">
              Error: {record.error_code}
            </p>
            <p className="text-sm text-red-600">{record.error_message}</p>
          </div>
          <button
            className="text-red-500 hover:text-red-700"
            onClick={onClose}
            aria-label="Close error details"
          >
            ✕
          </button>
        </div>
        {record.error_details && (
          <pre className="mt-2 p-3 bg-white rounded text-xs overflow-auto border">
            {JSON.stringify(record.error_details, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

// ─── Records Table ───────────────────────────────────────────────

function RecordsTable({
  records,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  expandedError,
  onToggleError,
  page,
  totalPages,
  total,
  onPageChange,
}: {
  records: SyncRecord[]
  selectedIds: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  expandedError: string | null
  onToggleError: (id: string | null) => void
  page: number
  totalPages: number
  total: number
  onPageChange: (page: number) => void
}) {
  const allSelected = records.length > 0 && records.every((r) => selectedIds.has(r.id))
  const expandedRecord = useMemo(
    () => (expandedError ? records.find((r) => r.id === expandedError) : null),
    [expandedError, records]
  )

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th scope="col" className="py-2 px-3 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleSelectAll}
                  aria-label="Select all records on this page"
                />
              </th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Entity Type</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Internal ID</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">External ID</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Status</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Direction</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Last Synced</th>
              <th scope="col" className="text-left py-2 px-3 font-medium">Error</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr
                key={record.id}
                className={`border-b hover:bg-muted/50 ${record.do_not_sync ? 'opacity-50' : ''}`}
              >
                <td className="py-2 px-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(record.id)}
                    onChange={() => onToggleSelect(record.id)}
                    aria-label={`Select record ${record.internal_record_id || record.id}`}
                  />
                </td>
                <td className="py-2 px-3">
                  <Badge variant="outline" className="capitalize">
                    {record.entity_type}
                  </Badge>
                </td>
                <td className="py-2 px-3 font-mono text-xs">
                  {record.internal_record_id || '-'}
                </td>
                <td className="py-2 px-3 font-mono text-xs">
                  {record.external_record_id || '-'}
                </td>
                <td className="py-2 px-3">
                  <RecordSyncStatusBadge
                    status={record.sync_status}
                    forceSyncedAt={record.force_synced_at}
                    doNotSync={record.do_not_sync}
                  />
                </td>
                <td className="py-2 px-3 capitalize">
                  {record.sync_direction || '-'}
                </td>
                <td className="py-2 px-3 text-muted-foreground">
                  {formatDate(record.updated_at)}
                </td>
                <td className="py-2 px-3">
                  {record.error_code ? (
                    <button
                      className="text-red-600 hover:underline text-left"
                      onClick={() =>
                        onToggleError(expandedError === record.id ? null : record.id)
                      }
                      aria-expanded={expandedError === record.id}
                    >
                      {record.error_code}
                      {expandedError === record.id ? ' ▼' : ' ▶'}
                    </button>
                  ) : (
                    '-'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {expandedRecord && (
        <ErrorDetailsPanel
          record={expandedRecord}
          onClose={() => onToggleError(null)}
        />
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            Page {page} of {totalPages} ({total} records)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page === 1}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Action Bar ──────────────────────────────────────────────────

function ActionBar({
  selectedCount,
  hasFailedOrConflict,
  hasDoNotSync,
  hasActive,
  onForceSync,
  onDoNotSyncEnable,
  onDoNotSyncDisable,
  isPending,
}: {
  selectedCount: number
  hasFailedOrConflict: boolean
  hasDoNotSync: boolean
  hasActive: boolean
  onForceSync: () => void
  onDoNotSyncEnable: () => void
  onDoNotSyncDisable: () => void
  isPending: boolean
}) {
  if (selectedCount === 0) return null

  return (
    <div className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
      <span className="text-sm font-medium text-blue-800">
        {selectedCount} selected
      </span>
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={onForceSync}
          disabled={!hasFailedOrConflict || isPending}
        >
          {isPending ? <Spinner size="sm" className="mr-1" /> : null}
          Force Sync
        </Button>
        {hasActive && (
          <Button
            size="sm"
            variant="outline"
            onClick={onDoNotSyncEnable}
            disabled={isPending}
          >
            Exclude from Sync
          </Button>
        )}
        {hasDoNotSync && (
          <Button
            size="sm"
            variant="outline"
            onClick={onDoNotSyncDisable}
            disabled={isPending}
          >
            Re-enable Sync
          </Button>
        )}
      </div>
    </div>
  )
}

// ─── Confirm Dialog ──────────────────────────────────────────────

function ConfirmDialog({
  title,
  message,
  onConfirm,
  onCancel,
  isPending,
}: {
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-lg p-6 max-w-sm w-full mx-4">
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-sm text-muted-foreground mb-4">{message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={onConfirm} disabled={isPending}>
            {isPending ? <Spinner size="sm" className="mr-1" /> : null}
            Confirm
          </Button>
        </div>
      </div>
    </div>
  )
}

// ─── Embeddable tab content ──────────────────────────────────────

export function IntegrationRecordsTab({ integrationId }: { integrationId: string }) {
  const api = useApiClient()
  const toast = useToast()
  const queryClient = useQueryClient()

  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<Filters>({})
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [expandedError, setExpandedError] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState<
    null | 'force-sync' | 'do-not-sync-on' | 'do-not-sync-off'
  >(null)

  // Fetch available integration (for entity types)
  const { data: availableIntegration } = useQuery({
    queryKey: ['available-integration', integrationId],
    queryFn: () => api.getAvailableIntegration(integrationId),
    enabled: !!integrationId,
  })

  // Fetch records
  const { data: recordsData, isLoading } = useQuery({
    queryKey: ['integration-records', integrationId, page, filters],
    queryFn: () =>
      api.getIntegrationRecords(integrationId, {
        page,
        page_size: DEFAULT_PAGE_SIZE,
        ...filters,
      }),
    enabled: !!integrationId,
  })

  const entityTypes = useMemo(
    () => availableIntegration?.supported_entities || [],
    [availableIntegration]
  )

  // Force sync mutation
  const forceSyncMutation = useMutation({
    mutationFn: () =>
      api.forceSyncRecords(integrationId, { state_ids: [...selectedIds] }),
    onSuccess: (result) => {
      toast.success(
        'Force sync complete',
        `${result.records_updated} records updated${result.records_skipped > 0 ? `, ${result.records_skipped} skipped` : ''}`
      )
      setSelectedIds(new Set())
      setShowConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['integration-records', integrationId] })
    },
    onError: (error: Error) => {
      toast.error('Force sync failed', error.message)
      setShowConfirm(null)
    },
  })

  // Do not sync mutation
  const doNotSyncMutation = useMutation({
    mutationFn: (doNotSync: boolean) =>
      api.setDoNotSync(integrationId, { state_ids: [...selectedIds], do_not_sync: doNotSync }),
    onSuccess: (result) => {
      toast.success(
        'Records updated',
        `${result.records_updated} records updated${result.records_skipped > 0 ? `, ${result.records_skipped} skipped` : ''}`
      )
      setSelectedIds(new Set())
      setShowConfirm(null)
      queryClient.invalidateQueries({ queryKey: ['integration-records', integrationId] })
    },
    onError: (error: Error) => {
      toast.error('Update failed', error.message)
      setShowConfirm(null)
    },
  })

  const records = recordsData?.records || []

  // Selection helpers
  const selectedRecords = useMemo(
    () => records.filter((r) => selectedIds.has(r.id)),
    [records, selectedIds]
  )
  const hasFailedOrConflict = selectedRecords.some(
    (r) => r.sync_status === 'failed' || r.sync_status === 'conflict'
  )
  const hasDoNotSync = selectedRecords.some((r) => r.do_not_sync)
  const hasActive = selectedRecords.some((r) => !r.do_not_sync)

  function handleFiltersChange(newFilters: Filters) {
    setFilters(newFilters)
    setPage(1)
    setSelectedIds(new Set())
  }

  function handlePageChange(newPage: number) {
    setPage(newPage)
    setSelectedIds(new Set())
    setExpandedError(null)
  }

  function handleToggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function handleToggleSelectAll() {
    if (records.every((r) => selectedIds.has(r.id))) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(records.map((r) => r.id)))
    }
  }

  function handleConfirm() {
    if (showConfirm === 'force-sync') {
      forceSyncMutation.mutate()
    } else if (showConfirm === 'do-not-sync-on') {
      doNotSyncMutation.mutate(true)
    } else if (showConfirm === 'do-not-sync-off') {
      doNotSyncMutation.mutate(false)
    }
  }

  const isPending = forceSyncMutation.isPending || doNotSyncMutation.isPending

  const confirmMessages: Record<string, { title: string; message: string }> = {
    'force-sync': {
      title: 'Force Sync Records',
      message: `Force sync ${selectedIds.size} record${selectedIds.size !== 1 ? 's' : ''}? This will clear errors and mark them for re-sync.`,
    },
    'do-not-sync-on': {
      title: 'Exclude from Sync',
      message: `Exclude ${selectedIds.size} record${selectedIds.size !== 1 ? 's' : ''} from syncing? They will be skipped in future sync jobs.`,
    },
    'do-not-sync-off': {
      title: 'Re-enable Sync',
      message: `Re-enable syncing for ${selectedIds.size} record${selectedIds.size !== 1 ? 's' : ''}? They will be included in future sync jobs.`,
    },
  }

  return (
    <div className="space-y-6">
      {/* Filters + Action Bar */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Records</CardTitle>
              <CardDescription>
                Browse all sync records for this integration
                {recordsData && ` (${recordsData.total} total)`}
              </CardDescription>
            </div>
            <RecordsFilterBar
              filters={filters}
              onFiltersChange={handleFiltersChange}
              entityTypes={entityTypes}
            />
          </div>
        </CardHeader>
        <CardContent>
          <ActionBar
            selectedCount={selectedIds.size}
            hasFailedOrConflict={hasFailedOrConflict}
            hasDoNotSync={hasDoNotSync}
            hasActive={hasActive}
            onForceSync={() => setShowConfirm('force-sync')}
            onDoNotSyncEnable={() => setShowConfirm('do-not-sync-on')}
            onDoNotSyncDisable={() => setShowConfirm('do-not-sync-off')}
            isPending={isPending}
          />

          {isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : records.length > 0 ? (
            <div className={selectedIds.size > 0 ? 'mt-4' : ''}>
              <RecordsTable
                records={records}
                selectedIds={selectedIds}
                onToggleSelect={handleToggleSelect}
                onToggleSelectAll={handleToggleSelectAll}
                expandedError={expandedError}
                onToggleError={setExpandedError}
                page={recordsData!.page}
                totalPages={recordsData!.total_pages}
                total={recordsData!.total}
                onPageChange={handlePageChange}
              />
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              No records found
            </div>
          )}
        </CardContent>
      </Card>

      {/* Confirm Dialog */}
      {showConfirm && (
        <ConfirmDialog
          title={confirmMessages[showConfirm].title}
          message={confirmMessages[showConfirm].message}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(null)}
          isPending={isPending}
        />
      )}
    </div>
  )
}

// ─── Standalone page wrapper ─────────────────────────────────────

export function IntegrationRecords() {
  const { integrationId } = useParams<{ integrationId: string }>()
  const navigate = useNavigate()

  if (!integrationId) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate('..')}>
          ← Back
        </Button>
        <h1 className="text-2xl font-bold">Integration Records</h1>
      </div>
      <IntegrationRecordsTab integrationId={integrationId} />
    </div>
  )
}
