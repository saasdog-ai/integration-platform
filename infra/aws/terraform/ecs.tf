# -----------------------------------------------------------------------------
# ECR Repository
# -----------------------------------------------------------------------------

resource "aws_ecr_repository" "app" {
  name                 = "${local.name_prefix}-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${var.environment}"
  })
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.name_prefix}-${var.environment}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${var.environment}"
  })
}

# -----------------------------------------------------------------------------
# ECS Task Definition
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name_prefix}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_task_cpu
  memory                   = var.ecs_task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "${var.app_name}-api"
      image = "${aws_ecr_repository.app.repository_url}:latest"

      portMappings = [
        {
          containerPort = var.container_port
          hostPort      = var.container_port
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "APP_ENV", value = var.environment },
        { name = "API_PORT", value = tostring(var.container_port) },
        { name = "CLOUD_PROVIDER", value = "aws" },
        { name = "AWS_REGION", value = var.aws_region },
        { name = "QUEUE_URL", value = aws_sqs_queue.sync_jobs.url },
        { name = "KMS_KEY_ID", value = aws_kms_key.credentials.key_id },
        { name = "LOG_LEVEL", value = "INFO" },
        { name = "AUTH_ENABLED", value = var.environment == "prod" ? "true" : "false" },
        { name = "DATABASE_NAME", value = var.db_name }
      ]

      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "XERO_CLIENT_ID"
          valueFrom = aws_secretsmanager_secret.xero_client_id.arn
        },
        {
          name      = "XERO_CLIENT_SECRET"
          valueFrom = aws_secretsmanager_secret.xero_client_secret.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${var.environment}"
  })
}

# -----------------------------------------------------------------------------
# ECS Service
# -----------------------------------------------------------------------------

resource "aws_ecs_service" "app" {
  name            = "${local.name_prefix}-${var.environment}"
  cluster         = local.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "${var.app_name}-api"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.http]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${var.environment}"
  })
}

# -----------------------------------------------------------------------------
# Auto Scaling
# -----------------------------------------------------------------------------

resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = 4
  min_capacity       = var.ecs_desired_count
  resource_id        = "service/${local.ecs_cluster_name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "ecs_cpu" {
  name               = "${local.name_prefix}-cpu-scaling-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
