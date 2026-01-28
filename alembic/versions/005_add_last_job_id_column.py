"""Add last_job_id column and performance indexes.

Revision ID: 005
Revises: 004_add_disconnected_at_column
Create Date: 2024-01-28

This migration adds:
1. last_job_id column to integration_state for tracking record-level job association
2. Performance indexes for sync_jobs table to optimize common query patterns

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # integration_state table changes
    # =========================================================================

    # Add last_job_id column to track which job last modified each record
    op.add_column(
        "integration_state",
        sa.Column("last_job_id", UUID(as_uuid=True), nullable=True),
    )

    # Add index for efficient queries by job_id (for GET /sync-jobs/{id}/records)
    op.create_index(
        "ix_integration_state_job",
        "integration_state",
        ["client_id", "last_job_id"],
        postgresql_where=sa.text("last_job_id IS NOT NULL"),
    )

    # =========================================================================
    # sync_jobs table indexes for query performance
    # =========================================================================

    # For checking running/pending jobs per client/integration (create_job_if_no_running)
    op.create_index(
        "ix_sync_jobs_running_check",
        "sync_jobs",
        ["client_id", "integration_id", "status"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    # For paginated job listing with ORDER BY created_at DESC
    op.create_index(
        "ix_sync_jobs_client_created",
        "sync_jobs",
        ["client_id", "created_at"],
    )

    # For stuck jobs query (status = 'running' AND started_at < X)
    op.create_index(
        "ix_sync_jobs_stuck",
        "sync_jobs",
        ["status", "started_at"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    # Drop sync_jobs indexes
    op.drop_index("ix_sync_jobs_stuck", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_client_created", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_running_check", table_name="sync_jobs")

    # Drop integration_state changes
    op.drop_index("ix_integration_state_job", table_name="integration_state")
    op.drop_column("integration_state", "last_job_id")
