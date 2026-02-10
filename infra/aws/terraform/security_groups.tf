# -----------------------------------------------------------------------------
# Security Groups (Project-specific)
# -----------------------------------------------------------------------------

# ALB Security Group
resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg-${var.environment}"
  description = "Security group for ${var.app_name} ALB"
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

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb-sg-${var.environment}"
  })
}

# ECS Tasks Security Group
resource "aws_security_group" "ecs_tasks" {
  name        = "${local.name_prefix}-ecs-sg-${var.environment}"
  description = "Security group for ${var.app_name} ECS tasks"
  vpc_id      = local.vpc_id

  ingress {
    description     = "From ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-sg-${var.environment}"
  })
}

# Allow ECS tasks to connect to shared RDS
resource "aws_security_group_rule" "ecs_to_rds" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.ecs_tasks.id
  security_group_id        = local.rds_security_group_id
  description              = "Allow ${var.app_name} ECS tasks to connect to RDS"
}
