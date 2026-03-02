"""Drop external_id from sample tables — use integration_state for ID mapping.

Revision ID: 016
Revises: 015
Create Date: 2026-03-02

The external_id column on sample_vendors, sample_bills, sample_invoices,
and sample_chart_of_accounts stored the ERP record ID (e.g., QBO vendor ID).
This is architecturally wrong for multi-integration scenarios: a client
connected to both QBO and Xero would have two different external IDs for
the same vendor, but the column can only hold one.

The integration_state table already stores the correct per-integration
mapping: (client_id, integration_id, entity_type, internal_record_id,
external_record_id). All lookups now use integration_state instead.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- sample_vendors --
    op.drop_constraint("uq_vendor_client_external_id", "sample_vendors", type_="unique")
    op.drop_index("ix_vendor_external_id", table_name="sample_vendors")
    op.drop_column("sample_vendors", "external_id")

    # -- sample_bills --
    op.drop_constraint("uq_bill_client_external_id", "sample_bills", type_="unique")
    op.drop_index("ix_bill_external_id", table_name="sample_bills")
    op.drop_column("sample_bills", "external_id")

    # -- sample_invoices --
    op.drop_constraint("uq_invoice_client_external_id", "sample_invoices", type_="unique")
    op.drop_index("ix_invoice_external_id", table_name="sample_invoices")
    op.drop_column("sample_invoices", "external_id")

    # -- sample_chart_of_accounts --
    op.drop_constraint("uq_coa_client_external_id", "sample_chart_of_accounts", type_="unique")
    op.drop_column("sample_chart_of_accounts", "external_id")


def downgrade() -> None:
    import sqlalchemy as sa

    # -- sample_chart_of_accounts --
    op.add_column("sample_chart_of_accounts", sa.Column("external_id", sa.String(255)))
    op.create_unique_constraint(
        "uq_coa_client_external_id", "sample_chart_of_accounts", ["client_id", "external_id"]
    )

    # -- sample_invoices --
    op.add_column("sample_invoices", sa.Column("external_id", sa.String(255)))
    op.create_index("ix_invoice_external_id", "sample_invoices", ["client_id", "external_id"])
    op.create_unique_constraint(
        "uq_invoice_client_external_id", "sample_invoices", ["client_id", "external_id"]
    )

    # -- sample_bills --
    op.add_column("sample_bills", sa.Column("external_id", sa.String(255)))
    op.create_index("ix_bill_external_id", "sample_bills", ["client_id", "external_id"])
    op.create_unique_constraint(
        "uq_bill_client_external_id", "sample_bills", ["client_id", "external_id"]
    )

    # -- sample_vendors --
    op.add_column("sample_vendors", sa.Column("external_id", sa.String(255)))
    op.create_index("ix_vendor_external_id", "sample_vendors", ["client_id", "external_id"])
    op.create_unique_constraint(
        "uq_vendor_client_external_id", "sample_vendors", ["client_id", "external_id"]
    )
