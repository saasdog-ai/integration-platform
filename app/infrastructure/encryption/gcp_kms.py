"""Google Cloud KMS encryption service."""

from app.core.config import get_settings
from app.core.exceptions import EncryptionError
from app.core.logging import get_logger
from app.domain.interfaces import EncryptionServiceInterface

logger = get_logger(__name__)


class GCPKMSEncryptionService(EncryptionServiceInterface):
    """Google Cloud KMS encryption service for production use."""

    def __init__(
        self,
        project_id: str | None = None,
        keyring: str | None = None,
        key_name: str | None = None,
        location: str = "global",
    ) -> None:
        """
        Initialize GCP Cloud KMS encryption service.

        Args:
            project_id: GCP project ID. If not provided, uses settings.
            keyring: KMS keyring name. If not provided, uses settings.
            key_name: KMS key name. If not provided, uses settings.
            location: KMS location (default: "global").
        """
        settings = get_settings()
        self._project_id = project_id or settings.gcp_project_id
        self._keyring = keyring or settings.gcp_kms_keyring
        self._key_name = key_name or settings.gcp_kms_key
        self._location = location
        self._client = None

        if not self._project_id:
            raise EncryptionError("GCP project ID not configured")
        if not self._keyring:
            raise EncryptionError("GCP KMS keyring not configured")
        if not self._key_name:
            raise EncryptionError("GCP KMS key name not configured")

    def _get_client(self):
        """Lazily create KMS client."""
        if self._client is None:
            try:
                from google.cloud import kms
            except ImportError:
                raise EncryptionError(
                    "google-cloud-kms is required. Install with: pip install google-cloud-kms"
                ) from None

            self._client = kms.KeyManagementServiceClient()

        return self._client

    @property
    def _key_path(self) -> str:
        """Full resource path to the crypto key."""
        from google.cloud import kms

        return kms.KeyManagementServiceClient.crypto_key_path(
            self._project_id, self._location, self._keyring, self._key_name
        )

    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """
        Encrypt data using GCP Cloud KMS.

        Returns:
            Tuple of (ciphertext, key_name_path)
        """
        try:
            import asyncio

            client = self._get_client()

            response = await asyncio.to_thread(
                client.encrypt,
                request={"name": self._key_path, "plaintext": plaintext},
            )

            ciphertext = response.ciphertext
            key_id = response.name  # Full resource path of the key version

            logger.debug(
                "Data encrypted with GCP KMS",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return ciphertext, key_id

        except Exception as e:
            logger.error("GCP KMS encryption failed", extra={"error": str(e)})
            raise EncryptionError(f"GCP KMS encryption failed: {e}") from e

    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt data using GCP Cloud KMS.

        Args:
            ciphertext: The encrypted data
            key_id: The key resource path used for encryption

        Returns:
            The decrypted plaintext
        """
        try:
            import asyncio

            client = self._get_client()

            # Use the key_path (not key_id from encrypt response, which includes version)
            # KMS can figure out the correct key version from the ciphertext
            response = await asyncio.to_thread(
                client.decrypt,
                request={"name": self._key_path, "ciphertext": ciphertext},
            )

            plaintext = response.plaintext

            logger.debug(
                "Data decrypted with GCP KMS",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return plaintext

        except Exception as e:
            logger.error("GCP KMS decryption failed", extra={"error": str(e)})
            raise EncryptionError(f"GCP KMS decryption failed: {e}") from e
