"""Add sample data tables for synced entities.

Revision ID: 008
Revises: 007
Create Date: 2026-01-29

Creates sample_vendors, sample_bills, sample_invoices, and
sample_chart_of_accounts tables in the integration_platform database.
These hold the local copies of synced entity data.

In production, these would be replaced by API calls to the internal
system. The InternalDataRepository abstraction layer makes that swap
transparent to the sync strategy.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Vendors --
    op.create_table(
        "sample_vendors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email_address", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("tax_number", sa.String(50)),
        sa.Column("is_supplier", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_customer", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("currency", sa.String(10)),
        sa.Column("address", JSON),
        sa.Column("phone_numbers", JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_id", sa.String(255)),
    )
    op.create_index("ix_sample_vendors_client_id", "sample_vendors", ["client_id"])
    op.create_index("ix_vendor_external_id", "sample_vendors", ["client_id", "external_id"])
    op.create_unique_constraint("uq_vendor_client_external_id", "sample_vendors", ["client_id", "external_id"])

    # -- Bills --
    op.create_table(
        "sample_bills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("bill_number", sa.String(100)),
        sa.Column("vendor_id", UUID(as_uuid=True), sa.ForeignKey("sample_vendors.id", ondelete="SET NULL")),
        sa.Column("project_id", UUID(as_uuid=True)),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("paid_on_date", sa.DateTime(timezone=True)),
        sa.Column("description", sa.Text),
        sa.Column("currency", sa.String(10)),
        sa.Column("status", sa.String(20)),
        sa.Column("line_items", JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_id", sa.String(255)),
    )
    op.create_index("ix_sample_bills_client_id", "sample_bills", ["client_id"])
    op.create_index("ix_bill_external_id", "sample_bills", ["client_id", "external_id"])
    op.create_unique_constraint("uq_bill_client_external_id", "sample_bills", ["client_id", "external_id"])

    # -- Invoices --
    op.create_table(
        "sample_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(100)),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("sample_vendors.id", ondelete="SET NULL")),
        sa.Column("issue_date", sa.DateTime(timezone=True)),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("paid_on_date", sa.DateTime(timezone=True)),
        sa.Column("memo", sa.Text),
        sa.Column("currency", sa.String(10)),
        sa.Column("exchange_rate", sa.Numeric(10, 4)),
        sa.Column("sub_total", sa.Numeric(15, 2)),
        sa.Column("total_tax_amount", sa.Numeric(15, 2)),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("balance", sa.Numeric(15, 2)),
        sa.Column("status", sa.String(20)),
        sa.Column("line_items", JSON),
        sa.Column("tracking_categories", JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_id", sa.String(255)),
    )
    op.create_index("ix_sample_invoices_client_id", "sample_invoices", ["client_id"])
    op.create_index("ix_invoice_external_id", "sample_invoices", ["client_id", "external_id"])
    op.create_unique_constraint("uq_invoice_client_external_id", "sample_invoices", ["client_id", "external_id"])

    # -- Chart of Accounts --
    op.create_table(
        "sample_chart_of_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_number", sa.String(50)),
        sa.Column("account_type", sa.String(100), nullable=False),
        sa.Column("account_sub_type", sa.String(100)),
        sa.Column("classification", sa.String(50)),
        sa.Column("current_balance", sa.Numeric(15, 2), server_default="0"),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("description", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("parent_account_external_id", sa.String(255)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_coa_client_id", "sample_chart_of_accounts", ["client_id"])
    op.create_unique_constraint("uq_coa_client_external_id", "sample_chart_of_accounts", ["client_id", "external_id"])


def downgrade() -> None:
    op.drop_table("sample_chart_of_accounts")
    op.drop_table("sample_invoices")
    op.drop_table("sample_bills")
    op.drop_table("sample_vendors")
