# =============================================================================
# Security Groups - Only created in standalone mode (use_shared_infra = false)
# =============================================================================

# ALB Security Group
resource "aws_security_group" "alb" {
  count = var.use_shared_infra ? 0 : 1

  name        = "${local.infra_name}-${var.environment}-alb-sg"
  description = "Security group for ALB"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.infra_name}-${var.environment}-alb-sg"
  }
}

# ECS Tasks Security Group
resource "aws_security_group" "ecs_tasks" {
  count = var.use_shared_infra ? 0 : 1

  name        = "${local.infra_name}-${var.environment}-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = local.vpc_id

  ingress {
    description     = "From ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.infra_name}-${var.environment}-ecs-tasks-sg"
  }
}

# RDS Security Group
resource "aws_security_group" "rds" {
  count = var.use_shared_infra ? 0 : 1

  name        = "${local.infra_name}-${var.environment}-rds-sg"
  description = "Security group for RDS"
  vpc_id      = local.vpc_id

  ingress {
    description     = "PostgreSQL from ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.infra_name}-${var.environment}-rds-sg"
  }
}
