"""Domain layer - entities, enums, and interfaces."""

from app.domain.entities import (
    AvailableIntegration,
    BaseEntity,
    ConnectionConfig,
    EntitySyncStatus,
    ExternalRecord,
    IntegrationStateRecord,
    OAuthTokens,
    QueueMessage,
    SyncJob,
    SyncJobMessage,
    SyncRule,
    SystemIntegrationSettings,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    AuthType,
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.domain.interfaces import (
    AdapterFactoryInterface,
    EncryptionServiceInterface,
    FeatureFlagServiceInterface,
    IntegrationAdapterInterface,
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    MessageQueueInterface,
    SyncJobRepositoryInterface,
    SyncSchedulerInterface,
)

__all__ = [
    # Entities
    "AvailableIntegration",
    "BaseEntity",
    "ConnectionConfig",
    "EntitySyncStatus",
    "ExternalRecord",
    "IntegrationStateRecord",
    "OAuthTokens",
    "QueueMessage",
    "SyncJob",
    "SyncJobMessage",
    "SyncRule",
    "SystemIntegrationSettings",
    "UserIntegration",
    "UserIntegrationSettings",
    # Enums
    "AuthType",
    "IntegrationStatus",
    "RecordSyncStatus",
    "SyncDirection",
    "SyncJobStatus",
    "SyncJobTrigger",
    "SyncJobType",
    # Interfaces
    "AdapterFactoryInterface",
    "EncryptionServiceInterface",
    "FeatureFlagServiceInterface",
    "IntegrationAdapterInterface",
    "IntegrationRepositoryInterface",
    "IntegrationStateRepositoryInterface",
    "MessageQueueInterface",
    "SyncJobRepositoryInterface",
    "SyncSchedulerInterface",
]
