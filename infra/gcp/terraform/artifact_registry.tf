# -----------------------------------------------------------------------------
# Artifact Registry (Docker Repository)
# -----------------------------------------------------------------------------

resource "google_artifact_registry_repository" "app" {
  location      = var.gcp_region
  repository_id = "${local.name_prefix}-${var.environment}"
  format        = "DOCKER"
  description   = "Docker repository for ${var.app_name}"

  labels = local.common_labels

  cleanup_policies {
    id     = "keep-last-10"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
    }
  }
}
