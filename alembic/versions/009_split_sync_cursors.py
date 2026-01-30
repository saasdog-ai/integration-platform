"""Split inbound/outbound sync cursors.

Revision ID: 009
Revises: 008
Create Date: 2026-01-29

Adds last_inbound_sync_at column to entity_sync_status so inbound syncs
use the external system's clock (max ExternalRecord.updated_at) while
outbound syncs continue using last_successful_sync_at (our clock).

Backfills existing rows from last_successful_sync_at so pre-migration
cursors are preserved.
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entity_sync_status",
        sa.Column("last_inbound_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from existing cursor so incremental syncs don't re-fetch everything
    op.execute(
        "UPDATE entity_sync_status "
        "SET last_inbound_sync_at = last_successful_sync_at "
        "WHERE last_successful_sync_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("entity_sync_status", "last_inbound_sync_at")
