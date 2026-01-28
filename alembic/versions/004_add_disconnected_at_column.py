"""Add disconnected_at column to user_integrations table.

Revision ID: 004_add_disconnected_at
Revises: 002_add_job_params
Create Date: 2026-01-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add disconnected_at timestamp column to user_integrations table."""
    op.add_column(
        "user_integrations",
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove disconnected_at column from user_integrations table."""
    op.drop_column("user_integrations", "disconnected_at")
