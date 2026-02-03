"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class TimestampMixin:
    """Mixin for created_at/updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AvailableIntegrationModel(Base, TimestampMixin):
    """Master list of supported integrations."""

    __tablename__ = "available_integrations"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # erp, hris, crm
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    supported_entities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    user_integrations: Mapped[list["UserIntegrationModel"]] = relationship(
        back_populates="integration"
    )
    system_settings: Mapped["SystemIntegrationSettingsModel | None"] = relationship(
        back_populates="integration", uselist=False
    )


class UserIntegrationModel(Base, TimestampMixin):
    """User's connected integrations with encrypted credentials."""

    __tablename__ = "user_integrations"
    __table_args__ = (Index("ix_user_integrations_client_id", "client_id"),)

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("available_integrations.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, connected, error, revoked
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    credentials_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    integration: Mapped["AvailableIntegrationModel"] = relationship(
        back_populates="user_integrations"
    )
    settings: Mapped["UserIntegrationSettingsModel | None"] = relationship(
        back_populates="user_integration",
        uselist=False,
        foreign_keys="[UserIntegrationSettingsModel.client_id, UserIntegrationSettingsModel.integration_id]",
        primaryjoin="and_(UserIntegrationModel.client_id == UserIntegrationSettingsModel.client_id, "
        "UserIntegrationModel.integration_id == UserIntegrationSettingsModel.integration_id)",
    )

    __table_args__ = (
        Index("ix_user_integrations_client_id", "client_id"),
        Index(
            "uq_user_integrations_client_integration",
            "client_id",
            "integration_id",
            unique=True,
        ),
    )


class UserIntegrationSettingsModel(Base, TimestampMixin):
    """User-specific sync settings."""

    __tablename__ = "user_integration_settings"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("available_integrations.id"),
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Relationships
    user_integration: Mapped["UserIntegrationModel | None"] = relationship(
        back_populates="settings",
        foreign_keys="[UserIntegrationSettingsModel.client_id, UserIntegrationSettingsModel.integration_id]",
        primaryjoin="and_(UserIntegrationSettingsModel.client_id == UserIntegrationModel.client_id, "
        "UserIntegrationSettingsModel.integration_id == UserIntegrationModel.integration_id)",
        viewonly=True,
    )

    __table_args__ = (
        Index(
            "uq_user_integration_settings_client_integration",
            "client_id",
            "integration_id",
            unique=True,
        ),
    )


class SystemIntegrationSettingsModel(Base, TimestampMixin):
    """Default settings for each integration."""

    __tablename__ = "system_integration_settings"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    integration_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("available_integrations.id"),
        nullable=False,
        unique=True,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Relationships
    integration: Mapped["AvailableIntegrationModel"] = relationship(
        back_populates="system_settings"
    )


class SyncJobModel(Base, TimestampMixin):
    """Sync job execution history."""

    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_client_id", "client_id"),
        Index(
            "ix_sync_jobs_status",
            "status",
            postgresql_where="status IN ('pending', 'running')",
        ),
        # For checking running/pending jobs per client/integration (create_job_if_no_running)
        Index(
            "ix_sync_jobs_running_check",
            "client_id",
            "integration_id",
            "status",
            postgresql_where="status IN ('pending', 'running')",
        ),
        # For paginated job listing with ORDER BY created_at DESC
        Index(
            "ix_sync_jobs_client_created",
            "client_id",
            "created_at",
        ),
        # For stuck jobs query (status = 'running' AND started_at < X)
        Index(
            "ix_sync_jobs_stuck",
            "status",
            "started_at",
            postgresql_where="status = 'running'",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("available_integrations.id"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # full_sync, incremental, entity_sync
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, running, succeeded, failed, cancelled
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entities_processed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="user"
    )  # user, scheduler, webhook
    job_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Full job request params (entity_types, entity_requests, etc.)

    # Relationships
    integration: Mapped["AvailableIntegrationModel"] = relationship()


class EntitySyncStatusModel(Base, TimestampMixin):
    """Last successful sync time per entity type."""

    __tablename__ = "entity_sync_status"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("available_integrations.id"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Configurable: bill, invoice, etc.
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_inbound_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_job_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_jobs.id"),
        nullable=True,
    )
    records_synced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "uq_entity_sync_status",
            "client_id",
            "integration_id",
            "entity_type",
            unique=True,
        ),
    )


class IntegrationStateModel(Base):
    """
    Record-level sync state.

    NOTE: This table is designed to be partitioned by client_id in production.
    The partition setup is handled in the Alembic migration.
    """

    __tablename__ = "integration_state"
    __table_args__ = (
        Index(
            "uq_integration_state_internal",
            "client_id",
            "integration_id",
            "entity_type",
            "internal_record_id",
            unique=True,
            postgresql_where="internal_record_id IS NOT NULL",
        ),
        Index(
            "ix_integration_state_pending",
            "client_id",
            "sync_status",
            postgresql_where="sync_status IN ('pending', 'failed')",
        ),
        Index(
            "uq_integration_state_external",
            "client_id",
            "integration_id",
            "entity_type",
            "external_record_id",
            unique=True,
            postgresql_where="external_record_id IS NOT NULL",
        ),
        Index(
            "ix_integration_state_job",
            "client_id",
            "last_job_id",
            postgresql_where="last_job_id IS NOT NULL",
        ),
    )

    # Composite primary key for partitioning
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Set composite primary key
    __mapper_args__ = {"primary_key": [client_id, id]}

    integration_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Configurable string, not enum
    internal_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, synced, failed, conflict
    sync_direction: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # inbound, outbound
    internal_version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    external_version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sync_version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_job_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # Links record to the sync job that last modified it
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IntegrationHistoryModel(Base):
    """
    Append-only log of per-record sync snapshots.

    Each row captures the state of a record at the time a specific job processed it.
    This allows records to remain associated with the correct job even after later
    jobs overwrite integration_state.last_job_id.
    """

    __tablename__ = "integration_history"
    __table_args__ = (
        Index(
            "ix_integration_history_job_entity",
            "client_id",
            "job_id",
            "entity_type",
        ),
        Index(
            "ix_integration_history_created",
            "created_at",
        ),
    )

    # Composite primary key (same pattern as integration_state)
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )
    client_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __mapper_args__ = {"primary_key": [client_id, id]}

    state_record_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    integration_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    internal_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), nullable=False)
    sync_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    job_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
