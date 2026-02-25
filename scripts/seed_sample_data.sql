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

-- Seed a sample client's user integration (connected to QuickBooks)
INSERT INTO user_integrations (id, client_id, integration_id, status, external_account_id, last_connected_at, created_at, updated_at)
VALUES
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'connected', 'realm-123456', NOW(), NOW(), NOW());

-- Seed user integration settings
INSERT INTO user_integration_settings (id, client_id, integration_id, settings, created_at, updated_at)
VALUES
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   '{"sync_rules": [{"entity_type": "bill", "direction": "inbound", "enabled": true}, {"entity_type": "vendor", "direction": "inbound", "enabled": true}, {"entity_type": "invoice", "direction": "outbound", "enabled": true}], "sync_frequency": "0 */6 * * *", "auto_sync_enabled": true}'::jsonb,
   NOW(), NOW());

-- Seed system default settings for QuickBooks
INSERT INTO system_integration_settings (id, integration_id, settings, created_at, updated_at)
VALUES
  ('dddddddd-dddd-dddd-dddd-dddddddddddd',
   '11111111-1111-1111-1111-111111111111',
   '{"sync_rules": [{"entity_type": "chart_of_accounts", "direction": "inbound", "enabled": true}, {"entity_type": "vendor", "direction": "inbound", "enabled": true}, {"entity_type": "customer", "direction": "inbound", "enabled": true}, {"entity_type": "bill", "direction": "bidirectional", "enabled": false}, {"entity_type": "invoice", "direction": "bidirectional", "enabled": false}], "sync_frequency": "0 0 * * *", "auto_sync_enabled": false}'::jsonb,
   NOW(), NOW());

-- Seed some sync jobs
INSERT INTO sync_jobs (id, client_id, integration_id, job_type, status, triggered_by, started_at, completed_at, entities_processed, created_at, updated_at)
VALUES
  ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'full_sync', 'succeeded', 'user',
   NOW() - INTERVAL '2 hours', NOW() - INTERVAL '1 hour 45 minutes',
   '{"bill": {"records_fetched": 150, "records_created": 150}, "vendor": {"records_fetched": 45, "records_created": 45}}'::jsonb,
   NOW() - INTERVAL '2 hours', NOW() - INTERVAL '1 hour 45 minutes'),

  ('ffffffff-ffff-ffff-ffff-ffffffffffff',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'incremental', 'succeeded', 'scheduler',
   NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '25 minutes',
   '{"bill": {"records_fetched": 5, "records_created": 3, "records_updated": 2}}'::jsonb,
   NOW() - INTERVAL '30 minutes', NOW() - INTERVAL '25 minutes'),

  ('11111111-aaaa-bbbb-cccc-dddddddddddd',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'incremental', 'running', 'scheduler',
   NOW() - INTERVAL '5 minutes', NULL, NULL,
   NOW() - INTERVAL '5 minutes', NOW());

-- Seed entity sync status
INSERT INTO entity_sync_status (id, client_id, integration_id, entity_type, last_successful_sync_at, last_sync_job_id, records_synced_count, created_at, updated_at)
VALUES
  ('77777777-7777-7777-7777-777777777777',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'bill', NOW() - INTERVAL '25 minutes', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 155,
   NOW() - INTERVAL '2 hours', NOW() - INTERVAL '25 minutes'),

  ('88888888-8888-8888-8888-888888888888',
   'cccccccc-cccc-cccc-cccc-cccccccccccc',
   '11111111-1111-1111-1111-111111111111',
   'vendor', NOW() - INTERVAL '1 hour 45 minutes', 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 45,
   NOW() - INTERVAL '2 hours', NOW() - INTERVAL '1 hour 45 minutes');
