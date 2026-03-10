# -----------------------------------------------------------------------------
# Service Account for Cloud Run
# -----------------------------------------------------------------------------

resource "google_service_account" "cloud_run" {
  account_id   = "${var.company_prefix}-${var.environment}-run"
  display_name = "${var.app_name} Cloud Run Service Account (${var.environment})"
}

# Pub/Sub Publisher
resource "google_project_iam_member" "pubsub_publisher" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Pub/Sub Subscriber
resource "google_project_iam_member" "pubsub_subscriber" {
  project = var.gcp_project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud KMS Encrypter/Decrypter
resource "google_project_iam_member" "kms_crypto" {
  project = var.gcp_project_id
  role    = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Secret Manager Accessor
resource "google_project_iam_member" "secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud SQL Client
resource "google_project_iam_member" "cloudsql_client" {
  project = var.gcp_project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# -----------------------------------------------------------------------------
# Secret Manager - Database URL
# -----------------------------------------------------------------------------

data "google_secret_manager_secret_version" "cloud_sql_master_password" {
  secret = var.shared_cloud_sql_master_password_secret_id
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.name_prefix}-database-url-${var.environment}"

  replication {
    auto {}
  }

  labels = local.common_labels
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+asyncpg://postgres:${urlencode(data.google_secret_manager_secret_version.cloud_sql_master_password.secret_data)}@${var.shared_cloud_sql_private_ip}:5432/${var.db_name}"
}

# -----------------------------------------------------------------------------
# Secret Manager - Admin API Key
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "admin_api_key" {
  secret_id = "${local.name_prefix}-admin-api-key-${var.environment}"

  replication {
    auto {}
  }

  labels = local.common_labels
}

# -----------------------------------------------------------------------------
# Cloud Run Service
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "app" {
  name     = "${local.name_prefix}-${var.environment}"
  location = var.gcp_region

  template {
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    vpc_access {
      connector = var.shared_vpc_connector_id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.app.repository_id}/${var.app_name}:${var.image_tag}"

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
      }

      # Environment variables matching config.py
      env {
        name  = "APP_ENV"
        value = var.environment == "prod" ? "production" : var.environment == "dev" ? "development" : var.environment
      }
      env {
        name  = "API_PORT"
        value = tostring(var.container_port)
      }
      env {
        name  = "CLOUD_PROVIDER"
        value = "gcp"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.gcp_project_id
      }
      env {
        name  = "GCP_KMS_KEYRING"
        value = google_kms_key_ring.main.name
      }
      env {
        name  = "GCP_KMS_KEY"
        value = google_kms_crypto_key.credentials.name
      }
      env {
        name  = "QUEUE_URL"
        value = google_pubsub_topic.sync_jobs.id
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
      env {
        name  = "AUTH_ENABLED"
        value = var.environment == "prod" ? "true" : "false"
      }
      env {
        name  = "DATABASE_NAME"
        value = var.db_name
      }

      # Secrets
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "ADMIN_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = var.container_port
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = var.container_port
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  labels = local.common_labels

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_project_iam_member.secret_accessor,
  ]
}

# Allow unauthenticated access (public API)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.gcp_project_id
  location = var.gcp_region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
