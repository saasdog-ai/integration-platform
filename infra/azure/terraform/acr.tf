# -----------------------------------------------------------------------------
# Azure Container Registry
# -----------------------------------------------------------------------------

resource "azurerm_resource_group" "app" {
  name     = "${local.name_prefix}-rg-${var.environment}"
  location = var.azure_location

  tags = local.common_tags
}

resource "azurerm_container_registry" "app" {
  # ACR names: alphanumeric only, 5-50 chars
  name                = replace("${var.company_prefix}intplatform${var.environment}", "-", "")
  resource_group_name = azurerm_resource_group.app.name
  location            = azurerm_resource_group.app.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = local.common_tags
}
