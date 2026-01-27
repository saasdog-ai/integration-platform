# SQS Queue for sync jobs
resource "aws_sqs_queue" "sync_jobs" {
  name                       = "${var.app_name}-${var.environment}-sync-jobs"
  delay_seconds              = 0
  max_message_size           = 262144 # 256 KB
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 20 # Long polling
  visibility_timeout_seconds = 300 # 5 minutes

  # Enable server-side encryption
  sqs_managed_sse_enabled = true

  # Redrive policy for dead letter queue
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.sync_jobs_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "${var.app_name}-${var.environment}-sync-jobs"
  }
}

# Dead Letter Queue
resource "aws_sqs_queue" "sync_jobs_dlq" {
  name                      = "${var.app_name}-${var.environment}-sync-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${var.app_name}-${var.environment}-sync-jobs-dlq"
  }
}

# SQS Queue Policy
resource "aws_sqs_queue_policy" "sync_jobs" {
  queue_url = aws_sqs_queue.sync_jobs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECSTaskAccess"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task_role.arn
        }
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = aws_sqs_queue.sync_jobs.arn
      }
    ]
  })
}
