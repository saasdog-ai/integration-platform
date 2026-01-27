"""Domain layer - entities, enums, and interfaces."""

from app.domain.entities import (
    AvailableIntegration,
    BaseEntity,
    EntitySyncStatus,
    ExternalRecord,
    IntegrationStateRecord,
    OAuthConfig,
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
    IntegrationAdapterInterface,
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    MessageQueueInterface,
    SyncJobRepositoryInterface,
)

__all__ = [
    # Entities
    "AvailableIntegration",
    "BaseEntity",
    "EntitySyncStatus",
    "ExternalRecord",
    "IntegrationStateRecord",
    "OAuthConfig",
    "OAuthTokens",
    "QueueMessage",
    "SyncJob",
    "SyncJobMessage",
    "SyncRule",
    "SystemIntegrationSettings",
    "UserIntegration",
    "UserIntegrationSettings",
    # Enums
    "IntegrationStatus",
    "RecordSyncStatus",
    "SyncDirection",
    "SyncJobStatus",
    "SyncJobTrigger",
    "SyncJobType",
    # Interfaces
    "AdapterFactoryInterface",
    "EncryptionServiceInterface",
    "IntegrationAdapterInterface",
    "IntegrationRepositoryInterface",
    "IntegrationStateRepositoryInterface",
    "MessageQueueInterface",
    "SyncJobRepositoryInterface",
]
