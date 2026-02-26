# -----------------------------------------------------------------------------
# Secrets Manager - Database URL
# -----------------------------------------------------------------------------
# Creates the DATABASE_URL connection string using:
# - Shared RDS endpoint from shared-infrastructure
# - App-specific database name and credentials

# Generate a password for this application's database user
resource "random_password" "db_password" {
  length  = 32
  special = false
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
  # Using the shared RDS with app-specific database
  # IMPORTANT: The database and user must be created by a DBA before first deployment.
  # Run: psql -h <rds-endpoint> -U postgres -f scripts/init-database.sql
  # See scripts/init-database.sql for details.
  secret_string = "postgresql+asyncpg://${var.db_username}:${urlencode(random_password.db_password.result)}@${local.rds_address}:5432/${var.db_name}"
}

# Output for reference
output "database_url_secret_arn" {
  description = "ARN of the database URL secret"
  value       = aws_secretsmanager_secret.database_url.arn
}
