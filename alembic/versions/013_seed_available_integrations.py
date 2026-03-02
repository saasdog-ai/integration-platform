"""Seed available integrations data.

Revision ID: 013
Revises: 012
Create Date: 2026-02-10
"""
from alembic import op

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Insert QuickBooks Online
    op.execute("""
        INSERT INTO available_integrations (id, name, type, description, connection_config, supported_entities, is_active, created_at, updated_at)
        VALUES (
            '11111111-1111-1111-1111-111111111111',
            'QuickBooks Online',
            'erp',
            'Intuit QuickBooks Online accounting software',
            '{"scopes": ["com.intuit.quickbooks.accounting"], "client_id": "ABS9sRNgUoYnToKsJI4neyFSxJmdz9iAscnFE2wSdrTXNmrN4s", "token_url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", "client_secret": "Xa6C6mpw7Om0sKQ6srnkS7S4CPySL4fop9r69xRP", "authorization_url": "https://appcenter.intuit.com/connect/oauth2"}',
            '["vendor", "customer", "chart_of_accounts", "item", "bill", "invoice", "payment"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
    """)

    # Insert Xero
    op.execute("""
        INSERT INTO available_integrations (id, name, type, description, connection_config, supported_entities, is_active, created_at, updated_at)
        VALUES (
            '22222222-2222-2222-2222-222222222222',
            'Xero',
            'erp',
            'Xero cloud accounting platform',
            '{"scopes": ["accounting.transactions", "accounting.contacts", "accounting.settings"], "token_url": "https://identity.xero.com/connect/token", "authorization_url": "https://login.xero.com/identity/connect/authorize"}',
            '["vendor", "customer", "invoice"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
    """)

    # Insert NetSuite
    op.execute("""
        INSERT INTO available_integrations (id, name, type, description, connection_config, supported_entities, is_active, created_at, updated_at)
        VALUES (
            '33333333-3333-3333-3333-333333333333',
            'NetSuite',
            'erp',
            'Oracle NetSuite ERP system',
            '{"scopes": ["rest_webservices"], "token_url": "https://system.netsuite.com/app/login/oauth2/token.nl", "authorization_url": "https://system.netsuite.com/app/login/oauth2/authorize.nl"}',
            '["vendor", "customer", "invoice", "bill"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
    """)

    # Insert Sage Intacct
    op.execute("""
        INSERT INTO available_integrations (id, name, type, description, connection_config, supported_entities, is_active, created_at, updated_at)
        VALUES (
            '44444444-4444-4444-4444-444444444444',
            'Sage Intacct',
            'erp',
            'Sage Intacct cloud financial management',
            NULL,
            '["vendor", "customer", "invoice"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
    """)

    # Insert HubSpot
    op.execute("""
        INSERT INTO available_integrations (id, name, type, description, connection_config, supported_entities, is_active, created_at, updated_at)
        VALUES (
            '55555555-5555-5555-5555-555555555555',
            'HubSpot',
            'crm',
            'HubSpot CRM and marketing platform',
            '{"scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"], "token_url": "https://api.hubapi.com/oauth/v1/token", "authorization_url": "https://app.hubspot.com/oauth/authorize"}',
            '["contact", "company", "deal"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DELETE FROM available_integrations WHERE id IN ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333', '44444444-4444-4444-4444-444444444444', '55555555-5555-5555-5555-555555555555');")
