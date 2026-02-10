# -----------------------------------------------------------------------------
# KMS Key for Credential Encryption
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "credentials" {
  description             = "KMS key for encrypting ${var.app_name} integration credentials"
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

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-credentials-key-${var.environment}"
  })
}

resource "aws_kms_alias" "credentials" {
  name          = "alias/${local.name_prefix}-credentials-${var.environment}"
  target_key_id = aws_kms_key.credentials.key_id
}
