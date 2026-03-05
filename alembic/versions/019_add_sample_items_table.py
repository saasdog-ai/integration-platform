"""Add sample_items table for synced item entities.

Revision ID: 019
Revises: 018
Create Date: 2026-03-05

Creates sample_items table to hold local copies of synced items
(products/services) from external integrations like Xero and QBO.
No external_id column — consistent with migration 016 which dropped
it from all sample tables; ID mapping lives in integration_state.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sample_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("purchase_description", sa.Text),
        sa.Column("sale_description", sa.Text),
        sa.Column("purchase_unit_price", sa.Numeric(15, 2)),
        sa.Column("sale_unit_price", sa.Numeric(15, 2)),
        sa.Column("item_type", sa.String(50)),
        sa.Column("is_sold", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_purchased", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sample_items_client_id", "sample_items", ["client_id"])
    op.create_index("ix_sample_items_client_code", "sample_items", ["client_id", "code"])


def downgrade() -> None:
    op.drop_table("sample_items")
