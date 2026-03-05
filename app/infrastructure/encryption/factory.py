"""Encryption service factory."""

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.interfaces import EncryptionServiceInterface

logger = get_logger(__name__)

# Singleton instance
_encryption_instance: EncryptionServiceInterface | None = None


def get_encryption_service() -> EncryptionServiceInterface:
    """
    Factory to create appropriate encryption service based on configuration.

    Returns:
        EncryptionServiceInterface implementation based on cloud_provider setting.
    """
    global _encryption_instance

    if _encryption_instance is not None:
        return _encryption_instance

    settings = get_settings()

    if settings.cloud_provider == "aws" and settings.kms_key_id:
        from app.infrastructure.encryption.aws_kms import AWSKMSEncryptionService

        _encryption_instance = AWSKMSEncryptionService()
        logger.info("Using AWS KMS encryption service")

    elif settings.cloud_provider == "azure" and settings.azure_keyvault_url:
        from app.infrastructure.encryption.azure_keyvault import (
            AzureKeyVaultEncryptionService,
        )

        _encryption_instance = AzureKeyVaultEncryptionService()
        logger.info("Using Azure Key Vault encryption service")

    elif settings.cloud_provider == "gcp" and settings.gcp_kms_keyring and settings.gcp_kms_key:
        from app.infrastructure.encryption.gcp_kms import GCPKMSEncryptionService

        _encryption_instance = GCPKMSEncryptionService()
        logger.info("Using GCP Cloud KMS encryption service")

    else:
        # Default to local encryption for development
        if settings.is_production:
            raise RuntimeError(
                "Production requires a cloud encryption backend "
                "(set CLOUD_PROVIDER=aws with KMS_KEY_ID, "
                "CLOUD_PROVIDER=azure with AZURE_KEYVAULT_URL, "
                "or CLOUD_PROVIDER=gcp with GCP_KMS_KEYRING and GCP_KMS_KEY)"
            )

        from app.infrastructure.encryption.local_encryption import (
            LocalEncryptionService,
        )

        _encryption_instance = LocalEncryptionService()
        logger.info("Using local encryption service (development mode)")

    return _encryption_instance


def reset_encryption_service() -> None:
    """Reset the encryption service instance (for testing)."""
    global _encryption_instance
    _encryption_instance = None
