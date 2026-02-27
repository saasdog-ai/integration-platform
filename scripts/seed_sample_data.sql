-- Seed Available Integrations
INSERT INTO available_integrations (id, name, type, description, supported_entities, connection_config, is_active, created_at, updated_at)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'QuickBooks Online', 'erp', 'Intuit QuickBooks Online accounting software',
   '["bill", "invoice", "vendor", "customer", "chart_of_accounts", "payment"]'::jsonb,
   '{"authorization_url": "https://appcenter.intuit.com/connect/oauth2", "token_url": "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", "scopes": ["com.intuit.quickbooks.accounting"]}'::jsonb,
   true, NOW(), NOW()),

  ('22222222-2222-2222-2222-222222222222', 'Xero', 'erp', 'Xero cloud accounting platform',
   '["vendor", "customer", "chart_of_accounts", "item", "bill", "invoice", "payment"]'::jsonb,
   '{"authorization_url": "https://login.xero.com/identity/connect/authorize", "token_url": "https://identity.xero.com/connect/token", "scopes": ["openid", "profile", "email", "accounting.contacts.read", "accounting.contacts", "accounting.transactions.read", "accounting.transactions", "accounting.settings.read", "accounting.settings", "offline_access"]}'::jsonb,
   true, NOW(), NOW()),

  ('33333333-3333-3333-3333-333333333333', 'NetSuite', 'erp', 'Oracle NetSuite ERP system',
   '["bill", "invoice", "vendor", "customer", "item", "journal_entry"]'::jsonb,
   '{"authorization_url": "https://system.netsuite.com/app/login/oauth2/authorize.nl", "token_url": "https://system.netsuite.com/app/login/oauth2/token.nl", "scopes": ["rest_webservices"]}'::jsonb,
   true, NOW(), NOW()),

  ('44444444-4444-4444-4444-444444444444', 'Sage Intacct', 'erp', 'Sage Intacct cloud financial management',
   '["bill", "invoice", "vendor", "customer", "gl_account", "journal"]'::jsonb,
   NULL,
   true, NOW(), NOW()),

  ('55555555-5555-5555-5555-555555555555', 'HubSpot', 'crm', 'HubSpot CRM and marketing platform',
   '["contact", "company", "deal", "ticket"]'::jsonb,
   '{"authorization_url": "https://app.hubspot.com/oauth/authorize", "token_url": "https://api.hubapi.com/oauth/v1/token", "scopes": ["crm.objects.contacts.read", "crm.objects.contacts.write"]}'::jsonb,
   true, NOW(), NOW());

-- NOTE: No per-user seed data (user_integrations, user_integration_settings, sync_jobs,
-- entity_sync_status) — users connect their own integrations via the UI.
-- Client IDs in saas-host-app: aaa00000-...-001 (Alice), bbb00000-...-002 (Bob).

-- Seed system default settings for QuickBooks Online
INSERT INTO system_integration_settings (id, integration_id, settings, created_at, updated_at)
VALUES
  ('dd000000-0000-0000-0000-000000000001',
   '11111111-1111-1111-1111-111111111111',
   '{"sync_rules": [{"entity_type": "chart_of_accounts", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "vendor", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "customer", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "item", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "bill", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "invoice", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "payment", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}], "sync_frequency": "0 */6 * * *", "auto_sync_enabled": false}'::jsonb,
   NOW(), NOW());

-- Seed system default settings for Xero
INSERT INTO system_integration_settings (id, integration_id, settings, created_at, updated_at)
VALUES
  ('dd000000-0000-0000-0000-000000000002',
   '22222222-2222-2222-2222-222222222222',
   '{"sync_rules": [{"entity_type": "chart_of_accounts", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "vendor", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "customer", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "item", "direction": "inbound", "enabled": true, "master_if_conflict": "external", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "bill", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "invoice", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}, {"entity_type": "payment", "direction": "outbound", "enabled": true, "master_if_conflict": "our_system", "change_source": "polling", "sync_trigger": "deferred"}], "sync_frequency": "0 */6 * * *", "auto_sync_enabled": false}'::jsonb,
   NOW(), NOW());

