"""Add job_params column to sync_jobs table.

Revision ID: 002_add_job_params
Revises: 001_initial_schema
Create Date: 2026-01-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add job_params JSONB column to sync_jobs table."""
    op.add_column(
        "sync_jobs",
        sa.Column("job_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove job_params column from sync_jobs table."""
    op.drop_column("sync_jobs", "job_params")
