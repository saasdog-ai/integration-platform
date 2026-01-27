"""System-level enums (NOT business entity types - those are stored in DB)."""

from enum import Enum


class IntegrationStatus(str, Enum):
    """Status of a user's integration connection."""

    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    REVOKED = "revoked"


class SyncJobStatus(str, Enum):
    """Status of a sync job execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RecordSyncStatus(str, Enum):
    """Sync status of an individual record."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    CONFLICT = "conflict"


class SyncDirection(str, Enum):
    """Direction of data sync."""

    INBOUND = "inbound"  # External -> Internal
    OUTBOUND = "outbound"  # Internal -> External
    BIDIRECTIONAL = "bidirectional"


class ConflictResolution(str, Enum):
    """Which system's data takes precedence when both have changes."""

    OUR_SYSTEM = "our_system"  # Our system overwrites external
    EXTERNAL = "external"  # External system overwrites ours


class SyncJobTrigger(str, Enum):
    """What triggered the sync job."""

    USER = "user"
    SCHEDULER = "scheduler"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class SyncJobType(str, Enum):
    """Type of sync job."""

    FULL_SYNC = "full_sync"
    INCREMENTAL = "incremental"
    ENTITY_SYNC = "entity_sync"
