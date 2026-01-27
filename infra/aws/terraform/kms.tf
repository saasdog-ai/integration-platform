# =============================================================================
# KMS - Only created in standalone mode (use_shared_infra = false)
# =============================================================================

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "credentials" {
  count = var.use_shared_infra ? 0 : 1

  description             = "KMS key for encrypting integration credentials"
  deletion_window_in_days = var.enable_deletion_protection ? 30 : 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow ECS Task Role"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task_role.arn
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = "${var.app_name}-${var.environment}-credentials-key"
  }
}

resource "aws_kms_alias" "credentials" {
  count = var.use_shared_infra ? 0 : 1

  name          = "alias/${var.app_name}-${var.environment}-credentials"
  target_key_id = aws_kms_key.credentials[0].key_id
}
