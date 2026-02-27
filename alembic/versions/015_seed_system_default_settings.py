"""Seed system default settings for QBO and Xero.

Revision ID: 015
Revises: 014
Create Date: 2026-02-27
"""
from alembic import op

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

# Shared sync rules for ERP integrations (QBO and Xero support the same entities)
# - Reference data (chart_of_accounts, vendor, customer, item): inbound, ERP is master
# - Transactional data (bill, invoice): outbound, our system is master
# - Payment: outbound, our system is master (saas-host-app is the payments app)
_SETTINGS_JSON = """{
    "sync_rules": [
        {"entity_type": "chart_of_accounts", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "vendor", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "customer", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "item", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "bill", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "invoice", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"},
        {"entity_type": "payment", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}
    ],
    "sync_frequency": "0 */6 * * *",
    "auto_sync_enabled": false
}"""


def upgrade() -> None:
    # QuickBooks Online defaults
    op.execute(f"""
        INSERT INTO system_integration_settings (id, integration_id, settings, created_at, updated_at)
        VALUES (
            'dd000000-0000-0000-0000-000000000001',
            '11111111-1111-1111-1111-111111111111',
            '{_SETTINGS_JSON}'::jsonb,
            NOW(),
            NOW()
        )
        ON CONFLICT (integration_id) DO NOTHING;
    """)

    # Xero defaults
    op.execute(f"""
        INSERT INTO system_integration_settings (id, integration_id, settings, created_at, updated_at)
        VALUES (
            'dd000000-0000-0000-0000-000000000002',
            '22222222-2222-2222-2222-222222222222',
            '{_SETTINGS_JSON}'::jsonb,
            NOW(),
            NOW()
        )
        ON CONFLICT (integration_id) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM system_integration_settings
        WHERE integration_id IN (
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222'
        );
    """)
