"""Equalize version vectors for synced records.

Revision ID: 010
Revises: 009
Create Date: 2026-02-02

Sets internal_version_id, external_version_id, and last_sync_version_id
to GREATEST(internal_version_id, external_version_id) for all records
with sync_status = 'synced'. This fixes diverged version vectors caused
by earlier bugs in inbound/outbound sync that failed to equalize all
three fields after a successful sync.

Records with other statuses (pending, failed, conflict) are left
untouched — their vectors reflect real divergence.
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE integration_state
        SET
            internal_version_id = GREATEST(internal_version_id, external_version_id),
            external_version_id = GREATEST(internal_version_id, external_version_id),
            last_sync_version_id = GREATEST(internal_version_id, external_version_id)
        WHERE sync_status = 'synced'
        """
    )


def downgrade() -> None:
    # Data migration — not reversible, but harmless.
    # Vectors will diverge naturally again on next sync if bugs recur.
    pass
