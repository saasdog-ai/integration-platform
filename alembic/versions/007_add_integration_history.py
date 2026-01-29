"""Add integration_history table for per-record sync snapshots.

Revision ID: 007
Revises: 006
Create Date: 2025-01-29

This migration creates the integration_history table, an append-only log
of per-record sync snapshots. Records remain associated with the correct
job even after later jobs overwrite integration_state.last_job_id.

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("state_record_id", UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("internal_record_id", sa.String(255), nullable=True),
        sa.Column("external_record_id", sa.String(255), nullable=True),
        sa.Column("sync_status", sa.String(20), nullable=False),
        sa.Column("sync_direction", sa.String(10), nullable=True),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("client_id", "id"),
    )

    # Index for Record Details queries (GET /sync-jobs/{job_id}/records)
    op.create_index(
        "ix_integration_history_job_entity",
        "integration_history",
        ["client_id", "job_id", "entity_type"],
    )

    # Index for retention cleanup
    op.create_index(
        "ix_integration_history_created",
        "integration_history",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_history_created", table_name="integration_history")
    op.drop_index("ix_integration_history_job_entity", table_name="integration_history")
    op.drop_table("integration_history")
