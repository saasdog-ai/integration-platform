"""Add audit_log table and sync override columns on integration_state.

Revision ID: 017
Revises: 016
Create Date: 2026-03-03

Adds:
1. audit_log table — tracks user/admin actions (force-sync, do-not-sync,
   settings changes, connect/disconnect). Separate from integration_history
   which is reserved for sync operations only.
2. do_not_sync (bool) column on integration_state — excludes records from
   syncing in both directions when true.
3. force_synced_at (datetime) column on integration_state — records when
   a user last force-synced the record.
4. Updates the partial index on integration_state to exclude do_not_sync
   records from the pending-records query.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 1. Create audit_log table --
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("target_record_ids", JSONB(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("performed_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("client_id", "id"),
    )

    op.create_index(
        "ix_audit_log_client_action",
        "audit_log",
        ["client_id", "action"],
    )

    op.create_index(
        "ix_audit_log_created",
        "audit_log",
        ["created_at"],
    )

    # -- 2. Add override columns to integration_state --
    op.add_column(
        "integration_state",
        sa.Column("do_not_sync", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "integration_state",
        sa.Column("force_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- 3. Update partial index to exclude do_not_sync records --
    op.drop_index("ix_integration_state_part_pending", table_name="integration_state")
    op.create_index(
        "ix_integration_state_part_pending",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "sync_status"],
        postgresql_where="sync_status IN ('pending', 'failed') AND do_not_sync = false",
    )


def downgrade() -> None:
    # -- Restore original partial index --
    op.drop_index("ix_integration_state_part_pending", table_name="integration_state")
    op.create_index(
        "ix_integration_state_part_pending",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "sync_status"],
        postgresql_where="sync_status IN ('pending', 'failed')",
    )

    # -- Drop override columns --
    op.drop_column("integration_state", "force_synced_at")
    op.drop_column("integration_state", "do_not_sync")

    # -- Drop audit_log --
    op.drop_index("ix_audit_log_created", table_name="audit_log")
    op.drop_index("ix_audit_log_client_action", table_name="audit_log")
    op.drop_table("audit_log")
