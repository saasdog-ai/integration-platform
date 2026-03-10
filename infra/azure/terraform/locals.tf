# -----------------------------------------------------------------------------
# Local Values
# -----------------------------------------------------------------------------

locals {
  name_prefix = "${var.company_prefix}-${var.app_name}"

  # Shortened prefix for resources with name length limits
  short_prefix = "${var.company_prefix}-intplat"

  common_tags = {
    Project     = var.app_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Company     = var.company_prefix
  }
}
