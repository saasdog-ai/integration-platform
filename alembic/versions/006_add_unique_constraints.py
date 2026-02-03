"""Add unique constraints to integration_state and make internal_record_id nullable.

Revision ID: 006
Revises: 005
Create Date: 2025-01-28

This migration:
1. Makes internal_record_id nullable (for inbound records not yet written internally)
2. Replaces ix_integration_state_lookup with a partial unique index on internal_record_id
3. Replaces ix_integration_state_external with a partial unique index including entity_type

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Make internal_record_id nullable
    op.alter_column(
        "integration_state",
        "internal_record_id",
        existing_type=sa.String(255),
        nullable=True,
    )

    # 2. Drop old non-unique lookup index, create partial unique index for outbound dedup
    op.drop_index("ix_integration_state_lookup", table_name="integration_state")
    op.create_index(
        "uq_integration_state_internal",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "internal_record_id"],
        unique=True,
        postgresql_where=sa.text("internal_record_id IS NOT NULL"),
    )

    # 3. Drop old external index (missing entity_type), create partial unique index for inbound dedup
    op.drop_index("ix_integration_state_external", table_name="integration_state")
    op.create_index(
        "uq_integration_state_external",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "external_record_id"],
        unique=True,
        postgresql_where=sa.text("external_record_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Reverse: drop unique indexes, recreate original non-unique indexes, make column NOT NULL

    # 3. Drop partial unique external index, recreate original (without entity_type)
    op.drop_index("uq_integration_state_external", table_name="integration_state")
    op.create_index(
        "ix_integration_state_external",
        "integration_state",
        ["client_id", "integration_id", "external_record_id"],
        postgresql_where=sa.text("external_record_id IS NOT NULL"),
    )

    # 2. Drop partial unique internal index, recreate original non-unique lookup
    op.drop_index("uq_integration_state_internal", table_name="integration_state")
    op.create_index(
        "ix_integration_state_lookup",
        "integration_state",
        ["client_id", "integration_id", "entity_type", "internal_record_id"],
    )

    # 1. Make internal_record_id NOT NULL again
    # NOTE: This will fail if any NULL values exist. Ensure data is backfilled first.
    op.alter_column(
        "integration_state",
        "internal_record_id",
        existing_type=sa.String(255),
        nullable=False,
    )
