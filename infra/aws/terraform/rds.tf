# =============================================================================
# RDS - Only created in standalone mode (use_shared_infra = false)
# =============================================================================

resource "random_password" "db_password" {
  count = var.use_shared_infra ? 0 : 1

  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db_password" {
  count = var.use_shared_infra ? 0 : 1

  name                    = "${var.app_name}-${var.environment}-db-password"
  recovery_window_in_days = var.enable_deletion_protection ? 30 : 0

  tags = {
    Name = "${var.app_name}-${var.environment}-db-password"
  }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  count = var.use_shared_infra ? 0 : 1

  secret_id = aws_secretsmanager_secret.db_password[0].id
  # Store as DATABASE_URL connection string for direct use by application
  secret_string = "postgresql+asyncpg://${var.db_username}:${urlencode(random_password.db_password[0].result)}@${aws_db_instance.main[0].address}:5432/${var.db_name}"
}

resource "aws_db_subnet_group" "main" {
  count = var.use_shared_infra ? 0 : 1

  name       = "${local.infra_name}-${var.environment}-db-subnet"
  subnet_ids = local.private_subnet_ids

  tags = {
    Name = "${local.infra_name}-${var.environment}-db-subnet"
  }
}

resource "aws_db_parameter_group" "main" {
  count = var.use_shared_infra ? 0 : 1

  name   = "${local.infra_name}-${var.environment}-pg15"
  family = "postgres15"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  tags = {
    Name = "${local.infra_name}-${var.environment}-pg15"
  }
}

resource "aws_db_instance" "main" {
  count = var.use_shared_infra ? 0 : 1

  identifier = "${local.infra_name}-${var.environment}"

  engine         = "postgres"
  engine_version = "15"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 2
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password[0].result

  db_subnet_group_name   = aws_db_subnet_group.main[0].name
  vpc_security_group_ids = [local.rds_security_group_id]
  parameter_group_name   = aws_db_parameter_group.main[0].name

  publicly_accessible = false
  multi_az            = var.environment == "prod"

  backup_retention_period = var.environment == "prod" ? 7 : 1
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection = var.enable_deletion_protection
  skip_final_snapshot = !var.enable_deletion_protection

  performance_insights_enabled = var.environment == "prod"

  tags = {
    Name = "${local.infra_name}-${var.environment}"
  }
}
