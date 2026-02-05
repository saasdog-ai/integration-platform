"""Rename oauth_config column to connection_config on available_integrations.

Revision ID: 011
Revises: 010
Create Date: 2026-02-05

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename oauth_config -> connection_config. JSONB data is unchanged."""
    op.alter_column(
        "available_integrations",
        "oauth_config",
        new_column_name="connection_config",
    )


def downgrade() -> None:
    """Rename connection_config -> oauth_config."""
    op.alter_column(
        "available_integrations",
        "connection_config",
        new_column_name="oauth_config",
    )
