"""Update Xero integration: supported entities and scopes.

Revision ID: 014
Revises: 013
Create Date: 2026-02-25
"""
from alembic import op

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE available_integrations
        SET supported_entities = '["vendor", "customer", "chart_of_accounts", "item", "bill", "invoice", "payment"]'::jsonb,
            connection_config = '{
                "authorization_url": "https://login.xero.com/identity/connect/authorize",
                "token_url": "https://identity.xero.com/connect/token",
                "scopes": [
                    "openid", "profile", "email",
                    "accounting.contacts.read", "accounting.contacts",
                    "accounting.transactions.read", "accounting.transactions",
                    "accounting.settings.read", "accounting.settings",
                    "offline_access"
                ]
            }'::jsonb,
            updated_at = NOW()
        WHERE id = '22222222-2222-2222-2222-222222222222'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE available_integrations
        SET supported_entities = '["bill", "invoice", "contact", "account", "payment"]'::jsonb,
            connection_config = '{
                "authorization_url": "https://login.xero.com/identity/connect/authorize",
                "token_url": "https://identity.xero.com/connect/token",
                "scopes": ["accounting.transactions", "accounting.contacts", "accounting.settings"]
            }'::jsonb,
            updated_at = NOW()
        WHERE id = '22222222-2222-2222-2222-222222222222'
    """)
