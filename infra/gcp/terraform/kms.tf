# -----------------------------------------------------------------------------
# Cloud KMS for Credential Encryption
# -----------------------------------------------------------------------------

resource "google_kms_key_ring" "main" {
  name     = "${local.name_prefix}-keyring-${var.environment}"
  location = var.gcp_region
}

resource "google_kms_crypto_key" "credentials" {
  name     = "${local.name_prefix}-credentials-key-${var.environment}"
  key_ring = google_kms_key_ring.main.id

  rotation_period = "7776000s" # 90 days

  labels = local.common_labels

  lifecycle {
    prevent_destroy = false # Set to true for production
  }
}
