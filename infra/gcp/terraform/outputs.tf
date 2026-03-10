# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# Cloud Run
output "cloud_run_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.app.uri
}

output "cloud_run_service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.app.name
}

# Artifact Registry
output "artifact_registry_url" {
  description = "Artifact Registry repository URL"
  value       = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.app.repository_id}"
}

# Pub/Sub
output "pubsub_topic_name" {
  description = "Pub/Sub topic name for sync jobs"
  value       = google_pubsub_topic.sync_jobs.name
}

output "pubsub_topic_id" {
  description = "Pub/Sub topic ID"
  value       = google_pubsub_topic.sync_jobs.id
}

output "pubsub_dlq_topic_name" {
  description = "Pub/Sub dead letter topic name"
  value       = google_pubsub_topic.sync_jobs_dlq.name
}

# KMS
output "kms_keyring_name" {
  description = "KMS key ring name"
  value       = google_kms_key_ring.main.name
}

output "kms_key_name" {
  description = "KMS crypto key name"
  value       = google_kms_crypto_key.credentials.name
}

# Secrets
output "database_url_secret_id" {
  description = "Secret Manager secret ID for DATABASE_URL"
  value       = google_secret_manager_secret.database_url.secret_id
}

output "admin_api_key_secret_id" {
  description = "Secret Manager secret ID for admin API key"
  value       = google_secret_manager_secret.admin_api_key.secret_id
}
