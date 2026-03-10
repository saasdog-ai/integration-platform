# -----------------------------------------------------------------------------
# Local Values
# -----------------------------------------------------------------------------

locals {
  name_prefix = "${var.company_prefix}-${var.app_name}"

  common_labels = {
    project     = var.app_name
    environment = var.environment
    managed-by  = "terraform"
    company     = var.company_prefix
  }
}
