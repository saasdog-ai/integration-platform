"""System-level enums (NOT business entity types - those are stored in DB)."""

from enum import StrEnum


class IntegrationStatus(StrEnum):
    """Status of a user's integration connection."""

    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    REVOKED = "revoked"


class SyncJobStatus(StrEnum):
    """Status of a sync job execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecordSyncStatus(StrEnum):
    """Sync status of an individual record."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    CONFLICT = "conflict"


class SyncDirection(StrEnum):
    """Direction of data sync."""

    INBOUND = "inbound"  # External -> Internal
    OUTBOUND = "outbound"  # Internal -> External
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(StrEnum):
    """Which system's data takes precedence when both have changes."""

    OUR_SYSTEM = "our_system"  # Our system overwrites external
    EXTERNAL = "external"  # External system overwrites ours


class SyncJobTrigger(StrEnum):
    """What triggered the sync job."""

    USER = "user"
    SCHEDULER = "scheduler"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class SyncJobType(StrEnum):
    """Type of sync job."""

    FULL_SYNC = "full_sync"
    INCREMENTAL = "incremental"
    ENTITY_SYNC = "entity_sync"
