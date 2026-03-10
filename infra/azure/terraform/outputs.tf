# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# Container App
output "container_app_url" {
  description = "Container App URL"
  value       = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "container_app_name" {
  description = "Container App name"
  value       = azurerm_container_app.app.name
}

# ACR
output "acr_login_server" {
  description = "ACR login server"
  value       = azurerm_container_registry.app.login_server
}

output "acr_name" {
  description = "ACR name"
  value       = azurerm_container_registry.app.name
}

# Queue
output "queue_name" {
  description = "Azure Storage Queue name for sync jobs"
  value       = azurerm_storage_queue.sync_jobs.name
}

output "queue_storage_account" {
  description = "Storage account for queues"
  value       = azurerm_storage_account.queue.name
}

output "dlq_name" {
  description = "Dead letter queue name"
  value       = azurerm_storage_queue.sync_jobs_dlq.name
}

# KMS
output "kms_key_id" {
  description = "Key Vault key ID for credential encryption"
  value       = azurerm_key_vault_key.credentials.id
}

# Secrets
output "database_url_secret_id" {
  description = "Key Vault secret ID for DATABASE_URL"
  value       = azurerm_key_vault_secret.database_url.id
}

output "admin_api_key_secret_id" {
  description = "Key Vault secret ID for admin API key"
  value       = azurerm_key_vault_secret.admin_api_key.id
}

# Resource Group
output "resource_group_name" {
  description = "App resource group name"
  value       = azurerm_resource_group.app.name
}
