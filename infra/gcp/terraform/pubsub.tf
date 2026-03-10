# -----------------------------------------------------------------------------
# Pub/Sub Topic & Subscriptions for Sync Jobs
# -----------------------------------------------------------------------------

resource "google_pubsub_topic" "sync_jobs" {
  name = "${local.name_prefix}-sync-jobs-${var.environment}"

  labels = local.common_labels

  message_retention_duration = "1209600s" # 14 days
}

resource "google_pubsub_subscription" "sync_jobs" {
  name  = "${local.name_prefix}-sync-jobs-sub-${var.environment}"
  topic = google_pubsub_topic.sync_jobs.id

  ack_deadline_seconds       = 300 # 5 minutes
  message_retention_duration = "1209600s" # 14 days

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.sync_jobs_dlq.id
    max_delivery_attempts = 3
  }

  labels = local.common_labels
}

# Dead Letter Topic
resource "google_pubsub_topic" "sync_jobs_dlq" {
  name = "${local.name_prefix}-sync-jobs-dlq-${var.environment}"

  labels = local.common_labels

  message_retention_duration = "1209600s" # 14 days
}

resource "google_pubsub_subscription" "sync_jobs_dlq" {
  name  = "${local.name_prefix}-sync-jobs-dlq-sub-${var.environment}"
  topic = google_pubsub_topic.sync_jobs_dlq.id

  ack_deadline_seconds       = 300
  message_retention_duration = "1209600s" # 14 days

  labels = local.common_labels
}
