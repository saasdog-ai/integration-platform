# -----------------------------------------------------------------------------
# Secrets Manager - Database URL
# -----------------------------------------------------------------------------
# Creates the DATABASE_URL connection string using:
# - Shared RDS master credentials (self-bootstrapping, no manual DB user needed)
# - App-specific database name

# Read master password from shared infrastructure's Secrets Manager secret
data "aws_secretsmanager_secret_version" "rds_master_password" {
  secret_id = var.shared_rds_master_password_secret_arn
}

# Store the complete DATABASE_URL for the application
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${local.name_prefix}-database-url-${var.environment}"
  description             = "Database connection URL for ${var.app_name}"
  recovery_window_in_days = var.enable_deletion_protection ? 30 : 0

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-database-url-${var.environment}"
  })
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  # Uses RDS master credentials — start.sh auto-creates the database and runs migrations.
  # No manual init-database.sql step required.
  secret_string = "postgresql+asyncpg://postgres:${urlencode(data.aws_secretsmanager_secret_version.rds_master_password.secret_string)}@${local.rds_address}:5432/${var.db_name}"
}

# -----------------------------------------------------------------------------
# Secrets Manager - Admin API Key
# -----------------------------------------------------------------------------
# Protects /admin/* endpoints. The key value must be created manually:
#   aws secretsmanager create-secret --name "saasdog-integration-platform-admin-api-key-dev" \
#     --secret-string "$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)"
# Terraform only references the secret (does not create or manage the value).

resource "aws_secretsmanager_secret" "admin_api_key" {
  name                    = "${local.name_prefix}-admin-api-key-${var.environment}"
  description             = "Admin API key for ${var.app_name} /admin/* endpoints"
  recovery_window_in_days = var.enable_deletion_protection ? 30 : 0

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-admin-api-key-${var.environment}"
  })
}

# Output for reference
output "database_url_secret_arn" {
  description = "ARN of the database URL secret"
  value       = aws_secretsmanager_secret.database_url.arn
}

output "admin_api_key_secret_arn" {
  description = "ARN of the admin API key secret"
  value       = aws_secretsmanager_secret.admin_api_key.arn
}
