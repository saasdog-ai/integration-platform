# -----------------------------------------------------------------------------
# User Assigned Managed Identity
# -----------------------------------------------------------------------------

resource "azurerm_user_assigned_identity" "app" {
  name                = "${local.name_prefix}-identity-${var.environment}"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name

  tags = local.common_tags
}

# Key Vault access policy for the managed identity
resource "azurerm_key_vault_access_policy" "app" {
  key_vault_id = var.shared_key_vault_id
  tenant_id    = azurerm_user_assigned_identity.app.tenant_id
  object_id    = azurerm_user_assigned_identity.app.principal_id

  secret_permissions = [
    "Get", "List",
  ]

  key_permissions = [
    "Get", "List", "Encrypt", "Decrypt", "WrapKey", "UnwrapKey",
  ]
}

# Storage Queue Data Contributor for the managed identity
resource "azurerm_role_assignment" "queue_contributor" {
  scope                = azurerm_storage_account.queue.id
  role_definition_name = "Storage Queue Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# -----------------------------------------------------------------------------
# Key Vault Secrets - Database URL & Admin API Key
# -----------------------------------------------------------------------------

data "azurerm_key_vault_secret" "postgresql_master_password" {
  name         = split("/", var.shared_postgresql_password_secret_id)[4]
  key_vault_id = var.shared_key_vault_id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "${local.short_prefix}-database-url-${var.environment}"
  value        = "postgresql+asyncpg://postgres:${urlencode(data.azurerm_key_vault_secret.postgresql_master_password.value)}@${var.shared_postgresql_fqdn}:5432/${var.db_name}?sslmode=require"
  key_vault_id = var.shared_key_vault_id
}

resource "azurerm_key_vault_secret" "admin_api_key" {
  name         = "${local.short_prefix}-admin-api-key-${var.environment}"
  value        = "CHANGE_ME"
  key_vault_id = var.shared_key_vault_id

  lifecycle {
    ignore_changes = [value]
  }
}

# -----------------------------------------------------------------------------
# Storage Account & Queues (Azure Queue Storage)
# -----------------------------------------------------------------------------

resource "azurerm_storage_account" "queue" {
  # Storage account names: lowercase, no hyphens, max 24 chars
  name                     = substr(replace("${var.company_prefix}intplatq${var.environment}", "-", ""), 0, 24)
  resource_group_name      = azurerm_resource_group.app.name
  location                 = azurerm_resource_group.app.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = local.common_tags
}

resource "azurerm_storage_queue" "sync_jobs" {
  name                 = "${local.short_prefix}-sync-jobs-${var.environment}"
  storage_account_name = azurerm_storage_account.queue.name
}

resource "azurerm_storage_queue" "sync_jobs_dlq" {
  name                 = "${local.short_prefix}-sync-jobs-dlq-${var.environment}"
  storage_account_name = azurerm_storage_account.queue.name
}

# -----------------------------------------------------------------------------
# Key Vault Key (for credential encryption)
# -----------------------------------------------------------------------------

resource "azurerm_key_vault_key" "credentials" {
  name         = "${local.short_prefix}-credentials-key-${var.environment}"
  key_vault_id = var.shared_key_vault_id
  key_type     = "RSA"
  key_size     = 2048

  key_opts = [
    "encrypt",
    "decrypt",
    "wrapKey",
    "unwrapKey",
  ]

  rotation_policy {
    automatic {
      time_before_expiry = "P30D"
    }

    expire_after         = "P90D"
    notify_before_expiry = "P29D"
  }
}

# -----------------------------------------------------------------------------
# Container App
# -----------------------------------------------------------------------------

resource "azurerm_container_app" "app" {
  name                         = "${local.short_prefix}-${var.environment}"
  container_app_environment_id = var.shared_container_apps_environment_id
  resource_group_name          = azurerm_resource_group.app.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server               = azurerm_container_registry.app.login_server
    username             = azurerm_container_registry.app.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.app.admin_password
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "admin-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.admin_api_key.id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = var.container_app_min_replicas
    max_replicas = var.container_app_max_replicas

    container {
      name   = "${var.app_name}-api"
      image  = "${azurerm_container_registry.app.login_server}/${var.app_name}:${var.image_tag}"
      cpu    = var.container_app_cpu
      memory = var.container_app_memory

      # Environment variables matching config.py
      env {
        name  = "APP_ENV"
        value = var.environment == "prod" ? "production" : var.environment == "dev" ? "development" : var.environment
      }
      env {
        name  = "API_PORT"
        value = tostring(var.container_port)
      }
      env {
        name  = "CLOUD_PROVIDER"
        value = "azure"
      }
      env {
        name  = "AZURE_KEYVAULT_URL"
        value = var.shared_key_vault_uri
      }
      env {
        name  = "AZURE_STORAGE_ACCOUNT_NAME"
        value = azurerm_storage_account.queue.name
      }
      env {
        name  = "QUEUE_URL"
        value = azurerm_storage_queue.sync_jobs.name
      }
      env {
        name  = "KMS_KEY_ID"
        value = azurerm_key_vault_key.credentials.id
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name  = "AUTH_ENABLED"
        value = var.environment == "prod" ? "true" : "false"
      }
      env {
        name  = "DATABASE_NAME"
        value = var.db_name
      }

      # Secrets
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name        = "ADMIN_API_KEY"
        secret_name = "admin-api-key"
      }

      startup_probe {
        transport = "HTTP"
        path      = "/health"
        port      = var.container_port

        interval_seconds        = 10
        failure_count_threshold = 3
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = var.container_port

        interval_seconds = 30
        failure_count_threshold = 3
      }
    }

    custom_scale_rule {
      name             = "cpu-scaling"
      custom_rule_type = "cpu"
      metadata = {
        type  = "Utilization"
        value = "70"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = var.container_port

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.common_tags

  depends_on = [
    azurerm_key_vault_access_policy.app,
    azurerm_role_assignment.queue_contributor,
  ]
}
