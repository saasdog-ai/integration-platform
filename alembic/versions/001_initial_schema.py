"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-01-26

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create available_integrations table
    op.create_table(
        "available_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("oauth_config", postgresql.JSONB(), nullable=True),
        sa.Column(
            "supported_entities",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create user_integrations table
    op.create_table(
        "user_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("credentials_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("credentials_key_id", sa.String(255), nullable=True),
        sa.Column("external_account_id", sa.String(255), nullable=True),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["available_integrations.id"],
        ),
    )
    op.create_index(
        "ix_user_integrations_client_id", "user_integrations", ["client_id"]
    )
    op.create_index(
        "uq_user_integrations_client_integration",
        "user_integrations",
        ["client_id", "integration_id"],
        unique=True,
    )

    # Create user_integration_settings table
    op.create_table(
        "user_integration_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["available_integrations.id"],
        ),
    )
    op.create_index(
        "uq_user_integration_settings_client_integration",
        "user_integration_settings",
        ["client_id", "integration_id"],
        unique=True,
    )

    # Create system_integration_settings table
    op.create_table(
        "system_integration_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["available_integrations.id"],
        ),
        sa.UniqueConstraint("integration_id"),
    )

    # Create sync_jobs table
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entities_processed", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=False, default="user"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["available_integrations.id"],
        ),
    )
    op.create_index("ix_sync_jobs_client_id", "sync_jobs", ["client_id"])
    op.create_index(
        "ix_sync_jobs_status",
        "sync_jobs",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    # Create entity_sync_status table
    op.create_table(
        "entity_sync_status",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column(
            "last_successful_sync_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_sync_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("records_synced_count", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["available_integrations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["last_sync_job_id"],
            ["sync_jobs.id"],
        ),
    )
    op.create_index(
        "uq_entity_sync_status",
        "entity_sync_status",
        ["client_id", "integration_id", "entity_type"],
        unique=True,
    )

    # Create integration_state table (designed for partitioning)
    # NOTE: In production, this should be partitioned by client_id
    # For simplicity, we create a regular table here
    # Partitioning can be set up via pg_partman or manual partition management
    op.create_table(
        "integration_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("internal_record_id", sa.String(255), nullable=False),
        sa.Column("external_record_id", sa.String(255), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False, default="pending"),
        sa.Column("sync_direction", sa.String(10), nullable=True),
        sa.Column("internal_version_id", sa.Integer(), nullable=False, default=1),
        sa.Column("external_version_id", sa.Integer(), nullable=False, default=0),
        sa.Column("last_sync_version_id", sa.Integer(), nullable=False, default=0),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Composite primary key for efficient partitioning
        sa.PrimaryKeyConstraint("client_id", "id"),
    )

    # Indexes for integration_state
    op.create_index(
        "ix_integration_state_lookup",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "internal_record_id"],
    )
    op.create_index(
        "ix_integration_state_pending",
        "integration_state",
        ["client_id", "sync_status"],
        postgresql_where=sa.text("sync_status IN ('pending', 'failed')"),
    )
    op.create_index(
        "ix_integration_state_external",
        "integration_state",
        ["client_id", "integration_id", "external_record_id"],
        postgresql_where=sa.text("external_record_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("integration_state")
    op.drop_table("entity_sync_status")
    op.drop_table("sync_jobs")
    op.drop_table("system_integration_settings")
    op.drop_table("user_integration_settings")
    op.drop_table("user_integrations")
    op.drop_table("available_integrations")
