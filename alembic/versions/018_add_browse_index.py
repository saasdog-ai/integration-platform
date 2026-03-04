"""Add browse index on integration_state for records browser query.

Revision ID: 018
Revises: 017
Create Date: 2026-03-04

The records browser query sorts by updated_at DESC for a given
(client_id, integration_id). Without this index, PostgreSQL must do a
full partition scan + sort on every page load. This index enables an
index-ordered scan: seek to (client_id, integration_id) then walk in
updated_at DESC order, applying entity_type/sync_status/do_not_sync
as post-index predicates.
"""

from alembic import op


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX ix_integration_state_browse
        ON integration_state (client_id, integration_id, updated_at DESC)
    """)


def downgrade() -> None:
    op.drop_index("ix_integration_state_browse", table_name="integration_state")
